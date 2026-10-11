"""Record the demonstration payloads the app opens in DEMO mode (public/data/recorded/*.json).

Each file is the exact JSON body a live backend endpoint returned, plus a `_snapshot` block that says when, at which
Ethereum block, from which endpoint and from which backend commit it was recorded. The app labels these files
RECORDED LIVE RUN and never presents them as live data.

    $env:PYTHONPATH='src'; python scripts/record_demo_payloads.py            # all three
    $env:PYTHONPATH='src'; python scripts/record_demo_payloads.py vault      # one of: pt, borrow, vault
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

OUT = ROOT / "public" / "data" / "recorded"
BELEM_VAULT = "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec"

TARGETS = {
    "pt": ("analyze-pt.json", "/api/analyze?ref=auto&value_usd=1000000"),
    "borrow": ("analyze-borrower.json", "/api/analyze?ref=auto&value_usd=1000000&borrower=auto"),
    "vault": ("vault-belem.json", f"/api/vault?address={BELEM_VAULT}&value_usd=1000000&horizon_days=30"),
}


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _call(url: str) -> tuple[int, dict]:
    if url.startswith("/api/vault"):
        from api.vault import respond
        return respond(url)
    import api.analyze as an
    try:
        return 200, an._payload(**an._params(url))
    except ValueError as e:
        return 400, {"error": str(e)}


def _block(body: dict) -> int | None:
    if "as_of_block" in body:
        return body.get("as_of_block")
    meta = (body.get("position") or {}).get("meta") or {}
    return meta.get("block_number")


def record(key: str) -> Path:
    name, url = TARGETS[key]
    t0 = time.time()
    status, body = _call(url)
    if status != 200:
        raise SystemExit(f"{key}: {url} returned {status}: {json.dumps(body)[:300]}")
    mode = body.get("mode") or body.get("source")
    if mode not in ("live",):
        raise SystemExit(f"{key}: refusing to record a non-live response (mode/source = {mode!r})")
    body["_snapshot"] = {
        "label": f"Saved snapshot of a live {url.split('?')[0]} response",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "block": _block(body),
        "source_url": url,
        "backend_commit": _commit(),
        "duration_s": round(time.time() - t0, 1),
        "note": "Recorded from the live backend for the app's DEMO mode. Shown with the label RECORDED LIVE RUN and "
                "its block; never presented as live data.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(body, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(f"{key}: {path.relative_to(ROOT)} block {body['_snapshot']['block']} in {body['_snapshot']['duration_s']} s")
    return path


if __name__ == "__main__":
    for k in (sys.argv[1:] or list(TARGETS)):
        record(k)
