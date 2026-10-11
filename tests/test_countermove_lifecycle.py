"""ARM PROTECTION lifecycle (countermove/lifecycle.py): every state is derived from evidence, never asserted."""
import pytest

from defirisk.countermove import lifecycle, policy

NOW = 1_700_000_000
KEEPER = "0x" + "11" * 20
VAULT = "0x" + "22" * 20
DRAFT = policy.validate({"strategies": "REPAY,TOP_UP", "trigger_ltv": "0.82", "min_ltv_after": "0.6",
                         "max_repay_per_action": "2500", "max_repay_total": "10000", "max_top_up_per_action": "1",
                         "max_top_up_total": "2", "min_loan_reserve": "50", "min_collateral_reserve": "0"}, now=NOW)


def vault(**over):
    v = {"address": VAULT, "code_present": True, "policy": dict(DRAFT["policy"]), "policy_nonce": 1, "keeper": KEEPER,
         "paused": False, "revoked": False, "loan_reserve": 3_000 * 10 ** 6, "collateral_reserve": 0}
    pol = over.pop("policy", None)
    if pol:
        v["policy"].update(pol)
    v.update(over)
    return v


def health(status="ok", vault_addr=VAULT, **pos):
    return {"status": status, "keeper": KEEPER, "positions": [{"id": "P", "vault": vault_addr, **pos}]}


def d(**kw):
    kw.setdefault("now", NOW)
    kw.setdefault("chain", {"chain_id": 31337, "head_timestamp": NOW})
    return lifecycle.derive(**kw)


def test_draft_and_validated_without_chain_evidence():
    bad = policy.validate({"trigger_ltv": "nan"}, now=NOW)
    assert d(draft=bad)["state"] == "DRAFT"
    r = d(draft=DRAFT)
    assert r["state"] == "VALIDATED" and r["armed"] is False and r["monitoring"] is False
    assert d()["state"] == "UNAVAILABLE"


def test_unavailable_when_vault_unreadable_is_never_armed():
    r = d(draft=DRAFT, vault_error="connection refused", health=health())
    assert r["state"] == "UNAVAILABLE" and not r["armed"] and not r["monitoring"]


@pytest.mark.parametrize("over,state", [
    ({"code_present": False}, "AWAITING_AUTHORIZATION"),
    ({"policy_nonce": 0}, "AWAITING_AUTHORIZATION"),
    ({"keeper": "0x" + "0" * 40}, "AWAITING_AUTHORIZATION"),
    ({"policy": {"trigger_ltv": 83 * 10 ** 16}}, "AWAITING_AUTHORIZATION"),
    ({"paused": True}, "PAUSED"),
    ({"revoked": True, "paused": True}, "REVOKED"),
    ({"policy": {"valid_until": NOW - 1}}, "EXPIRED"),
])
def test_onchain_gates(over, state):
    r = d(draft=DRAFT, vault=vault(**over), health=health())
    assert r["state"] == state, r
    assert r["armed"] is False and r["monitoring"] is False


def test_expiry_uses_chain_time_not_wall_clock():
    v = vault(policy={"valid_until": NOW + 100})
    assert d(vault=v, health=health(), chain={"head_timestamp": NOW + 101})["state"] == "EXPIRED"
    assert d(vault=v, health=health(), chain={"head_timestamp": NOW + 99})["state"] == "MONITORING"


def test_wrong_keeper_service_is_not_armed():
    h = health()
    h["keeper"] = "0x" + "33" * 20
    assert d(vault=vault(), health=h)["state"] == "AWAITING_AUTHORIZATION"


def test_reserves_requirement():
    r = d(vault=vault(loan_reserve=100 * 10 ** 6), requirement={"loan_raw": 2_000 * 10 ** 6}, health=health())
    assert r["state"] == "AWAITING_RESERVES" and "loan reserve" in r["reason"]
    r = d(vault=vault(), requirement={"loan_raw": 2_000 * 10 ** 6}, health=health())
    assert r["state"] == "MONITORING"
    gate = next(g for g in d(vault=vault(), health=health())["gates"] if g["gate"] == "reserves_sufficient")
    assert gate["ok"] is None  # not checked != passed


@pytest.mark.parametrize("h", [None, {"status": "stale", "keeper": KEEPER, "positions": [{"vault": VAULT}]},
                               {"status": "degraded", "keeper": KEEPER, "positions": [{"vault": VAULT}]},
                               {"status": "ok", "keeper": KEEPER, "positions": [{"vault": "0x" + "44" * 20}]}])
def test_armed_but_not_monitored_without_a_live_keeper_on_this_vault(h):
    r = d(draft=DRAFT, vault=vault(), health=h)
    assert r["state"] == "ARMED" and r["armed"] is True and r["monitoring"] is False
    assert "NOT monitored" in r["reason"]


@pytest.mark.parametrize("js,state", [("WATCHING", "MONITORING"), ("DETECTED", "TRIGGERED"), ("PLANNING", "EVALUATING"),
                                      ("VALIDATING", "EVALUATING"), ("EXECUTING", "EXECUTING"), ("FAILED", "FAILED")])
def test_journal_states(js, state):
    r = d(vault=vault(), health=health(), journal_last={"state": js, "ts": NOW})
    assert r["state"] == state and r["monitoring"] is True


def test_no_action_is_monitoring_with_alert():
    r = d(vault=vault(), health=health(), journal_last={"state": "NO_ACTION", "reason": "reserve empty"})
    assert r["state"] == "MONITORING" and r["alert"] is True and "reserve empty" in r["reason"]


def test_confirmed_is_not_verified_until_final():
    tx = "0x" + "ab" * 32
    last = {"state": "CONFIRMED", "tx_hash": tx}
    assert d(vault=vault(), health=health(), journal_last=last)["state"] == "EXECUTING"
    pend = {"status": "pending", "tx_hash": tx, "confirmations": 1}
    assert d(vault=vault(), health=health(), journal_last=last, finality=pend)["state"] == "EXECUTING"
    fin = {"status": "final", "tx_hash": tx, "confirmations": 3}
    assert d(vault=vault(), health=health(), journal_last=last, finality=fin)["state"] == "VERIFIED"
    other = {"status": "final", "tx_hash": "0x" + "cd" * 32}
    assert d(vault=vault(), health=health(), journal_last=last, finality=other)["state"] == "EXECUTING"
    gone = {"status": "reorged", "tx_hash": tx}
    assert d(vault=vault(), health=health(), journal_last=last, finality=gone)["state"] == "FAILED"


def test_outcome_survives_later_watching_records():
    tx = "0x" + "ab" * 32
    watching = {"state": "WATCHING", "decision": "HOLD"}
    term = {"state": "CONFIRMED", "tx_hash": tx, "at": NOW}
    fin = {"status": "final", "tx_hash": tx.upper().replace("0X", "0x"), "confirmations": 2}
    assert d(vault=vault(), health=health(), journal_last=watching, last_terminal=term, finality=fin)["state"] == "VERIFIED"
    assert d(vault=vault(), health=health(), journal_last=watching, last_terminal=term)["state"] == "EXECUTING"
    failed = {"state": "FAILED", "reason": "reorged", "at": NOW}
    assert d(vault=vault(), health=health(), journal_last={"state": "WATCHING", "event": "backoff"},
             last_terminal=failed)["state"] == "FAILED"
    assert d(vault=vault(), health=health(), journal_last=watching, last_terminal=failed)["state"] == "MONITORING"


def test_owner_controls_override_journal_activity():
    r = d(vault=vault(paused=True), health=health(), journal_last={"state": "EXECUTING"})
    assert r["state"] == "PAUSED"


def test_transition_table():
    assert set(lifecycle.ALLOWED) == set(lifecycle.STATES)
    assert lifecycle.ALLOWED["REVOKED"] == {"REVOKED"}
    assert lifecycle.can_transition("ARMED", "MONITORING")
    assert not lifecycle.can_transition("DRAFT", "ARMED")
    assert not lifecycle.can_transition("VALIDATED", "MONITORING")
    assert not lifecycle.can_transition("MONITORING", "VERIFIED")  # must go through TRIGGERED -> ... -> EXECUTING
    assert lifecycle.can_transition("EXECUTING", "VERIFIED")
    for s in lifecycle.STATES:
        if s != "REVOKED":
            assert lifecycle.can_transition(s, "REVOKED") and lifecycle.can_transition(s, "UNAVAILABLE")
