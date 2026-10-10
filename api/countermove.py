"""Vercel Python serverless function - Phase 2 Autonomous Countermove (read-only).

GET /api/countermove[?live=1]            -> faultline.countermove/1: the recorded local mainnet-fork run (SIMULATED
                                            environment, CONFIRMED / FAILED / NO_ACTION per position) [+ LIVE mainnet
                                            dependency reads when live=1]
GET /api/countermove?action=policy-draft&...  (alias: /api/countermove/policy-draft, local dev server only: Vercel
                                            file routing does not reach sub-paths of a function)
                                         -> validated setPolicy calldata for the USER's own wallet (never signed here)
GET /api/countermove?action=dry-run&market=<id|alias>&borrower=<0x..|auto>[&rank=1][&<policy / reserve fields>]
                                         -> faultline.countermove.dryrun/1: a REAL mainnet borrower read now (LIVE) and
                                            what the keeper would do under a hypothetical policy (DRY-RUN, no tx)
Errors are JSON {"error": {"code", "status", "message", ...}} (400 invalid input, 404 unknown market / borrower,
503 mainnet RPC or Morpho API unavailable), never HTML.
This endpoint never signs or sends a transaction: the keeper is a separate local process (python -m defirisk.countermove).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk.countermove import api as cm  # noqa: E402
from defirisk.countermove import dryrun  # noqa: E402

ACTIONS = ("policy-draft", "dry-run")


def respond(path: str) -> tuple[int, dict]:
    u = urlparse(path)
    q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
    try:
        if u.path.rstrip("/").endswith("/policy-draft") or q.get("action") == "policy-draft":
            return 200, cm.policy_draft(q)
        if u.path.rstrip("/").endswith("/dry-run") or q.get("action") == "dry-run":
            return 200, dryrun.run(q)
        if "action" in q:
            return 400, {"error": {"code": "invalid_input", "status": 400, "field": "action",
                                   "message": f"unknown action (accepted: {', '.join(ACTIONS)})"}}
        return 200, cm.payload(live=q.get("live") == "1")
    except dryrun.DryRunError as e:
        return e.status, e.to_dict()
    except (ValueError, KeyError) as e:
        return 400, {"error": {"code": "invalid_input", "status": 400, "message": str(e)[:300]}}
    except Exception as e:  # noqa: BLE001 - generic message, details stay server-side
        print(f"countermove api failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 500, {"error": {"code": "internal_error", "status": 500, "message": "countermove data unavailable"}}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = respond(self.path)
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
