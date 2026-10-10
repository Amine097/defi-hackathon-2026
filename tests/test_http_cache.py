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
