"""Select-screen lookups added for the Claude Design app: /api/analyze?lookup=1&ref=morpho:1:<id> and
/api/vault?lookup=1&address=0x.. (offline: sources are stubbed; DEFIRISK_LIVE_TESTS=1 adds real mainnet checks)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from defirisk.data import discovery  # noqa: E402
from defirisk import vault_reader  # noqa: E402

PT_MARKET = "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64"
LIVE = os.environ.get("DEFIRISK_LIVE_TESTS") == "1"


@pytest.mark.parametrize("ref", ["auto", "pendle:1:0x13285bcbc27f92b47b4edb99d744c07b48c977c0", "morpho:1:" + PT_MARKET])
def test_check_ref_accepts_supported_forms(ref):
    discovery._check_ref(ref, 1)


@pytest.mark.parametrize("ref", ["morpho:8453:" + PT_MARKET, "morpho:1:0x1234", "pendle:42161:0xabc", "wallet:0xabc", "foo"])
def test_check_ref_rejects_other_forms(ref):
    with pytest.raises(ValueError):
        discovery._check_ref(ref, 1)


def _stub_markets(monkeypatch):
    pt = "0xecfafdc7741323a945a163ed068b5a3c43483957"
    monkeypatch.setattr(discovery.sources, "pendle_active_markets", lambda chain: [
        {"address": "0x13285bcbc27f92b47b4edb99d744c07b48c977c0", "pt": "1-" + pt, "expiry": "2026-12-10T00:00:00.000Z"}])
    monkeypatch.setattr(discovery.sources, "morpho_markets_for_collateral", lambda c, chain, min_supply_usd=0: [
        {"marketId": PT_MARKET, "listed": True, "lltv": "915000000000000000", "collateralAsset": {"address": pt, "symbol": "PT-reUSD-10DEC2026"},
         "loanAsset": {"symbol": "USDC"}, "state": {"supplyAssetsUsd": 1.2e8}}])


def test_market_lookup_identifies_a_supported_market(monkeypatch):
    _stub_markets(monkeypatch)
    r = discovery.lookup("morpho:1:" + PT_MARKET)
    assert r["kind"] == "pt_market" and r["market_id"] == PT_MARKET and r["pt_symbol"] == "PT-reUSD-10DEC2026"
    assert r["loan_symbol"] == "USDC" and r["lltv"] == pytest.approx(0.915)


def test_market_lookup_rejects_a_market_outside_the_supported_set(monkeypatch):
    _stub_markets(monkeypatch)
    with pytest.raises(discovery.UnsupportedMarket):
        discovery.lookup("morpho:1:0x" + "ab" * 32)


def test_vault_lookup_endpoint_validates_the_address_before_any_read(monkeypatch):
    import api.vault as av
    monkeypatch.setattr(vault_reader, "lookup", lambda a: pytest.fail("no read for an invalid address"))
    status, body = av.respond("/api/vault?lookup=1&address=0x123")
    assert status == 400 and body["error"]["code"] == "invalid_input"


def test_vault_lookup_endpoint_returns_identification_only(monkeypatch):
    import api.vault as av
    monkeypatch.setattr(vault_reader.sources, "eth_block", lambda tag: {"number": 1, "timestamp": 0})
    monkeypatch.setattr(vault_reader, "detect", lambda a, b: {"version": "v2", "factory": "0xA1D9", "factory_name": "Morpho VaultV2Factory"})
    monkeypatch.setattr(vault_reader, "_one", lambda to, sig, block, args="": int("5f7827fdeb7c20b443265fc2f40845b715385ff2", 16))
    monkeypatch.setattr(vault_reader, "_string", lambda to, sig, block: ("EURCV" if to.lower().startswith("0x5f78") else {"name()": "Belem RWA EURCV", "symbol()": "rwaEURCV"}[sig]))
    status, body = av.respond("/api/vault?lookup=1&address=0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec")
    assert status == 200 and body["kind"] == "vault" and body["lookup"] is True
    assert body["name"] == "Belem RWA EURCV" and body["asset_symbol"] == "EURCV" and body["version"] == "v2"
    assert "decision" not in body and "risk" not in body


@pytest.mark.skipif(not LIVE, reason="set DEFIRISK_LIVE_TESTS=1 for mainnet reads")
def test_live_lookups():
    import api.vault as av
    status, body = av.respond("/api/vault?lookup=1&address=0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec")
    assert status == 200 and body["version"] == "v2" and body["asset_symbol"] == "EURCV"
    assert discovery.lookup("morpho:1:" + PT_MARKET)["pt_symbol"].startswith("PT-")
    status, body = av.respond("/api/vault?lookup=1&address=0x8f3cf7ad23cd3cadbd9735aff958023239c6a063")
    assert status in (404, 422)
