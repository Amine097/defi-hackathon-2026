import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest

from defirisk import http


class FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"ok": 1}


def test_cache_fallback(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(http, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResp())
    assert http.get_json("http://x/api") == {"ok": 1}

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(requests, "request", boom)
    assert http.get_json("http://x/api") == {"ok": 1}  # served from cache
    with pytest.raises(RuntimeError):
        http.get_json("http://x/other")


def test_cache_write_is_atomic(tmp_path, monkeypatch):
    """A failed write leaves the previous cache entry intact and no temp file behind (no truncated JSON)."""
    import os
    import requests

    monkeypatch.setattr(http, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResp())
    http.get_json("http://x/api")
    entry = next(tmp_path.glob("*.json"))
    before = entry.read_bytes()

    def broken_replace(src, dst):
        raise OSError("disk full")

    class Other(FakeResp):
        def json(self):
            return {"ok": 2}

    monkeypatch.setattr(requests, "request", lambda *a, **k: Other())
    monkeypatch.setattr(os, "replace", broken_replace)
    assert http.get_json("http://x/api") == {"ok": 2}  # live data still served; caching is best-effort
    assert entry.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [entry.name]
