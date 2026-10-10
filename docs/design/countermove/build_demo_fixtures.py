"""Builds the Countermove DEMO fixtures in public/data/countermove/.

These are NOT backend output. No Countermove backend exists yet. Every number comes from the formula in
docs/FAULTLINE_Countermove_v3_Autonomous_Crisis_Response.md section 4:

    B_s(r, q) = LLTV * (V_s + q_s) - (D - r)        target: B_s >= safety_margin

The script first reproduces the spec's own worked example (repay 460, top-up 594.32) and refuses to write
anything if it does not match. Run:  python3 docs/design/countermove/build_demo_fixtures.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "public" / "data" / "countermove"


def min_repay(D, V, lltv, shock, margin):
    return max(0.0, D - (lltv * V * (1 - shock) - margin))


def min_topup_pre_shock(D, V, lltv, shock, margin):
    need_post = max(0.0, (D + margin) / lltv - V * (1 - shock))
    return need_post / (1 - shock)


def buffer(D, V, lltv):
    return lltv * V - D


# spec section 4 worked example: 10,000 collateral, 8,000 debt, LLTV 86%, -10% shock, 200 margin
assert round(min_repay(8000, 10000, 0.86, 0.10, 200), 2) == 460.00
assert round(min_topup_pre_shock(8000, 10000, 0.86, 0.10, 200), 2) == 594.32

# Demo position. LLTV is the real value of the market in the saved run (public/data/sample.json); sizes are invented.
D, V, LLTV, SHOCK, MARGIN = 8600.0, 10000.0, 0.915, 0.10, 200.0
R = round(min_repay(D, V, LLTV, SHOCK, MARGIN), 2)            # 565.00
Q = round(min_topup_pre_shock(D, V, LLTV, SHOCK, MARGIN), 2)  # 686.10
r2 = lambda x: round(x, 2)

POSITION = {
    "label": "Demo borrower on PT-reUSD-10DEC2026 / USDC",
    "market_label": "Morpho Blue · PT-reUSD-10DEC2026 / USDC", "loan_token": "USDC", "collateral_token": "PT-reUSD-10DEC2026",
    "lltv": LLTV, "lltv_source": "real market parameter, from the saved run",
    "debt": D, "collateral_value": V, "buffer": r2(buffer(D, V, LLTV)), "health_factor": round(LLTV * V / D, 3),
    "sizes_source": "invented for the demo",
}
SCENARIO = {"name": "Collateral oracle value falls a further 10%", "oracle_drop": SHOCK, "required_buffer": MARGIN,
            "buffer_without_action": r2(buffer(D, V * (1 - SHOCK), LLTV)),
            "note": "A conditional stress, not a forecast."}
TRIGGER = {"node_id": "feed", "kind": "dependency_signal",
           "description": "The price feed provider behind the market's oracle is assumed to deviate. The position fails the selected stress scenario.",
           "graph_source": "node id from the saved real dependency graph"}


def policy(usdc, coll, max_repay=800.0, max_topup=800.0, partial=False):
    return {"allowed_actions": ["REPAY", "TOP_UP"], "loan_reserve": usdc, "collateral_reserve_value": coll,
            "max_repay_per_event": min(max_repay, usdc), "max_topup_per_event": min(max_topup, coll), "required_scenario_buffer": MARGIN,
            "trigger_buffer_below": 600.0, "allow_partial_protection": partial, "automation_enabled": True}


def strategies(p):
    rep_ok = R <= p["loan_reserve"] and R <= p["max_repay_per_event"]
    top_ok = Q <= p["collateral_reserve_value"] and Q <= p["max_topup_per_event"]
    why = lambda need, have, cap, unit: None if need <= have and need <= cap else (
        f"Needs {need:,.2f} {unit}; the reserve holds {have:,.2f}." if need > have else f"Needs {need:,.2f} {unit}; the per-event limit is {cap:,.2f}.")
    return [
        {"id": "REPAY", "name": "Auto-repay", "feasible": rep_ok, "amount": R, "unit": "USDC",
         "stressed_buffer_after": MARGIN if rep_ok else None, "reserve_after": r2(p["loan_reserve"] - R) if rep_ok else None,
         "effect": "Debt falls. Collateral and its market exposure are unchanged.", "rejected_reason": why(R, p["loan_reserve"], p["max_repay_per_event"], "USDC")},
        {"id": "TOP_UP", "name": "Auto-top-up", "feasible": top_ok, "amount": Q, "unit": "USDC of collateral",
         "stressed_buffer_after": MARGIN if top_ok else None, "reserve_after": r2(p["collateral_reserve_value"] - Q) if top_ok else None,
         "effect": "Collateral rises. Debt is unchanged and exposure to the collateral increases.", "rejected_reason": why(Q, p["collateral_reserve_value"], p["max_topup_per_event"], "USDC of collateral")},
        {"id": "NO_ACTION", "name": "No action", "feasible": True, "amount": 0, "unit": "USDC",
         "stressed_buffer_after": SCENARIO["buffer_without_action"], "reserve_after": None,
         "effect": "Nothing is spent. The position fails the stress scenario.", "rejected_reason": None},
    ]


def state(debt, coll):
    return {"debt": r2(debt), "collateral_value": r2(coll), "buffer": r2(buffer(debt, coll, LLTV)), "stressed_buffer": r2(buffer(debt, coll * (1 - SHOCK), LLTV))}


def fixture(fid, title, summary, p, selected, reason, final, after, spent):
    ev = [{"state": "DETECTED", "note": "Watcher flags the trigger and the failed stress scenario."},
          {"state": "PLANNING", "note": "Allowed actions are sized and checked against reserves and limits."}]
    if selected != "NO_ACTION":
        ev.append({"state": "EXECUTING", "note": "Guard checks pass. The executor submits the transaction."})
    ev.append({"state": final, "note": {"CONFIRMED": "The fixture records a successful result. No transaction exists.",
                                        "REVERTED": "The fixture records a reverted transaction. Nothing changed.",
                                        "NO_ACTION": "No permitted action is fully funded. Nothing is spent and the user is alerted."}[final]})
    return {
        "demo": True, "schema": "faultline.countermove.demo/0 (frontend demo shape, not a backend contract)", "fixture_id": fid, "title": title, "summary": summary,
        "computed_by": "docs/design/countermove/build_demo_fixtures.py, formula from the v3 spec section 4",
        "position": POSITION, "policy": p, "trigger": TRIGGER, "scenario": SCENARIO,
        "plan": {"strategies": strategies(p), "selected": selected, "reason": reason},
        "events": ev,
        "execution": {"status": final, "environment": "demo", "action": selected, "amount": spent["amount"], "unit": spent["unit"],
                      "tx_hash": None, "block_number": None, "receipt": None, "chain_id": None, "post_state_reread": False},
        "before": state(D, V), "after": after,
        "reserves": {"loan_before": p["loan_reserve"], "collateral_before": p["collateral_reserve_value"],
                     "loan_after": r2(p["loan_reserve"] - (spent["amount"] if selected == "REPAY" and final == "CONFIRMED" else 0)),
                     "collateral_after": r2(p["collateral_reserve_value"] - (spent["amount"] if selected == "TOP_UP" and final == "CONFIRMED" else 0))},
    }


F = [
    fixture("repay", "Repay is funded, top-up is not", "USDC reserve covers the repayment. The collateral reserve is too small for a top-up.",
            policy(1000.0, 400.0), "REPAY", "Repay is the only action that meets the required buffer within the reserves. It also keeps exposure to the collateral unchanged.",
            "CONFIRMED", state(D - R, V), {"amount": R, "unit": "USDC"}),
    fixture("topup", "Top-up is funded, repay is not", "The USDC reserve is too small to repay. Pre-funded collateral covers a top-up.",
            policy(300.0, 900.0), "TOP_UP", "The USDC reserve cannot cover the repayment. Top-up is the only action that meets the required buffer.",
            "CONFIRMED", state(D, V + Q), {"amount": Q, "unit": "USDC of collateral"}),
    fixture("no_action", "Nothing is fully funded", "Neither reserve covers its action and partial protection is not allowed.",
            policy(300.0, 400.0), "NO_ACTION", "No permitted action meets the required buffer within the reserves, and the policy does not allow partial protection.",
            "NO_ACTION", state(D, V), {"amount": 0, "unit": "USDC"}),
    fixture("reverted", "Repay is chosen, the transaction reverts", "Same plan as the repay case. The fixture records a reverted transaction.",
            policy(1000.0, 400.0), "REPAY", "Repay is the only action that meets the required buffer within the reserves.",
            "REVERTED", state(D, V), {"amount": R, "unit": "USDC"}),
]
OUT.mkdir(parents=True, exist_ok=True)
for f in F:
    (OUT / f"demo-{f['fixture_id']}.json").write_text(json.dumps(f, indent=1) + "\n")
(OUT / "index.json").write_text(json.dumps({"demo": True, "fixtures": [{"id": f["fixture_id"], "title": f["title"], "summary": f["summary"]} for f in F]}, indent=1) + "\n")
print("repay", R, "top-up", Q, "wrote", len(F), "fixtures to", OUT)
