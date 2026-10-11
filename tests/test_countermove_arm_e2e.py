"""ARM PROTECTION end to end on a local Anvil chain (real Morpho Blue bytecode + RescueVault + the real keeper service):
AWAITING_AUTHORIZATION -> AWAITING_RESERVES -> ARMED (not monitored) -> MONITORING -> shock -> EXECUTING (CONFIRMED,
awaiting depth) -> VERIFIED, plus reorg, pause, revoke, expiry and single-instance checks. Every state is read back from
the chain / heartbeat / journal through the same code path as GET /api/countermove?action=policy-status.
Local test chain only: no mainnet, no real funds. Skipped when Foundry or the artifacts are missing
(FAULTLINE_REQUIRE_E2E=1 turns the skip into a failure, see tests/conftest.py)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_countermove_e2e import (HAVE, USDC, USER, arm, cfg, env, shock, world)  # noqa: E402,F401 - fixtures
from defirisk.countermove import devchain, status  # noqa: E402
from defirisk.countermove.chain import RPC  # noqa: E402
from defirisk.countermove.evidence import EvidenceStore  # noqa: E402
from defirisk.countermove.service import KeeperService, LeaseHeld  # noqa: E402

pytestmark = pytest.mark.skipif(not HAVE, reason="needs Foundry (anvil, cast) and `forge build` artifacts in contracts/out")

DRAFT = {"strategies": "REPAY,TOP_UP,FULL_REPAY", "lltv": "0.86", "trigger_ltv": "0.82", "min_ltv_after": "0.4",
         "cooldown_s": "3600", "max_repay_per_action": "2500", "max_top_up_per_action": "1", "max_full_repay": "9000",
         "max_repay_total": "10000", "max_top_up_total": "2", "min_loan_reserve": "0", "min_collateral_reserve": "0"}


@pytest.fixture()
def arm_env(env, tmp_path, monkeypatch):
    monkeypatch.setenv("FAULTLINE_ARM_RPC_URL", env["url"])
    monkeypatch.delenv("FAULTLINE_ARM_ENVIRONMENT", raising=False)
    monkeypatch.delenv("FAULTLINE_EVIDENCE_DB", raising=False)
    monkeypatch.delenv("FAULTLINE_KEEPER_HEALTH", raising=False)
    store = EvidenceStore(tmp_path / "evidence.sqlite")
    services = []

    def service(**kw):
        s = KeeperService(cfg(env), RPC(env["url"]), env["journal"], env["signer"], state_dir=tmp_path / "keeper",
                          store=store, sleep=lambda _: None, **kw)
        services.append(s)
        return s

    yield {**env, "store": store, "service": service, "monkeypatch": monkeypatch}
    for s in services:
        s.stop()
    store.close()


def ps(e, **q):
    return status.policy_status({"vault": e["vault"], **q})


def mine(e, n=1):
    for _ in range(n):
        e["rpc"].call("evm_mine", [])


def armed_and_watched(e, confirmations=2):
    arm(e, loan=3_000 * USDC, coll=0, min_loan_reserve=0, min_collateral_reserve=0)
    s = e["service"](confirmations=confirmations)
    s.start()
    e["monkeypatch"].setenv("FAULTLINE_KEEPER_HEALTH", str(s.health_path))
    s.tick()
    return s


def test_arm_lifecycle_through_verified(arm_env):
    e = arm_env
    r = ps(e)
    assert r["state"] == "AWAITING_AUTHORIZATION" and not r["armed"] and "policy_nonce = 0" in r["reason"]
    assert r["chain"]["chain_id"] == 31337 and r["chain"]["environment"] == "local-test"

    arm(e, loan=0, coll=0)  # owner signs the policy, reserve not funded yet
    r = ps(e, required_loan_raw=str(2_000 * USDC), **DRAFT)
    assert r["state"] == "AWAITING_RESERVES", r["reason"]
    assert next(g for g in r["gates"] if g["gate"] == "policy_matches_draft")["ok"] is True

    devchain.call(e["rpc"], USER, e["vault"], "deposit(address,uint256)", [e["usdc"], 3_000 * USDC])
    r = ps(e, required_loan_raw=str(2_000 * USDC), **DRAFT)
    assert r["state"] == "ARMED" and r["armed"] and not r["monitoring"] and "NOT monitored" in r["reason"]
    assert ps(e, **{**DRAFT, "trigger_ltv": "0.8"})["state"] == "AWAITING_AUTHORIZATION"  # signed policy != draft

    s = e["service"](confirmations=3)
    s.start()
    e["monkeypatch"].setenv("FAULTLINE_KEEPER_HEALTH", str(s.health_path))
    assert ps(e)["state"] == "ARMED"  # lock taken, but no tick yet: status 'starting' is not monitoring
    s.tick()
    r = ps(e, **DRAFT)
    assert r["state"] == "MONITORING" and r["monitoring"] and r["keeper"]["watching_this_vault"]
    assert status.keeper_status({})["status"] == "OK"

    shock(e, 1_880)  # SIMULATED -6% ETH/USD on the local test feed: LTV 80% -> 85.1% (trigger 82%)
    out = s.tick()
    conf = [x for x in out["results"] if x["state"] == "CONFIRMED"]
    assert len(conf) == 1, out["results"]
    tx = conf[0]["tx_hash"]
    r = ps(e)
    assert r["state"] == "EXECUTING" and "confirmation depth" in r["reason"]  # CONFIRMED is not VERIFIED yet

    mine(e, 1)
    s.tick()
    assert ps(e)["state"] == "EXECUTING"
    mine(e, 1)
    s.tick()
    r = ps(e)
    assert r["state"] == "VERIFIED" and r["finality"]["status"] == "final" and r["finality"]["confirmations"] >= 3
    assert r["finality"]["tx_hash"] == tx.lower()

    st = e["store"]
    receipts = st.query(kinds=["receipt"], limit=500)
    assert [x["tx_hash"] for x in receipts] == [tx.lower()]  # exactly one receipt row
    assert st.query(kinds=["execution_attempt"], limit=500)[0]["tx_hash"] == tx.lower()
    assert any(x["state"] == "VERIFIED" for x in st.query(kinds=["finality"], limit=500))
    assert st.verify()["ok"] and all(x["environment"] == "local-test" for x in st.query(limit=500))

    s.stop()
    r = ps(e)
    assert r["state"] == "ARMED" and not r["monitoring"]  # keeper stopped: honest downgrade
    assert status.keeper_status({})["status"] == "STOPPED"


def test_reorg_of_a_confirmed_action_is_failed_not_verified(arm_env):
    e = arm_env
    s = armed_and_watched(e, confirmations=3)
    shock(e, 1_880)
    snap = e["rpc"].call("evm_snapshot", [])
    out = s.tick()
    tx = next(x["tx_hash"] for x in out["results"] if x["state"] == "CONFIRMED").lower()
    e["rpc"].call("evm_revert", [snap])  # the block with the rescue disappears (local reorg injection)
    s.watcher.cfg["positions"][0]["retry_after_failed_s"] = 3600  # hold the re-plan so the FAILED state is observable
    s.tick()
    it = s.finality.items[tx]
    assert it["status"] == "reorged" or it.get("reverified") is True
    if it["status"] == "reorged":
        assert any(x["state"] == "FAILED" and x.get("event") == "reorged" and x["tx_hash"] == tx
                   for x in e["journal"].entries("P"))
        r = ps(e)
        assert r["state"] == "FAILED" and r["state"] != "VERIFIED"
    assert json.loads(s.health_path.read_text())["reorg_suspected"] is True


def test_owner_controls_and_expiry(arm_env):
    e = arm_env
    s = armed_and_watched(e)
    assert ps(e)["state"] == "MONITORING"
    devchain.call(e["rpc"], USER, e["vault"], "setPaused(bool)", [True])
    s.tick()
    assert ps(e)["state"] == "PAUSED"
    shock(e, 1_880)
    out = s.tick()
    assert not any(x["state"] in ("EXECUTING", "CONFIRMED") for x in out["results"])  # paused: the keeper cannot act
    devchain.call(e["rpc"], USER, e["vault"], "setPaused(bool)", [False])
    e["rpc"].call("evm_increaseTime", [31 * 86_400])
    mine(e)
    assert ps(e)["state"] == "EXPIRED"  # chain time, not wall-clock time
    devchain.call(e["rpc"], USER, e["vault"], "revoke()", [])
    assert ps(e)["state"] == "REVOKED"


def test_second_keeper_on_the_same_state_is_refused(arm_env):
    e = arm_env
    armed_and_watched(e)
    with pytest.raises(LeaseHeld):
        e["service"]().start()
