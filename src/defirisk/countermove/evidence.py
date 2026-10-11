"""Durable, append-only evidence store for ARM PROTECTION (SQLite, WAL, one file).

Every keeper observation, trigger, decision, rejected strategy, execution attempt, receipt, verification, finality check,
heartbeat and error becomes one row. Properties the tests pin down:
  * append-only      UPDATE / DELETE are refused by triggers (tampering needs a different tool and breaks the chain)
  * hash chain       each row stores sha256(prev_hash + canonical row): verify() detects any edited / removed row
  * idempotent       a UNIQUE idempotency key: replaying a journal or re-delivering an event is a no-op, and a given
                     tx hash can produce only one `receipt` row (no duplicate CONFIRMED)
  * labelled         every row carries its environment: local-test | fork | mainnet-readonly. Transaction kinds are
                     refused for mainnet-readonly (FAULTLINE never transacts on mainnet), so fork evidence can never be
                     presented as mainnet evidence.
  * concurrent-safe  BEGIN IMMEDIATE serialises writers across threads and processes (busy timeout 10 s)
The keeper's JSONL journal stays the primary crash-safe record; Journal(sink=store.sink(...)) mirrors it here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = "faultline.evidence/1"
ENVIRONMENTS = ("local-test", "fork", "mainnet-readonly")
KINDS = ("policy_draft", "transition", "observation", "trigger", "decision", "rejected_strategy", "validation",
         "execution_attempt", "receipt", "verification", "finality", "failure", "heartbeat", "error", "lifecycle")
TX_KINDS = {"execution_attempt", "receipt", "verification", "finality"}
_GENESIS = "0" * 64
_DDL = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  idem TEXT NOT NULL UNIQUE,
  ts REAL NOT NULL,
  environment TEXT NOT NULL CHECK (environment IN ('local-test','fork','mainnet-readonly')),
  chain_id INTEGER,
  position TEXT,
  vault TEXT,
  kind TEXT NOT NULL,
  state TEXT,
  tx_hash TEXT,
  block INTEGER,
  payload TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_position ON events(position, seq);
CREATE INDEX IF NOT EXISTS events_tx ON events(tx_hash);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""
_COLS = ("seq", "idem", "ts", "environment", "chain_id", "position", "vault", "kind", "state", "tx_hash", "block", "payload",
         "prev_hash", "hash")


def _canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _digest(prev: str, row: dict) -> str:
    body = {k: row[k] for k in ("idem", "ts", "environment", "chain_id", "position", "vault", "kind", "state", "tx_hash",
                                "block", "payload")}
    return hashlib.sha256((prev + _canon(body)).encode()).hexdigest()


def classify(rec: dict) -> str:
    """Evidence kind of one keeper journal record."""
    st, ev = rec.get("state"), rec.get("event")
    if st == "EXECUTING":
        return "execution_attempt" if rec.get("tx_hash") and rec.get("nonce") is not None else "observation"
    if st == "WATCHING":
        return "error" if ev in ("rpc_error", "internal_error") else "observation"
    if st == "FAILED" and ev == "reorged":
        return "finality"
    return {"DETECTED": "trigger", "PLANNING": "decision", "VALIDATING": "validation", "NO_ACTION": "decision",
            "FAILED": "failure", "CONFIRMED": "receipt"}.get(st, "transition")


class EvidenceStore:
    def __init__(self, path: str | Path, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self._local = threading.local()
        if readonly:
            if not self.path.exists():
                raise FileNotFoundError(str(self.path))
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._conn()
        c.executescript(_DDL)
        c.execute("INSERT OR IGNORE INTO meta(k, v) VALUES ('schema', ?)", (SCHEMA,))
        c.commit()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            if self.readonly:
                c = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, timeout=10.0, isolation_level=None)
            else:
                c = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA synchronous=FULL")
            c.execute("PRAGMA busy_timeout=10000")
            self._local.c = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "c", None)
        if c is not None:
            c.close()
            self._local.c = None

    # ---- write ------------------------------------------------------------------------------------------------------
    def append(self, kind: str, *, environment: str, payload: dict, idem: str | None = None, position: str | None = None,
               vault: str | None = None, state: str | None = None, tx_hash: str | None = None, block: int | None = None,
               chain_id: int | None = None, ts: float | None = None) -> dict:
        """Returns the stored row (the EXISTING row when the idempotency key was already recorded: 'duplicate': True)."""
        if environment not in ENVIRONMENTS:
            raise ValueError(f"environment must be one of {ENVIRONMENTS}")
        if kind not in KINDS:
            raise ValueError(f"unknown evidence kind {kind!r}")
        if environment == "mainnet-readonly" and kind in TX_KINDS:
            raise ValueError("FAULTLINE never transacts on mainnet: transaction evidence cannot be labelled mainnet")
        payload_s = _canon(payload)
        row = {"idem": idem or hashlib.sha256((kind + payload_s).encode()).hexdigest(), "ts": float(ts or time.time()),
               "environment": environment, "chain_id": chain_id, "position": position, "vault": vault and vault.lower(),
               "kind": kind, "state": state, "tx_hash": tx_hash and tx_hash.lower(), "block": block, "payload": payload_s}
        c = self._conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            hit = c.execute(f"SELECT {','.join(_COLS)} FROM events WHERE idem = ?", (row["idem"],)).fetchone()
            if hit:
                c.execute("COMMIT")
                return {**self._row(hit), "duplicate": True}
            last = c.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            row["prev_hash"] = last[0] if last else _GENESIS
            row["hash"] = _digest(row["prev_hash"], row)
            cur = c.execute(f"INSERT INTO events({','.join(_COLS[1:])}) VALUES ({','.join('?' * (len(_COLS) - 1))})",
                            [row[k] for k in _COLS[1:]])
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        return {**row, "seq": cur.lastrowid, "payload": payload, "duplicate": False}

    def record_journal(self, rec: dict, *, environment: str, chain_id: int | None = None) -> list[dict]:
        """Map one keeper journal record to evidence rows (one per record, plus one per rejected strategy)."""
        st = rec.get("state")
        kind = classify(rec)
        base = {"environment": environment, "chain_id": chain_id, "position": rec.get("position"), "vault": rec.get("vault"),
                "state": st, "tx_hash": rec.get("tx_hash"), "block": rec.get("block"), "ts": rec.get("ts")}
        idem = "journal:" + hashlib.sha256(_canon(rec).encode()).hexdigest()
        if kind == "receipt" and rec.get("tx_hash"):
            idem = f"receipt:{rec['tx_hash'].lower()}"  # one CONFIRMED per transaction, whatever replays happen
        if kind == "execution_attempt":
            idem = f"attempt:{rec['tx_hash'].lower()}"  # one signed attempt per transaction hash
        out = [self.append(kind, payload=rec, idem=idem, **base)]
        if kind == "receipt" and rec.get("verification"):
            out.append(self.append("verification", payload=rec["verification"], idem=f"verification:{rec['tx_hash'].lower()}",
                                   **base))
        for c in ((rec.get("plan") or {}).get("candidates") or []) if st == "PLANNING" else []:
            if c.get("rejected_at"):
                out.append(self.append("rejected_strategy", payload=c, idem=f"{idem}:rejected:{c.get('strategy')}", **base))
        return out

    def sink(self, environment: str, chain_id: int | None = None):
        """Callable for Journal(sink=...): mirrors every journal record into the store."""
        return lambda rec: self.record_journal(rec, environment=environment, chain_id=chain_id)

    # ---- read -------------------------------------------------------------------------------------------------------
    def _row(self, t) -> dict:
        r = dict(zip(_COLS, t))
        r["payload"] = json.loads(r["payload"])
        return r

    def query(self, *, position: str | None = None, kinds: list[str] | None = None, tx_hash: str | None = None,
              since_seq: int = 0, limit: int = 200) -> list[dict]:
        sql, args = f"SELECT {','.join(_COLS)} FROM events WHERE seq > ?", [since_seq]
        if position:
            sql += " AND position = ?"
            args.append(position)
        if tx_hash:
            sql += " AND tx_hash = ?"
            args.append(tx_hash.lower())
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += kinds
        sql += " ORDER BY seq LIMIT ?"
        args.append(max(1, min(int(limit), 1000)))
        return [self._row(t) for t in self._conn().execute(sql, args).fetchall()]

    def latest(self, kind: str, position: str | None = None) -> dict | None:
        sql, args = f"SELECT {','.join(_COLS)} FROM events WHERE kind = ?", [kind]
        if position:
            sql += " AND position = ?"
            args.append(position)
        t = self._conn().execute(sql + " ORDER BY seq DESC LIMIT 1", args).fetchone()
        return self._row(t) if t else None

    def count(self) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def verify(self) -> dict:
        """Recompute the hash chain. ok=False names the first row that does not match (edited, inserted or removed)."""
        prev, n = _GENESIS, 0
        for t in self._conn().execute(f"SELECT {','.join(_COLS)} FROM events ORDER BY seq"):
            r = dict(zip(_COLS, t))
            if r["prev_hash"] != prev or _digest(prev, r) != r["hash"]:
                return {"ok": False, "rows": n, "broken_at_seq": r["seq"]}
            prev, n = r["hash"], n + 1
        return {"ok": True, "rows": n, "head": prev}


def import_journal(journal_path: str | Path, store: EvidenceStore, *, environment: str, chain_id: int | None = None) -> dict:
    """Read-only import of an existing journal.jsonl (e.g. the recorded fork run). The source file is never modified."""
    lines = Path(journal_path).read_text(encoding="utf-8").splitlines()
    new = dup = 0
    for line in lines:
        if not line.strip():
            continue
        for r in store.record_journal(json.loads(line), environment=environment, chain_id=chain_id):
            dup += r["duplicate"]
            new += not r["duplicate"]
    return {"records": sum(1 for x in lines if x.strip()), "rows_added": new, "rows_duplicate": dup}
