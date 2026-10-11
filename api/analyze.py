"""Vercel Python serverless function: GET /api/analyze?ref=auto&value_usd=1000000&shock=<node id>&severity=0.3&borrower=0x..|auto
ref: auto | pendle:1:<Pendle market address> | morpho:1:<Morpho Blue market id>
GET /api/analyze?lookup=1&ref=morpho:1:<market id> -> cheap identification (no analysis); 404 if not in the supported set.
payload["source"] is the single source of truth for the UI badge:
  live | cache | mixed  -> real data (cache = replayed from data/cache, see payload["data_as_of"])
  mock                  -> demo graph requested explicitly (ref=mock); there is no silent demo fallback:
                           a failed live discovery returns 502 {"error", "code": "discovery_failed", "hint"}
Errors: 400 invalid_input | 404 unsupported_market | 502 discovery_failed, shape {"error": str, "code": str}
"""
import json
import math
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk.api_payload import build_payload  # noqa: E402
from defirisk.data.discovery import UnsupportedMarket, lookup  # noqa: E402
from defirisk.leverage import parse_borrower  # noqa: E402


def _payload(ref: str, value_usd: float = 1_000_000, shock=None, severity=None, borrower=None, **book) -> dict:
    if ref == "mock":
        return build_payload("mock", True, value_usd=value_usd, shock_node=shock, severity=severity, **book)
    return build_payload(ref, False, value_usd=value_usd, shock_node=shock, severity=severity, borrower=borrower, **book)


def _params(path: str) -> dict:
    q = parse_qs(urlparse(path).query)
    one = lambda k: (q.get(k) or [None])[0]  # noqa: E731

    def frac(k):
        v = one(k)
        if v in (None, ""):
            return None
        v = float(v)
        if not math.isfinite(v) or not 0 <= v <= 1:
            raise ValueError(f"{k} must be within [0, 1]")
        return v

    value = float(one("value_usd") or 1_000_000)
    if not math.isfinite(value) or not 1_000 <= value <= 100_000_000:
        raise ValueError("value_usd must be within [1e3, 1e8]")
    book_usd = float(one("book_usd") or 10_000_000)
    if not math.isfinite(book_usd) or not 10_000 <= book_usd <= 10_000_000_000:
        raise ValueError("book_usd must be within [1e4, 1e10]")
    sev = frac("severity")
    ref = one("ref") or "auto"
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", ref):
        raise ValueError("invalid ref")
    shock = one("shock")
    if shock is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", shock):
        raise ValueError("invalid shock node id")
    book_shock = one("book_shock")
    if book_shock is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", book_shock):
        raise ValueError("invalid book_shock dependency key")
    weights = one("weights")
    if weights:
        weights = [float(x) for x in weights.split(",") if x.strip()]
        if not 1 <= len(weights) <= 10 or any(not math.isfinite(x) or x < 0 for x in weights):
            raise ValueError("weights: 1 to 10 non-negative numbers, comma-separated")
        total = sum(weights)
        if total <= 0:
            raise ValueError("weights must not all be 0")
        weights = [x / total for x in weights]
    return {"ref": ref, "value_usd": value, "shock": shock, "severity": sev, "borrower": parse_borrower(one("borrower")),
            "book_usd": book_usd, "exit_cost_pct": frac("exit_cost_pct"), "book_shock": book_shock,
            "book_severity": frac("book_severity"), "weights": weights or None}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = parse_qs(urlparse(self.path).query)
            if (q.get("lookup") or [None])[0] == "1":  # cheap identification for the app's select screen, no analysis
                ref = (q.get("ref") or [""])[0]
                if not re.fullmatch(r"morpho:1:0x[0-9a-fA-F]{64}", ref):
                    raise ValueError("lookup needs ref=morpho:1:<Morpho Blue market id>")
                body, status = json.dumps(lookup(ref.lower())).encode(), 200
            else:
                body, status = json.dumps(_payload(**_params(self.path))).encode(), 200
        except ValueError as e:
            body, status = json.dumps({"error": str(e), "code": "invalid_input"}).encode(), 400
        except UnsupportedMarket as e:
            body, status = json.dumps({"error": str(e), "code": "unsupported_market"}).encode(), 404
        except Exception as e:  # live discovery failed: say why, never substitute the demo graph silently
            body, status = json.dumps({"error": f"{type(e).__name__}: {e}"[:500], "code": "discovery_failed",
                                       "hint": "retry, or ask explicitly for the demo graph with ref=mock"}).encode(), 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=60")
        self.end_headers()
        self.wfile.write(body)
