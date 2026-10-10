"""Countermove engine (borrower side): exact minimal amounts, ordered constraints, explainable choice, NO_ACTION.
Pure tests: no chain. Units are raw integers exactly as on-chain (USDC 6 decimals, collateral 18 or 8 decimals)."""
import pytest

from defirisk.countermove import dependencies, engine
from defirisk.countermove.engine import WAD, EngineConfig, Scenario

KEEPER = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
USDC = 10 ** 6
ETH = 10 ** 18
TS = 1_800_000_000


def mkpos(C=5 * ETH, D=8_000 * USDC, P=2 * 10 ** 27, lltv=86 * 10 ** 16, rate=0, cd=18):
    """Spec example: 5 units at 2,000 USDC = 10,000 USDC of collateral, 8,000 USDC debt, LLTV 86% -> LTV 80%."""
    return {"collateral": C, "debt": D, "borrow_shares": D * 10 ** 6, "price": P, "lltv": lltv, "rate_per_s": rate,
            "timestamp": TS, "block": 100, "loan_decimals": 6, "collateral_decimals": cd, "loan_symbol": "USDC",
            "collateral_symbol": "WETH", "loan_token": "0x" + "a" * 40, "collateral_token": "0x" + "b" * 40}


def mkvault(loan=1_000 * USDC, coll=ETH, **pol):
    policy = {"allowed_strategies": 7, "valid_until": TS + 86_400, "cooldown": 3_600, "trigger_ltv": 78 * 10 ** 16,
              "min_ltv_after": 30 * 10 ** 16, "max_repay_per_action": 800 * USDC, "max_top_up_per_action": ETH // 2,
              "max_full_repay": 10_000 * USDC, "max_repay_total": 10_000 * USDC, "max_top_up_total": ETH,
              "min_loan_reserve": 0, "min_collateral_reserve": 0}
    policy.update(pol)
    return {"address": "0x" + "1" * 40, "policy": policy, "policy_nonce": 1, "keeper": KEEPER, "paused": False,
            "revoked": False, "repaid_total": 0, "topped_up_total": 0, "last_action_at": 0, "loan_reserve": loan,
            "collateral_reserve": coll}


SHOCK10 = [Scenario("now", "current", WAD, [], "current"), Scenario("s10", "collateral -10%", 9 * 10 ** 17)]
CFG = EngineConfig(safety_margin_raw=200 * USDC, interest_horizon_s=0)


def cand(pl, s):
    return next(c for c in pl["candidates"] if c["strategy"] == s)


# ---- exact minimal amounts ------------------------------------------------------------------------------------------
def test_spec_worked_example_repay_460_topup_594():
    pos = mkpos()
    r = engine.min_repay(pos, SHOCK10, CFG)
    assert r == 460 * USDC + CFG.repay_rounding_raw  # 8,000 - (0.86 x 9,000 - 200)
    q = engine.min_top_up(pos, SHOCK10, CFG)
    value = engine.collateral_value(q, pos["price"])
    assert value == pytest.approx(594.32 * USDC, abs=0.01 * USDC)  # 534.88 needed after the shock / 0.9
    pl = engine.plan(pos, mkvault(), SHOCK10, CFG, KEEPER)
    assert pl["decision"] == "EXECUTE" and pl["chosen"]["strategy"] == "REPAY"
    assert cand(pl, "TOP_UP")["status"] == "eligible" and cand(pl, "REPAY")["metrics"]["capital_committed_raw"] < \
        cand(pl, "TOP_UP")["metrics"]["capital_committed_raw"]
    assert "least reserve value" in pl["why"]


@pytest.mark.parametrize("C,D,P,lltv,margin,factors", [
    (5 * ETH, 8_000 * USDC, 2 * 10 ** 27, 86 * 10 ** 16, 200 * USDC, [WAD, 9 * 10 ** 17]),
    (10 ** 8, 64_000 * USDC, 8 * 10 ** 38, 86 * 10 ** 16, 1_000 * USDC, [WAD, 95 * 10 ** 16, 88 * 10 ** 16]),  # 8-dec BTC
    (3 * ETH + 12345, 5_432_123_456, 2_513 * 10 ** 24, 915 * 10 ** 15, 1, [WAD, 97 * 10 ** 16]),
    (7 * ETH, 9_999 * USDC, 2 * 10 ** 27, 77 * 10 ** 16, 50 * USDC, [WAD, 80 * 10 ** 16, 85 * 10 ** 16]),
])
def test_min_amounts_are_exact_and_minimal(C, D, P, lltv, margin, factors):
    pos = mkpos(C=C, D=D, P=P, lltv=lltv)
    sc = [Scenario(f"f{i}", "x", f) for i, f in enumerate(factors)]
    cfg = EngineConfig(safety_margin_raw=margin, interest_horizon_s=0, repay_rounding_raw=0)
    r = engine.min_repay(pos, sc, cfg)
    q = engine.min_top_up(pos, sc, cfg)
    if r is not None and r > 0:
        assert engine.evaluate(pos, sc, cfg, repay=r)["meets_target"]
        assert not engine.evaluate(pos, sc, cfg, repay=r - 1)["meets_target"]  # minimal to the wei
    if q is not None and q > 0:
        assert engine.evaluate(pos, sc, cfg, add=q)["meets_target"]
        assert not engine.evaluate(pos, sc, cfg, add=q - 1)["meets_target"]  # minimal to the raw unit


def test_interest_projection_raises_the_minimum():
    rate = int(0.10 * WAD / (365 * 86_400))  # 10% APR per second (WAD)
    pos = mkpos(rate=rate)
    r0 = engine.min_repay(pos, SHOCK10, EngineConfig(200 * USDC, interest_horizon_s=0))
    r1 = engine.min_repay(pos, SHOCK10, EngineConfig(200 * USDC, interest_horizon_s=7 * 86_400))
    assert r1 > r0  # a week of interest on the remaining debt must be covered too
    ev = engine.evaluate(pos, SHOCK10, EngineConfig(200 * USDC, interest_horizon_s=7 * 86_400), repay=r1)
    assert ev["meets_target"] and ev["debt_projected"] > ev["debt"]


def test_projection_matches_morpho_taylor():
    from defirisk import morpho
    rate = int(0.05 * WAD / (365 * 86_400))
    d = 1_234_567_890
    assert engine.project_debt(d, rate, 86_400) == d + morpho.mul_div_up(d, morpho.w_taylor_compounded(rate, 86_400), WAD)
    assert engine.project_debt(d, None, 86_400) == d and engine.project_debt(d, rate, 0) == d


def test_partial_repay_impossible_needs_full_repay():
    pos = mkpos()
    huge = EngineConfig(safety_margin_raw=8_000 * USDC, interest_horizon_s=0)  # margin above any post-shock capacity
    assert engine.min_repay(pos, SHOCK10, huge) is None
    pl = engine.plan(pos, mkvault(loan=9_000 * USDC, max_repay_per_action=9_000 * USDC), SHOCK10, huge, KEEPER)
    assert cand(pl, "REPAY")["rejected_at"] == "feasibility"
    assert pl["decision"] == "EXECUTE" and pl["chosen"]["strategy"] == "FULL_REPAY"
    assert pl["chosen"]["keeper_bound"] >= pos["debt"]  # maxAssets covers interest accrued before inclusion
    assert pl["chosen"]["after"]["debt"] == 0 and pl["chosen"]["after"]["collateral"] == pos["collateral"]


# ---- constraint order and resource-driven choice --------------------------------------------------------------------
def test_insufficient_usdc_makes_topup_the_only_defense():
    pl = engine.plan(mkpos(), mkvault(loan=200 * USDC), SHOCK10, CFG, KEEPER)
    rep = cand(pl, "REPAY")
    assert rep["status"] == "rejected" and rep["rejected_at"] == "feasibility" and "reserve holds" in rep["reasons"][0]
    assert pl["decision"] == "EXECUTE" and pl["chosen"]["strategy"] == "TOP_UP"
    assert pl["chosen"]["after"]["debt"] == mkpos()["debt"]  # debt unchanged by a top-up
    assert "LLTV" in pl["why"]  # the efficiency trade-off is explained


def test_no_safe_action_explains_every_rejection():
    v = mkvault(loan=100 * USDC, coll=10 ** 16, max_full_repay=0)
    pl = engine.plan(mkpos(), v, SHOCK10, CFG, KEEPER)
    assert pl["decision"] == "NO_ACTION" and pl["chosen"] is None and pl["alert"]
    for s in ("REPAY", "TOP_UP", "FULL_REPAY"):
        assert s in pl["why"]
        assert cand(pl, s)["status"] == "rejected" and cand(pl, s)["reasons"]


def test_partial_protection_only_when_allowed():
    v = mkvault(loan=300 * USDC, coll=0, max_full_repay=0)
    no = engine.plan(mkpos(), v, SHOCK10, CFG, KEEPER)
    assert no["decision"] == "NO_ACTION"
    cfg = EngineConfig(safety_margin_raw=200 * USDC, interest_horizon_s=0, allow_partial=True)
    yes = engine.plan(mkpos(), v, SHOCK10, cfg, KEEPER)
    assert yes["decision"] == "EXECUTE" and yes["partial_protection"] and yes["chosen"]["strategy"] == "REPAY"
    assert yes["chosen"]["amount_raw"] == 300 * USDC and not yes["chosen"]["after"]["meets_target"]
    assert yes["chosen"]["after"]["min_buffer"] > yes["hold"]["min_buffer"]


@pytest.mark.parametrize("pol,expect", [
    ({"max_repay_per_action": 400 * USDC}, "per-action cap"),
    ({"max_repay_total": 400 * USDC, "max_full_repay": 400 * USDC}, "cumulative budget"),
    ({"min_loan_reserve": 600 * USDC}, "reserve floor"),
    ({"min_ltv_after": 77 * 10 ** 16}, "owner floor"),
    ({"allowed_strategies": 2}, "not among the strategies"),
])
def test_security_rejections_for_repay(pol, expect):
    pl = engine.plan(mkpos(), mkvault(**pol), SHOCK10, CFG, KEEPER)
    rep = cand(pl, "REPAY")
    assert rep["status"] == "rejected" and rep["rejected_at"] == "security"
    assert any(expect in r for r in rep["reasons"]), rep["reasons"]


@pytest.mark.parametrize("vault_kw,state_kw,expect", [
    ({}, {"paused": True}, "paused"),
    ({}, {"revoked": True}, "revoked"),
    ({"valid_until": TS - 1}, {}, "expired"),
    ({}, {"last_action_at": TS - 60}, "cooldown"),
    ({}, {"keeper": "0x" + "9" * 40}, "not the vault's authorized keeper"),
    ({}, {"policy_nonce": 0}, "no policy"),
])
def test_global_gates_force_no_action(vault_kw, state_kw, expect):
    v = mkvault(**vault_kw)
    v.update(state_kw)
    pl = engine.plan(mkpos(), v, SHOCK10, CFG, KEEPER)
    assert pl["decision"] == "NO_ACTION" and expect in pl["why"]
    assert all(c["rejected_at"] == "security" for c in pl["candidates"])


def test_below_trigger_hold_or_alert_never_execute():
    v = mkvault(trigger_ltv=82 * 10 ** 16)  # LTV 80% < trigger 82%
    healthy = engine.plan(mkpos(), v, [Scenario("now", "c", WAD, [], "current")], CFG, KEEPER)
    assert healthy["decision"] == "HOLD"
    breach = engine.plan(mkpos(), v, SHOCK10, CFG, KEEPER)  # -10% would break the margin, but no on-chain trigger
    assert breach["decision"] == "NO_ACTION" and breach["alert"] and "ALERT only" in breach["why"]
    assert breach["chosen"] is None


def test_target_already_met_is_hold():
    pl = engine.plan(mkpos(), mkvault(), [Scenario("now", "c", WAD, [], "current")], CFG, KEEPER)
    assert pl["decision"] == "HOLD" and "already met" in pl["why"]


def test_preference_tie_break_is_configurable():
    cfg = EngineConfig(200 * USDC, interest_horizon_s=0, ranking="preference", preference=("TOP_UP", "REPAY", "FULL_REPAY"))
    pl = engine.plan(mkpos(), mkvault(), SHOCK10, cfg, KEEPER)
    assert pl["chosen"]["strategy"] == "TOP_UP" and "preference" in pl["why"]


def test_quantities_are_reported_separately():
    pl = engine.plan(mkpos(), mkvault(), SHOCK10, CFG, KEEPER)
    rep, top = cand(pl, "REPAY")["metrics"], cand(pl, "TOP_UP")["metrics"]
    assert rep["principal_repaid_raw"] == rep["capital_committed_raw"] and rep["collateral_added_raw"] == 0
    assert top["principal_repaid_raw"] == 0 and top["exposure_added_value_raw"] == top["capital_committed_raw"] > 0
    assert set(rep["notes"]) == {"principal_repaid", "collateral_added", "gas", "hypothetical_penalty"}
    assert pl["hold"]["hypothetical_liquidation_penalty_raw"] >= 0


def test_hypothetical_penalty_when_worst_scenario_liquidates():
    deep = [Scenario("now", "c", WAD, [], "current"), Scenario("s15", "-15%", 85 * 10 ** 16)]
    pl = engine.plan(mkpos(), mkvault(loan=1_500 * USDC, max_repay_per_action=1_000 * USDC), deep, CFG, KEEPER)
    assert pl["hold"]["scenarios"][1]["liquidatable"]
    # 8,500 of collateral, 8,000 debt, LIF 1.0438: liquidators seize 8,350 for 8,000 repaid -> 350 penalty (hypothetical)
    assert pl["hold"]["hypothetical_liquidation_penalty_raw"] == pytest.approx(350 * USDC, rel=0.01)
    assert pl["chosen"]["strategy"] == "REPAY"
    assert pl["chosen"]["metrics"]["hypothetical_liquidation_penalty_after_raw"] == 0


def test_keeper_bound_and_action_id():
    pl = engine.plan(mkpos(), mkvault(), SHOCK10, CFG, KEEPER)
    ch = pl["chosen"]
    assert ch["keeper_bound"] == ch["after"]["ltv_now"] + CFG.ltv_bound_slack_wad
    assert ch["action_id"] == engine.action_id(mkvault()["address"], 1, 100, "REPAY", ch["amount_raw"])
    assert ch["action_id"] != engine.action_id(mkvault()["address"], 1, 101, "REPAY", ch["amount_raw"])


def test_zero_price_collateral_cannot_be_topped_up():
    pos = mkpos(P=0)
    assert engine.min_top_up(pos, SHOCK10, CFG) is None
    assert engine.ltv_wad(pos["debt"], pos["collateral"], 0) is None


# ---- dependency shocks -> exact price factors ----------------------------------------------------------------------
DEPS = {"feeds": [
    {"id": "feed:0x01", "role": "BASE_FEED_1", "side": "base", "address": "0x01", "description": "weETH/ETH exchange rate"},
    {"id": "feed:0x02", "role": "BASE_FEED_2", "side": "base", "address": "0x02", "description": "ETH / USD"},
    {"id": "feed:0x03", "role": "QUOTE_FEED_1", "side": "quote", "address": "0x03", "description": "USDC / USD"}]}


def test_price_factor_base_quote_and_combined():
    f, ap = dependencies.price_factor(DEPS, [{"dependency": "BASE_FEED_2", "drop": 0.10}])
    assert f == 9 * 10 ** 17 and ap[0]["label"] == "ETH / USD"
    f, _ = dependencies.price_factor(DEPS, [{"dependency": "usdc / usd", "drop": 0.05}])
    assert f == WAD * WAD // (95 * 10 ** 16)  # quote currency falls -> collateral price in loan units rises
    f, ap = dependencies.price_factor(DEPS, [{"dependency": "weETH/ETH", "drop": 0.05}, {"dependency": "ETH / USD", "drop": 0.10}])
    assert f == 95 * 10 ** 16 * 9 // 10 and len(ap) == 2
    with pytest.raises(ValueError):
        dependencies.price_factor(DEPS, [{"dependency": "BTC / USD", "drop": 0.1}])
    with pytest.raises(ValueError):
        dependencies.price_factor(DEPS, [{"dependency": "ETH / USD", "drop": 1.0}])


def test_build_scenarios_always_contains_now():
    sc = dependencies.build_scenarios(DEPS, [{"id": "eth10", "label": "ETH -10%", "shocks": [{"dependency": "ETH / USD", "drop": 0.1}]}])
    assert [s.id for s in sc] == ["now", "eth10"] and sc[0].factor_wad == WAD and sc[1].shocks[0]["role"] == "BASE_FEED_2"


def test_attribute_move_names_the_dependency():
    ref = {"block": 1, "oracle": {"price": 100}, "feeds": [{"id": "feed:0x02", "answer": 2_500, "role": "BASE_FEED_2", "side": "base",
                                                         "description": "ETH / USD"}]}
    now = {"block": 2, "oracle": {"price": 92}, "feeds": [{"id": "feed:0x02", "answer": 2_300, "role": "BASE_FEED_2", "side": "base",
                                                         "description": "FAULTLINE SIMULATED SHOCK (local fork only)", "simulated": True}]}
    m = dependencies.attribute_move(now, ref)
    assert m["movers"][0]["label"] == "ETH / USD (SIMULATED SHOCK)" and m["movers"][0]["change"] == pytest.approx(-0.08)
    assert m["oracle_change"] == pytest.approx(-0.08) and m["movers"][0]["simulated"]
