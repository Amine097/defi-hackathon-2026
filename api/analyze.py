"""Vercel Python serverless function: GET /api/analyze?ref=auto&value_usd=1000000&shock=<node id>&severity=0.3

payload["source"] is the single source of truth for the UI badge:
  live | cache | mixed  -> real data (cache = replayed from data/cache, see payload["data_as_of"])
  mock                  -> demo graph requested explicitly (ref=mock)
  mock-fallback         -> live discovery FAILED; demo graph shown, error in payload["discovery_error"]
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk.api_payload import build_payload  # noqa: E402


def _payload(ref: str, value_usd: float = 1_000_000, shock=None, severity=None) -> dict:
    if ref == "mock":
        return build_payload("mock", True, value_usd=value_usd, shock_node=shock, severity=severity)
    try:
        return build_payload(ref, False, value_usd=value_usd, shock_node=shock, severity=severity)
    except Exception as e:  # never leave the UI blank, but label it loudly
        p = build_payload("mock", True, value_usd=value_usd)
        p["source"] = "mock-fallback"
        p["discovery_error"] = f"{type(e).__name__}: {e}"[:500]
        return p


def _params(path: str) -> dict:
    q = parse_qs(urlparse(path).query)
    one = lambda k: (q.get(k) or [None])[0]  # noqa: E731
    value = float(one("value_usd") or 1_000_000)
    if not 1_000 <= value <= 100_000_000:
        raise ValueError("value_usd must be within [1e3, 1e8]")
    sev = one("severity")
    return {"ref": one("ref") or "auto", "value_usd": value, "shock": one("shock"),
            "severity": float(sev) if sev not in (None, "") else None}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, status = json.dumps(_payload(**_params(self.path))).encode(), 200
        except ValueError as e:
            body, status = json.dumps({"error": str(e)}).encode(), 400
        except Exception as e:  # surface errors to the UI instead of a blank 500
            body, status = json.dumps({"error": str(e)}).encode(), 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=60")
        self.end_headers()
        self.wfile.write(body)
