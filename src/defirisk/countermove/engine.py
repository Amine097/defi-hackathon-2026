"""Countermove Engine: deterministic, explainable choice among PRE-AUTHORIZED defenses for one Morpho Blue borrower.

Units: every amount is a raw token integer; prices use Morpho's oracle scale (1e36 x loan raw per collateral raw); LTVs
and factors are WAD (1e18 = 100%). Health uses Morpho Blue's exact integer formula:
    maxBorrow(C, P) = wMulDown(mulDivDown(C, P, 1e36), LLTV);  liquidatable iff maxBorrow < debt.
Scenario s multiplies the oracle price by f_s (from the Dependency Engine). Debt is projected over a reaction horizon h
with the on-chain borrow rate: D_h = D + mulDivUp(D, wTaylorCompounded(rate, h), WAD).
Buffer B_s = maxBorrow(C', P_s) - D'_h. Target: B_s >= m (safety margin) in EVERY configured scenario.

Constraint order (mission spec): 1. security & permissions (policy bits, caps, reserve floors, LTV floor, pause /
revoke / expiry / cooldown / keeper / on-chain trigger) -> 2. technical & financial feasibility (tokens actually in
the reserve, partial repay < debt, price > 0) -> 3. buffer target in all scenarios -> 4. ranking among survivors:
least reserve value committed (configurable: preference order). If nothing qualifies: NO_ACTION with the reasons
(partial protection only if the user explicitly allowed it). Repaid principal, added collateral, gas and hypothetical
losses are reported as DIFFERENT quantities; only gas is a cost lost.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import abi, morpho
from ..keccak import keccak256

WAD = 10 ** 18
ORACLE_SCALE = 10 ** 36
STRATEGIES = ("REPAY", "TOP_UP", "FULL_REPAY")
BITS = {"REPAY": 1, "TOP_UP": 2, "FULL_REPAY": 4}


@dataclass
class Scenario:
    id: str
    label: str
    factor_wad: int  # oracle price multiplier; WAD = current price
    shocks: list = field(default_factory=list)  # [{"dependency": id, "label": str, "drop": float}] for the explanation
    kind: str = "dependency_shock"  # "current" | "dependency_shock"


@dataclass
class EngineConfig:
    safety_margin_raw: int  # buffer required in every scenario, loan-token raw units
    interest_horizon_s: int = 86_400
    allow_partial: bool = False
    ranking: str = "min_capital"  # "min_capital" | "preference"
    preference: tuple = ("REPAY", "TOP_UP", "FULL_REPAY")
    ltv_bound_slack_wad: int = 2 * 10 ** 15  # keeper's maxLtvAfter = predicted LTV + 0.2 pp
    full_repay_slack_bps: int = 10  # keeper's maxAssets = debt x (1 + 0.1%)
    repay_rounding_raw: int = 2  # share rounding of a partial repay


# ---- exact Morpho arithmetic ------------------------------------------------------------------------------------------
def max_borrow(collateral: int, price: int, lltv: int) -> int:
    return morpho.max_borrow(collateral, price, lltv)


def collateral_value(collateral: int, price: int) -> int:
    return morpho.mul_div_down(collateral, price, ORACLE_SCALE)


def ltv_wad(debt: int, collateral: int, price: int) -> int | None:
    """debt / collateral value, rounded up (Morpho wDivUp); None = no collateral value (infinite LTV)."""
    if debt == 0:
        return 0
    v = collateral_value(collateral, price)
    return None if v == 0 else morpho.mul_div_up(debt, WAD, v)


def project_debt(debt: int, rate_per_s: int | None, horizon_s: int) -> int:
    if not debt or not rate_per_s or horizon_s <= 0:
        return debt
    return debt + morpho.mul_div_up(debt, morpho.w_taylor_compounded(rate_per_s, horizon_s), WAD)


def scenario_price(price: int, factor_wad: int) -> int:
    return price * factor_wad // WAD  # rounded down: the lower price is the conservative one


def _max_debt_with_projection(allowed: int, rate: int | None, h: int) -> int:
    """Largest x with project_debt(x) <= allowed (monotone): binary search, exact."""
    if allowed < 0:
        return -1
    lo, hi = 0, allowed
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if project_debt(mid, rate, h) <= allowed:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _min_collateral(target_debt: int, price: int, lltv: int) -> int | None:
    """Smallest C with maxBorrow(C, price) >= target_debt (monotone): estimate then exact binary search."""
    if target_debt <= 0:
        return 0
    if price == 0 or lltv == 0:
        return None
    est = -(-(-(-target_debt * WAD // lltv)) * ORACLE_SCALE // price) + 2
    lo, hi = 0, est
    while max_borrow(hi, price, lltv) < target_debt:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if max_borrow(mid, price, lltv) >= target_debt:
            hi = mid
        else:
            lo = mid + 1
    return lo


def min_repay(pos: dict, scenarios: list[Scenario], cfg: EngineConfig) -> int | None:
    """Minimal partial repay so that every scenario keeps buffer >= m. None = only closing the debt can do it."""
    C, D, P, lltv, rate = pos["collateral"], pos["debt"], pos["price"], pos["lltv"], pos.get("rate_per_s")
    need = 0
    for s in scenarios:
        allowed = max_borrow(C, scenario_price(P, s.factor_wad), lltv) - cfg.safety_margin_raw
        x = _max_debt_with_projection(allowed, rate, cfg.interest_horizon_s)
        if x < 0:
            return None
        need = max(need, D - x)
    if need <= 0:
        return 0
    need += cfg.repay_rounding_raw
    return need if need < D else None


def min_top_up(pos: dict, scenarios: list[Scenario], cfg: EngineConfig) -> int | None:
    """Minimal collateral to add (raw) so that every scenario keeps buffer >= m. The added collateral is valued with the
    SAME scenario price as the existing collateral (same token, same oracle path)."""
    C, P, lltv = pos["collateral"], pos["price"], pos["lltv"]
    target = project_debt(pos["debt"], pos.get("rate_per_s"), cfg.interest_horizon_s) + cfg.safety_margin_raw
    need = 0
    for s in scenarios:
        c_req = _min_collateral(target, scenario_price(P, s.factor_wad), lltv)
        if c_req is None:
            return None
        need = max(need, c_req - C)
    return need


def evaluate(pos: dict, scenarios: list[Scenario], cfg: EngineConfig, repay: int = 0, add: int = 0,
             full: bool = False) -> dict:
    """Position after an action, now and in every scenario (buffers in loan raw units, signed)."""
    C2 = pos["collateral"] + add
    D2 = 0 if full else pos["debt"] - repay
    Dh = project_debt(D2, pos.get("rate_per_s"), cfg.interest_horizon_s)
    P, lltv = pos["price"], pos["lltv"]
    rows = []
    for s in scenarios:
        ps = scenario_price(P, s.factor_wad)
        mb = max_borrow(C2, ps, lltv)
        rows.append({"scenario": s.id, "label": s.label, "price": ps, "max_borrow": mb, "debt_projected": Dh,
                     "buffer": mb - Dh, "ltv": ltv_wad(Dh, C2, ps), "liquidatable": mb < Dh,
                     "meets_margin": D2 == 0 or mb - Dh >= cfg.safety_margin_raw})
    mb_now = max_borrow(C2, P, lltv)
    liq_price = (D2 * ORACLE_SCALE * WAD + C2 * lltv - 1) // (C2 * lltv) if (D2 and C2 and lltv) else None
    return {"collateral": C2, "debt": D2, "debt_projected": Dh, "ltv_now": ltv_wad(D2, C2, P),
            "buffer_now": mb_now - D2, "healthy_now": mb_now >= D2, "scenarios": rows,
            "min_buffer": min(r["buffer"] for r in rows) if rows else mb_now - Dh,
            "meets_target": D2 == 0 or all(r["meets_margin"] for r in rows),
            "liquidation_price": liq_price,
            "drop_to_liquidation_wad": (WAD - liq_price * WAD // P) if (liq_price is not None and P and liq_price < P) else (0 if liq_price else None)}


def _penalty_if_liquidated(pos: dict, ev: dict, worst: Scenario | None) -> int:
    """Hypothetical liquidation penalty (loan raw) the borrower would pay if the worst scenario happened and liquidators
    closed the position (Morpho LIF): HYPOTHETICAL, never added to costs."""
    if worst is None or ev["debt"] == 0:
        return 0
    drop = 1 - worst.factor_wad / WAD
    lif = morpho.liquidation_incentive_factor(pos["lltv"]) / WAD
    st = {"collateral_value_usd_oracle": collateral_value(ev["collateral"], pos["price"]), "debt_value_usd": ev["debt_projected"],
          "lltv": pos["lltv"] / WAD, "liquidation_incentive_factor": lif}
    out = morpho.liquidation_outcome(st, max(drop, 0.0))
    return int(out["of_which_liquidation_penalty_usd"]) if out["liquidated"] else 0


# ---- the comparator ---------------------------------------------------------------------------------------------------
def _global_gates(pos: dict, vault: dict, keeper: str | None, now_ts: int) -> list[str]:
    p = vault["policy"]
    out = []
    if vault["policy_nonce"] == 0:
        out.append("no policy configured by the owner: automation is not armed")
    if vault["revoked"]:
        out.append("automation revoked by the owner (irreversible)")
    elif vault["paused"]:
        out.append("automation paused by the owner")
    if keeper and vault["keeper"].lower() != keeper.lower():
        out.append(f"this keeper ({keeper}) is not the vault's authorized keeper ({vault['keeper']})")
    if p["valid_until"] < now_ts:
        out.append(f"policy expired at {p['valid_until']} (now {now_ts})")
    if vault["last_action_at"] and now_ts < vault["last_action_at"] + p["cooldown"]:
        out.append(f"cooldown active until {vault['last_action_at'] + p['cooldown']} (now {now_ts})")
    if pos["borrow_shares"] == 0:
        out.append("the position has no debt: nothing to protect")
    return out


def action_id(vault: str, policy_nonce: int, block: int, strategy: str, amount: int) -> str:
    return "0x" + keccak256(abi.encode_tuple(["address", "uint256", "uint256", "uint8", "uint256"],
                                             [vault, policy_nonce, block, BITS[strategy], amount])).hex()


def plan(pos: dict, vault: dict, scenarios: list[Scenario], cfg: EngineConfig, keeper: str | None = None) -> dict:
    """Full decision record. pos: collateral, debt (accrued), borrow_shares, price, lltv, rate_per_s, block, timestamp,
    loan/collateral decimals+symbols. vault: contracts.read_vault() output."""
    p = vault["policy"]
    now = pos["timestamp"]
    worst = min(scenarios, key=lambda s: s.factor_wad) if scenarios else None
    hold = evaluate(pos, scenarios, cfg)
    ltv_now = hold["ltv_now"]
    trigger_met = ltv_now is None or ltv_now >= p["trigger_ltv"]
    gates = _global_gates(pos, vault, keeper, now)
    base = {"block": pos["block"], "timestamp": now, "policy_nonce": vault["policy_nonce"], "ltv_now": ltv_now,
            "trigger_ltv": p["trigger_ltv"], "trigger_met": trigger_met, "lltv": pos["lltv"],
            "safety_margin_raw": cfg.safety_margin_raw, "interest_horizon_s": cfg.interest_horizon_s,
            "scenarios": [{"id": s.id, "label": s.label, "factor_wad": s.factor_wad, "shocks": s.shocks, "kind": s.kind}
                          for s in scenarios],
            "hold": {**hold, "hypothetical_liquidation_penalty_raw": _penalty_if_liquidated(pos, hold, worst)},
            "global_gates": gates, "ranking": cfg.ranking, "preference": list(cfg.preference),
            "rule": "1 security & permissions -> 2 feasibility -> 3 buffer >= margin in every scenario -> 4 least reserve "
                    "value committed (tie: preference order); none -> NO_ACTION (partial only if allowed)"}
    cands = [_candidate(s, pos, vault, scenarios, cfg, gates, trigger_met, worst) for s in STRATEGIES]
    base["candidates"] = cands

    if not trigger_met:
        why = (f"on-chain LTV {_pct(ltv_now)} is below the trigger {_pct(p['trigger_ltv'])} the owner set: the RescueVault "
               "would refuse any action (a hypothetical scenario alone never unlocks the reserve)")
        if hold["meets_target"]:
            return {**base, "decision": "HOLD", "chosen": None, "why": "position healthy and inside the scenario target; " + why}
        return {**base, "decision": "NO_ACTION", "chosen": None, "alert": True,
                "why": "scenario breach detected (" + _breaches(hold, pos) + ") but " + why + ": ALERT only"}
    if gates:
        return {**base, "decision": "NO_ACTION", "chosen": None, "alert": True, "why": "; ".join(gates)}
    if hold["meets_target"]:
        return {**base, "decision": "HOLD", "chosen": None,
                "why": "the configured scenario target is already met: no reserve needs to be spent"}

    ok = [c for c in cands if c["status"] == "eligible"]
    if ok:
        chosen = sorted(ok, key=lambda c: _rank_key(c, cfg))[0]
        chosen["rank"] = 1
        for i, c in enumerate(sorted([c for c in ok if c is not chosen], key=lambda c: _rank_key(c, cfg)), start=2):
            c["rank"] = i
        return {**base, "decision": "EXECUTE", "chosen": _chosen(chosen, vault, pos), "partial_protection": False,
                "why": _why(chosen, ok, cands, cfg, pos)}
    if cfg.allow_partial:
        part = [c for c in cands if c.get("bounded") and c["bounded"]["status"] == "eligible_partial"]
        if part:
            best = max(part, key=lambda c: c["bounded"]["after"]["min_buffer"])
            b = {**best, "amount_raw": best["bounded"]["amount_raw"], "after": best["bounded"]["after"],
                 "keeper_bound": best["bounded"]["keeper_bound"], "metrics": best["bounded"]["metrics"]}
            return {**base, "decision": "EXECUTE", "chosen": _chosen(b, vault, pos), "partial_protection": True,
                    "why": f"no authorized action meets the target; the owner allowed partial protection: {best['strategy']} "
                           f"of the maximum the policy permits raises the worst-case buffer to "
                           f"{_amt(best['bounded']['after']['min_buffer'], pos)} (target {_amt(cfg.safety_margin_raw, pos)})"}
    return {**base, "decision": "NO_ACTION", "chosen": None, "alert": True,
            "why": "no authorized action can reach the target within the policy and the funded reserves: "
                   + " | ".join(f"{c['strategy']}: {c['reasons'][0] if c['reasons'] else c['status']}" for c in cands)}


def _pct(w: int | None) -> str:
    return "inf" if w is None else f"{w / WAD:.2%}"


def _amt(raw: int | None, pos: dict, which: str = "loan") -> str:
    """Human amount for explanations (token decimals + symbol); raw integers stay in the structured fields."""
    if raw is None:
        return "n/a"
    dec, sym = pos.get(f"{which}_decimals"), pos.get(f"{which}_symbol") or ""
    if dec is None:
        return f"{raw} raw"
    return f"{raw / 10 ** dec:,.{2 if which == 'loan' else 6}f} {sym}".strip()


def _breaches(ev: dict, pos: dict) -> str:
    return ", ".join(f"{r['label']}: buffer {_amt(r['buffer'], pos)}" for r in ev["scenarios"] if not r["meets_margin"]) or "none"


def _rank_key(c: dict, cfg: EngineConfig):
    pref = cfg.preference.index(c["strategy"]) if c["strategy"] in cfg.preference else 99
    cap = c["metrics"]["capital_committed_raw"]
    return (pref, cap) if cfg.ranking == "preference" else (cap, pref)


def _token(pos: dict, which: str) -> dict:
    return {"symbol": pos.get(f"{which}_symbol"), "decimals": pos.get(f"{which}_decimals"), "address": pos.get(f"{which}_token")}


def _candidate(strategy: str, pos: dict, vault: dict, scenarios: list[Scenario], cfg: EngineConfig, gates: list[str],
               trigger_met: bool, worst: Scenario | None) -> dict:
    p = vault["policy"]
    D, C, P = pos["debt"], pos["collateral"], pos["price"]
    is_loan = strategy in ("REPAY", "FULL_REPAY")
    reserve = vault["loan_reserve"] if is_loan else vault["collateral_reserve"]
    floor_tok = p["min_loan_reserve"] if is_loan else p["min_collateral_reserve"]
    spent = vault["repaid_total"] if is_loan else vault["topped_up_total"]
    total_cap = p["max_repay_total"] if is_loan else p["max_top_up_total"]
    per_cap = {"REPAY": p["max_repay_per_action"], "TOP_UP": p["max_top_up_per_action"], "FULL_REPAY": p["max_full_repay"]}[strategy]
    if strategy == "REPAY":
        req = min_repay(pos, scenarios, cfg)
    elif strategy == "TOP_UP":
        req = min_top_up(pos, scenarios, cfg)
    else:
        req = D
    c = {"strategy": strategy, "token": _token(pos, "loan" if is_loan else "collateral"), "required_raw": req,
         "amount_raw": req, "reserve_raw": reserve, "reserve_floor_raw": floor_tok, "per_action_cap_raw": per_cap,
         "cumulative_left_raw": max(total_cap - spent, 0), "reasons": [], "status": "eligible", "rejected_at": None}
    tok = "loan" if is_loan else "collateral"
    F = lambda x: _amt(x, pos, tok)  # noqa: E731
    sec, fea = [], []
    # 1. security & permissions
    sec += gates
    if not trigger_met:
        sec.append("on-chain trigger not reached")
    if not p["allowed_strategies"] & BITS[strategy]:
        sec.append(f"{strategy} is not among the strategies the owner authorized")
    if req is not None:
        if req > per_cap:
            sec.append(f"needs {F(req)} > per-action cap {F(per_cap)}")
        if spent + req > total_cap:
            sec.append(f"needs {F(req)} > cumulative budget left {F(max(total_cap - spent, 0))}")
        if reserve >= req and reserve - req < floor_tok:
            sec.append(f"would leave {F(reserve - req)} < reserve floor {F(floor_tok)}")
    # 2. feasibility
    if req is None:
        fea.append("a partial repay cannot reach the target: only closing the debt can" if strategy == "REPAY" else
                   "collateral has no oracle value: adding more cannot help")
    elif strategy != "FULL_REPAY" and req == 0:
        fea.append("nothing to add: target already met")
    elif reserve < req:
        fea.append(f"reserve holds {F(reserve)} < required {F(req)} (funds must be pre-deposited in the RescueVault)")
    if strategy == "FULL_REPAY" and p["max_full_repay"] == 0:
        sec.append("full repay disabled by the owner (cap 0)")
    after = None
    if req is not None and (strategy == "FULL_REPAY" or req > 0):
        after = evaluate(pos, scenarios, cfg, repay=req if strategy == "REPAY" else 0, add=req if strategy == "TOP_UP" else 0,
                         full=strategy == "FULL_REPAY")
        if strategy != "FULL_REPAY" and after["ltv_now"] is not None and after["ltv_now"] < p["min_ltv_after"]:
            sec.append(f"would push LTV to {_pct(after['ltv_now'])} < owner floor {_pct(p['min_ltv_after'])}")
    c["after"] = after
    c["metrics"] = _metrics(strategy, req or 0, pos, after, reserve, worst)
    c["keeper_bound"] = _bound(strategy, after, pos, cfg)
    if sec:
        c.update(status="rejected", rejected_at="security", reasons=sec + fea)
    elif fea:
        c.update(status="rejected", rejected_at="feasibility", reasons=fea)
    elif after is None or not after["meets_target"]:
        c.update(status="rejected", rejected_at="buffer", reasons=["does not keep the margin in every scenario"])
    c["bounded"] = _bounded(strategy, pos, vault, scenarios, cfg, per_cap, total_cap - spent, reserve, floor_tok, worst,
                            gates or ([] if trigger_met else ["trigger"]))
    return c


def _metrics(strategy: str, amount: int, pos: dict, after: dict | None, reserve: int, worst: Scenario | None) -> dict:
    value = amount if strategy != "TOP_UP" else collateral_value(amount, pos["price"])
    return {"capital_committed_raw": value,
            "capital_unit": "loan-token raw units at the current oracle price",
            "reserve_share_used": (amount / reserve) if reserve else None,
            "principal_repaid_raw": amount if strategy != "TOP_UP" else 0,
            "collateral_added_raw": amount if strategy == "TOP_UP" else 0,
            "collateral_added_value_raw": value if strategy == "TOP_UP" else 0,
            "exposure_added_value_raw": value if strategy == "TOP_UP" else 0,
            "residual_min_buffer_raw": after["min_buffer"] if after else None,
            "residual_ltv_now": after["ltv_now"] if after else None,
            "drop_to_liquidation_after_wad": after["drop_to_liquidation_wad"] if after else None,
            "hypothetical_liquidation_penalty_after_raw": _penalty_if_liquidated(pos, after, worst) if after else None,
            "notes": {"principal_repaid": "reduces debt 1:1; not a loss", "collateral_added": "stays the user's asset; adds "
                      "exposure to the collateral's dependencies", "gas": "the only cost lost (estimated at validation)",
                      "hypothetical_penalty": "only if the worst scenario happens and liquidators act; never summed"}}


def _bound(strategy: str, after: dict | None, pos: dict, cfg: EngineConfig) -> int | None:
    if after is None:
        return None
    if strategy == "FULL_REPAY":
        return pos["debt"] + pos["debt"] * cfg.full_repay_slack_bps // 10_000 + 1
    return (after["ltv_now"] or 0) + cfg.ltv_bound_slack_wad


def _bounded(strategy, pos, vault, scenarios, cfg, per_cap, left, reserve, floor_tok, worst, blocked) -> dict | None:
    """The most the policy and the reserve allow for this strategy, and what it achieves (residual risk)."""
    if strategy == "FULL_REPAY" or blocked or not vault["policy"]["allowed_strategies"] & BITS[strategy]:
        return None
    p = vault["policy"]
    amt = min(per_cap, max(left, 0), max(reserve - floor_tok, 0))
    D, C, P = pos["debt"], pos["collateral"], pos["price"]
    if strategy == "REPAY":
        floor_debt = morpho.mul_div_up(p["min_ltv_after"], collateral_value(C, P), WAD)
        amt = min(amt, D - 1, max(D - floor_debt - 1, 0))
    else:
        if p["min_ltv_after"]:
            c_max = D * WAD * ORACLE_SCALE // (p["min_ltv_after"] * P) if P else 0
            amt = min(amt, max(c_max - C - 1, 0))
    if amt <= 0:
        return {"status": "none", "amount_raw": 0}
    after = evaluate(pos, scenarios, cfg, repay=amt if strategy == "REPAY" else 0, add=amt if strategy == "TOP_UP" else 0)
    improves = after["min_buffer"] > evaluate(pos, scenarios, cfg)["min_buffer"]
    return {"status": "eligible_partial" if improves else "none", "amount_raw": amt, "after": after,
            "meets_target": after["meets_target"], "keeper_bound": _bound(strategy, after, pos, cfg),
            "metrics": _metrics(strategy, amt, pos, after, reserve, worst)}


def _chosen(c: dict, vault: dict, pos: dict) -> dict:
    return {"strategy": c["strategy"], "amount_raw": c["amount_raw"], "token": c["token"], "keeper_bound": c["keeper_bound"],
            "bound_kind": "maxAssets" if c["strategy"] == "FULL_REPAY" else "maxLtvAfter (WAD)",
            "action_id": action_id(vault["address"], vault["policy_nonce"], pos["block"], c["strategy"], c["amount_raw"]),
            "policy_nonce": vault["policy_nonce"], "after": c["after"], "metrics": c["metrics"]}


def _why(chosen: dict, ok: list, cands: list, cfg: EngineConfig, pos: dict) -> str:
    rejected = [f"{c['strategy']} rejected at {c['rejected_at']}: {c['reasons'][0]}" for c in cands if c["status"] != "eligible"]
    others = [c for c in ok if c is not chosen]
    cmp_ = ""
    if others:
        o = others[0]
        cmp_ = (f" Both reach the target; {chosen['strategy']} commits {_amt(chosen['metrics']['capital_committed_raw'], pos)} vs "
                f"{o['strategy']} {_amt(o['metrics']['capital_committed_raw'], pos)} (value at the current oracle price)"
                + (" - by the owner's preference order" if cfg.ranking == "preference" else
                   ": the least reserve value committed leaves the most reserve for the next shock") + ".")
    eff = ""
    if chosen["strategy"] == "TOP_UP":
        eff = (f" A unit of collateral only adds LLTV x scenario price to the buffer (efficiency "
               f"{pos['lltv'] / WAD:.2f} x price factor) while a repaid unit adds 1:1, so TOP_UP wins only when the loan-"
               "token route is unavailable or not preferred.")
    tok = "collateral" if chosen["strategy"] == "TOP_UP" else "loan"
    head = (f"FULL_REPAY closes the whole accrued debt ({_amt(chosen['amount_raw'], pos)}): no debt, no borrowing liquidation "
            "risk; the collateral is NOT sold or withdrawn." if chosen["strategy"] == "FULL_REPAY" else
            f"{chosen['strategy']} {_amt(chosen['amount_raw'], pos, tok)} is the minimal amount that keeps the liquidation buffer "
            f">= {_amt(cfg.safety_margin_raw, pos)} in every configured scenario.")
    return (head + cmp_ + eff + (" Rejected: " + "; ".join(rejected) + "." if rejected else ""))
