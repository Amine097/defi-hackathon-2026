"""Rules added after the review against the Belem brief (docs/FAULTLINE_BELEM_BRIEF_REVIEW.md, section 9):
role-aware losses (step 1), hold to maturity (2), calibrated loss-given-failure (3), real book (4), incident (5),
multi-feed + explicit chain support (6), no silent mock (7), signal -> Countermove policy (C2)."""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from defirisk import leverage, uncertainty  # noqa: E402
from defirisk.core import book as book_lib  # noqa: E402
from defirisk.core.maturity import maturity_options  # noqa: E402
from defirisk.core.models import DepGraph, Edge, Node, Position  # noqa: E402
from defirisk.core.propagation import best_paths, blocked_channels, simulate  # noqa: E402
from defirisk.data import http, priors  # noqa: E402

EXPIRY_TS = 1_800_000_000
NOW = EXPIRY_TS - 60 * 86400


def _graph(role="collateral_only"):
    """Collateral-only PT position: principal through Pendle core + Morpho Blue custody, oracle/market on the debt
    channel, AMM on the exit channel."""
    n = lambda i, layer, role_, p, lgf, **m: Node(i, layer, i, p, lgf, {"role": role_, "source": "DefiLlama hacks x", **m})  # noqa: E731
    nodes = [Node("pos", "protocol", "Position", 0, 0, {"role": "position"}),
             n("pendle_core", "amm", "pendle_core", 0.001, 0.2, expiry="2027-01-15T08:00:00.000Z"),
             n("amm", "amm", "amm", 0.001, 0.2, implied_apy=0.12),
             n("underlying", "yield_source", "underlying", 0.002, 0.2),
             n("morpho", "protocol", "morpho_blue", 0.001, 0.2),
             n("lending", "lending", "lending", 0.001, 0.2),
             n("oracle", "oracle", "oracle", 0.002, 0.4)]
    edges = [Edge("pos", "pendle_core", 1.0, "holds the PT"), Edge("pos", "amm", 1.0, "exit route", "exit"),
             Edge("pos", "morpho", 1.0, "custody"), Edge("pos", "lending", 1.0, "collateral on the market", "debt"),
             Edge("pendle_core", "underlying", 0.9, "SY wraps"), Edge("lending", "oracle", 0.8, "oracle")]
    pos = Position("pos", "PT on Morpho", "ethereum", 1_000_000, 30,
                   {"exposure_role": role, "block_timestamp": NOW, "real": False})
    return DepGraph(pos, nodes, edges)


def test_collateral_without_debt_is_not_hit_by_oracle_market_or_amm():
    g = _graph()
    t = {k: v[0] for k, v in best_paths(g).items()}
    assert t["oracle"] == 0 and t["lending"] == 0 and t["amm"] == 0
    assert t["pendle_core"] == 1 and t["morpho"] == 1 and t["underlying"] == pytest.approx(0.9)
    assert blocked_channels(g, "oracle") == ["debt"] and blocked_channels(g, "amm") == ["exit"]
    assert blocked_channels(g, "underlying") == []
    sim = simulate(g)
    assert sim.node_contrib["oracle"] == 0 and sim.node_contrib["lending"] == 0 and sim.node_contrib["amm"] == 0
    # the uncertainty band uses the same channel rule
    band = uncertainty.loss_band(g)
    assert band["central_usd"] == pytest.approx(sim.expected_loss_usd)


def test_borrower_is_hit_by_oracle_and_market_through_the_debt_channel():
    g = _graph("borrower")
    t = {k: v[0] for k, v in best_paths(g).items()}
    assert t["oracle"] == pytest.approx(0.8) and t["lending"] == 1 and t["amm"] == 0
    assert simulate(g).expected_loss_usd > simulate(_graph()).expected_loss_usd


def test_hold_to_maturity_is_costed_on_the_same_window_as_exit():
    g = _graph()
    ex = {"usd": 20_000.0, "slippage_and_fees_usd": 19_990.0, "gas_usd": 10.0, "quote_status": "simulated",
          "method": "pendle_sdk_quote"}

    class D:  # the 30-day decision (only its loss band is read)
        loss_band = {"central_usd": 100.0, "low_usd": 10.0, "high_usd": 1000.0}
        expected_loss_usd = 100.0
        verdict = "STAY"

    m = maturity_options(g, ex, D(), gas_usd_fn=lambda units: (5.0, "test"))
    assert m["status"] == "ok" and m["days_to_maturity"] == pytest.approx(60, abs=0.01)
    opts = {o["option"]: o for o in m["options"]}
    assert set(opts) == {"EXIT", "HOLD_TO_MATURITY", "STAY"}
    assert opts["HOLD_TO_MATURITY"]["redemption_gas_usd"] == 5.0
    assert opts["HOLD_TO_MATURITY"]["central_usd"] < opts["EXIT"]["central_usd"]  # $20k exit vs small loss
    assert m["best_over_window"] == "HOLD_TO_MATURITY"
    assert maturity_options(_graph("borrower"), ex, D())["status"] == "not_applicable"


def test_loss_given_failure_is_calibrated_on_real_exploits():
    sev = priors.hack_severity()
    assert sev and sev["n"] >= 10 and 0 < sev["low"] <= sev["mean"] <= sev["high"] <= 1
    node = Node("x", "protocol", "x", 0.01, sev["mean"], {"lgf_source": sev["source"], "role": "morpho_blue",
                                                         "lgf_band": {"low": sev["low"], "high": sev["high"]}})
    c = uncertainty.classify_lgf(node)
    assert c["class"] == "calibrated" and c["low"] == sev["low"] and c["high"] == sev["high"]


def _markets():
    def dep(key, p, lgf, T, node_id=None):
        return {"key": key, "label": key, "role": "underlying", "p_fail": p, "lgf": lgf, "transmission": T, "source": "",
                "node_id": node_id}
    common = [dep("chain:ethereum", 0.0004, 0.3, 1.0), dep("morpho_blue", 0.0002, 0.2, 1.0)]
    mk = lambda i, und, mine=False: {"market_id": f"m{i}", "label": f"P{i}", "is_mine": mine, "pendle_market": f"pm{i}",  # noqa: E731
                                     "implied_apy": 0.10, "pool_liquidity_usd": 5e6, "exit_route": {},
                                     "dependencies": common + [dep(f"underlying:{und}", 0.0004, 0.2, 0.9)]}
    return [mk(1, "a"), mk(2, "a"), mk(3, "b")]


def test_real_book_shared_dependency_hits_every_pocket_that_shares_it():
    g = _graph()
    r = book_lib.evaluate(g, _markets(), 3_000_000, exit_cost_pct=0.11, shock_key="underlying:a", severity=0.3,
                          reference_apy=0.07, quote=False)
    assert r["affected"] == ["P1", "P2"] and r["n_pockets"] == 3
    hit = [p for p in r["pockets"] if p["affected"]]
    assert all(p["exit_cost_usd"] == pytest.approx(0.11 * 1_000_000) for p in r["pockets"])
    assert all(p["stay_loss_usd"] > 0.27 * 1_000_000 * 0.99 for p in hit)  # 30% x 0.9 transmission
    assert all(p["verdict"] == ("EXIT" if p["stay_loss_usd"] > p["exit_total_usd"] else "STAY") for p in r["pockets"])
    assert r["total_optimal_usd"] == pytest.approx(sum(min(p["stay_loss_usd"], p["exit_total_usd"]) for p in r["pockets"]))
    shared = {s["key"]: s for s in r["shared_dependencies"]}
    assert shared["morpho_blue"]["n_pockets"] == 3 and shared["underlying:a"]["n_pockets"] == 2
    assert shared["underlying:a"]["exposed_usd"] == pytest.approx(2 * 1_000_000 * 0.9)
    with pytest.raises(ValueError):
        book_lib.evaluate(g, _markets(), 3e6, weights=[0.5, 0.5], quote=False)


def test_countermove_suggestion_is_a_valid_policy():
    from defirisk.countermove import api as cm
    st = {"lltv": 0.915, "ltv": 0.80, "debt_assets": 800_000.0, "collateral_value_loan_units": 1_000_000.0,
          "collateral_amount": 1_020_000.0, "loan_decimals": 6, "collateral_decimals": 6, "decision": {"verdict": "STAY"}}
    s = leverage.countermove_suggestion(st)
    q = {k: v[0] for k, v in parse_qs(urlparse(s["policy_draft_url"]).query).items()}
    r = cm.policy_draft(q)
    assert r["valid"], r["errors"]
    assert s["policy_draft_query"]["trigger_ltv"] < 0.915 and s["policy_draft_query"]["strategies"] == "REPAY,TOP_UP"
    hit15 = s["reserve_per_first_hit"][-1]
    assert hit15["min_repay"] == pytest.approx(800_000 - (0.875 - 0.05) * 1_000_000 * 0.85)
    st["decision"] = {"verdict": "EXIT"}
    s2 = leverage.countermove_suggestion(st)
    assert s2["policy_draft_query"]["strategies"] == "FULL_REPAY"
    assert cm.policy_draft({k: v[0] for k, v in parse_qs(urlparse(s2["policy_draft_url"]).query).items()})["valid"]


def test_api_params_and_unsupported_chain():
    import analyze
    from defirisk.data import discovery
    p = analyze._params("/api/analyze?exit_cost_pct=0.11&weights=1,1,2&book_shock=underlying:0xab&book_severity=0.3")
    assert p["exit_cost_pct"] == 0.11 and p["weights"] == pytest.approx([0.25, 0.25, 0.5]) and p["book_severity"] == 0.3
    for bad in ("exit_cost_pct=1.5", "weights=1,-1", "book_usd=5", "book_shock=a%20b"):
        with pytest.raises(ValueError):
            analyze._params("/api/analyze?" + bad)
    with pytest.raises(ValueError, match="Ethereum mainnet only"):
        discovery.discover_real("pendle:8453:0xabc", 1e6, 30)


@pytest.mark.skipif(not any(http.CACHE_DIR.glob("*.json")), reason="no recorded API cache")
def test_replay_no_debt_means_no_oracle_or_market_loss(monkeypatch):
    monkeypatch.setenv("DEFIRISK_OFFLINE", "1")
    monkeypatch.setenv("DEFIRISK_NO_QUOTE", "1")
    from defirisk.api_payload import build_payload
    try:
        p = build_payload("auto", False)
    except Exception as e:  # noqa: BLE001 - incomplete cache
        pytest.skip(f"replay unavailable: {e}")
    base = p["decision"]["expected_loss_usd"]
    rows = {r["id"]: r for r in p["stress_table"]}
    for nid in ("oracle", "lending", "amm"):
        assert rows[nid]["conditional_loss_usd"] == pytest.approx(base, rel=1e-6), nid
        assert rows[nid]["channel"]["blocked_by"]
    assert rows["pendle_core"]["conditional_loss_usd"] > base and rows["morpho"]["conditional_loss_usd"] > base
    assert p["maturity"]["status"] in ("ok", "matured")
    assert p["book"]["mode"] == "real_book" and p["book"]["affected"]
