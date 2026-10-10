"""End-to-end: the real Morpho Blue v1.0.0 bytecode + RescueVault on a local Anvil chain, driven by the actual keeper
(Watcher -> Countermove engine -> Guarded Executor signing with Foundry cast -> Verifier). No mainnet, no real funds:
tokens / feed / oracle are local test contracts (contracts/src/sim). Skipped when Foundry or the artifacts are missing.
Real-market runs on a mainnet FORK are in scripts/countermove_fork_demo.py."""
import socket
from pathlib import Path

import pytest

from defirisk import abi
from defirisk.countermove import chain as chainmod
from defirisk.countermove import contracts, devchain, engine, reader
from defirisk.countermove.chain import RPC, RPCError
from defirisk.countermove.journal import Journal
from defirisk.countermove.watcher import Watcher

try:
    devchain.anvil_path()
    from defirisk.countermove.signer import CastSigner, cast_path, anvil_test_key
    cast_path()
    HAVE = (devchain.OUT / "RescueVault.sol" / "RescueVault.json").exists() and (devchain.OUT / "LocalSim.sol").exists()
except FileNotFoundError:
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="needs Foundry (anvil, cast) and `forge build` artifacts in contracts/out")

USDC, ETH = 10 ** 6, 10 ** 18
ZERO = "0x" + "0" * 40
DEP, KEEPER, USER, LP, ATTACKER = (devchain.ROLE[k] for k in ("deployer", "keeper", "user", "lp", "attacker"))
MP = "(address,address,address,address,uint256)"
POLICY_SIG = "setPolicy((uint8,uint64,uint32,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256))"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def world():
    node = devchain.Anvil(_free_port()).start()
    rpc = RPC(node.url)
    try:
        d = devchain.deploy
        w = {"rpc": rpc, "url": node.url}
        w["morpho"] = d(rpc, DEP, "Morpho", ["address"], [DEP])
        w["irm"] = d(rpc, DEP, "IrmMock")
        w["usdc"] = d(rpc, DEP, "TestToken", ["string", "string", "uint8"], ["USD Coin (local test)", "USDC", 6], "LocalSim")
        w["weth"] = d(rpc, DEP, "TestToken", ["string", "string", "uint8"], ["Wrapped Ether (local test)", "WETH", 18], "LocalSim")
        w["feed"] = d(rpc, DEP, "SimFeed", ["string", "uint8", "int256"], ["ETH / USD", 8, 2000 * 10 ** 8], "LocalSim")
        w["oracle"] = d(rpc, DEP, "SimChainlinkOracle", ["address"] * 4 + ["uint256"], [w["feed"], ZERO, ZERO, ZERO, 10 ** 16], "LocalSim")
        c = devchain.call
        c(rpc, DEP, w["morpho"], "enableIrm(address)", [w["irm"]])
        c(rpc, DEP, w["morpho"], "enableLltv(uint256)", [86 * 10 ** 16])
        w["params"] = [w["usdc"], w["weth"], w["oracle"], w["irm"], 86 * 10 ** 16]
        c(rpc, DEP, w["morpho"], f"createMarket({MP})", [w["params"]])
        w["market_id"] = abi.market_id({"loan_token": w["usdc"], "collateral_token": w["weth"], "oracle": w["oracle"],
                                        "irm": w["irm"], "lltv_raw": 86 * 10 ** 16})
        c(rpc, DEP, w["usdc"], "mint(address,uint256)", [LP, 1_000_000 * USDC])
        c(rpc, LP, w["usdc"], "approve(address,uint256)", [w["morpho"], 2 ** 256 - 1])
        c(rpc, LP, w["morpho"], f"supply({MP},uint256,uint256,address,bytes)", [w["params"], 1_000_000 * USDC, 0, LP, b""])
        # the user's own position, opened BEFORE any crisis: 5 WETH at 2,000 = 10,000 USDC, 8,000 USDC debt (LTV 80%)
        c(rpc, DEP, w["weth"], "mint(address,uint256)", [USER, 10 * ETH])
        c(rpc, USER, w["weth"], "approve(address,uint256)", [w["morpho"], 2 ** 256 - 1])
        c(rpc, USER, w["morpho"], f"supplyCollateral({MP},uint256,address,bytes)", [w["params"], 5 * ETH, USER, b""])
        c(rpc, USER, w["morpho"], f"borrow({MP},uint256,uint256,address,address)", [w["params"], 8_000 * USDC, 0, USER, USER])
        w["vault"] = d(rpc, USER, "RescueVault", ["address", MP, "address", "address"], [w["morpho"], w["params"], USER, KEEPER])
        c(rpc, DEP, w["usdc"], "mint(address,uint256)", [USER, 10_000 * USDC])
        for t in ("usdc", "weth"):
            c(rpc, USER, w[t], "approve(address,uint256)", [w["vault"], 2 ** 256 - 1])
        w["signer"] = CastSigner(anvil_test_key(1))
        assert w["signer"].address.lower() == KEEPER.lower()
        yield w
    finally:
        node.stop()


@pytest.fixture()
def env(world, tmp_path):
    rpc = world["rpc"]
    snap = rpc.call("evm_snapshot", [])
    yield {**world, "journal": Journal(tmp_path / "journal")}
    rpc.call("evm_revert", [snap])


def arm(w, loan=3_000 * USDC, coll=ETH // 2, strategies=7, full_cap=9_000 * USDC, top_cap=ETH, **over):
    """The user's one-time setup before going offline: fund the reserve and sign the policy."""
    rpc = w["rpc"]
    now = rpc.block()["timestamp"]
    if loan:
        devchain.call(rpc, USER, w["vault"], "deposit(address,uint256)", [w["usdc"], loan])
    if coll:
        devchain.call(rpc, USER, w["vault"], "deposit(address,uint256)", [w["weth"], coll])
    pol = {"allowed_strategies": strategies, "valid_until": now + 30 * 86_400, "cooldown": 3_600, "trigger_ltv": 82 * 10 ** 16,
           "min_ltv_after": 40 * 10 ** 16, "max_repay_per_action": 2_500 * USDC, "max_top_up_per_action": top_cap,
           "max_full_repay": full_cap, "max_repay_total": 10_000 * USDC, "max_top_up_total": 2 * ETH,
           "min_loan_reserve": 50 * USDC if loan else 0, "min_collateral_reserve": ETH // 100 if coll else 0}
    pol.update(over)
    devchain.call(rpc, USER, w["vault"], POLICY_SIG, [[pol[k] for k in contracts.POLICY_FIELDS]])


def shock(w, usd: int, age_s: int = 0):
    """SIMULATED ETH/USD move on the local test feed (clearly a test input, not market data)."""
    ts = w["rpc"].block()["timestamp"]
    devchain.call(w["rpc"], DEP, w["feed"], "set(int256,uint256)", [usd * 10 ** 8, ts - age_s])


def cfg(w, **over):
    p = {"id": "P", "label": "WETH/USDC local test position", "rescue_vault": w["vault"],
         "engine": {"safety_margin": "200", "interest_horizon_s": 86_400},
         "scenarios": [{"id": "eth10", "label": "ETH / USD -10% follow-on", "shocks": [{"dependency": "ETH / USD", "drop": 0.10}]}],
         "retry_after_failed_s": 0, "realert_s": 0}
    p.update(over)
    return {"rpc_url": w["url"], "positions": [p], "limits": {"receipt_timeout_s": 20}}


def watcher(w, signer=True, **over):
    return Watcher(cfg(w, **over), RPC(w["url"]), w["journal"], w["signer"] if signer else None)


def states(w):
    return [e["state"] for e in w["journal"].entries("P")]


# ---- scenario 1 / 2 / 3 / 4 on the local chain ----------------------------------------------------------------------
def test_e2e_auto_repay_confirmed_without_user_signature(env):
    arm(env)
    user_nonce = env["rpc"].nonce(USER, "latest")
    shock(env, 1_880)  # -6%: LTV 80% -> 85.1% (trigger 82%, LLTV 86%)
    pos0, v0 = reader.read(env["rpc"], env["vault"])
    out = watcher(env).tick()[0]
    assert out["state"] == "CONFIRMED", out
    assert states(env) == ["DETECTED", "PLANNING", "VALIDATING", "EXECUTING", "CONFIRMED"]
    ver = out["verification"]
    assert ver["verified"] and all(c["ok"] for c in ver["checks"])
    assert out["chosen"]["strategy"] == "REPAY"
    pos1, v1 = reader.read(env["rpc"], env["vault"])
    assert pos1["debt"] < pos0["debt"] and pos1["collateral"] == pos0["collateral"]
    assert engine.ltv_wad(pos1["debt"], pos1["collateral"], pos1["price"]) < engine.ltv_wad(pos0["debt"], pos0["collateral"], pos0["price"])
    assert v0["loan_reserve"] - v1["loan_reserve"] == out["chosen"]["amount_raw"]
    tx = env["rpc"].transaction(out["tx_hash"])
    assert tx["from"].lower() == KEEPER.lower() and tx["to"].lower() == env["vault"].lower()
    assert env["rpc"].nonce(USER, "pending") == user_nonce, "the user signed nothing during the crisis"
    # the minimal amount really is what the engine said: 8,000 - (0.86 x 5 x 1,692 - 200) ~ 924.4 USDC (+ 1 day interest)
    assert 924 * USDC < out["chosen"]["amount_raw"] < 926 * USDC
    # next cycle: position inside the target again -> back to WATCHING, nothing spent
    assert watcher(env).tick()[0]["state"] == "WATCHING"


def test_e2e_auto_topup_when_usdc_reserve_insufficient(env):
    arm(env, loan=100 * USDC, coll=2 * ETH)
    shock(env, 1_880)
    out = watcher(env).tick()[0]
    assert out["state"] == "CONFIRMED", out
    plan = next(e for e in env["journal"].entries("P") if e["state"] == "PLANNING")["plan"]
    rep = next(c for c in plan["candidates"] if c["strategy"] == "REPAY")
    assert rep["rejected_at"] == "feasibility" and "reserve holds" in rep["reasons"][0]
    assert out["chosen"]["strategy"] == "TOP_UP"
    ev = out["verification"]["event"]
    assert ev["debt_before"] == ev["debt_after"] and ev["collateral_after"] - ev["collateral_before"] == ev["assets"]
    assert out["verification"]["verified"]


def test_e2e_no_safe_action_sends_nothing(env):
    arm(env, loan=100 * USDC, coll=ETH // 10, full_cap=0)
    shock(env, 1_880)
    n0 = env["rpc"].nonce(KEEPER, "latest")
    _, v0 = reader.read(env["rpc"], env["vault"])
    out = watcher(env).tick()[0]
    assert out["state"] == "NO_ACTION" and "no authorized action" in out["reason"]
    assert env["rpc"].nonce(KEEPER, "pending") == n0, "no transaction at all (not even an unmined one)"
    _, v1 = reader.read(env["rpc"], env["vault"])
    assert (v1["loan_reserve"], v1["collateral_reserve"]) == (v0["loan_reserve"], v0["collateral_reserve"])


def test_e2e_emergency_full_repay(env):
    arm(env, loan=9_000 * USDC, coll=0, strategies=4)
    shock(env, 1_880)
    out = watcher(env).tick()[0]
    assert out["state"] == "CONFIRMED" and out["chosen"]["strategy"] == "FULL_REPAY"
    pos1, _ = reader.read(env["rpc"], env["vault"])
    assert pos1["borrow_shares"] == 0 and pos1["collateral"] == 5 * ETH  # debt closed, collateral NOT sold


def test_e2e_hold_when_healthy_and_alert_below_trigger(env):
    arm(env)
    mild = [{"id": "eth3", "label": "ETH / USD -3%", "shocks": [{"dependency": "ETH / USD", "drop": 0.03}]}]
    out = watcher(env, scenarios=mild).tick()[0]
    assert out["state"] == "WATCHING" and out["decision"] == "HOLD"
    shock(env, 1_960)  # -2%: LTV 81.6% < trigger 82%, but the -3% scenario now breaks the 200 USDC margin
    out = watcher(env, scenarios=mild).tick()[0]
    assert out["state"] == "NO_ACTION" and "ALERT only" in out["reason"]
    # at 80% LTV the default -10% follow-on scenario already breaks the margin: alert, never a transaction
    assert watcher(env).tick()[0]["state"] == "NO_ACTION"


# ---- failure handling ------------------------------------------------------------------------------------------------
def test_e2e_stale_feed_means_no_action(env):
    arm(env)
    shock(env, 1_880, age_s=6 * 3_600)
    out = watcher(env).tick()[0]
    assert out["state"] == "NO_ACTION" and "stale" in out["reason"]


def test_e2e_rpc_down_is_handled(env, tmp_path):
    w = Watcher(cfg(env), RPC(f"http://127.0.0.1:{_free_port()}", timeout=1, retries=0), Journal(tmp_path / "j2"), None)
    out = w.tick()[0]
    assert out["state"] == "WATCHING" and out["event"] == "rpc_error"


def test_e2e_gas_cap_and_watch_only(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)
    w.executor.limits["max_gas_units"] = 10_000
    out = w.tick()[0]
    assert out["state"] == "NO_ACTION" and "gas estimate" in out["reason"]
    out = watcher(env, signer=False).tick()[0]
    assert out["state"] == "NO_ACTION" and "watch-only" in out["reason"]


def test_e2e_onchain_revert_is_failed_not_retried_blindly(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)
    orig = w.executor.send

    def race(vault, chosen, val, on_signed):  # the owner pauses between validation and inclusion
        devchain.call(env["rpc"], USER, env["vault"], "setPaused(bool)", [True])
        return orig(vault, chosen, val, on_signed)
    w.executor.send = race
    _, v0 = reader.read(env["rpc"], env["vault"])
    out = w.tick()[0]
    assert out["state"] == "FAILED" and "IsPaused" in out["reason"]
    _, v1 = reader.read(env["rpc"], env["vault"])
    assert v1["loan_reserve"] == v0["loan_reserve"] and v1["action_count"] == 0
    assert watcher(env).tick()[0]["state"] == "NO_ACTION"  # still paused: refused before sending anything


def test_e2e_keeper_killed_after_broadcast_resumes_without_resending(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)

    def killed(tx_hash):
        raise SystemError("keeper process killed before reading the receipt")
    w.executor.wait = killed
    n_before = env["rpc"].nonce(KEEPER, "latest")
    first = w.tick()[0]
    pend = env["journal"].pending("P")
    assert first["event"] == "internal_error" and pend
    # no nonce snapshot here: Anvil's automine may answer eth_sendRawTransaction before mining the block
    out = watcher(env).tick()[0]  # a NEW keeper process on the same journal
    assert out["state"] == "CONFIRMED" and out["verification"]["verified"]
    assert out["tx_hash"].lower() == pend["tx_hash"].lower(), "the journaled transaction is the one confirmed"
    assert env["rpc"].nonce(KEEPER, "latest") == n_before + 1, "exactly one keeper transaction: nothing re-sent after the restart"
    assert reader.read(env["rpc"], env["vault"])[1]["action_count"] == 1
    assert env["journal"].pending("P") is None


def test_e2e_ambiguous_broadcast_resolved_from_chain(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)
    real = w.rpc.send_raw

    def flaky(raw):
        real(raw)
        raise RPCError("eth_sendRawTransaction: read timeout")
    w.rpc.send_raw = flaky
    out = w.tick()[0]
    assert out["state"] == "CONFIRMED" and reader.read(env["rpc"], env["vault"])[1]["action_count"] == 1


def test_e2e_dropped_transaction_is_failed_then_replanned(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)

    def lost(raw):
        raise RPCError("eth_sendRawTransaction: connection reset")
    w.rpc.send_raw = lost
    out = w.tick()[0]
    assert out["state"] == "FAILED" and "did not execute" in out["reason"]
    assert reader.read(env["rpc"], env["vault"])[1]["action_count"] == 0
    again = watcher(env).tick()[0]
    assert again["state"] == "CONFIRMED"
    assert len([e for e in env["journal"].entries("P") if e["state"] == "EXECUTING"]) == 2  # re-planned, then executed once
    assert reader.read(env["rpc"], env["vault"])[1]["action_count"] == 1


def test_e2e_price_moves_during_validation_replans(env):
    arm(env)
    shock(env, 1_880)
    w = watcher(env)
    real = w._observe
    calls = {"n": 0}

    def moving(p, block="latest"):
        calls["n"] += 1
        if calls["n"] == 2:
            shock(env, 1_860)  # the market keeps falling between planning and validation
        return real(p, block)
    w._observe = moving
    out = w.tick()[0]
    assert out["state"] == "CONFIRMED"
    val = next(e for e in env["journal"].entries("P") if e["state"] == "VALIDATING")
    assert val["amount_changed"] is True and val["validated_block"] > val["planned_block"]


def test_e2e_duplicate_and_malicious_keeper_transactions_fail(env):
    arm(env)
    shock(env, 1_880)
    out = watcher(env).tick()[0]
    assert out["state"] == "CONFIRMED"
    rpc, s, vault = env["rpc"], env["signer"], env["vault"]
    _, v0 = reader.read(rpc, vault)
    nonce0 = v0["policy_nonce"]

    def keeper_tx(data):
        t = {"to": vault, "data": data, "chain_id": 31337, "nonce": rpc.nonce(KEEPER), "gas": 500_000,
             "max_fee_per_gas": 50 * 10 ** 9, "max_priority_fee_per_gas": 10 ** 9}
        h = rpc.send_raw(s.sign(t, rpc.url))
        from defirisk.countermove.executor import GuardedExecutor
        return GuardedExecutor(rpc, None).wait(h, 20)
    devchain.mine(rpc, 3_601)  # past the cooldown, still at risk after a deeper simulated leg
    shock(env, 1_700)
    attempts = [
        contracts.execute_calldata("REPAY", out["chosen"]["action_id"], 100 * USDC, nonce0, 10 ** 18),  # replayed id
        contracts.execute_calldata("REPAY", "0x" + "ab" * 32, 2_500 * USDC + 1, nonce0, 10 ** 18),  # above cap
        contracts.execute_calldata("TOP_UP", "0x" + "cd" * 32, ETH, nonce0, 10 ** 18),  # beyond reserve floor
        abi.encode_call("withdrawReserve(address,uint256)", [env["usdc"], 1]),  # owner-only
        abi.encode_call("setKeeper(address)", [ATTACKER]),  # owner-only
        abi.encode_call("transfer(address,uint256)", [ATTACKER, 1]),  # no such function
    ]
    for data in attempts:
        rc = keeper_tx(data)
        assert int(rc["status"], 16) == 0, data[:10]
    _, v1 = reader.read(rpc, vault)
    assert (v1["loan_reserve"], v1["collateral_reserve"], v1["keeper"].lower()) == (v0["loan_reserve"], v0["collateral_reserve"], KEEPER.lower())
    for tok in ("usdc", "weth"):
        assert rpc.read(env[tok], "balanceOf(address)", [ATTACKER]) == 0


def test_chain_guard_refuses_non_local(monkeypatch):
    r = RPC("https://eth.example.org")
    monkeypatch.setattr(r, "chain_id", lambda: 1)
    with pytest.raises(chainmod.UnsafeChainError):
        r.assert_local()
    r2 = RPC("http://127.0.0.1:8545")
    monkeypatch.setattr(r2, "chain_id", lambda: 1)  # a mainnet fork that kept chain id 1 is refused too
    with pytest.raises(chainmod.UnsafeChainError):
        r2.assert_local()


def test_bindings_match_compiled_abi():
    a = contracts.artifact()["abi"]
    names = {f"{x['name']}({','.join(i['type'] if i['type'] != 'tuple' else '(' + ','.join(c['type'] for c in i['components']) + ')' for i in x['inputs'])})"
             for x in a if x["type"] in ("function", "event", "error")}
    for sig in ("executeRepay(bytes32,uint256,uint256,uint256)", "executeTopUp(bytes32,uint256,uint256,uint256)",
                "executeFullRepay(bytes32,uint256,uint256)", contracts.RESCUE_EXECUTED, POLICY_SIG):
        assert sig in names, sig
    for sig in contracts.ERRORS:
        if sig.split("(")[0] in ("ReentrancyGuardReentrantCall", "SafeERC20FailedOperation", "Error", "Panic"):
            continue
        assert sig in names, sig
    assert Path(contracts.ARTIFACT).exists()
