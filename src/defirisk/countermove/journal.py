"""Append-only journal (JSONL) + crash-safe state file for the Countermove keeper.

Every state transition is one JSON line. `state.json` keeps, per position, the last state, the reference dependency
snapshot (last healthy observation) and any PENDING action (signed tx hash + action id + nonce written BEFORE the
transaction is broadcast), so a keeper restarted after a crash checks the chain before doing anything else.
"""
from __future__ import annotations

import json
import os
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
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "journal.jsonl"
        self.state_path = self.dir / "state.json"
        self.run_id = uuid.uuid4().hex[:12]

    def append(self, position_id: str, state: str, **data) -> dict:
        rec = {"ts": time.time(), "run_id": self.run_id, "position": position_id, "state": state, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_jsonable(rec), allow_nan=False) + "\n")
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
        tmp.write_text(json.dumps(_jsonable(st), indent=1, allow_nan=False), encoding="utf-8")
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
