"""Compliance tests for the Belem challenge requirements (offline, deterministic; live checks gated by env)."""
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parents[1] / "api"))

import pytest

from defirisk import decision, priors, sources
from defirisk.decision import decide, exit_cost_for, quote_exit
from defirisk.discovery import MOCK
from defirisk.models import DepGraph
from defirisk.propagation import best_paths, simulate
from defirisk.scenarios import SCENARIOS, apply, shock

LIVE = os.getenv("DEFIRISK_LIVE_TESTS") == "1"


def mock_graph(value=1_000_000):
    g = DepGraph.load(str(MOCK))
    g.position.value_usd = value
    return g


# ---------- M05: exit cost from an executable quote, with real decimals --------------------------------------
@pytest.fixture
def fake_quote(monkeypatch):
    calls = {}

    def pendle_quote(token_in, amount_in_raw, token_out, chain_id=1):
        calls["raw"] = amount_in_raw
        # 1% below mid, in 6-decimals USDC
        out_usdc = amount_in_raw / 1e6 * 0.98 * 0.99
        return {"amount_out_raw": int(out_usdc * 1e6), "price_impact": -0.01, "fee_usd": 100.0, "gas_used": 350_000,
                "aggregator": "NONE", "method": "swapExactPtForToken"}

    monkeypatch.setattr(sources, "pendle_quote", pendle_quote)
    monkeypatch.setattr(sources, "llama_prices", lambda coins: {c: ({"price": 1.0, "decimals": 6} if "0xusdc" in c
                                                                    else {"price": 2000.0}) for c in coins})
    monkeypatch.setattr(sources, "eth_gas_price_wei", lambda: 10 * 10**9)
    return calls


ROUTE = {"pt": "0xpt", "pt_decimals": 6, "pt_price_usd": 0.98, "out": "0xusdc", "out_symbol": "USDC", "chain_id": 1}


def test_quote_exit_uses_token_decimals_and_counts_gas(fake_quote):
    q = quote_exit(ROUTE, 1_000_000)
    assert fake_quote["raw"] == int(1_000_000 / 0.98 * 1e6)  # 6 decimals, not 18
    assert q["method"] == "pendle_sdk_quote"
    assert q["slippage_and_fees_usd"] == pytest.approx(10_000, rel=1e-3)  # 1% below mid
    gas = (350_000 + decision.MORPHO_WITHDRAW_GAS) * 10e9 / 1e18 * 2000
    assert q["gas_usd"] == pytest.approx(gas)
    assert q["usd"] == pytest.approx(10_000 + gas, rel=1e-3)


def test_exit_cost_reuses_quote_and_stress_raises_it(fake_quote):
    g = mock_graph()
    g.position.meta["exit_route"] = ROUTE
    base = exit_cost_for(g)
    stressed = exit_cost_for(g, None, 0.5)
    assert base["method"] == "pendle_sdk_quote"
    assert stressed["usd"] > base["usd"]
    assert stressed["slippage_and_fees_usd"] == pytest.approx(2 * base["slippage_and_fees_usd"])
    assert "STRESSED" in stressed["basis"]


def test_exit_cost_fallback_is_flagged_as_approximation():
    g = mock_graph()
    ex = exit_cost_for(g)
    assert ex["method"] == "approximation_constant_product"
    assert ex["basis"].startswith("APPROXIMATION")


def test_exit_cost_grows_with_size():
    costs = [exit_cost_for(mock_graph(v))["pct"] for v in (1e5, 1e6, 1e7)]
    assert costs == sorted(costs)


# ---------- M06: decision rule ---------------------------------------------------------------------------------
def test_verdict_flips_with_exit_cost():
    g = mock_graph()
    sim = simulate(g)
    assert decide(g, sim, sim.expected_loss_usd * 0.5).verdict == "EXIT"
    d = decide(g, sim, sim.expected_loss_usd * 2)
    assert d.verdict == "STAY"
    assert d.breakeven_risk_multiplier == pytest.approx(2.0)
    assert "STAY" in d.explanation and "exit cost" in d.explanation
    assert len(d.top_drivers) == 3


def test_expected_loss_exact_matches_monte_carlo():
    g = mock_graph()
    for n in g.nodes:  # raise probabilities so 20k draws are precise enough
        n.p_fail = min(1.0, n.p_fail * 20)
    s = simulate(g, n_sims=200_000)
    assert s.expected_loss_usd == pytest.approx(s.mc_mean_usd, rel=0.03)


# ---------- M03/M04: shocks propagate through the graph ----------------------------------------------------------
def test_shock_any_node_direct_vs_indirect_and_monotone():
    g = mock_graph()
    paths = best_paths(g)
    for nid, (t, path) in paths.items():
        losses = [simulate(apply(g, shock(g, nid, s))).expected_loss_usd for s in (0.1, 0.5, 1.0)]
        assert losses == sorted(losses), nid
        iso = deepcopy(g)  # only the shocked node can fail -> exact closed form
        for n in iso.nodes:
            n.p_fail = 0.0
        exact = simulate(apply(iso, shock(iso, nid, 1.0))).expected_loss_usd
        assert exact == pytest.approx(g.position.value_usd * t, rel=1e-9)  # loss = value x severity x best path
    hops = {nid: len(p) - 1 for nid, (_, p) in paths.items()}
    assert min(hops.values()) == 1 and max(hops.values()) >= 2  # direct and indirect dependencies exist


def test_shock_rejects_unknown_node_and_bad_severity():
    g = mock_graph()
    with pytest.raises(ValueError):
        shock(g, "nope")
    with pytest.raises(ValueError):
        shock(g, next(n.id for n in g.nodes if n.id != g.position.id), 1.5)


def test_liquidity_scenario_stresses_exit():
    assert next(s for s in SCENARIOS if s.name == "Liquidity crisis").exit_liquidity_factor < 1


# ---------- priors calibrated on data, cohort-consistent -------------------------------------------------------
def test_base_rate_counts_only_cohort_incidents():
    now = time.time()
    protocols = [{"id": str(i), "tvl": 2e7, "category": "Lending"} for i in range(100)] + \
                [{"id": str(100 + i), "tvl": 2e6, "category": "Dexs"} for i in range(900)]
    hacks = [{"date": now - 86400, "amount": 5e6, "defillamaId": "3"},       # in cohort
             {"date": now - 86400, "amount": 5e6, "defillamaId": "500"},     # small protocol
             {"date": now - 86400, "amount": 5e6, "defillamaId": None}]      # unlisted
    r = priors.base_rates(hacks, protocols)
    assert r["incidents_in_cohort"] == 1
    assert r["annual_per_protocol"] == pytest.approx(1 / priors.LOOKBACK_YEARS / 100)
    assert r["annual_per_protocol_upper"] == pytest.approx(max(3 / priors.LOOKBACK_YEARS / 1000, r["annual_per_protocol"]))


def test_stablecoin_depeg_from_price_history():
    day = 86400
    prices = [1.0] * 800
    prices[100:103] = [0.97, 0.90, 0.95]   # one episode, min 0.90
    prices[500] = 0.99                      # not a depeg (threshold 2%)
    hist = [{"date": i * day, "prices": {"x": p}} for i, p in enumerate(prices)]
    d = priors.stablecoin_depeg("x", hist)
    assert d["episodes"] == 1 and d["severity"] == pytest.approx(0.10)
    p, lgf, why = priors.p_stablecoin(d, 30, "X")
    assert 0 < p < 1 and lgf == pytest.approx(0.10) and "DefiLlama" in why


# ---------- M07/M08: provenance is never misrepresented --------------------------------------------------------
def test_api_labels_mock_and_fallback(monkeypatch):
    import analyze
    from defirisk import api_payload

    assert analyze._payload("mock")["source"] == "mock"
    real = api_payload.build_payload

    def broken(ref, use_mock, **kw):
        if not use_mock:
            raise RuntimeError("pendle down")
        return real(ref, use_mock, **kw)

    monkeypatch.setattr(analyze, "build_payload", broken)
    p = analyze._payload("auto")
    assert p["source"] == "mock-fallback" and "pendle down" in p["discovery_error"]


def test_payload_contract():
    from defirisk.api_payload import build_payload
    p = build_payload("mock", True, value_usd=2_000_000, shock_node="oracle", severity=0.5)
    assert p["source"] == "mock" and p["position"]["value_usd"] == 2_000_000
    assert all(s["loss_type"] == "conditional_on_shock" for s in p["scenarios"])
    assert p["custom_shock"]["severity"] == 0.5 and p["custom_shock"]["verdict"] in ("STAY", "EXIT")
    assert p["stress_table"] and {"hops", "direct", "conditional_loss_usd", "path"} <= p["stress_table"][0].keys()
    assert p["exit"]["method"] and p["decision"]["rule"]
    assert p["assumptions"] and p["sensitivity"]["rows"]
    json.dumps(p)  # serialisable


def test_bad_shock_node_is_reported_not_fatal():
    from defirisk.api_payload import build_payload
    p = build_payload("mock", True, shock_node="nope")
    assert "error" in p["custom_shock"]


# ---------- M08: reproducible replay of real data from cache ---------------------------------------------------
def test_offline_replay_is_reproducible(monkeypatch):
    from defirisk import http
    if not any(http.CACHE_DIR.glob("*.json")):
        pytest.skip("no cached real data (run the live pipeline once)")
    from defirisk.api_payload import build_payload
    monkeypatch.setenv("DEFIRISK_OFFLINE", "1")
    monkeypatch.setattr(http, "now", lambda: 1.9e9)  # freshness ages depend on the clock: freeze it
    try:
        a = build_payload("auto", False)
    except RuntimeError as e:
        pytest.skip(f"cache incomplete: {e}")
    b = build_payload("auto", False)
    assert a["source"] == "cache" and a["position"]["meta"]["real"] is True
    assert a["decision"] == b["decision"]
    assert a["decision"]["verdict"] == "REVIEW"  # a cache replay is never presented as a live, firm signal
    assert a["data_as_of"]


# ---------- live (network) checks: DEFIRISK_LIVE_TESTS=1 ------------------------------------------------------
@pytest.mark.skipif(not LIVE, reason="set DEFIRISK_LIVE_TESTS=1 to hit the real APIs")
def test_live_discovery_matches_chain():
    from defirisk.discovery import discover_real
    g = discover_real("auto", 1_000_000, 30)
    m = g.position.meta
    nodes = {n.id: n for n in g.nodes}
    assert m["real"] and m["block_number"] and m["exit_quote"]["method"] == "pendle_sdk_quote"
    # Morpho Blue idToMarketParams(id): loan, collateral, oracle, irm, lltv
    r = sources.eth_call("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", "0x2c3c9157" + m["morpho_market"][2:])
    w = ["0x" + r[2 + i * 64 + 24: 2 + (i + 1) * 64] for i in range(3)]
    assert w[1] == m["exit_route"]["pt"].lower()           # collateral is the PT
    assert w[0] == m["exit_route"]["out"].lower()          # loan asset
    assert w[2] == nodes["oracle"].meta["address"].lower()  # oracle
    # Pendle market readTokens() -> (SY, PT, YT)
    t = sources.eth_call(m["pendle_market"], "0x2c8ce6bc")
    assert "0x" + t[2 + 64 + 24: 2 + 128] == m["exit_route"]["pt"].lower()
    assert any(n.meta.get("hidden") for n in g.nodes)
    assert 0 < m["exit_quote"]["pct"] < 0.05
