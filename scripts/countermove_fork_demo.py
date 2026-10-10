"""FAULTLINE Phase 2 - reproducible Autonomous Countermove demo on an Ethereum MAINNET FORK (local Anvil, chain id 31337).

Real contracts and markets: Morpho Blue 0xBBBB...EFFCb, weETH/USDC and cbBTC/USDC markets (LLTV 86%) and the
PT-reUSD-10DEC2026/USDC market (LLTV 91.5%) with their real MorphoChainlinkOracleV2 oracles, real IRMs, real liquidity,
at a pinned block. Test funds are written into local storage; the crises are SIMULATED controlled shocks of one real
dependency each (feed code replaced on the fork only).

    $env:PYTHONPATH='src'; python scripts/countermove_fork_demo.py [--fork-block N] [--port 8547] [--keep-alive]

Phase A  "LRT crisis": weETH/ETH exchange rate -9% (SIMULATED); positions opened at 75% LTV -> 82.4% (trigger 82%)
         S1 user A, funded USDC reserve           -> AUTO-REPAY executed, confirmed, verified
         S3 user C, tiny reserves, no full repay  -> NO ACTION (nothing sent), reasons explained
Phase B  "BTC crisis": BTC / USD -9% (SIMULATED)
         S2 user B, USDC reserve too small, cbBTC reserve -> AUTO-TOP-UP executed, confirmed, verified
         S4 user D, policy = full close only, USDC reserve -> EMERGENCY FULL REPAY executed, confirmed, verified
Phase C  "PT oracle incident" (the Belem brief's own example: a Pendle PT used as collateral on a lending market, incident
         on the oracle pricing the PT): the Ojo PT feed of the PT-reUSD market -5% (SIMULATED); opened at 85% LTV -> 89.5%
         (trigger 88%, LLTV 91.5%)
         S5 user E, USDC AND PT reserves, repay or top-up allowed -> both reach the target; AUTO-REPAY chosen (least
            reserve value committed, and no extra exposure to the PT oracle in incident), confirmed, verified
S5's user arms after phase B (still before ITS crisis), so S1-S4 run on exactly the same blocks as without S5.
Each user signs ONLY before the crisis (position, vault, reserve, policy). The keeper runs as a separate process
(`python -m defirisk.countermove`) holding only the keeper's test key, in an encrypted keystore created for the run
(never on a command line): user nonces are checked unchanged afterwards.
Nothing is ever sent to mainnet: the RPC is a loopback Anvil, every signer refuses other chains.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defirisk import abi  # noqa: E402
from defirisk.countermove import contracts, devchain, reader  # noqa: E402
from defirisk.countermove.chain import RPC  # noqa: E402
from defirisk.countermove.signer import KEYSTORE_ENV, PASSWORD_FILE_ENV, import_test_keystore  # noqa: E402

FORK_BLOCK = 26_164_248
DEFAULT_FORK_RPC = "https://eth-mainnet.public.blastapi.io"
FORK_RPC = os.environ.get("FORK_RPC_URL", DEFAULT_FORK_RPC)
# a custom endpoint URL may embed an API key: only the public default is written into the recorded evidence
FORK_RPC_LABEL = FORK_RPC if FORK_RPC == DEFAULT_FORK_RPC else "custom FORK_RPC_URL (not recorded)"
MORPHO = contracts.MORPHO_BLUE
WEETH_USDC = "0x85252bb8485c99bba46fe149c7dd2aad83672640f53c630890673cf1848ba16e"
CBBTC_USDC = "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64"
PT_REUSD_USDC = "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64"  # PT-reUSD-10DEC2026 / USDC, LLTV 91.5%
A = devchain.ACCOUNTS
KEEPER, USER_A, USER_B, USER_C, USER_D, USER_E = A[1], A[2], A[3], A[4], A[5], A[6]
MP = "(address,address,address,address,uint256)"
POLICY_SIG = "setPolicy((uint8,uint64,uint32,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256))"
OUT = ROOT / "data" / "countermove" / "demo" / "latest"
USDC = 10 ** 6
PT = 10 ** 6  # PT-reUSD-10DEC2026 has 6 decimals


def mp_tuple(mp: dict) -> list:
    return [mp["loan_token"], mp["collateral_token"], mp["oracle"], mp["irm"], mp["lltv_raw"]]


def open_position(rpc: RPC, user: str, market_id: str, coll_raw: int, ltv_bps: int) -> dict:
    """The user's own Morpho position (opened before any crisis), funded with LOCAL TEST tokens."""
    mp = contracts.market_params(rpc, MORPHO, market_id)
    devchain.set_token_balance(rpc, mp["collateral_token"], user, coll_raw)
    devchain.call(rpc, user, mp["collateral_token"], "approve(address,uint256)", [MORPHO, 2 ** 256 - 1])
    devchain.call(rpc, user, MORPHO, f"supplyCollateral({MP},uint256,address,bytes)", [mp_tuple(mp), coll_raw, user, b""])
    price = contracts.oracle_price(rpc, mp["oracle"])
    borrow = coll_raw * price // 10 ** 36 * ltv_bps // 10_000
    devchain.call(rpc, user, MORPHO, f"borrow({MP},uint256,uint256,address,address)", [mp_tuple(mp), borrow, 0, user, user])
    return {"market_id": market_id, "params": mp, "collateral_raw": coll_raw, "borrowed_raw": borrow, "oracle_price": price}


def arm(rpc: RPC, user: str, mp: dict, loan_reserve: int, coll_reserve: int, policy: dict) -> str:
    """The user's one-time pre-crisis setup: deploy the RescueVault, fund the reserve, sign the policy."""
    vault = devchain.deploy(rpc, user, "RescueVault", ["address", MP, "address", "address"], [MORPHO, mp_tuple(mp), user, KEEPER])
    for tok, amt in ((mp["loan_token"], loan_reserve), (mp["collateral_token"], coll_reserve)):
        if amt:
            bal = rpc.read(tok, "balanceOf(address)", [user])
            devchain.set_token_balance(rpc, tok, user, bal + amt)
            devchain.call(rpc, user, tok, "approve(address,uint256)", [vault, amt])
            devchain.call(rpc, user, vault, "deposit(address,uint256)", [tok, amt])
    now = rpc.block()["timestamp"]
    pol = {"allowed_strategies": 7, "valid_until": now + 30 * 86_400, "cooldown": 3_600, "trigger_ltv": 82 * 10 ** 16,
           "min_ltv_after": 40 * 10 ** 16, "max_repay_per_action": 0, "max_top_up_per_action": 0, "max_full_repay": 0,
           "max_repay_total": 0, "max_top_up_total": 0, "min_loan_reserve": 0, "min_collateral_reserve": 0, **policy}
    devchain.call(rpc, user, vault, POLICY_SIG, [[pol[k] for k in contracts.POLICY_FIELDS]])
    return vault


def position_cfg(pid: str, label: str, vault: str, scenario_role: str, scenario_label: str, drop: float = 0.08) -> dict:
    return {"id": pid, "label": label, "rescue_vault": vault,
            "engine": {"safety_margin": "250", "interest_horizon_s": 86_400, "ranking": "min_capital"},
            "scenarios": [{"id": "follow_on", "label": scenario_label, "shocks": [{"dependency": scenario_role, "drop": drop}]}],
            "retry_after_failed_s": 0, "realert_s": 0}


def pt_feed(rpc: RPC, oracle: str) -> tuple[str, str]:
    """(address, role) of the feed that prices the PT in the market oracle: the dependency in incident for S5."""
    for role in ("BASE_FEED_1", "BASE_FEED_2"):
        addr = rpc.read(oracle, f"{role}()", [], "address")
        if int(addr, 16) and " PT " in f" {rpc.read(addr, 'description()', [], 'string')} ":
            return addr, role
    raise RuntimeError(f"no PT feed found in oracle {oracle}")


def run_keeper(rpc_url: str, positions: list[dict], journal_dir: Path, tag: str, until_terminal: bool,
               keystore: tuple[Path, Path]) -> dict:
    """The keeper as an independent OS process (no browser, no user key): python -m defirisk.countermove.
    It gets only the PATHS of its encrypted keystore and password file: no key on any command line or in its environment."""
    cfg_path = journal_dir / f"keeper_config_{tag}.json"
    cfg_path.write_text(json.dumps({"rpc_url": rpc_url, "positions": positions,
                                    "limits": {"receipt_timeout_s": 60, "max_gas_units": 700_000}}, indent=1), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FAULTLINE_USER", "FAULTLINE_KEEPER"))}
    env.update(PYTHONPATH=str(ROOT / "src"), **{KEYSTORE_ENV: str(keystore[0]), PASSWORD_FILE_ENV: str(keystore[1])})
    # repository-relative paths (the process runs from ROOT): the recorded command is complete and machine-independent
    args = [sys.executable, "-m", "defirisk.countermove", "--config", cfg_path.relative_to(ROOT).as_posix(),
            "--journal-dir", journal_dir.relative_to(ROOT).as_posix(), "--interval", "1"]
    args += ["--until-terminal", "--max-ticks", "6"] if until_terminal else ["--once"]
    t0 = time.time()
    r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=900, cwd=str(ROOT))
    if r.returncode != 0:
        raise RuntimeError(f"keeper process failed: {r.stderr[-2000:]}")
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.strip().startswith("{")]
    return {"tag": tag, "command": "python -m defirisk.countermove " + " ".join(args[3:]),
            "seconds": round(time.time() - t0, 1), "stderr_head": r.stderr.strip().splitlines()[:2], "results": lines}


def _ev(entries: list[dict], state: str) -> dict | None:
    return next((e for e in reversed(entries) if e["state"] == state), None)


def scenario_record(rpc: RPC, journal: list[dict], pid: str, meta: dict) -> dict:
    es = [e for e in journal if e["position"] == pid]
    conf, plan, det, noact, val, exe = (_ev(es, s) for s in ("CONFIRMED", "PLANNING", "DETECTED", "NO_ACTION", "VALIDATING", "EXECUTING"))
    terminal = [e for e in es if e["state"] in ("CONFIRMED", "FAILED", "NO_ACTION")]
    rec = {**meta, "states": [e["state"] for e in es], "final_state": terminal[0]["state"] if terminal else None,
           "post_crisis_state": es[-1]["state"] if es else None,
           "detected": det and {"trigger": det.get("trigger"), "movers": det.get("movers"),
                                "simulated_dependencies": det.get("simulated_dependencies")},
           "plan": plan and plan.get("plan"), "validation": val and val.get("validation"),
           "no_action_reason": noact and noact.get("reason")}
    if conf:
        tx = rpc.transaction(conf["tx_hash"])
        rc = rpc.receipt(conf["tx_hash"])
        rec["execution"] = {"tx_hash": conf["tx_hash"], "block": int(rc["blockNumber"], 16), "from": tx["from"], "to": tx["to"],
                            "status": int(rc["status"], 16), "gas_used": int(rc["gasUsed"], 16),
                            "effective_gas_price_wei": int(rc.get("effectiveGasPrice", "0x0"), 16),
                            "signed_by": "keeper (anvil test account #1) - no user signature", "action_id": exe and exe.get("action_id")}
        rec["verification"] = conf["verification"]
        rec["chosen"] = conf["chosen"]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fork-block", type=int, default=FORK_BLOCK)
    ap.add_argument("--port", type=int, default=8547)
    ap.add_argument("--keep-alive", action="store_true", help="leave the fork running for the UI (Ctrl+C to stop)")
    a = ap.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    t0 = time.time()
    key_dir = Path(tempfile.mkdtemp(prefix="faultline_keeper_"))  # outside the repository, deleted at the end
    keystore = import_test_keystore(1, key_dir)
    node = devchain.Anvil(a.port, FORK_RPC, a.fork_block, log=OUT / "anvil.log").start(timeout=300)
    rpc = RPC(node.url, timeout=60)
    try:
        rpc.assert_local()
        fork_blk = rpc.block()
        print(f"fork of mainnet block {a.fork_block} on {node.url} (chain id {rpc.chain_id()})")
        weeth_mp = contracts.market_params(rpc, MORPHO, WEETH_USDC)
        cbbtc_mp = contracts.market_params(rpc, MORPHO, CBBTC_USDC)
        weeth_rate_feed = rpc.read(weeth_mp["oracle"], "BASE_FEED_1()", [], "address")
        btc_usd_feed = rpc.read(cbbtc_mp["oracle"], "BASE_FEED_1()", [], "address")

        # ---- before the crisis: each user opens a position, deploys a RescueVault, funds it, signs a policy -------------
        pos = {"A": open_position(rpc, USER_A, WEETH_USDC, 10 * 10 ** 18, 7_500),
               "C": open_position(rpc, USER_C, WEETH_USDC, 4 * 10 ** 18, 7_500),
               "B": open_position(rpc, USER_B, CBBTC_USDC, 50_000_000, 7_500),
               "D": open_position(rpc, USER_D, CBBTC_USDC, 30_000_000, 7_500)}
        common = {"max_repay_total": 30_000 * USDC}
        vaults = {
            "A": arm(rpc, USER_A, weeth_mp, 5_000 * USDC, 5 * 10 ** 16, {**common, "max_repay_per_action": 5_000 * USDC,
                     "max_top_up_per_action": 10 ** 18, "max_top_up_total": 10 ** 18, "max_full_repay": 25_000 * USDC,
                     "min_loan_reserve": 100 * USDC, "min_collateral_reserve": 10 ** 16}),
            "C": arm(rpc, USER_C, weeth_mp, 150 * USDC, 10 ** 16, {**common, "max_repay_per_action": 2_000 * USDC,
                     "max_top_up_per_action": 10 ** 18, "max_top_up_total": 10 ** 18, "max_full_repay": 0}),
            "B": arm(rpc, USER_B, cbbtc_mp, 100 * USDC, 20_000_000, {**common, "max_repay_per_action": 5_000 * USDC,
                     "max_top_up_per_action": 15_000_000, "max_top_up_total": 20_000_000, "max_full_repay": 0,
                     "min_collateral_reserve": 100_000}),
            "D": arm(rpc, USER_D, cbbtc_mp, 21_000 * USDC, 0, {**common, "allowed_strategies": 4,
                     "max_full_repay": 25_000 * USDC, "min_loan_reserve": 100 * USDC}),
        }
        armed_nonces = {k: rpc.nonce(u, "latest") for k, u in (("A", USER_A), ("B", USER_B), ("C", USER_C), ("D", USER_D))}
        pcfg = {"A": position_cfg("S1-weETH-repay", "S1 | user A | weETH/USDC | USDC reserve", vaults["A"], "BASE_FEED_2",
                                  "ETH / USD -8% follow-on"),
                "C": position_cfg("S3-weETH-no-action", "S3 | user C | weETH/USDC | tiny reserves, full repay disabled",
                                  vaults["C"], "BASE_FEED_2", "ETH / USD -8% follow-on"),
                "B": position_cfg("S2-cbBTC-topup", "S2 | user B | cbBTC/USDC | cbBTC reserve, 100 USDC", vaults["B"],
                                  "BASE_FEED_1", "BTC / USD -8% follow-on"),
                "D": position_cfg("S4-cbBTC-full-repay", "S4 | user D | cbBTC/USDC | policy: close the debt", vaults["D"],
                                  "BASE_FEED_1", "BTC / USD -8% follow-on")}
        before = {k: reader.read(rpc, v)[0] for k, v in vaults.items()}
        runs = [run_keeper(node.url, list(pcfg.values()), OUT, "pre_crisis", False, keystore)]

        # ---- phase A: SIMULATED LRT crisis (one real dependency of the weETH market) ----------------------------------
        shock_a = devchain.shock_feed(rpc, weeth_rate_feed, 900)
        runs.append(run_keeper(node.url, [pcfg["A"], pcfg["C"]], OUT, "phase_A_weETH", True, keystore))
        # ---- phase B: SIMULATED BTC crisis (the cbBTC market's only feed) --------------------------------------------
        shock_b = devchain.shock_feed(rpc, btc_usd_feed, 900)
        runs.append(run_keeper(node.url, [pcfg["B"], pcfg["D"]], OUT, "phase_B_cbBTC", True, keystore))

        # ---- S5, the Belem brief's example: user E borrows USDC against a Pendle PT, arms BEFORE the PT incident -----
        # (armed after phase B so that S1-S4 run on exactly the same blocks, hence the same transactions, as before S5)
        pt_mp = contracts.market_params(rpc, MORPHO, PT_REUSD_USDC)
        pt_feed_addr, pt_role = pt_feed(rpc, pt_mp["oracle"])
        pos["E"] = open_position(rpc, USER_E, PT_REUSD_USDC, 50_000 * PT, 8_500)
        vaults["E"] = arm(rpc, USER_E, pt_mp, 3_000 * USDC, 5_000 * PT, {
            "allowed_strategies": 3, "trigger_ltv": 88 * 10 ** 16, "max_repay_per_action": 2_500 * USDC,
            "max_repay_total": 30_000 * USDC, "max_top_up_per_action": 2_500 * PT, "max_top_up_total": 5_000 * PT,
            "max_full_repay": 0, "min_loan_reserve": 100 * USDC, "min_collateral_reserve": 100 * PT})
        armed_nonces["E"] = rpc.nonce(USER_E, "latest")
        pcfg["E"] = position_cfg("S5-PT-reUSD-repay", "S5 | user E | PT-reUSD/USDC | USDC + PT reserves, PT oracle incident",
                                 vaults["E"], pt_role, "PT feed -5% follow-on", drop=0.05)
        before["E"] = reader.read(rpc, vaults["E"])[0]
        runs.append(run_keeper(node.url, [pcfg["E"]], OUT, "pre_crisis_S5", False, keystore))
        # ---- phase C: SIMULATED incident on the oracle pricing the PT (the market's only feed) ---------------------
        shock_c = devchain.shock_feed(rpc, pt_feed_addr, 500)
        runs.append(run_keeper(node.url, [pcfg["E"]], OUT, "phase_C_PT", True, keystore))
        # ---- after: one more keeper pass over everyone ---------------------------------------------------------------
        runs.append(run_keeper(node.url, list(pcfg.values()), OUT, "post_crisis", False, keystore))

        journal = [json.loads(x) for x in (OUT / "journal.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        users = {"A": USER_A, "B": USER_B, "C": USER_C, "D": USER_D, "E": USER_E}
        after_nonces = {k: rpc.nonce(u, "latest") for k, u in users.items()}
        shocks = {"A": shock_a, "B": shock_b, "C": shock_c}
        scen = []
        for k, sid, expect, strategy, shock_key in (
                ("A", "S1", "CONFIRMED", "REPAY", "A"), ("B", "S2", "CONFIRMED", "TOP_UP", "B"),
                ("C", "S3", "NO_ACTION", None, "A"), ("D", "S4", "CONFIRMED", "FULL_REPAY", "B"),
                ("E", "S5", "CONFIRMED", "REPAY", "C")):
            after = reader.read(rpc, vaults[k])
            meta = {"scenario": sid, "position_id": pcfg[k]["id"], "label": pcfg[k]["label"], "user": users[k],
                    "rescue_vault": vaults[k], "market_id": pos[k]["market_id"],
                    "expected_final_state": expect, "expected_strategy": strategy, "simulated_shock": shocks[shock_key],
                    "position_opened": {kk: vv for kk, vv in pos[k].items() if kk != "params"},
                    "before_shock": {kk: before[k][kk] for kk in ("block", "collateral", "debt", "price", "borrow_shares")},
                    "end_state": {kk: after[0][kk] for kk in ("block", "collateral", "debt", "price", "borrow_shares")},
                    "end_vault": {kk: after[1][kk] for kk in ("loan_reserve", "collateral_reserve", "repaid_total",
                                                             "topped_up_total", "action_count", "policy_nonce", "paused")},
                    "user_nonce_after_arming": armed_nonces[k], "user_nonce_at_end": after_nonces[k],
                    "user_signed_during_crisis": after_nonces[k] != armed_nonces[k]}
            scen.append(scenario_record(rpc, journal, pcfg[k]["id"], meta))
        ok = all(s["final_state"] == s["expected_final_state"] for s in scen) and not any(s["user_signed_during_crisis"] for s in scen)
        ok = ok and all(s.get("verification", {}).get("verified") for s in scen if s["expected_final_state"] == "CONFIRMED")
        ok = ok and all((s.get("chosen") or {}).get("strategy") == s["expected_strategy"] for s in scen)
        summary = {"schema": "faultline.countermove-demo/1", "generated_at": time.time(),
                   "environment": {"kind": "local Anvil fork of Ethereum mainnet (SIMULATED environment)",
                                   "fork_rpc": FORK_RPC_LABEL, "fork_block": a.fork_block, "fork_block_timestamp": fork_blk["timestamp"],
                                   "chain_id": rpc.chain_id(), "rpc": node.url, "morpho_blue": MORPHO,
                                   "markets": {"weETH/USDC": WEETH_USDC, "cbBTC/USDC": CBBTC_USDC,
                                               "PT-reUSD-10DEC2026/USDC": PT_REUSD_USDC},
                                   "keeper": KEEPER, "notes": ["real Morpho Blue, markets, oracles, IRMs and liquidity at the pinned block",
                                                               "test funds written into local storage (not real tokens)",
                                                               "price crises are SIMULATED controlled shocks of one real feed each",
                                                               "keeper key used from an encrypted keystore created for the run "
                                                               "(never on a command line)",
                                                               "no transaction was sent to Ethereum mainnet"]},
                   "scenarios": scen, "keeper_runs": runs, "all_expected": ok,
                   "duration_s": round(time.time() - t0, 1)}
        (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        for s in scen:
            ex = s.get("execution") or {}
            print(f"{s['scenario']} {s['label'][:52]:52s} -> {s['final_state']:9s} {ex.get('tx_hash', s.get('no_action_reason') or '')[:90]}")
        print(f"all expected outcomes: {ok}; summary: {OUT / 'summary.json'}")
        if a.keep_alive:
            print("fork kept alive for the UI; Ctrl+C to stop")
            while True:
                time.sleep(3600)
        return 0 if ok else 1
    finally:
        node.stop()
        shutil.rmtree(key_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
