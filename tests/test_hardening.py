"""Phase 0.5 hardening tests (R01-R20). Offline and deterministic unless DEFIRISK_LIVE_TESTS=1."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pytest

from defirisk import decision, http, sources
from defirisk.decision import exit_cost_for, quote_exit
from defirisk.keccak import keccak256, selector, topic

from defirisk.discovery import MOCK
from defirisk.models import DepGraph

LIVE = os.getenv("DEFIRISK_LIVE_TESTS") == "1"

def mock_graph(value=1_000_000):
    g = DepGraph.load(str(MOCK))
    g.position.value_usd = value
    return g


ROUTE = {"pt": "0xpt", "pt_decimals": 6, "pt_price_usd": 0.98, "out": "0xusdc", "out_symbol": "USDC", "chain_id": 1}


# ---------- keccak (selectors / storage slots / event topics) --------------------------------------------------
def test_keccak_known_vectors():
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert topic("Transfer(address,address,uint256)") == "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    assert selector("balanceOf(address)") == "0x70a08231"
    assert selector("idToMarketParams(bytes32)") == "0x2c3c9157"
    assert keccak256(b"a" * 200) != keccak256(b"a" * 201)  # multi-block absorb


# ---------- H03 exit quote ----------------------------------------------------------------------------------------
@pytest.fixture
def market(monkeypatch):
    """Fake SDK + prices. state['out_ratio'] = proceeds / value at mid; state['sim'] = simulate_swap result."""
    state = {"out_ratio": 0.99, "out_price": 1.0, "fetched_at": None, "sim": None, "tx": None, "raw": []}

    def pendle_quote(token_in, amount_in_raw, token_out, chain_id=1):
        state["raw"].append(amount_in_raw)
        size = amount_in_raw / 1e6 * 0.98
        ratio = state["out_ratio"] - 0.002 * size / 1e6  # deeper sizes -> worse price
        return {"amount_out_raw": int(size * ratio * 1e6), "price_impact": -0.001, "fee_usd": 100.0, "gas_used": 400_000,
                "aggregator": "NONE", "method": "swapExactPtForToken", "tx": state["tx"],
                "fetched_at": state["fetched_at"], "from_cache": False}

    monkeypatch.setattr(sources, "pendle_quote", pendle_quote)
    monkeypatch.setattr(sources, "llama_prices", lambda coins: {c: ({"price": state["out_price"], "decimals": 6} if "0xusdc" in c
                                                                    else {"price": 2000.0}) for c in coins})
    monkeypatch.setattr(sources, "eth_gas_price_wei", lambda: 10 * 10**9)
    monkeypatch.setattr(sources, "eth_block", lambda n="latest": {"number": 123, "timestamp": 0})
    monkeypatch.setattr(sources, "simulate_swap", lambda tx, t, raw, block=None: dict(state["sim"]))
    return state


def test_R02_cost_by_size_monotone_and_decomposition_adds_up(market):
    costs = []
    for v in (10_000, 1_000_000, 5_000_000):
        q = quote_exit(ROUTE, v, simulate=False)
        d = q["decomposition"]
        assert q["pt_in_raw"] == int(v / 0.98 * 1e6)  # PT has 6 decimals
        assert d["value_at_mid_usd"] - d["proceeds_usd"] == pytest.approx(d["execution_shortfall_usd"])
        parts = d["of_which_pendle_fee_usd"] + d["of_which_out_token_off_peg_usd"] + d["of_which_price_impact_and_route_usd"]
        assert parts == pytest.approx(d["execution_shortfall_usd"])  # components explain the gap, they are not added on top
        assert q["usd"] == pytest.approx(d["execution_shortfall_usd"] + q["gas_usd"])  # fee counted exactly once
        costs.append(q["pct"])
    assert costs[1] < costs[2]


def test_R03_non_dollar_exit_token_is_priced(market):
    market["out_price"] = 0.99
    q = quote_exit(ROUTE, 1_000_000, simulate=False)
    assert q["decomposition"]["of_which_out_token_off_peg_usd"] == pytest.approx(q["out_amount"] * 0.01)
    market["out_price"] = 1.0
    assert quote_exit(ROUTE, 1_000_000, simulate=False)["usd"] < q["usd"]


def test_R03_quote_status_and_ttl(market):
    market["tx"] = {"to": "0xrouter", "data": "0x"}
    market["sim"] = {"status": "simulated", "amount_out_raw": None, "gas_estimate": 900_000}
    q0 = quote_exit(ROUTE, 1_000_000, simulate=False)
    assert q0["quote_status"] == "indicative" and q0["quote_ttl_s"] == decision.QUOTE_TTL_S
    market["sim"]["amount_out_raw"] = q0["out_amount_raw"]
    q = quote_exit(ROUTE, 1_000_000, simulate=True)
    assert q["quote_status"] == "simulated" and q["quote_block"] == 123
    assert q["gas_units"] == 900_000 + decision.MORPHO_WITHDRAW_GAS  # eth_estimateGas preferred over SDK gas
    market["sim"]["amount_out_raw"] = int(q0["out_amount_raw"] * 0.97)  # chain disagrees -> keep the worse
    q = quote_exit(ROUTE, 1_000_000, simulate=True)
    assert q["quote_status"] == "simulation_mismatch" and q["out_amount_raw"] == market["sim"]["amount_out_raw"]
    market["fetched_at"] = http.now() - 10 * decision.QUOTE_TTL_S
    assert quote_exit(ROUTE, 1_000_000, simulate=False)["quote_status"] == "stale"


def test_R04_missing_route_falls_back_and_says_so(monkeypatch):

    def no_route(*a, **k):
        raise RuntimeError("Pendle SDK returned no route")
    monkeypatch.setattr(sources, "pendle_quote", no_route)
    g = mock_graph()
    g.position.meta["exit_route"] = ROUTE
    ex = exit_cost_for(g)
    assert ex["method"] == "approximation_constant_product" and ex["basis"].startswith("APPROXIMATION")
    assert "no route" in g.position.meta["exit_quote_errors"][0]


def test_R04_simulation_unavailable_is_indicative_not_simulated(market):
    market["tx"] = {"to": "0xrouter", "data": "0x"}
    market["sim"] = {"status": "unavailable", "reason": "no override support"}
    q = quote_exit(ROUTE, 1_000_000, simulate=True)
    assert q["quote_status"] == "indicative" and q["simulation"]["status"] == "unavailable"


@pytest.mark.skipif(not LIVE, reason="set DEFIRISK_LIVE_TESTS=1 to hit the real APIs")
def test_R02_live_sdk_quote_reexecuted_onchain():
    from defirisk.discovery import discover_real
    g = discover_real("auto", 1_000_000, 30)
    route = g.position.meta["exit_route"]
    for v in (10_000, 1_000_000):
        q = quote_exit(route, v, simulate=True)
        assert q["quote_status"] == "simulated", q["simulation"]
        assert q["simulation"]["deviation_vs_sdk"] <= decision.SIM_TOLERANCE
        assert 0 < q["pct"] < 0.05


# ======================= H02 liquidation (R05-R09) ===============================================================
from defirisk import freshness, leverage, morpho, uncertainty  # noqa: E402
from defirisk.models import Edge, Node, Position  # noqa: E402
from defirisk.propagation import simulate  # noqa: E402

E36 = 10**36


def _state(collateral=12_392_000, debt=10_557_000, price=0.98172, lltv=0.915):
    """6-decimal loan and collateral (as the live PT/USDC market). Shares = assets x 1e6 (virtual shares)."""
    tba = 50_000_000 * 10**6
    tbs = tba * 10**6
    return morpho.compute_state(collateral * 10**6, debt * 10**6 * 10**6, tba, tbs, int(price * E36), int(lltv * 1e18), 6, 6)


def test_r05_debt_free_is_not_applicable_not_zero():
    from defirisk.api_payload import build_payload
    liq = build_payload("mock", True)["liquidation"]
    assert liq["mode"] == "unlevered_exposure" and liq["liquidation"] == "NOT_APPLICABLE"
    assert liq["debt_assets"] is None  # unknown / not applicable, never a fake 0
    assert leverage.parse_borrower(None) is None and leverage.parse_borrower("auto") == "auto"
    for bad in ("0x123", "abc", "0x" + "g" * 40):
        with pytest.raises(ValueError):
            leverage.parse_borrower(bad)


def test_r07_shares_rounding_oracle_scale_and_threshold():
    assert morpho.to_assets_up(1, 0, 0) == 1 and morpho.to_assets_down(1, 0, 0) == 0  # virtual shares, rounding sides
    s = _state()
    assert s["debt_assets"] == pytest.approx(10_557_000, abs=1e-6)
    assert s["oracle_price"] == pytest.approx(0.98172)
    hf = 12_392_000 * 0.98172 * 0.915 / 10_557_000
    assert s["health_factor"] == pytest.approx(hf, rel=1e-9)
    dist = s["distance_to_liquidation_pct"]
    assert dist == pytest.approx(1 - 1 / hf, rel=1e-9)
    assert not morpho.liquidation_outcome(s, dist - 1e-6)["liquidated"]
    assert morpho.liquidation_outcome(s, dist + 1e-6)["liquidated"]
    assert s["liquidation_incentive_factor"] == pytest.approx(min(1.15, 1 / (1 - 0.3 * (1 - 0.915))), rel=1e-12)


def test_r07_seized_formula_matches_real_liquidation_numbers():
    """Tx 0x906a5315...e0d (block 25829913): repaid 791807542116, seized 855192274744 (receipt). The oracle price at that
    block is not stored offline, so check the formula's inverse: implied price is the one-ulp-consistent value."""
    repaid, seized = 791807542116, 855192274744
    lif = morpho.liquidation_incentive_factor(int(0.915e18))
    implied = morpho.w_mul_down(repaid, lif) * E36 // seized
    assert morpho.mul_div_down(morpho.w_mul_down(repaid, lif), E36, implied) in (seized, seized + 1)
    assert 0.94 < implied / E36 < 0.96  # PT priced ~0.95 USDC at the time, consistent with the live replay


def test_r08_stress_threshold_monotone_and_terminal():
    s = _state()
    losses = [morpho.liquidation_outcome(s, d)["borrower_loss_usd"] for d in (0, 0.02, 0.05, 0.06, 0.1, 0.2, 0.5, 1.0)]
    assert losses[0] == 0 and all(a <= b + 1e-6 for a, b in zip(losses, losses[1:]))
    assert losses[-1] == pytest.approx(s["equity_usd_oracle"])  # non-recourse: never more than equity
    o = morpho.liquidation_outcome(s, 0.10)
    assert o["liquidated"] and o["of_which_liquidation_penalty_usd"] > 0 and o["lender_bad_debt_usd"] == 0
    drift = leverage._drift({**s, "borrow_rate_per_s": 2526709348}, 30)
    assert drift["debt_growth_factor"] > 1 and drift["health_factor_at_horizon_constant_price"] < s["health_factor"]


def test_r09_borrower_vs_lender_no_double_counting():
    s = _state()
    o = morpho.liquidation_outcome(s, 0.5)
    assert o["lender_bad_debt_usd"] > 0
    assert o["borrower_loss_usd"] == pytest.approx(s["equity_usd_oracle"])  # bad debt is the lenders', not added here
    assert o["borrower_loss_usd"] == pytest.approx(o["of_which_price_move_usd"] + o["of_which_liquidation_penalty_usd"])


@pytest.mark.skipif(not LIVE, reason="set DEFIRISK_LIVE_TESTS=1")
def test_r06_live_borrower_and_historical_liquidation():
    mid = "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64"
    top = morpho.top_borrowers(mid, 1)[0]
    s = morpho.borrower_state(mid, top["address"])
    assert s["mode"] == "borrower_position" and s["as_of_block"] > 0
    assert s["health_factor"] == pytest.approx(float(top["health_factor_api"]), rel=1e-3)
    v = morpho.verify_liquidation("0x906a5315a31c4b3e2956524a819069367d625ee532871ddcef98ee6edd729e0d")
    assert v["seized_assets"] == 855192274744 and v["relative_error"] < 1e-9


# ======================= H01 uncertainty, carry, robust verdict (R10-R15) ========================================
def _diamond(p=0.1, lgf=0.5):
    """pos -> A -> X and pos -> B -> X: X is shared; best path A (0.9) must be used once, not both."""
    pos = Position("pos", "P", "ethereum", 1_000_000, 30, {"real": True})
    nodes = [Node("pos", "protocol", "P", 0, 0), Node("A", "amm", "A", 0, 0.5, {"source": "DefiLlama hacks x"}),
             Node("B", "lending", "B", 0, 0.5, {"source": "DefiLlama hacks x"}),
             Node("X", "yield_source", "X", p, lgf, {"source": "DefiLlama hacks x"})]
    edges = [Edge("pos", "A", 1.0), Edge("pos", "B", 1.0), Edge("A", "X", 0.9), Edge("B", "X", 0.5)]
    return DepGraph(pos, nodes, edges)


def test_r10_shared_node_counted_once():
    g = _diamond()
    lb = uncertainty.loss_band(g)
    assert lb["central_usd"] == pytest.approx(1_000_000 * 0.1 * 0.5 * 0.9)
    assert simulate(g).expected_loss_usd == pytest.approx(lb["central_usd"])


def test_r11_bands_bracket_central_and_dependence_bounds():
    g = mock_graph()
    lb = uncertainty.loss_band(g)
    lo_dep, hi_dep = lb["dependence_bounds_at_central_usd"]
    assert lb["low_usd"] <= lb["central_usd"] <= lb["high_usd"]
    assert lo_dep <= lb["central_usd"] <= hi_dep <= lb["high_usd"]
    assert "independence" in lb["formula"]


def test_r12_priors_consistent_and_classified():
    lo, hi = uncertainty._poisson_ci(1)
    assert lo == pytest.approx(0.0253, abs=1e-4) and hi == pytest.approx(5.5716, abs=1e-4)
    assert uncertainty._poisson_ci(0) == (0.0, pytest.approx(3.6889, abs=1e-4))
    assert uncertainty._horizon_from_annual(0.12, 365) == pytest.approx(0.12)
    assert uncertainty._horizon_from_annual(0.12, 30) == pytest.approx(1 - 0.88 ** (30 / 365))
    inv = uncertainty.inventory(mock_graph())
    for n in inv["nodes"]:
        pc = n["p_fail_horizon"]
        assert pc["class"] in uncertainty.CLASSES and 0 <= pc["low"] <= pc["central"] <= pc["high"] <= 1
        lg = n["loss_given_failure"]
        assert 0 <= lg["low"] <= lg["central"] <= lg["high"] <= 1


def test_r13_shock_monotone_and_terminals():
    from defirisk.scenarios import apply, shock
    g = mock_graph()
    node = next(n.id for n in g.nodes if n.id != g.position.id)
    losses = [simulate(apply(g, shock(g, node, s))).expected_loss_usd for s in (0, 0.25, 0.5, 1.0)]
    assert losses[0] <= losses[1] <= losses[2] <= losses[3] <= g.position.value_usd


def test_r13_correlated_scenario_dominates_its_parts():
    from defirisk.api_payload import build_payload
    sc = {s["name"]: s for s in build_payload("mock", True)["scenarios"]}
    joint = sc["Correlated: depeg + oracle + liquidity"]["conditional_loss_usd"]
    assert joint >= max(sc[k]["conditional_loss_usd"] for k in ("Underlying depeg", "Oracle failure", "Liquidity crisis"))


def _band(c, lo, hi):
    return {"central_usd": c, "low_usd": lo, "high_usd": hi}


def test_r14_robust_verdict_rules():
    known = {"status": "estimated"}
    assert uncertainty.robust_signal(_band(10, 8, 12), _band(3, 2, 4), known, [])["verdict"] == "EXIT"
    assert uncertainty.robust_signal(_band(2, 1, 3), _band(8, 6, 10), known, [])["verdict"] == "STAY"
    r = uncertainty.robust_signal(_band(5, 2, 9), _band(4, 3, 6), known, [])
    assert r["verdict"] == "REVIEW" and r["point_verdict"] == "EXIT" and "conditional" in r["lean"]
    r = uncertainty.robust_signal(_band(10, 8, 12), _band(3, 2, 4), known, ["stale exit_quote"])
    assert r["verdict"] == "REVIEW" and r["point_verdict"] == "EXIT"


def test_r15_carry_signed_and_unknown_degrades():
    g = mock_graph()
    amm = next(n for n in g.nodes if n.meta.get("role") == "amm" or n.layer == "amm")
    amm.meta.update(role="amm", implied_apy=0.10)
    c = uncertainty.carry(g, {"supply_apy": 0.04, "source": "test"})
    assert c["usd"] == pytest.approx(1_000_000 * 0.06 * 30 / 365)
    neg = uncertainty.carry(g, {"supply_apy": 0.15, "source": "test"})
    assert neg["usd"] < 0  # PT yields less than the alternative: exiting gains carry
    assert uncertainty.carry(g, None)["status"] == "unknown"
    r = uncertainty.robust_signal(_band(10, 8, 12), _band(3, 2, 4), {"status": "unknown"}, [])
    assert r["verdict"] == "EXIT" and r["confidence"] == "medium"
    ex = {"usd": 1000, "slippage_and_fees_usd": 990, "gas_usd": 10, "method": "pendle_sdk_quote", "quote_status": "simulated"}
    eb = uncertainty.exit_band(ex, c)
    assert eb["central_usd"] == pytest.approx(1000 + c["usd"]) and eb["low_usd"] <= eb["central_usd"] <= eb["high_usd"]


# ======================= H05 freshness (R17-R18) =================================================================
def _real_graph_with_quote(monkeypatch, t0=1_900_000_000.0):
    monkeypatch.setattr(http, "now", lambda: t0)
    g = mock_graph()
    g.position.meta.update(real=True, observed_at=t0, block_timestamp=int(t0) - 6, block_number=1)
    ex = {"usd": 1000.0, "slippage_and_fees_usd": 990.0, "gas_usd": 10.0, "method": "pendle_sdk_quote",
          "quote_status": "simulated", "quote_fetched_at": t0 - 5, "quote_block": 1}
    return g, ex


def test_r17_ttl_per_data_type_with_injected_clock(monkeypatch):
    g, ex = _real_graph_with_quote(monkeypatch)
    fr = freshness.evaluate(g, ex, {"cached": 0})
    assert fr["label"] == "fresh" and not fr["blockers"]
    monkeypatch.setattr(http, "now", lambda: 1_900_000_000.0 + 61)  # quote now 66 s old, chain state 67 s
    fr = freshness.evaluate(g, ex, {"cached": 0})
    assert [b for b in fr["blockers"] if "exit_quote" in b] and not [b for b in fr["blockers"] if "onchain" in b]
    monkeypatch.setattr(http, "now", lambda: 1_900_000_000.0 + 200)
    assert any("onchain_state" in b for b in freshness.evaluate(g, ex, {"cached": 0})["blockers"])
    assert freshness.evaluate(g, ex, {"cached": 3, "oldest_cache_ts": 1})["label"] == "replay"
    assert freshness.TTL_S["exit_quote"] < freshness.TTL_S["onchain_state"] < freshness.TTL_S["market_data"] < freshness.TTL_S["priors"]


def test_r17_stale_quote_forces_review_never_firm(monkeypatch):
    g, ex = _real_graph_with_quote(monkeypatch)
    sim = simulate(g)
    fresh = decision.decide_robust(g, sim, ex, {"cached": 0})
    monkeypatch.setattr(http, "now", lambda: 1_900_000_000.0 + 3600)
    stale = decision.decide_robust(g, sim, ex, {"cached": 0})
    assert stale.verdict == "REVIEW" and stale.point_verdict == fresh.point_verdict
    assert any("stale" in r for r in stale.reasons)


def test_r18_api_input_validation_and_no_secret_leak(monkeypatch):
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from api import analyze
    for q in ("value_usd=1", "value_usd=nan", "value_usd=1e12", "severity=2", "borrower=0xdead", "ref=<script>",
              "shock=a%20b"):
        with pytest.raises(ValueError):
            analyze._params("/api/analyze?" + q)
    ok = analyze._params("/api/analyze?ref=pendle:0x13285bcbc27f92b47b4edb99d744c07b48c977c0&borrower=auto&severity=0.3")
    assert ok["borrower"] == "auto" and ok["severity"] == 0.3
    monkeypatch.setenv("ETH_RPC_URL", "https://rpc.example/secret-key-123")
    import json as _json
    from defirisk.api_payload import build_payload
    assert "secret-key-123" not in _json.dumps(build_payload("mock", True))


# ======================= H04 historical replay without look-ahead (R16) ==========================================
REPLAY = Path(__file__).parents[1] / "data" / "fixtures" / "replay_h04.json"


def _replay():
    import json as _json
    if not REPLAY.exists():
        pytest.skip("run scripts/replay_h04.py once (network) to create the dated fixture")
    return _json.loads(REPLAY.read_text(encoding="utf-8"))


def test_r16_usdc_svb_replay_no_lookahead():
    from defirisk import priors
    r = _replay()["usdc_svb"]
    gid, cut, end = r["gecko_id"], r["cutoff"], r["horizon_end"]
    before = [{"date": t, "prices": {gid: p}} for t, p in r["series"] if t < cut]
    assert before and max(d["date"] for d in before) < cut  # the prior never sees the event
    dep = priors.stablecoin_depeg(gid, before)
    p30, lgf, why = priors.p_stablecoin(dep, 30, "USDC")
    assert dep["episodes"] == 0 and p30 > 0.01  # zero observed history -> non-zero floor, not p = 0
    lgf = lgf or priors.LGF["stablecoin"]
    after = [p for t, p in r["series"] if cut <= t < end]
    happened = min(after) < 0.98
    depth = 1 - min(after)
    assert happened and 0.03 < depth < 0.05  # 2023-03-12 daily close $0.961 (intraday low not in this daily dataset)
    lo, hi = uncertainty._poisson_ci(0)
    p_hi = uncertainty._horizon_from_annual(hi / dep["years"], 30)
    assert p30 < p_hi  # the event sits inside the stated band, at its pessimistic end
    # Brier score vs a naive frequentist p = 0 (0 events seen): the floored prior scores strictly better.
    assert (1 - p30) ** 2 < 1.0
    # severity: the default LGF (assumption) over-states this episode's depth -> conservative, documented
    assert lgf >= depth


def test_r16_liquidation_replay_predicted_from_previous_block():
    r = _replay()["liquidation"]
    pre = r["pre_state"]
    assert pre["healthy"] is False and pre["health_factor"] < 1  # read at block N-1: eligible before the tx
    assert r["predicted_seized_assets"] in (r["seized_assets"], r["seized_assets"] + 1)
    debt_pre_raw = pre["debt_assets"] * 1e6
    assert abs(r["repaid_assets"] - debt_pre_raw) / debt_pre_raw < 1e-4  # whole debt closed = model's worst case
