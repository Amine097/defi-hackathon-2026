"""HTTP/RPC with disk cache + offline fallback, so the demo survives API outages.

Usage: from .http import get_json
- Live call succeeds -> response saved to data/cache/<hash>.json
- Live call fails (or DEFIRISK_OFFLINE=1) -> last saved response is returned
Pre-warm before the demo: run the app once with internet, then commit data/cache.
"""
import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"


def _key(method: str, url: str, params, body) -> Path:
    raw = json.dumps([method, url, params, body], sort_keys=True, default=str)
    return CACHE_DIR / (hashlib.sha256(raw.encode()).hexdigest()[:24] + ".json")


def _cached(method: str, url: str, params=None, body=None, timeout: float = 8.0):
    import requests

    path = _key(method, url, params, body)
    if os.getenv("DEFIRISK_OFFLINE") != "1":
        try:
            r = requests.request(method, url, params=params, json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"url": url, "data": data}), encoding="utf-8")
            except OSError:  # read-only filesystem (e.g. Vercel): skip caching, committed cache still read
                pass
            return data
        except Exception as e:
            if not path.exists():
                raise RuntimeError(f"{url} failed and no cached copy: {e}") from e
            print(f"[cache] live call failed, using cached copy for {url}")
    elif not path.exists():
        raise RuntimeError(f"offline mode and no cached copy for {url}")
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def get_json(url: str, params: dict | None = None, timeout: float = 8.0):
    return _cached("GET", url, params, None, timeout)


def post_json(url: str, body: dict, timeout: float = 8.0):
    """For JSON-RPC calls (eth_call, eth_getLogs...)."""
    return _cached("POST", url, None, body, timeout)
