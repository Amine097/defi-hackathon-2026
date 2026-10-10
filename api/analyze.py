"""Vercel Python serverless function: GET /api/analyze"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urllib.parse import parse_qs, urlparse

from defirisk.api_payload import build_payload  # noqa: E402


def _payload(ref: str) -> dict:
    if ref == "mock":
        return build_payload("mock", True)
    try:
        p = build_payload(ref, False)
        p["source"] = "live"
        return p
    except Exception as e:  # never leave the UI blank: fall back to the mock graph
        p = build_payload("mock", True)
        p["source"] = "mock-fallback"
        p["discovery_error"] = str(e)
        return p


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            ref = parse_qs(urlparse(self.path).query).get("ref", ["auto"])[0]
            body, status = json.dumps(_payload(ref)).encode(), 200
        except Exception as e:  # surface errors to the UI instead of a blank 500
            body, status = json.dumps({"error": str(e)}).encode(), 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=60")
        self.end_headers()
        self.wfile.write(body)
