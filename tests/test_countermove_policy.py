"""Strict ARM PROTECTION policy validation (countermove/policy.py) and the policy-draft API contract."""
import math

import pytest

from defirisk.countermove import api as cm
from defirisk.countermove import policy

NOW = 1_700_000_000
BASE = {"strategies": "REPAY,TOP_UP", "lltv": "0.86", "trigger_ltv": "0.82", "min_ltv_after": "0.6",
        "max_repay_per_action": "2500", "max_repay_total": "10000", "max_full_repay": "0",
        "max_top_up_per_action": "1", "max_top_up_total": "2", "min_loan_reserve": "50", "min_collateral_reserve": "0.01"}


def v(**over):
    return policy.validate({**BASE, **over}, now=NOW)


def codes(r):
    return {(e["field"], e["code"]) for e in r["errors"]}


def test_valid_policy_exact_raw_units_and_struct():
    r = v()
    assert r["errors"] == [] and r["warnings"] == []
    p = r["policy"]
    assert p["allowed_strategies"] == 3 and p["trigger_ltv"] == 82 * 10 ** 16 and p["min_ltv_after"] == 6 * 10 ** 17
    assert p["valid_until"] == NOW + 30 * 86_400 and p["cooldown"] == 3600
    assert p["max_repay_per_action"] == 2_500 * 10 ** 6 and p["max_top_up_total"] == 2 * 10 ** 18
    assert p["min_collateral_reserve"] == 10 ** 16


def test_decimal_conversion_has_no_float_rounding():
    # float(4.1) * 1e6 = 4099999.9999999995 -> int() would give 4099999 raw units
    assert int(float("4.1") * 10 ** 6) == 4_099_999
    r = v(max_repay_per_action="4.1")
    assert r["policy"]["max_repay_per_action"] == 4_100_000 and r["warnings"] == []
    r = v(max_top_up_per_action="0.57")
    assert r["policy"]["max_top_up_per_action"] == 57 * 10 ** 16
    r = v(max_repay_per_action="1.1234567")  # 7 decimals on a 6-decimal token
    assert r["policy"]["max_repay_per_action"] == 1_123_456
    assert any("truncated" in w for w in r["warnings"])


@pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf", "Infinity", "abc", "1e", "0x10"])
def test_non_finite_and_garbage_numbers_are_rejected(bad):
    r = v(max_repay_total=bad)
    assert r["policy"] is None
    assert {c for f, c in codes(r) if f == "max_repay_total"} & {"not_finite", "not_a_number"}


def test_negative_amounts_and_ltv():
    assert ("max_top_up_total", "negative") in codes(v(max_top_up_total="-1"))
    assert ("min_ltv_after", "negative") in codes(v(min_ltv_after="-0.1"))
    assert ("trigger_ltv", "out_of_range") in codes(v(trigger_ltv="-0.5"))


def test_contract_rules_are_mirrored():
    assert ("trigger_ltv", "above_lltv") in codes(v(trigger_ltv="0.86"))
    assert ("min_ltv_after", "not_below_trigger") in codes(v(min_ltv_after="0.82"))
    assert ("max_repay_total", "caps_inconsistent") in codes(v(max_repay_per_action="20000"))
    assert ("max_repay_total", "caps_inconsistent") in codes(v(strategies="FULL_REPAY", max_full_repay="20000"))
    assert ("max_top_up_total", "caps_inconsistent") in codes(v(max_top_up_per_action="3"))
    for e in v(trigger_ltv="0.9")["errors"]:
        assert e["contract_rule"] == "triggerLtv"


def test_strategies_unknown_duplicate_empty_and_order():
    assert ("strategies", "unknown_strategy") in codes(v(strategies="REPAY,SWAP"))
    assert ("strategies", "duplicate_strategy") in codes(v(strategies="REPAY,repay"))
    assert ("strategies", "empty") in codes(v(strategies=""))
    assert ("strategies", "empty") in codes(v(strategies=" , "))
    r = v(strategies="top_up, Repay")
    assert r["errors"] == [] and r["preference_order"] == ["TOP_UP", "REPAY"] and r["policy"]["allowed_strategies"] == 3
    d = dict(BASE)
    d.pop("strategies")
    assert policy.validate(d, now=NOW)["preference_order"] == ["REPAY", "TOP_UP"]  # absent -> documented default


def test_decimals_lltv_validity_cooldown_bounds():
    assert ("loan_decimals", "out_of_range") in codes(v(loan_decimals="37"))
    assert ("loan_decimals", "not_an_integer") in codes(v(loan_decimals="6.5"))
    assert ("lltv", "out_of_range") in codes(v(lltv="1"))
    assert ("lltv", "out_of_range") in codes(v(lltv="0"))
    assert ("valid_days", "out_of_range") in codes(v(valid_days="0"))
    assert ("valid_days", "out_of_range") in codes(v(valid_days="366"))
    assert v(valid_days="0.5")["policy"]["valid_until"] == NOW + 43_200
    assert ("cooldown_s", "out_of_range") in codes(v(cooldown_s=str(31 * 86_400)))
    assert ("max_repay_total", "too_large") in codes(v(max_repay_total="1e16"))


def test_chain_allowlist_and_addresses():
    assert ("chain_id", "unsupported_chain") in codes(v(chain_id="8453"))
    r = v(chain_id="1")
    assert r["errors"] == [] and r["chain"]["keeper_executable"] is False
    assert any("only transacts on local test chains" in w for w in r["warnings"])
    assert v(chain_id="31337")["chain"]["keeper_executable"] is True
    assert ("vault", "invalid_address") in codes(v(vault="0x1234"))
    assert ("keeper", "invalid_address") in codes(v(keeper="0x" + "0" * 40))
    good = "0x" + "ab" * 20
    assert v(vault=good)["vault"].lower() == good


def test_health_factor_mapping_and_target():
    r = v(target_health_factor="1.25")
    rm = r["risk_mapping"]
    assert math.isclose(rm["trigger_health_factor"], 0.86 / 0.82)
    assert math.isclose(rm["floor_health_factor"], 0.86 / 0.6)
    assert math.isclose(rm["target"]["ltv"], 0.86 / 1.25)
    assert ("target_health_factor", "out_of_range") in codes(v(target_health_factor="1"))
    assert ("target_health_factor", "not_below_trigger") in codes(v(target_health_factor="1.01"))
    assert ("target_health_factor", "below_floor") in codes(v(target_health_factor="2"))


def test_warnings_flag_policies_that_cannot_protect():
    r = v(max_top_up_per_action="0")
    assert any("TOP_UP is allowed but its cap is 0" in w for w in r["warnings"]) and r["errors"] == []
    r = v(strategies="REPAY", max_repay_per_action="0")
    assert any("never protect" in w for w in r["warnings"])
    r = v(strategies="REPAY")
    assert any("max_top_up_per_action is set but TOP_UP is not allowed" in w for w in r["warnings"])
    r = v(loan_reserve="10")
    assert any("below its floor" in w for w in r["warnings"])
    r = v(loan_reserve="1000")
    assert any("smaller than the per-action cap" in w for w in r["warnings"])
    r = v(trigger_ltv="0.858")
    assert any("within 0.5%" in w for w in r["warnings"])


def test_matches_ignores_valid_until_only():
    d = v()["policy"]
    on = dict(d, valid_until=d["valid_until"] + 999)
    assert policy.matches(on, d) == []
    assert policy.matches(dict(on, trigger_ltv=1), d) == ["trigger_ltv"]


def test_policy_draft_api_contract():
    r = cm.policy_draft({**BASE, "target_health_factor": "1.25"})
    assert r["schema"] == "faultline.countermove.policy-draft/2" and r["valid"] is True
    assert r["lifecycle_state"] == "VALIDATED" and r["calldata"].startswith("0x")
    assert r["risk_mapping"]["target"] is not None and r["preference_order"] == ["REPAY", "TOP_UP"]
    bad = cm.policy_draft({**BASE, "strategies": "REPAY,NOPE", "max_repay_total": "nan"})
    assert bad["valid"] is False and bad["lifecycle_state"] == "DRAFT" and bad["calldata"] is None
    assert all(isinstance(e, str) for e in bad["errors"])  # v1 shape kept
    assert {d["code"] for d in bad["error_details"]} >= {"unknown_strategy", "not_finite"}
