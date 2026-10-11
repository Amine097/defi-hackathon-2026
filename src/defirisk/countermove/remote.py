"""Server-side read of the hosted keeper's status API (Railway), for the Vercel function.

The browser cannot call the Railway domain (CSP connect-src 'self'), so /api/countermove fetches it server-side and
returns the same schema with a `hosted` block. The URL comes ONLY from server configuration (no SSRF):
  FAULTLINE_KEEPER_URL   e.g. https://faultline-keeper.up.railway.app   (unset -> the local behaviour, UNAVAILABLE on Vercel)
Read-only: GET keeper-status | policy-status | evidence. Nothing here signs or sends a transaction.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

ACTIONS = ("keeper-status", "policy-status", "evidence")
ENVIRONMENT = ("hosted keeper service: a local Anvil test chain (chain id 31337) inside the container, test tokens, "
               "SIMULATED price feed; not Ethereum mainnet")
_MAX = 2_000_000


def base_url() -> str | None:
    u = (os.getenv("FAULTLINE_KEEPER_URL") or "").strip().rstrip("/")
    if not u:
        return None
    p = urlparse(u)
    local = p.hostname in ("127.0.0.1", "localhost")
    if p.scheme not in ("https", "http") or (p.scheme == "http" and not local) or not p.hostname or p.query:
        return None
    return u


def fetch(action: str, q: dict, timeout: float = 8.0) -> tuple[int, dict] | None:
    """(status, payload) from the hosted keeper, or None when it is not configured. Unreachable -> None + reason via
    unreachable(); a 4xx JSON error from the keeper is passed through (it validated the same input)."""
    base = base_url()
    if not base or action not in ACTIONS:
        return None
    params = {k: v for k, v in q.items() if k != "action" and isinstance(v, str) and len(v) <= 200}
    url = f"{base}/api/countermove?{urlencode({'action': action, **params})}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "faultline-vercel/1"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed server-configured https URL
            status, raw = r.status, r.read(_MAX + 1)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(_MAX + 1)
        if status >= 500:
            raise HostedError(f"hosted keeper answered HTTP {status}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HostedError(f"hosted keeper unreachable: {type(e).__name__}") from None
    if len(raw) > _MAX:
        raise HostedError("hosted keeper response too large")
    try:
        body = json.loads(raw)
    except ValueError:
        raise HostedError("hosted keeper returned non-JSON") from None
    if not isinstance(body, dict) or not (status >= 400 or str(body.get("schema", "")).startswith("faultline.")):
        raise HostedError("hosted keeper returned an unexpected payload")
    body["hosted"] = {"status": "ok", "host": urlparse(base).hostname, "environment": ENVIRONMENT,
                      "fetched_at": round(time.time(), 3), "latency_ms": round((time.time() - t0) * 1000)}
    return status, body


class HostedError(RuntimeError):
    pass


def unreachable(payload: dict, why: str) -> dict:
    payload["hosted"] = {"status": "UNREACHABLE", "host": urlparse(base_url() or "").hostname, "reason": why,
                         "environment": ENVIRONMENT}
    if payload.get("schema") == "faultline.keeper.status/1":
        payload["reason"] = f"{why}; showing this deployment's own status instead"
    return payload
