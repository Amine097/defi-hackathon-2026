"""Coherence of the headline numbers with the verdict (STAY / EXIT / REVIEW).

Invariant: every number shown next to a verdict is on the verdict's basis, i.e. central expected loss vs the exit side
= execution (slippage + fees + gas) + carry forgone. A REVIEW / lean STAY must never be displayed with a margin that
says "stay costs more" (the +$371 bug: execution-only margin positive while the carry made exiting more expensive).
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import pytest

from defirisk import decision, http
from defirisk.propagation import simulate
from test_hardening import _diamond

ROOT = Path(__file__).parents[1]
T0 = 1_900_000_000.0


def _robust(monkeypatch, p, exec_usd, implied=0.08, supply=0.05):
    monkeypatch.setattr(http, "now", lambda: T0)
    g = _diamond(p, 0.9)
    g.position.meta.update(observed_at=T0, block_timestamp=int(T0) - 6, block_number=1,
                           reference_rates={"supply_apy": supply, "source": "test"})
    next(n for n in g.nodes if n.id == "A").meta.update(role="amm", implied_apy=implied)
    ex = {"usd": float(exec_usd), "slippage_and_fees_usd": exec_usd - 10.0, "gas_usd": 10.0,
          "method": "pendle_sdk_quote", "quote_status": "simulated", "quote_fetched_at": T0 - 5, "quote_block": 1}
    return decision.decide_robust(g, simulate(g), ex, {"cached": 0})


def assert_coherent(d):
    lb, eb = d.loss_band, d.exit_band
    carry = d.carry_usd or 0.0
    assert d.exit_total_usd == pytest.approx(eb["central_usd"])
    assert d.exit_total_usd == pytest.approx(d.exit_cost_usd + carry)
    assert d.expected_loss_usd == pytest.approx(lb["central_usd"])
    assert d.margin_usd == pytest.approx(d.expected_loss_usd - d.exit_total_usd)
    assert d.point_verdict == ("EXIT" if d.margin_usd > 0 else "STAY")  # sign of the shown margin = point verdict
    assert d.breakeven_risk_multiplier == pytest.approx(d.exit_total_usd / d.expected_loss_usd)
    assert d.verdict in (d.point_verdict, "REVIEW")
    if d.verdict == "EXIT":
        assert lb["low_usd"] > eb["high_usd"] and not d.reasons
    elif d.verdict == "STAY":
        assert lb["high_usd"] < eb["low_usd"] and not d.reasons
    else:
        assert d.reasons and d.lean and d.point_verdict in d.lean


def test_firm_exit_is_coherent(monkeypatch):
    d = _robust(monkeypatch, 0.3, 1_000)
    assert d.verdict == "EXIT" and d.margin_usd > 0
    assert_coherent(d)


def test_firm_stay_is_coherent(monkeypatch):
    d = _robust(monkeypatch, 0.01, 50_000)
    assert d.verdict == "STAY" and d.margin_usd < 0
    assert_coherent(d)


def test_review_lean_exit_is_coherent(monkeypatch):
    d = _robust(monkeypatch, 0.3, 60_000)
    assert d.verdict == "REVIEW" and d.point_verdict == "EXIT" and d.margin_usd > 0
    assert_coherent(d)


def test_review_lean_stay_carry_flips_margin_sign(monkeypatch):
    """The reported bug: execution alone < loss < execution + carry. The headline margin must be negative (exit costs
    more, consistent with lean STAY); the execution-only figure is kept separately and labelled as such."""
    d = _robust(monkeypatch, 0.01, 7_000)
    assert d.verdict == "REVIEW" and d.point_verdict == "STAY"
    assert d.exit_cost_usd < d.expected_loss_usd < d.exit_total_usd
    assert d.margin_usd < 0 < d.margin_usd_execution_only
    assert d.point_verdict_execution_only == "EXIT"
    assert "lean STAY" in d.lean
    assert_coherent(d)


def test_decide_counts_carry_on_exit_side():
    g = _diamond(0.01, 0.9)
    sim = simulate(g)
    loss = sim.expected_loss_usd
    d = decision.decide(g, sim, {"usd": loss * 0.9, "method": "t", "carry_usd": loss * 0.2})
    assert d.verdict == "STAY" and d.exit_total_usd == pytest.approx(loss * 1.1)
    assert d.margin_usd == pytest.approx(-loss * 0.1) and d.breakeven_risk_multiplier == pytest.approx(1.1)
    assert "carry forgone" in d.explanation and "certain" not in d.explanation
    d0 = decision.decide(g, sim, {"usd": loss * 0.9, "method": "t"})  # no carry: legacy behaviour unchanged
    assert d0.verdict == "EXIT" and d0.margin_usd == pytest.approx(loss * 0.1)


def _check_payload(p):
    d = p["decision"]
    exit_side = d["exit_total_usd"]
    carry = d["carry_usd"] or 0.0
    assert d["margin_usd"] == pytest.approx(d["expected_loss_usd"] - exit_side)
    assert d["point_verdict"] == ("EXIT" if d["margin_usd"] > 0 else "STAY")
    assert p["exit"]["total_usd"] == pytest.approx(exit_side)
    for s in p["scenarios"] + ([p["custom_shock"]] if p.get("custom_shock") and "verdict" in p["custom_shock"] else []):
        assert s["exit_total_usd"] == pytest.approx(s["exit_cost_usd"] + carry)
        assert s["verdict"] == ("EXIT" if s["conditional_loss_usd"] > s["exit_total_usd"] else "STAY")
        assert s["margin_usd"] == pytest.approx(s["conditional_loss_usd"] - s["exit_total_usd"])
    for r in p["stress_table"]:
        assert r["exit_total_usd"] == pytest.approx(exit_side)
        assert r["verdict_if_shocked"] == ("EXIT" if r["conditional_loss_usd"] > exit_side else "STAY")
    be = p["sensitivity"]["breakeven_risk_multiplier"]
    for r in p["sensitivity"]["rows"]:
        assert r["verdict"] == ("EXIT" if r["expected_loss_usd"] > exit_side else "STAY")
        if be and abs(r["p_fail_multiplier"] - be) / be > 0.05:  # away from the knife edge (MC/nonlinearity)
            assert (r["verdict"] == "EXIT") == (r["p_fail_multiplier"] > be)
    rate = carry / d["value_usd"]
    for pk in p["book"]["pockets"]:
        assert pk["carry_usd"] == pytest.approx(pk["value_usd"] * rate)
        assert pk["exit_total_usd"] == pytest.approx(pk["exit_cost_usd"] + pk["carry_usd"])
        assert pk["verdict"] == ("EXIT" if pk["stay_loss_usd"] > pk["exit_total_usd"] else "STAY")


def test_payload_every_verdict_uses_exit_side_incl_carry_mock():
    from defirisk.api_payload import build_payload
    p = build_payload("mock", True, shock_node="susde", severity=0.5)
    assert p["custom_shock"].get("verdict") in ("STAY", "EXIT")
    _check_payload(p)


def test_payload_every_verdict_uses_exit_side_incl_carry_replay(monkeypatch):
    if not any(http.CACHE_DIR.glob("*.json")):
        pytest.skip("no cached real data (run the live pipeline once)")
    from defirisk.api_payload import build_payload
    monkeypatch.setenv("DEFIRISK_OFFLINE", "1")
    monkeypatch.setattr(http, "now", lambda: T0)
    try:
        p = build_payload("auto", False)
    except RuntimeError as e:
        pytest.skip(f"cache incomplete: {e}")
    assert p["decision"]["carry"]["status"] == "estimated" and p["decision"]["carry_usd"] > 0
    _check_payload(p)


def test_frontend_decision_view_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "js" / "decision_view.test.mjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
