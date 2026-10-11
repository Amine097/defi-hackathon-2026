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
GET /api/countermove?action=evidence[&position=<id>][&since=<seq>][&limit=1..500][&source=all|recorded|store][&kinds=a,b]
                                         -> faultline.countermove.evidence/1: the recorded fork journal (labelled `fork`,
                                            sha256 integrity) + the keeper's SQLite evidence store when configured
GET /api/countermove?action=keeper-status -> faultline.keeper.status/1: the keeper heartbeat (OK / STALE / DEGRADED /
                                            UNAVAILABLE / STOPPED); UNAVAILABLE on Vercel (no keeper process there)
GET /api/countermove?action=policy-status&vault=<0x..>[&<policy draft fields>][&required_loan_raw=..&required_collateral_raw=..]
                                         -> faultline.countermove.lifecycle/1: ARM state DERIVED from the vault read on
                                            the server-configured chain (FAULTLINE_ARM_RPC_URL) + keeper heartbeat +
                                            journal; UNAVAILABLE (with the reason) when that evidence is missing
keeper-status / policy-status / evidence are read server-side from the hosted keeper (Railway) when
FAULTLINE_KEEPER_URL is set; the answer carries `hosted` (test chain label, host, latency). Without vault=, policy-status
then reports the hosted keeper's own test vault.
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
from defirisk.countermove import remote  # noqa: E402
from defirisk.countermove import status as cms  # noqa: E402

ACTIONS = ("policy-draft", "dry-run", "evidence", "keeper-status", "policy-status")
_STATUS = {"evidence": cms.evidence, "keeper-status": cms.keeper_status, "policy-status": cms.policy_status}


def respond(path: str) -> tuple[int, dict]:
    u = urlparse(path)
    q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
    try:
        if u.path.rstrip("/").endswith("/policy-draft") or q.get("action") == "policy-draft":
            return 200, cm.policy_draft(q)
        if u.path.rstrip("/").endswith("/dry-run") or q.get("action") == "dry-run":
            return 200, dryrun.run(q)
        if q.get("action") in _STATUS:
            try:
                hosted = remote.fetch(q["action"], q)
            except remote.HostedError as e:
                try:
                    return 200, remote.unreachable(_STATUS[q["action"]](q), str(e))
                except (ValueError, KeyError):
                    return 503, {"error": {"code": "keeper_unreachable", "status": 503, "message": str(e)}}
            if hosted is not None:
                return hosted
            return 200, _STATUS[q["action"]](q)
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
