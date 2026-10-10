"""Token lineage, look-through exposure and peg checks (offline: every network call is faked)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest

from defirisk import discovery, exposure, lineage, peg, sources

PT, SY, SUSDE, USDE, USDC, REUSD = "0xpt", "0xsy", "0xs0de", "0x05de", "0xa0b8", "0x7e05"
WORD = lambda a: "0x" + a[2:].rjust(64, "0")  # noqa: E731

REGISTRY = {
    USDE: {"symbol": "USDe", "type": "stablecoin_synthetic", "issuer": "Ethena", "source_url": "https://x/ethena",
           "as_of": "2026-10-10", "confidence": "low",
           "components": [{"to": "base:HEDGED_DELTA_NEUTRAL", "weight": None}, {"to": USDC, "weight": None}]},
    USDC: {"symbol": "USDC", "type": "stablecoin_fiat", "source_url": "https://x/circle", "as_of": "2026-10-10",
           "confidence": "medium", "components": [{"to": "base:USD_FIAT", "weight": 1.0}]},
}


def pend(und, und_sym, acc=None, acc_sym=None):
    return {"pt": {"address": PT, "symbol": f"PT-{und_sym}"}, "sy": {"address": SY, "symbol": f"SY-{und_sym}"},
            "underlyingAsset": {"address": und, "symbol": und_sym},
            "accountingAsset": {"address": acc or und, "symbol": acc_sym or und_sym}}


@pytest.fixture
def chain(monkeypatch):
    """sUSDe is an ERC-4626 vault on USDe (1 share = 1.2 USDe); everything else reverts."""
    def eth_call(to, data):
        if to == SUSDE and data == "0x38d52e0f":
            return WORD("0x" + USDE[2:].rjust(40, "0"))
        if data == "0x313ce567":
            return WORD(hex(18))
        if to == SUSDE and data.startswith("0x07a2d13a"):
            return WORD(hex(12 * 10 ** 17))
        return None
    monkeypatch.setattr(sources, "eth_call", eth_call)


def _usde_addr():
    return "0x" + USDE[2:].rjust(40, "0")


def test_lineage_follows_4626_and_registry(chain):
    reg = {**REGISTRY, _usde_addr(): REGISTRY[USDE]}
    lin = lineage.trace_pendle(pend(SUSDE, "sUSDe"), reg)
    syms = [(lin.tokens[e["parent"]]["symbol"], lin.tokens[e["child"]]["symbol"], e["weight"], e["confidence"]) for e in lin.edges]
    assert ("PT-sUSDe", "SY-sUSDe", 1.0, "high") in syms
    assert ("sUSDe", "USDe", 1.0, "high") in syms                     # read on-chain via asset()
    assert ("USDe", "USDC", None, "low") in syms                      # registry, weight unknown -> None, not guessed
    assert ("USDC", "US dollars (bank/T-bills)", 1.0, "medium") in syms
    e = next(e for e in lin.edges if e["child"] == _usde_addr())
    assert e["rate"] == pytest.approx(1.2) and e["source"].startswith("on-chain")
    assert all(e["as_of"] and e["source"] for e in lin.edges)


def test_lookthrough_unknown_share_and_reasons(chain):
    reg = {**REGISTRY, _usde_addr(): REGISTRY[USDE]}
    lt = exposure.lookthrough(lineage.trace_pendle(pend(SUSDE, "sUSDe"), reg))
    cov = lt["coverage"]
    assert cov["unknown_pct"] == pytest.approx(1.0) and cov["traced_pct"] == 0 and cov["severity"] == "RED"
    assert "USDe" in cov["summary"] and "not published" in cov["summary"]
    usdc = next(r for r in lt["tokens"] if r["symbol"] == "USDC")
    assert usdc["pct"] is None and usdc["routes"]                     # reached, size unknown
    assert next(r for r in lt["tokens"] if r["symbol"] == "USDe")["pct"] == pytest.approx(1.0)


def test_lookthrough_multiplies_along_paths_and_adds_across(monkeypatch):
    monkeypatch.setattr(sources, "eth_call", lambda to, data: None)
    reg = {"0xa": {"symbol": "A", "type": "stablecoin_synthetic", "source_url": "u", "as_of": "d", "confidence": "medium",
                   "components": [{"to": "0xb", "weight": 0.5}, {"to": USDC, "weight": 0.3}]},
           "0xb": {"symbol": "B", "type": "stablecoin_synthetic", "source_url": "u", "as_of": "d", "confidence": "medium",
                   "components": [{"to": USDC, "weight": 0.6}, {"to": "base:ETH", "weight": 0.4}]},
           USDC: REGISTRY[USDC]}
    lt = exposure.lookthrough(lineage.trace_pendle(pend("0xa", "A"), reg))
    tok = {r["symbol"]: r["pct"] for r in lt["tokens"]}
    assert tok["USDC"] == pytest.approx(0.3 + 0.5 * 0.6)              # two paths add up
    base = {r["id"]: r["pct"] for r in lt["base_assets"]}
    assert base["base:ETH"] == pytest.approx(0.2) and base["base:USD_FIAT"] == pytest.approx(0.6)
    assert base["base:UNKNOWN"] == pytest.approx(0.2)                 # A: 20% of backing undescribed
    assert lt["coverage"]["traced_pct"] == pytest.approx(0.8) and lt["coverage"]["severity"] == "ORANGE"


def test_cycle_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr(sources, "eth_call", lambda to, data: None)
    reg = {"0xa": {"symbol": "A", "source_url": "u", "as_of": "d", "confidence": "low", "components": [{"to": "0xb", "weight": 0.5}]},
           "0xb": {"symbol": "B", "source_url": "u", "as_of": "d", "confidence": "low", "components": [{"to": "0xa", "weight": 0.4}]}}
    lin = lineage.trace_pendle(pend("0xa", "A"), reg)
    assert lin.cycles and lin.cycles[0]["path"] == ["A", "B", "A"]
    assert lin.cycles[0]["gain"] == pytest.approx(0.2) and lin.cycles[0]["amplification"] == pytest.approx(1.25)
    exposure.lookthrough(lin)  # terminates


def test_accounting_asset_hint_has_unknown_weight(monkeypatch):
    monkeypatch.setattr(sources, "eth_call", lambda to, data: None)
    lin = lineage.trace_pendle(pend(REUSD, "reUSD", USDC, "USDC"), {USDC: REGISTRY[USDC]})
    e = next(e for e in lin.edges if e["parent"] == REUSD)
    assert e["child"] == USDC and e["weight"] is None and e["confidence"] == "low"


def test_registry_file_is_sourced_and_never_invents_weights():
    reg = lineage.load_registry()
    assert reg
    for addr, t in reg.items():
        assert addr.startswith("0x") and len(addr) == 42 and addr == addr.lower()
        assert t["source_url"].startswith("https://") and t["as_of"] and t["confidence"] in ("high", "medium", "low")
        for c in t["components"]:
            assert c["weight"] is None or 0 < c["weight"] <= 1
        known = [c["weight"] for c in t["components"] if c["weight"] is not None]
        assert sum(known) <= 1 + 1e-9


# ---------- peg / basis --------------------------------------------------------------------------------------
def test_peg_stats_max_and_latest():
    s = peg.peg_stats([1.0] * 25 + [0.97, 0.995], 1.0, 90)
    assert not s["insufficient_data"]
    assert s["max_dev_pct"] == pytest.approx(-3.0) and s["latest_dev_pct"] == pytest.approx(-0.5)


def test_peg_insufficient_data_is_explicit():
    for prices in (None, [], [1.0] * 5):
        s = peg.peg_stats(prices, 1.0, 90)
        assert s["insufficient_data"] and s["max_dev_pct"] is None and s["reason"]


def test_peg_annotate_uses_rate_for_wrappers(chain, monkeypatch):
    u = _usde_addr()
    reg = {**REGISTRY, u: REGISTRY[USDE]}
    lin = lineage.trace_pendle(pend(SUSDE, "sUSDe"), reg)
    monkeypatch.setattr(peg, "price_history", lambda addrs, window_days=90: {u: [1.0] * 30, SUSDE: [1.2] * 29 + [1.188]})
    out = peg.annotate(lin)
    assert out[u]["max_dev_pct"] == pytest.approx(0) and not out[u]["insufficient_data"]
    assert out[SUSDE]["kind"] == "basis" and out[SUSDE]["latest_dev_pct"] == pytest.approx(-1.0)
    assert out[USDC]["insufficient_data"]                             # no prices returned -> said so


def test_price_history_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(peg, "get_json", boom)
    assert peg.price_history(["0xa"]) == {}


# ---------- portfolio: shared exposure + issuer concentration fix ---------------------------------------------
def _market(mid, pt_addr, pt_sym, loan, supply):
    return {"marketId": mid, "collateralAsset": {"address": pt_addr, "symbol": pt_sym}, "loanAsset": {"symbol": loan},
            "state": {"supplyAssetsUsd": supply}, "oracle": None}


def test_shared_exposure_routes_across_markets(monkeypatch):
    monkeypatch.setattr(sources, "eth_call", lambda to, data: None)
    reg = {"0xa": {"symbol": "A", "source_url": "u", "as_of": "d", "confidence": "medium", "components": [{"to": USDC, "weight": 1.0}]},
           "0xb": {"symbol": "B", "source_url": "u", "as_of": "d", "confidence": "medium", "components": [{"to": USDC, "weight": 0.5}]},
           USDC: REGISTRY[USDC]}
    mk = lambda und, sym, supply, mine=False: {"label": sym, "supply_usd": supply, "is_mine": mine,  # noqa: E731
                                              "lookthrough": exposure.lookthrough(lineage.trace_pendle(pend(und, sym), reg))}
    sh = exposure.shared_exposure([mk("0xa", "A", 60.0, True), mk("0xb", "B", 40.0)])
    usdc = next(r for r in sh["rows"] if r["symbol"] == "USDC")
    assert usdc["markets"] == 2 and usdc["share_pct"] == pytest.approx(80.0) and usdc["in_position"]
    assert len(usdc["routes"]) == 2 and "A" in usdc["routes"][0]["route"]
    assert not any(r["type"] in ("pendle_pt", "pendle_sy") for r in sh["rows"])
    assert "2 of 2" in usdc["sentence"]


def test_issuer_concentration_uses_pendle_protocol(monkeypatch):
    monkeypatch.setattr(sources, "read_feed", lambda f: None)
    by_pt = {"0xp1": {"address": "0xm1", "name": "reUSD"}, "0xp2": {"address": "0xm2", "name": "sUSDe"}}
    ms = [_market("a", "0xp1", "PT-reUSD-1", "USDC", 60), _market("b", "0xp1", "PT-reUSD-1", "USDT", 20),
          _market("c", "0xp2", "PT-sUSDe-1", "USDC", 20)]
    details = {"a": {"protocol": "re.xyz"}, "b": {"protocol": "re.xyz"}, "c": {"protocol": "Ethena"}}
    rows = discovery._concentration(ms, by_pt, ms[0], {"provider": "unknown"}, details)
    iss = next(r for r in rows if r["node"] == "issuer")
    assert iss["label"] == "PT issuer / protocol: re.xyz" and iss["markets"] == 2 and iss["share_pct"] == pytest.approx(80)
    rows = discovery._concentration(ms, by_pt, ms[2], {"provider": "unknown"}, {})  # no detail -> market name, never None
    iss = next(r for r in rows if r["node"] == "issuer")
    assert "None" not in iss["label"] and iss["markets"] == 1 and iss["share_pct"] == pytest.approx(20)
