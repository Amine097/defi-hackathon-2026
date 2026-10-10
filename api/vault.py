"""Vercel Python serverless function - Phase 1 Vault Risk Analyzer.

GET /api/vault?address=0x..|url=<morpho/etherscan link>&value_usd=100000&chain_id=1&horizon_days=30&shock=<node id>&severity=0.4

200 -> faultline.vault/1 payload (mode live | cache | mixed | offline; never mock)
4xx/5xx -> {"error": {"code", "status", "message", ...}}; no traceback, no fallback demo data.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk.vault_input import VaultError, parse_request  # noqa: E402
from defirisk import vault_model  # noqa: E402


def respond(path: str) -> tuple[int, dict]:
    q = {k: v[0] for k, v in parse_qs(urlparse(path).query).items() if v}
    try:
        return 200, vault_model.analyze(parse_request(q))
    except VaultError as e:
        return e.status, e.to_dict()
    except ValueError as e:
        return 400, {"error": {"code": "invalid_input", "status": 400, "message": str(e)[:300]}}
    except Exception as e:  # noqa: BLE001 - generic message, details stay server-side
        print(f"vault analysis failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 500, {"error": {"code": "internal_error", "status": 500,
                               "message": "vault analysis failed; no figures are shown rather than unverified ones"}}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = respond(self.path)
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=30" if status == 200 else "no-store")
        self.end_headers()
        self.wfile.write(body)
