"""Input contract of the vault analyzer (P1-01): address, chain, exposure, horizon, scenario parameters.

Every check is local and deterministic (no network): bad input -> ValueError -> HTTP 400.
A pasted vault URL is reduced to the address it contains, only for an allowlist of known hosts, without ever
fetching the URL (no SSRF).
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlparse

from .keccak import keccak256

SUPPORTED_CHAINS = {1: "Ethereum mainnet"}
VALUE_BOUNDS = (1_000.0, 100_000_000.0)
HORIZON_BOUNDS = (1, 365)
URL_HOSTS = {"app.morpho.org", "morpho.org", "etherscan.io", "www.etherscan.io", "dune.com"}
_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
_NODE = re.compile(r"[A-Za-z0-9_.:-]{1,100}")


class VaultError(Exception):
    """Structured error: code (machine), status (HTTP), message (human, no secrets)."""

    def __init__(self, code: str, status: int, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code, self.status, self.message, self.detail = code, status, message, detail or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "status": self.status, "message": self.message, **self.detail}}


def to_checksum(address: str) -> str:
    """EIP-55 mixed-case checksum encoding."""
    a = address.lower().removeprefix("0x")
    h = keccak256(a.encode()).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c for i, c in enumerate(a))


def parse_address(raw: str | None) -> dict:
    """0x + 40 hex. Mixed case must match EIP-55; all-lower / all-upper is accepted (no checksum carried)."""
    if raw is None or not str(raw).strip():
        raise ValueError("address is required")
    s = str(raw).strip()
    if len(s) > 200:
        raise ValueError("address too long")
    if not _ADDR.fullmatch(s):
        raise ValueError("address must be 0x followed by 40 hexadecimal characters")
    body = s[2:]
    cs = to_checksum(s)
    if body != body.lower() and body != body.upper() and s != cs:
        raise ValueError("address checksum (EIP-55) is invalid")
    if int(body, 16) == 0:
        raise ValueError("zero address is not a vault")
    return {"address": cs, "checksum": "verified" if s == cs else "not_provided"}


def address_from_url(url: str) -> str:
    """Extract a vault address from a pasted link (allowlisted hosts only). The URL is never requested."""
    if len(url) > 500:
        raise ValueError("url too long")
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in URL_HOSTS:
        raise ValueError(f"url host not allowed (accepted: {', '.join(sorted(URL_HOSTS))})")
    hits = _ADDR.findall(u.path + "?" + u.query)
    if len(set(h.lower() for h in hits)) != 1:
        raise ValueError("url must contain exactly one 0x address")
    return hits[0]


def parse_value(raw) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError("value_usd must be a number") from None
    lo, hi = VALUE_BOUNDS
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f"value_usd must be within [{lo:,.0f}, {hi:,.0f}]")
    return v


def parse_request(q: dict) -> dict:
    """q: query parameters (single values). Returns the validated request."""
    raw_addr = q.get("address")
    if not raw_addr and q.get("url"):
        raw_addr = address_from_url(q["url"])
    addr = parse_address(raw_addr)
    try:
        chain = int(q.get("chain_id") or 1)
    except ValueError:
        raise ValueError("chain_id must be an integer") from None
    if chain not in SUPPORTED_CHAINS:
        raise ValueError(f"chain_id {chain} not supported (supported: 1 = Ethereum mainnet)")
    value = parse_value(q.get("value_usd") if q.get("value_usd") not in (None, "") else 100_000)
    try:
        horizon = int(q.get("horizon_days") or 30)
    except ValueError:
        raise ValueError("horizon_days must be an integer") from None
    if not HORIZON_BOUNDS[0] <= horizon <= HORIZON_BOUNDS[1]:
        raise ValueError(f"horizon_days must be within {list(HORIZON_BOUNDS)}")
    shock = q.get("shock") or None
    if shock is not None and not _NODE.fullmatch(shock):
        raise ValueError("invalid shock node id")
    sev = q.get("severity")
    if sev not in (None, ""):
        try:
            sev = float(sev)
        except ValueError:
            raise ValueError("severity must be a number") from None
        if not math.isfinite(sev) or not 0 <= sev <= 1:
            raise ValueError("severity must be within [0, 1]")
    else:
        sev = None
    return {"address": addr["address"], "checksum": addr["checksum"], "chain_id": chain, "value_usd": value,
            "horizon_days": horizon, "shock": shock, "severity": sev}
