"""Hosted keeper read (remote.py) and the /api/countermove proxy: server-configured URL only, schema-checked payloads,
an honest UNREACHABLE fallback, never a fabricated OK."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from defirisk.countermove import remote

ROOT = Path(__file__).resolve().parents[1]


class _H(BaseHTTPRequestHandler):
    reply = (200, {"schema": "faultline.keeper.status/1", "status": "OK"})
    seen: list = []

    def do_GET(self):
        _H.seen.append(self.path)
        code, body = _H.reply
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


@pytest.fixture()
def keeper(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FAULTLINE_KEEPER_URL", f"http://127.0.0.1:{srv.server_port}/")
    _H.seen = []
    _H.reply = (200, {"schema": "faultline.keeper.status/1", "status": "OK"})
    yield _H
    srv.shutdown()


@pytest.mark.parametrize("url,ok", [("", False), ("https://k.up.railway.app", True), ("http://k.up.railway.app", False),
                                    ("http://127.0.0.1:8791", True), ("https://k.app/?x=1", False), ("ftp://k.app", False)])
def test_base_url_rules(monkeypatch, url, ok):
    monkeypatch.setenv("FAULTLINE_KEEPER_URL", url)
    assert (remote.base_url() is not None) is ok


def test_not_configured_returns_none(monkeypatch):
    monkeypatch.delenv("FAULTLINE_KEEPER_URL", raising=False)
    assert remote.fetch("keeper-status", {}) is None


def test_fetch_ok_adds_hosted_block_and_forwards_params(keeper):
    status, body = remote.fetch("evidence", {"action": "evidence", "source": "store", "limit": "8", "big": "x" * 300})
    assert status == 200 and body["hosted"]["status"] == "ok" and body["hosted"]["host"] == "127.0.0.1"
    assert "not Ethereum mainnet" in body["hosted"]["environment"]
    path = keeper.seen[-1]
    assert path.startswith("/api/countermove?action=evidence") and "limit=8" in path and "big=" not in path


@pytest.mark.parametrize("reply", [(500, {"error": "boom"}), (200, {"status": "OK"}), (200, b"<html>")])
def test_fetch_rejects_bad_answers(keeper, reply):
    keeper.reply = reply
    with pytest.raises(remote.HostedError):
        remote.fetch("keeper-status", {})


def test_fetch_passes_4xx_through(keeper):
    keeper.reply = (400, {"error": "bad_request"})
    assert remote.fetch("policy-status", {"vault": "nope"})[0] == 400


def _api():
    spec = importlib.util.spec_from_file_location("api_countermove", ROOT / "api" / "countermove.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_api_proxies_hosted_status(keeper):
    keeper.reply = (200, {"schema": "faultline.keeper.status/1", "status": "OK", "monitoring": True})
    code, body = _api().respond("/api/countermove?action=keeper-status")
    assert code == 200 and body["status"] == "OK" and body["hosted"]["status"] == "ok"


def test_api_unreachable_falls_back_honestly(monkeypatch):
    monkeypatch.setenv("FAULTLINE_KEEPER_URL", "http://127.0.0.1:9")
    code, body = _api().respond("/api/countermove?action=keeper-status")
    assert code == 200 and body["hosted"]["status"] == "UNREACHABLE" and body["status"] != "OK"
