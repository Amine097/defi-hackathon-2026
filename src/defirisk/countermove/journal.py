"""Append-only journal (JSONL) + crash-safe state file for the Countermove keeper.

Every state transition is one JSON line. `state.json` keeps, per position, the last state, the reference dependency
snapshot (last healthy observation) and any PENDING action (signed tx hash + action id + nonce written BEFORE the
transaction is broadcast), so a keeper restarted after a crash checks the chain before doing anything else.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path


def _jsonable(o):
    """Exact integers are kept (Python json handles big ints); JS-safe strings are the API layer's job."""
    if isinstance(o, bool) or o is None or isinstance(o, (str, float, int)):
        return o
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "__dict__"):
        return _jsonable(vars(o))
    return str(o)


class Journal:
    def __init__(self, directory: str | Path, sink=None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "journal.jsonl"
        self.state_path = self.dir / "state.json"
        self.run_id = uuid.uuid4().hex[:12]
        self.sink = sink  # optional mirror (evidence.EvidenceStore.sink): the JSONL line is written first
        self.sink_errors = 0

    def append(self, position_id: str, state: str, **data) -> dict:
        rec = {"ts": time.time(), "run_id": self.run_id, "position": position_id, "state": state, **data}
        safe = _jsonable(rec)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(safe, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if self.sink is not None:
            try:
                self.sink(safe)
            except Exception as e:  # noqa: BLE001 - the JSONL record exists; a mirror failure must not stop the keeper
                self.sink_errors += 1
                print(f"[journal] evidence sink failed ({type(e).__name__}: {e})", file=sys.stderr)
        return rec

    def entries(self, position_id: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [e for e in out if position_id is None or e.get("position") == position_id]

    def state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}

    def _save(self, st: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_jsonable(st), indent=1, allow_nan=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)

    def update(self, position_id: str, **fields) -> dict:
        st = self.state()
        cur = st.setdefault(position_id, {})
        cur.update(fields)
        cur["updated_at"] = time.time()
        self._save(st)
        return cur

    def pending(self, position_id: str) -> dict | None:
        return self.state().get(position_id, {}).get("pending")

    def set_pending(self, position_id: str, pending: dict | None) -> None:
        self.update(position_id, pending=pending)
