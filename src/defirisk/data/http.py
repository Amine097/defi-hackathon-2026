"""HTTP/RPC with disk cache + offline fallback, so the demo survives API outages.

Usage: from .http import get_json
- Live call succeeds -> response saved to data/cache/<hash>.json
- Live call fails (or DEFIRISK_OFFLINE=1) -> last saved response is returned
Pre-warm before the demo: run the app once with internet, then commit data/cache.
"""
import hashlib
import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"

# Provenance of every response served since the last reset(): lets the payload say honestly whether the
# numbers come from live calls or from the disk cache (and how old that cache is).
_PROV = {"live": 0, "cached": 0, "oldest_cache_ts": None, "cached_urls": []}
# Metadata of the most recent response (fetch time + whether it came from the cache), for freshness checks.
LAST = {"fetched_at": None, "cached": False, "url": None}


def now() -> float:
    """Injectable clock (tests monkeypatch this): every freshness computation goes through it."""
    return time.time()


def reset_provenance() -> None:
    _PROV.update(live=0, cached=0, oldest_cache_ts=None, cached_urls=[])


def provenance() -> dict:
    p = dict(_PROV)
    p["mode"] = "live" if p["cached"] == 0 else ("cache" if p["live"] == 0 else "mixed")
    return p


def _note_cached(url: str, path: Path, stored: dict) -> None:
    ts = stored.get("fetched_at") or int(path.stat().st_mtime)
    _PROV["cached"] += 1
    _PROV["oldest_cache_ts"] = ts if _PROV["oldest_cache_ts"] is None else min(_PROV["oldest_cache_ts"], ts)
    if url not in _PROV["cached_urls"]:
        _PROV["cached_urls"].append(url)


def _key(method: str, url: str, params, body) -> Path:
    raw = json.dumps([method, url, params, body], sort_keys=True, default=str)
    return CACHE_DIR / (hashlib.sha256(raw.encode()).hexdigest()[:24] + ".json")


def _cached(method: str, url: str, params=None, body=None, timeout: float = 8.0, use_cache: bool = True):
    import requests

    path = _key(method, url, params, body)
    if os.getenv("DEFIRISK_OFFLINE") != "1":
        try:
            r = requests.request(method, url, params=params, json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            rpc_error = isinstance(data, dict) and "jsonrpc" in data and data.get("error")
            try:
                if not rpc_error:  # never cache JSON-RPC errors (rate limits...)
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"url": url, "fetched_at": int(now()), "data": data}), encoding="utf-8")
            except OSError:  # read-only filesystem (e.g. Vercel): skip caching, committed cache still read
                pass
            _PROV["live"] += 1
            LAST.update(fetched_at=now(), cached=False, url=url)
            return data
        except Exception as e:
            if not use_cache or not path.exists():
                raise RuntimeError(f"{url} failed and no cached copy: {e}") from e
            print(f"[cache] live call failed, using cached copy for {url}")
    elif not use_cache or not path.exists():
        raise RuntimeError(f"offline mode and no cached copy for {url}")
    stored = json.loads(path.read_text(encoding="utf-8"))
    _note_cached(url, path, stored)
    LAST.update(fetched_at=stored.get("fetched_at") or int(path.stat().st_mtime), cached=True, url=url)
    return stored["data"]


def get_json(url: str, params: dict | None = None, timeout: float = 8.0):
    return _cached("GET", url, params, None, timeout)


def post_json(url: str, body: dict, timeout: float = 8.0, use_cache: bool = True):
    """For JSON-RPC calls (eth_call, eth_getLogs...). use_cache=False: live only (lets callers try other endpoints
    before falling back to a cached copy)."""
    return _cached("POST", url, None, body, timeout, use_cache)
