"""Vercel Python serverless function: GET /api/analyze"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk.api_payload import build_payload  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, status = json.dumps(build_payload()).encode(), 200
        except Exception as e:  # surface errors to the UI instead of a blank 500
            body, status = json.dumps({"error": str(e)}).encode(), 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=60")
        self.end_headers()
        self.wfile.write(body)
