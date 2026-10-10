"""STAY / EXIT / HOLD TO MATURITY for a PT (the brief asks stay or exit; a principal token adds a third answer).

A PT redeems at par at maturity through Pendle's PT/SY contracts, whatever happens to the AMM pool it trades in. So
the alternative to selling now is holding to maturity: no AMM execution cost, the full PT yield is earned, but the
position stays exposed to its principal dependencies (issuer, underlying, Pendle contracts, Morpho Blue custody, chain)
for the whole remaining term. Both are compared over the SAME window (now -> maturity):

  EXIT now          = execution cost now (swap fees + price impact + gas) + excess carry forgone until maturity
  HOLD TO MATURITY  = expected loss until maturity (same dependency model, failure probabilities rescaled from the
                      analysis horizon to the remaining term) + redemption gas

The main 30-day verdict (STAY vs EXIT over the horizon, then re-assess) is reported next to them, unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .. import uncertainty
from .models import DepGraph

REDEEM_GAS = 250_000  # assumption: Pendle redeemPyToToken / SY redeem at maturity (order of magnitude, +-50% band)


def days_to_maturity(g: DepGraph) -> float | None:
    node = next((n for n in g.nodes if n.meta.get("role") in ("pendle_core", "amm") and n.meta.get("expiry")), None)
    if node is None:
        return None
    raw = node.meta["expiry"]
    try:
        exp = float(raw) if isinstance(raw, (int, float)) else datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    now = g.position.meta.get("block_timestamp") or g.position.meta.get("observed_at")
    if not now:
        return None
    return max((exp - float(now)) / 86400, 0.0)


def rescale(g: DepGraph, days: float) -> DepGraph:
    """Copy of g with every failure probability converted from the analysis horizon to `days` (constant hazard)."""
    g2 = deepcopy(g)
    H = g.position.horizon_days
    for n in g2.nodes:
        if 0 < n.p_fail < 1:
            n.p_fail = 1 - (1 - n.p_fail) ** (days / H)
    g2.position.horizon_days = days
    return g2


def _band(central: float, low: float, high: float) -> dict:
    return {"central_usd": central, "low_usd": low, "high_usd": high}


def maturity_options(g: DepGraph, ex: dict, decision, gas_usd_fn=None) -> dict:
    """ex = exit_cost_for(g) (execution only). decision = the robust 30-day Decision (for the STAY row)."""
    days = days_to_maturity(g)
    if days is None:
        return {"status": "not_applicable", "reason": "no maturity found: not a principal token"}
    if g.position.meta.get("exposure_role") == "borrower":
        return {"status": "not_applicable", "days_to_maturity": days,
                "reason": "borrower: holding to maturity keeps the debt (interest accrues, liquidation risk until "
                          "maturity); see the borrower decision in the liquidation section"}
    if days <= 0:
        return {"status": "matured", "days_to_maturity": 0.0,
                "reason": "the PT has matured: redeem at par through Pendle (no AMM exit needed)"}
    from .decision import _gas_usd
    gas_usd, gas_why = (gas_usd_fn or _gas_usd)(REDEEM_GAS)
    rates = g.position.meta.get("reference_rates") if g.position.meta.get("real") else None
    gm = rescale(g, days)
    lb = uncertainty.loss_band(gm)
    cr = uncertainty.carry(gm, rates)
    eb = uncertainty.exit_band(ex, cr)
    hold = _band(lb["central_usd"] + gas_usd, lb["low_usd"] + gas_usd * (1 - uncertainty.GAS_BAND),
                 lb["high_usd"] + gas_usd * (1 + uncertainty.GAS_BAND))
    exit_now = _band(eb["central_usd"], eb["low_usd"], eb["high_usd"])
    if hold["high_usd"] < exit_now["low_usd"]:
        best, conf = "HOLD_TO_MATURITY", "high"
    elif hold["low_usd"] > exit_now["high_usd"]:
        best, conf = "EXIT", "high"
    else:
        best = "HOLD_TO_MATURITY" if hold["central_usd"] <= exit_now["central_usd"] else "EXIT"
        conf = "low"
    V = g.position.value_usd
    H = g.position.horizon_days
    return {
        "status": "ok", "days_to_maturity": days, "window": f"now -> maturity ({days:.0f} days)",
        "best_over_window": best, "confidence": conf,
        "options": [
            {"option": "EXIT", "label": "Sell now through the Pendle AMM", **exit_now,
             "execution_usd": ex["usd"], "carry_forgone_usd": cr.get("usd"),
             "basis": f"execution {ex.get('method')} + excess carry forgone until maturity ({cr.get('status')})"},
            {"option": "HOLD_TO_MATURITY", "label": "Hold and redeem at par at maturity", **hold,
             "expected_loss_usd": lb["central_usd"], "redemption_gas_usd": gas_usd, "redemption_gas_source": gas_why,
             "amm_exposure": "none: redemption goes through the PT/SY contracts, not the pool",
             "basis": f"expected loss over {days:.0f} days (probabilities rescaled from {H} days, constant hazard) + "
                      f"redemption gas ({REDEEM_GAS:,} gas, assumption)"},
            {"option": "STAY", "label": f"Stay {H} days, then re-assess", "window_days": H,
             "central_usd": decision.loss_band["central_usd"] if decision.loss_band else decision.expected_loss_usd,
             "low_usd": (decision.loss_band or {}).get("low_usd"), "high_usd": (decision.loss_band or {}).get("high_usd"),
             "verdict_vs_exit": decision.verdict,
             "basis": f"the main {H}-day verdict (different window: not ranked against the two above)"},
        ],
        "pct_of_position": {"exit": exit_now["central_usd"] / V, "hold_to_maturity": hold["central_usd"] / V},
        "if_amm_fails": "holding to maturity is unaffected: the AMM only matters for selling early",
        "rule": "Same window (now -> maturity): HOLD_TO_MATURITY if its high cost < EXIT's low cost, EXIT if its high "
                "cost < HOLD's low cost, else the lower central cost with low confidence.",
    }
