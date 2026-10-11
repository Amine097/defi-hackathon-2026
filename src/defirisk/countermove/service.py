"""Persistent keeper service: the long-running process behind MONITORING.

    python -m defirisk.countermove.service --config keeper.json [--state-dir DIR] [--evidence-db FILE]
                                           [--environment local-test|fork] [--confirmations 2] [--interval 3]

Adds to the per-cycle Watcher (which already journals pending tx BEFORE broadcast and resolves them from the chain on
restart):
  * single instance   an OS file lock (msvcrt / fcntl) held for the process lifetime: a second keeper on the same state
                      directory refuses to start; the OS frees the lock if the process dies (no stale-lease guessing)
  * heartbeat         health.json rewritten atomically every tick (status, chain head, per-position state, finality);
                      readers treat a heartbeat older than `stale_after_s` as STALE, never as monitoring
  * chain head        head number regression or same-height hash change -> reorg suspected (evidence row); optional
                      max head age (a frozen RPC is not a live chain) -> no decision this tick
  * backoff           consecutive RPC failures -> exponential backoff, status degraded / unavailable, no decision
  * finality          a CONFIRMED action (receipt + verifier, 1 block) becomes FINAL only after `confirmations` blocks
                      with its block hash still canonical; if the receipt disappears (reorg) the journal records FAILED
                      (event reorged) and the watcher re-plans from fresh state with a new action id
  * evidence          optional EvidenceStore mirror of every journal record + heartbeats + finality rows
  * shutdown          SIGINT / SIGTERM finish the current tick, write status 'stopped', release the lock
The service never signs for a non-local chain (Watcher / GuardedExecutor / signer_from_env enforce it).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import uuid
from pathlib import Path

from . import verifier
from .chain import RPC, RPCError
from .evidence import EvidenceStore
from .journal import Journal
from .watcher import Watcher, load_config, signer_from_env

HEALTH_SCHEMA = "faultline.keeper.health/1"
LOCAL_IDS = {31337, 1337}


def _slim(e: dict | None) -> dict | None:
    if not e:
        return None
    return {k: e.get(k) for k in ("ts", "state", "event", "reason", "tx_hash", "block", "decision") if e.get(k) is not None}


class LeaseHeld(RuntimeError):
    """Another keeper process holds the lock on this state directory."""


class Lease:
    """Exclusive OS lock on <dir>/keeper.lock + an info file (<dir>/keeper.lease.json) describing the holder."""

    def __init__(self, directory: str | Path, owner: str | None = None, clock=time.time):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock_path, self.info_path = self.dir / "keeper.lock", self.dir / "keeper.lease.json"
        self.owner, self.clock, self._f = owner or uuid.uuid4().hex[:12], clock, None

    def acquire(self) -> dict:
        f = open(self.lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            held = self.holder()
            raise LeaseHeld(f"another keeper holds {self.lock_path} ({held or 'holder unknown'})") from None
        self._f = f
        info = {"owner": self.owner, "pid": os.getpid(), "acquired_at": self.clock()}
        _atomic_json(self.info_path, info)
        return info

    def holder(self) -> dict | None:
        try:
            return json.loads(self.info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @property
    def held(self) -> bool:
        return self._f is not None

    def release(self) -> None:
        if self._f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        finally:
            self._f.close()
            self._f = None
            try:
                if (self.holder() or {}).get("owner") == self.owner:
                    self.info_path.unlink()
            except OSError:
                pass


def _atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(obj, indent=1, allow_nan=False, default=str))
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(5):  # Windows: a reader may hold the file for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    os.replace(tmp, path)


def read_health(path: str | Path, now: float | None = None, stale_after_s: float | None = None) -> dict | None:
    """The keeper's last heartbeat, with status downgraded to 'stale' when it is older than stale_after_s (default: the
    service's own value). None if there is no readable health file."""
    try:
        h = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    now = time.time() if now is None else now
    limit = stale_after_s if stale_after_s is not None else float(h.get("stale_after_s") or 30)
    age = now - float(h.get("heartbeat_at") or 0)
    h["heartbeat_age_s"] = age
    if h.get("status") not in ("stopped",) and age > limit:
        h["reported_status"], h["status"] = h.get("status"), "stale"
    return h


class Finality:
    """CONFIRMED tx -> FINAL after N blocks on the canonical chain; REORGED if its receipt / block disappears."""

    def __init__(self, path: Path, depth: int):
        self.path, self.depth = path, max(1, int(depth))
        try:
            self.items = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = {}

    def save(self) -> None:
        _atomic_json(self.path, self.items)

    def track(self, rec: dict, receipt: dict | None) -> None:
        tx = rec["tx_hash"].lower()
        if tx in self.items:
            return
        self.items[tx] = {"tx_hash": tx, "position": rec.get("position"), "vault": rec.get("vault"),
                          "block": int(receipt["blockNumber"], 16) if receipt else rec.get("block"),
                          "block_hash": receipt.get("blockHash") if receipt else None, "status": "pending",
                          "confirmations": 1, "chosen": rec.get("chosen"), "since": time.time()}

    def latest_for(self, position: str) -> dict | None:
        rows = [v for v in self.items.values() if v.get("position") == position]
        return {k: v for k, v in max(rows, key=lambda r: r["since"]).items() if k != "chosen"} if rows else None


class KeeperService:
    def __init__(self, cfg: dict, rpc: RPC, journal: Journal, signer=None, *, state_dir: str | Path,
                 store: EvidenceStore | None = None, environment: str = "local-test", confirmations: int = 2,
                 interval_s: float = 3.0, stale_after_s: float | None = None, max_head_age_s: float | None = None,
                 max_backoff_s: float = 60.0, heartbeat_evidence_s: float = 60.0, clock=time.time, sleep=time.sleep,
                 watcher: Watcher | None = None):
        if environment not in ("local-test", "fork"):
            raise ValueError("the keeper service runs only on local test chains or local forks (environment local-test|fork)")
        self.cfg, self.rpc, self.journal, self.signer = cfg, rpc, journal, signer
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.store, self.environment, self.interval_s = store, environment, interval_s
        self.stale_after_s = stale_after_s if stale_after_s is not None else max(3 * interval_s, 15.0)
        self.max_head_age_s, self.max_backoff_s, self.heartbeat_evidence_s = max_head_age_s, max_backoff_s, heartbeat_evidence_s
        self.clock, self.sleep = clock, sleep
        self.instance = uuid.uuid4().hex[:12]
        self.lease = Lease(self.state_dir, self.instance, clock)
        self.health_path = self.state_dir / "health.json"
        self.finality = Finality(self.state_dir / "finality.json", confirmations)
        self.watcher = watcher or Watcher(cfg, rpc, journal, signer)
        self.chain_id: int | None = None
        self.head: dict | None = None
        self.errors = 0
        self.reorg_suspected = False
        self.started_at = clock()
        self._last_hb_evidence = 0.0
        self._stop = threading.Event()

    # ---- lifecycle --------------------------------------------------------------------------------------------------
    def start(self) -> None:
        self.lease.acquire()
        try:
            self.chain_id = self.rpc.chain_id()
        except RPCError:
            self.chain_id = None
        if self.chain_id is not None and self.chain_id not in LOCAL_IDS:
            self.lease.release()
            raise ValueError(f"chain id {self.chain_id} is not a local test chain: the keeper service refuses to run")
        if self.store is not None and self.journal.sink is None:
            self.journal.sink = self.store.sink(self.environment, self.chain_id)
        self._write_health("starting", note="lock acquired")

    def stop(self, note: str = "graceful shutdown") -> None:
        self._stop.set()
        if self.lease.held:
            self._write_health("stopped", note=note)
            self.lease.release()

    def request_stop(self) -> None:
        self._stop.set()

    # ---- one tick ---------------------------------------------------------------------------------------------------
    def tick(self) -> dict:
        if not self.lease.held:
            raise LeaseHeld("tick() without the lock: call start() first")
        try:
            head = self.rpc.block("latest")
        except RPCError as e:
            return self._rpc_failed(e)
        if self.chain_id is None:  # the RPC was down at start(): the local-chain gate must still pass before any decision
            try:
                self.chain_id = self.rpc.chain_id()
            except RPCError as e:
                return self._rpc_failed(e)
            if self.chain_id not in LOCAL_IDS:
                cid, self.chain_id = self.chain_id, None
                self.stop(note=f"chain id {cid} is not a local test chain: refused, no decision taken")
                raise ValueError(f"chain id {cid} is not a local test chain: the keeper service refuses to run")
            if self.store is not None and self.journal.sink is None:
                self.journal.sink = self.store.sink(self.environment, self.chain_id)
        note = self._check_head(head)
        if note == "stale_head":
            self._write_health("degraded", note=f"chain head {head['number']} is older than {self.max_head_age_s}s: no "
                                                 "decision on a frozen chain view")
            return {"status": "degraded", "skipped": "stale_head", "results": []}
        # finality first: a reorged action must be journaled FAILED before the watcher decides anything new
        fin = self._check_finality()
        results = self.watcher.tick()
        rpc_fail = [r for r in results if r.get("event") == "rpc_error"]
        self.errors = self.errors + 1 if rpc_fail and len(rpc_fail) == len(results) else 0
        for r in results:
            if r.get("state") == "CONFIRMED" and r.get("tx_hash"):
                try:
                    self.finality.track(r, self.rpc.receipt(r["tx_hash"]))
                except RPCError:
                    self.finality.track(r, None)
        self.finality.save()
        status = "ok" if not self.errors else ("degraded" if self.errors < 3 else "unavailable")
        self._write_health(status, note=note)
        self._heartbeat_evidence(status)
        return {"status": status, "results": results, "finality": fin, "head": self.head}

    def _rpc_failed(self, e: Exception) -> dict:
        self.errors += 1
        status = "degraded" if self.errors < 3 else "unavailable"
        self._write_health(status, note=f"RPC failure #{self.errors}: {str(e)[:200]}; no decision this tick")
        self._evidence("error", {"event": "rpc_unavailable", "error": str(e)[:300], "consecutive": self.errors},
                       idem=f"rpcerr:{self.instance}:{self.errors}:{int(self.clock())}")
        return {"status": status, "skipped": "rpc_unavailable", "results": []}

    def _check_head(self, head: dict) -> str | None:
        prev, self.head = self.head, head
        note = None
        if prev and (head["number"] < prev["number"] or (head["number"] == prev["number"] and head.get("hash") != prev.get("hash"))):
            self.reorg_suspected = True
            note = f"chain head moved from {prev['number']} to {head['number']} (hash changed): reorg or chain reset suspected"
            self._evidence("observation", {"event": "head_regressed", "from": prev, "to": head},
                           idem=f"head:{prev.get('hash')}:{head.get('hash')}")
        if self.max_head_age_s is not None and self.clock() - head["timestamp"] > self.max_head_age_s:
            return "stale_head"
        return note

    def _check_finality(self) -> list[dict]:
        out = []
        for tx, it in self.finality.items.items():
            if it["status"] != "pending":
                continue
            try:
                rc = self.rpc.receipt(tx)
                head = self.head["number"]
                canon = self.rpc.block(int(rc["blockNumber"], 16))["hash"] if rc else None
            except RPCError:
                continue
            if rc is None:
                self.reorg_suspected = True
                it["status"] = "reorged"
                self._journal_fail(it, "the confirmed transaction is no longer in the canonical chain (reorg): it will be "
                                       "re-planned from fresh state with a new action id")
                self._evidence("finality", {**it, "chosen": None}, idem=f"reorged:{tx}", position=it["position"],
                               vault=it.get("vault"), tx_hash=tx, state="REORGED")
                out.append(it)
                continue
            if rc.get("blockHash") != it.get("block_hash") or canon != rc.get("blockHash"):
                self.reorg_suspected = True
                ver = verifier.verify(self.rpc, it["vault"], it.get("chosen") or {}, rc) if it.get("chosen") else {"verified": False}
                it.update(block=int(rc["blockNumber"], 16), block_hash=rc.get("blockHash"), reincluded=True,
                          reverified=bool(ver.get("verified")))
                self._evidence("finality", {**it, "chosen": None, "event": "reincluded"},
                               idem=f"reincluded:{tx}:{rc.get('blockHash')}", position=it["position"], vault=it.get("vault"),
                               tx_hash=tx, state="EXECUTING")
                if not ver.get("verified"):
                    it["status"] = "reorged"
                    self._journal_fail(it, "re-included after a reorg but the re-read state no longer verifies")
                    out.append(it)
                    continue
            it["confirmations"] = head - it["block"] + 1
            if it["confirmations"] >= self.finality.depth and canon == it["block_hash"]:
                it["status"], it["final_at"] = "final", self.clock()
                self._evidence("finality", {**it, "chosen": None}, idem=f"final:{tx}", position=it["position"],
                               vault=it.get("vault"), tx_hash=tx, block=it["block"], state="VERIFIED")
            out.append(it)
        return out

    # ---- health + evidence ------------------------------------------------------------------------------------------
    def _journal_fail(self, it: dict, reason: str) -> None:
        rec = self.journal.append(it["position"], "FAILED", event="reorged", tx_hash=it["tx_hash"], vault=it.get("vault"),
                                  reason=reason)
        self.journal.update(it["position"], state="FAILED", last_event=rec,
                            last_terminal={"state": "FAILED", "at": rec["ts"], "reason": reason, "tx_hash": it["tx_hash"]})

    def _write_health(self, status: str, note: str | None = None) -> None:
        st = self.journal.state()
        positions = [{"id": p["id"], "vault": p["rescue_vault"], "label": p.get("label"),
                      "state": (st.get(p["id"]) or {}).get("state"),
                      "last_event_at": ((st.get(p["id"]) or {}).get("last_event") or {}).get("ts"),
                      "last_event": _slim((st.get(p["id"]) or {}).get("last_event")),
                      "last_terminal": (st.get(p["id"]) or {}).get("last_terminal"),
                      "pending_tx": ((st.get(p["id"]) or {}).get("pending") or {}).get("tx_hash"),
                      "finality": self.finality.latest_for(p["id"])} for p in self.cfg["positions"]]
        now = self.clock()
        h = {"schema": HEALTH_SCHEMA, "status": status, "note": note, "instance": self.instance, "pid": os.getpid(),
             "started_at": self.started_at, "heartbeat_at": now, "stale_after_s": self.stale_after_s,
             "environment": self.environment, "chain_id": self.chain_id,
             "keeper": getattr(self.signer, "address", None), "watch_only": self.signer is None,
             "head": None if not self.head else {**self.head, "age_s": now - self.head["timestamp"]},
             "consecutive_rpc_errors": self.errors, "next_delay_s": self.next_delay(),
             "reorg_suspected": self.reorg_suspected, "confirmations_required": self.finality.depth,
             "journal": str(self.journal.path), "evidence_db": str(self.store.path) if self.store else None,
             "positions": positions}
        _atomic_json(self.health_path, h)

    def _evidence(self, kind: str, payload: dict, *, idem: str, **kw) -> None:
        if self.store is None:
            return
        try:
            self.store.append(kind, environment=self.environment, chain_id=self.chain_id, payload=payload, idem=idem, **kw)
        except Exception as e:  # noqa: BLE001 - evidence mirror failure is reported, never fatal to monitoring
            print(f"[service] evidence write failed: {type(e).__name__}: {e}", file=sys.stderr)

    def _heartbeat_evidence(self, status: str) -> None:
        now = self.clock()
        if now - self._last_hb_evidence >= self.heartbeat_evidence_s:
            self._last_hb_evidence = now
            self._evidence("heartbeat", {"status": status, "head": self.head, "instance": self.instance},
                           idem=f"hb:{self.instance}:{int(now)}")

    def next_delay(self) -> float:
        return self.interval_s if not self.errors else min(self.interval_s * 2 ** self.errors, self.max_backoff_s)

    # ---- loop -------------------------------------------------------------------------------------------------------
    def run(self, max_ticks: int | None = None) -> int:
        n = 0
        try:
            while not self._stop.is_set() and (max_ticks is None or n < max_ticks):
                try:
                    self.tick()
                except LeaseHeld:
                    raise
                except Exception as e:  # noqa: BLE001 - one bad tick must not kill the monitor; it is reported
                    self.errors += 1
                    self._write_health("degraded", note=f"tick failed: {type(e).__name__}: {str(e)[:200]}")
                n += 1
                if max_ticks is not None and n >= max_ticks:
                    break
                if self.sleep is time.sleep:
                    self._stop.wait(self.next_delay())  # wakes immediately on SIGINT / SIGTERM
                else:
                    self.sleep(self.next_delay())
        finally:
            self.stop()
        return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FAULTLINE persistent keeper service (local test chains / local forks only)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--journal-dir")
    ap.add_argument("--state-dir", help="lock, health.json, finality.json (default: the journal directory)")
    ap.add_argument("--evidence-db", help="SQLite evidence store (default: <state-dir>/evidence.sqlite; 'none' disables)")
    ap.add_argument("--environment", choices=("local-test", "fork"))
    ap.add_argument("--confirmations", type=int, default=2)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--max-ticks", type=int)
    ap.add_argument("--max-head-age", type=float, help="seconds; skip decisions when the chain head is older")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    rpc = RPC(cfg["rpc_url"])
    signer = signer_from_env(rpc)
    jdir = Path(a.journal_dir or cfg.get("journal_dir", "data/countermove/journal"))
    sdir = Path(a.state_dir or jdir)
    store = None if (a.evidence_db or "").lower() == "none" else EvidenceStore(a.evidence_db or sdir / "evidence.sqlite")
    svc = KeeperService(cfg, rpc, Journal(jdir), signer, state_dir=sdir, store=store,
                        environment=a.environment or cfg.get("environment", "local-test"), confirmations=a.confirmations,
                        interval_s=a.interval, max_head_age_s=a.max_head_age)
    try:
        svc.start()
    except LeaseHeld as e:
        print(f"refusing to start: {e}", file=sys.stderr)
        return 2
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: svc.request_stop())
    print(f"FAULTLINE keeper service {svc.instance} ({'watch-only' if signer is None else signer.address}) chain "
          f"{svc.chain_id} env {svc.environment} -> {svc.health_path}", file=sys.stderr)
    svc.run(a.max_ticks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
