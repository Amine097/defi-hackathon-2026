"""Liquidation section of the analysis (H02): unlevered by default, real borrower on request.

Mode A (default) unlevered_exposure: the user gives a position size, not a borrower. A market LLTV is not evidence of
debt, so no liquidation is shown (NOT_APPLICABLE).
Mode B borrower_position: borrower=0x... (or "auto" = the largest real borrower of the market, from the Morpho API,
then every number re-read on-chain at the analysis block). Collateral loss fractions come from the same failure model
as the main decision (scenarios + Monte Carlo samples) and are fed through Morpho Blue's liquidation arithmetic.
Assumptions: the oracle tracks the collateral loss one-for-one (the PT oracle reads the Pendle market), liquidators
close the full debt when eligible (worst case, allowed by Morpho Blue), normal PT price volatility is NOT modelled.
"""
from __future__ import annotations

import math
import re

import numpy as np

from . import morpho

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
MIN_DISTANCE = 0.10  # below this distance to liquidation, ordinary PT price moves (not modelled) matter -> REVIEW
REPAY_GAS = 120_000  # assumption: repay() on Morpho Blue


def parse_borrower(value: str | None) -> str | None:
    if value in (None, "", "none"):
        return None
    if value == "auto" or ADDRESS.match(value):
        return value
    raise ValueError("borrower must be a 0x-prefixed 20-byte address or 'auto'")


def _grid(state: dict) -> list[dict]:
    dist = state.get("distance_to_liquidation_pct") or 0.0
    drops = sorted({0.0, 0.02, 0.05, 0.10, 0.20, 0.50, round(max(dist - 0.001, 0), 4), round(min(dist + 0.001, 1), 4)})
    return [morpho.liquidation_outcome(state, d) for d in drops]


def _expected(state: dict, sim, value_usd: float) -> dict:
    fr = np.clip(np.asarray(sim.loss_samples, dtype=float) / value_usd, 0, 1)
    vals, counts = np.unique(np.round(fr, 6), return_counts=True)
    w = counts / counts.sum()
    outs = [morpho.liquidation_outcome(state, float(v)) for v in vals]
    return {"expected_borrower_loss_usd": float(sum(o["borrower_loss_usd"] * p for o, p in zip(outs, w))),
            "expected_penalty_usd": float(sum(o["of_which_liquidation_penalty_usd"] * p for o, p in zip(outs, w))),
            "expected_lender_bad_debt_usd": float(sum(o["lender_bad_debt_usd"] * p for o, p in zip(outs, w))),
            "p_liquidation": float(sum(p for o, p in zip(outs, w) if o["liquidated"])),
            "method": f"{len(fr):,} Monte Carlo collateral-loss draws of the dependency model (same seed as the main "
                      "decision) pushed through Morpho liquidation arithmetic"}


def _drift(state: dict, horizon_days: int) -> dict:
    r = state.get("borrow_rate_per_s")
    if not r:
        return {"status": "unknown", "reason": "borrow rate unreadable"}
    growth = math.exp(r / morpho.WAD * horizon_days * 86400)
    hf = state["health_factor"] / growth if state.get("health_factor") else None
    return {"debt_growth_factor": growth, "debt_at_horizon_usd": state["debt_value_usd"] * growth,
            "health_factor_at_horizon_constant_price": hf,
            "liquidated_by_interest_alone": hf is not None and hf < 1,
            "note": f"debt accrues at the current on-chain borrow rate for {horizon_days}d, oracle price held constant"}


def analyze(g, sim, scenarios: list[dict], borrower: str | None) -> dict:
    if borrower is None:
        return morpho.unlevered()
    m = g.position.meta
    if not m.get("real"):
        return morpho.unlevered("mock graph: borrower analysis needs a real Morpho market")
    mid, block = m["morpho_market"], m.get("block_number")
    selected = "user-supplied address"
    if borrower == "auto":
        top = morpho.top_borrowers(mid, 1)
        if not top:
            return morpho.unlevered("no borrower with debt in this market (Morpho API)")
        borrower, selected = top[0]["address"], "auto: largest borrower by shares (Morpho API), re-read on-chain"
    st = morpho.borrower_state(mid, borrower, block)
    st["selected_by"] = selected
    if st["mode"] != "borrower_position":
        return st
    V = g.position.value_usd
    st["scenarios"] = [{"name": s["name"], "collateral_loss_fraction": s["conditional_loss_usd"] / V,
                        **morpho.liquidation_outcome(st, s["conditional_loss_usd"] / V)} for s in scenarios]
    st["price_grid"] = _grid(st)
    st["expected"] = _expected(st, sim, V)
    st["drift"] = _drift(st, g.position.horizon_days)
    st["decision"] = _borrower_decision(g, st)
    st["countermove_suggestion"] = countermove_suggestion(st)
    try:
        liq = morpho.recent_liquidations(mid, 1)
        st["historical_check"] = morpho.verify_liquidation(liq[0]["tx"]) if liq else {"status": "no liquidation found"}
    except Exception as e:
        st["historical_check"] = {"status": "unavailable", "reason": f"{type(e).__name__}: {e}"[:200]}
    return st


TRIGGER_GAP = 0.04  # suggested trigger = LLTV - 4 pp (same default as the Countermove dry run)
FLOOR_GAP = 0.10  # suggested LTV floor after an action = trigger - 10 pp
FIRST_HITS = (0.05, 0.10, 0.15)


def countermove_suggestion(st: dict) -> dict:
    """Signal -> action: a RescueVault policy for THIS borrower, in the units of /api/countermove?action=policy-draft.

    Reserve per first hit h: repay R so that the LTV after the hit is back at the trigger - 5 pp target:
    R = max(0, debt - target x collateral value x (1 - h)); or top up T collateral so that
    debt <= target x (collateral + T) x price x (1 - h). An EXIT verdict suggests closing the debt (FULL_REPAY).
    The owner signs it; nothing is sent from here."""
    lltv, ltv = st["lltv"], st.get("ltv") or 0.0
    debt, cv = st["debt_assets"], st["collateral_value_loan_units"]
    coll_amt = st["collateral_amount"]
    price = cv / coll_amt if coll_amt else None
    trigger = round(max(min(lltv - TRIGGER_GAP, lltv - 0.005), 0.01), 4)
    floor = round(max(trigger - FLOOR_GAP, 0.0), 4)
    target = max(trigger - 0.05, floor + 0.01)
    rows = []
    for h in FIRST_HITS:
        v = cv * (1 - h)
        repay = max(0.0, debt - target * v)
        top_up = max(0.0, debt / (target * price * (1 - h)) - coll_amt) if price else None
        rows.append({"first_hit": h, "ltv_after_hit": debt / v if v else None, "liquidatable_after_hit": debt > lltv * v,
                     "min_repay": repay, "min_top_up": top_up})
    full = (st.get("decision") or {}).get("verdict") == "EXIT"
    worst = rows[-1]
    loan_reserve = debt * 1.01 if full else worst["min_repay"]
    q = {"strategies": "FULL_REPAY" if full else "REPAY,TOP_UP", "trigger_ltv": trigger, "min_ltv_after": floor, "lltv": lltv,
         "max_repay_per_action": 0 if full else round(worst["min_repay"], 2),
         "max_repay_total": round(loan_reserve, 2), "max_full_repay": round(debt * 1.01, 2) if full else 0,
         "min_loan_reserve": 0, "max_top_up_per_action": 0 if full else round(worst["min_top_up"] or 0, 8),
         "max_top_up_total": 0 if full else round(worst["min_top_up"] or 0, 8), "min_collateral_reserve": 0,
         "valid_days": 30, "loan_decimals": st["loan_decimals"], "collateral_decimals": st["collateral_decimals"]}
    from urllib.parse import urlencode
    return {"policy_draft_query": q, "policy_draft_url": "/api/countermove?action=policy-draft&" + urlencode(q),
            "reserve_to_deposit": {"loan_token": round(loan_reserve, 2),
                                   "collateral_token": 0 if full else round(worst["min_top_up"] or 0, 8)},
            "reserve_per_first_hit": rows, "already_above_trigger": ltv >= trigger,
            "why": ("EXIT verdict: close the debt automatically if the trigger is crossed (FULL_REPAY)" if full else
                    f"act at LTV {trigger:.1%} (LLTV {lltv:.1%} - {TRIGGER_GAP:.0%}); reserve sized for a "
                    f"{FIRST_HITS[-1]:.0%} first hit, back to {target:.1%}"),
            "note": "suggestion only: the owner reviews and signs setPolicy with their own wallet; amounts in token units"}


def _borrower_decision(g, st: dict) -> dict:
    from .decision import _gas_usd, quote_exit
    exp = st["expected"]["expected_borrower_loss_usd"]
    route = g.position.meta.get("exit_route")
    try:  # deleverage = sell all collateral (repays the debt); indicative quote, no re-execution (latency)
        q = quote_exit(route, st["collateral_value_usd_oracle"], simulate=False)
        gas, _ = _gas_usd(REPAY_GAS)
        cost, method = q["usd"] + gas, f"Pendle SDK quote on ${st['collateral_value_usd_oracle']:,.0f} of collateral [{q['quote_status']}] + repay gas"
    except Exception as e:
        return {"verdict": "REVIEW", "reasons": [f"deleverage quote unavailable: {e}"[:200]]}
    reasons = []
    dist = st.get("distance_to_liquidation_pct")
    if dist is not None and dist < MIN_DISTANCE:
        reasons.append(f"only {dist:.1%} from liquidation: ordinary PT price volatility (not modelled) can trigger it")
    if st["drift"].get("liquidated_by_interest_alone"):
        reasons.append("interest accrual alone crosses the LLTV within the horizon")
    point = "EXIT" if exp > cost else "STAY"
    return {"verdict": "REVIEW" if reasons else point, "point_verdict": point, "expected_loss_usd": exp,
            "exit_cost_usd": cost, "exit_method": method, "reasons": reasons,
            "rule": f"borrower expected loss (price move + liquidation penalty, non-recourse) vs deleverage execution cost "
                    f"(carry not counted); REVIEW if "
                    f"distance to liquidation < {MIN_DISTANCE:.0%} or interest alone liquidates"}
