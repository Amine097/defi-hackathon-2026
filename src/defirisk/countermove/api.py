"""Backend of the Countermove page (GET /api/countermove): every figure the UI shows is computed here, never in JS.

Sources, each labelled:
  * SIMULATED   the recorded local mainnet-FORK run (data/countermove/demo/latest): real Morpho markets / oracles at a
                pinned block, test funds, controlled shocks. Transactions there are CONFIRMED only with a receipt AND a
                passed verification; otherwise FAILED / NO ACTION.
  * LIVE        optional (?live=1): the same markets' oracle dependencies read now on Ethereum mainnet (read-only).
Also: a policy draft validator / encoder (the USER signs setPolicy with their wallet; FAULTLINE never holds that key).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import abi
from . import contracts, dependencies, engine
from .chain import RPC

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "data" / "countermove" / "demo" / "latest"
FIRST_HITS = (0.05, 0.09, 0.12, 0.15)
LIVE_RPCS = ("https://eth-mainnet.public.blastapi.io", "https://1rpc.io/eth", "https://eth.drpc.org")


def _h(raw, dec):
    return None if raw is None else int(raw) / 10 ** dec


def _js(o):
    if isinstance(o, bool) or o is None:
        return o
    if isinstance(o, int):
        return str(o) if abs(o) > 2 ** 53 else o
    if isinstance(o, float):
        return o if o == o and abs(o) != float("inf") else None
    if isinstance(o, dict):
        return {k: _js(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_js(v) for v in o]
    return o


def _entries(demo: Path) -> list[dict]:
    p = demo / "journal.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def _first(es, state, key=None):
    return next((e for e in es if e["state"] == state and (key is None or e.get(key) is not None)), None)


def _last(es, state):
    return next((e for e in reversed(es) if e["state"] == state), None)


def reserve_requirements(snap: dict, pcfg: dict) -> list[dict]:
    """Backend what-if for 'which reserves would I need': after a first hit of h on the collateral price, the minimal
    repay / top-up that keeps the configured follow-on scenarios inside the margin (same engine, exact integers)."""
    raw = snap["raw"]
    ld, cd = snap["loan"]["decimals"], snap["collateral"]["decimals"]
    ecfg = engine.EngineConfig(safety_margin_raw=int(float(pcfg["engine"]["safety_margin"]) * 10 ** ld),
                               interest_horizon_s=int(pcfg["engine"].get("interest_horizon_s", 86_400)))
    follow = [engine.Scenario("now", "current", engine.WAD)]
    for s in pcfg.get("scenarios", []):
        f = engine.WAD
        for sh in s["shocks"]:
            f = f * (engine.WAD - int(round(sh["drop"] * engine.WAD))) // engine.WAD  # base-feed falls (the configured ones)
        follow.append(engine.Scenario(s["id"], s.get("label", s["id"]), f))
    out = []
    for hit in FIRST_HITS:
        pos = {"collateral": int(raw["collateral"]), "debt": int(raw["debt"]), "price": int(raw["price"]) * (10_000 - int(hit * 10_000)) // 10_000,
               "lltv": int(raw["lltv"]), "rate_per_s": raw.get("rate_per_s")}
        r = engine.min_repay(pos, follow, ecfg)
        q = engine.min_top_up(pos, follow, ecfg)
        ltv = engine.ltv_wad(pos["debt"], pos["collateral"], pos["price"])
        out.append({"first_hit": hit, "ltv_after_hit": None if ltv is None else ltv / 1e18,
                    "liquidatable_after_hit": engine.max_borrow(pos["collateral"], pos["price"], pos["lltv"]) < pos["debt"],
                    "min_repay": _h(r, ld), "repay_possible": r is not None,
                    "min_top_up": _h(q, cd), "min_top_up_value": _h(engine.collateral_value(q, pos["price"]) if q else 0, ld),
                    "full_repay": _h(pos["debt"], ld)})
    return out


def _cand_view(c: dict, ld: int, cd: int) -> dict:
    dec = cd if c["strategy"] == "TOP_UP" else ld
    a = c.get("after") or {}
    m = c.get("metrics") or {}
    return {"strategy": c["strategy"], "status": c["status"], "rejected_at": c.get("rejected_at"), "reasons": c.get("reasons", []),
            "rank": c.get("rank"), "token": (c.get("token") or {}).get("symbol"),
            "required": _h(c.get("required_raw"), dec), "reserve": _h(c.get("reserve_raw"), dec),
            "reserve_floor": _h(c.get("reserve_floor_raw"), dec), "per_action_cap": _h(c.get("per_action_cap_raw"), dec),
            "cumulative_left": _h(c.get("cumulative_left_raw"), dec),
            "capital_committed": _h(m.get("capital_committed_raw"), ld), "principal_repaid": _h(m.get("principal_repaid_raw"), ld),
            "collateral_added": _h(m.get("collateral_added_raw"), cd), "exposure_added_value": _h(m.get("exposure_added_value_raw"), ld),
            "reserve_share_used": m.get("reserve_share_used"),
            "ltv_after": None if a.get("ltv_now") is None else int(a["ltv_now"]) / 1e18,
            "worst_buffer_after": _h(a.get("min_buffer"), ld), "meets_target": a.get("meets_target"),
            "hypothetical_penalty_after": _h(m.get("hypothetical_liquidation_penalty_after_raw"), ld),
            "scenarios_after": [{"label": r["label"], "buffer": _h(r["buffer"], ld), "liquidatable": r["liquidatable"],
                                 "ltv": None if r["ltv"] is None else int(r["ltv"]) / 1e18} for r in a.get("scenarios", [])]}


def position_view(sc: dict, es: list[dict], pcfg: dict | None) -> dict:
    pre = _first(es, "WATCHING", "snapshot")
    det = _first(es, "DETECTED")
    plan_e = _first(es, "PLANNING")
    val = _first(es, "VALIDATING")
    exe = _first(es, "EXECUTING", "tx_hash")
    term = next((e for e in es if e["state"] in ("CONFIRMED", "FAILED", "NO_ACTION")), None)
    last_snap = next((e.get("snapshot") for e in reversed(es) if e.get("snapshot")), None)
    snap0 = (pre or {}).get("snapshot") or (det or {}).get("snapshot") or {}
    ld = snap0.get("loan", {}).get("decimals", 6)
    cd = snap0.get("collateral", {}).get("decimals", 18)
    plan = (plan_e or {}).get("plan") or {}
    state = term["state"] if term else (es[-1]["state"] if es else "UNKNOWN")
    ver = (term or {}).get("verification") or {}
    if state == "CONFIRMED" and not (term.get("tx_hash") and ver.get("verified")):
        state = "FAILED"  # never show a confirmation without a receipt + passed verification
    out = {"id": sc["position_id"], "scenario": sc["scenario"], "label": sc["label"], "user": sc["user"],
           "rescue_vault": sc["rescue_vault"], "market_id": sc["market_id"], "status": state,
           "environment": "SIMULATED", "expected_status": sc["expected_final_state"],
           "user_signed_during_crisis": sc["user_signed_during_crisis"],
           "user_nonce": {"after_arming": sc["user_nonce_after_arming"], "at_end": sc["user_nonce_at_end"]},
           "before": snap0, "shock": sc.get("simulated_shock"),
           "timeline": [{"state": e["state"], "ts": e["ts"], "note": e.get("note") or e.get("reason") or e.get("why"),
                         "tx_hash": e.get("tx_hash"), "block": (e.get("snapshot") or {}).get("block") or e.get("block")} for e in es],
           "reserve_requirements": reserve_requirements(snap0, pcfg) if (pcfg and snap0.get("raw")) else []}
    if det:
        trig = det.get("trigger") or {}
        out["crisis"] = {"snapshot": det.get("snapshot"), "movers": (det.get("movers") or {}).get("movers", []),
                         "oracle_change": (det.get("movers") or {}).get("oracle_change"),
                         "ltv": None if trig.get("ltv") is None else int(trig["ltv"]) / 1e18,
                         "trigger_ltv": None if trig.get("trigger_ltv") is None else int(trig["trigger_ltv"]) / 1e18,
                         "trigger_met": trig.get("trigger_met"),
                         "scenario_breaches": [{"label": r["label"], "buffer": _h(r["buffer"], ld)} for r in trig.get("scenario_breaches", [])],
                         "simulated_dependencies": det.get("simulated_dependencies")}
    if plan:
        out["decision"] = {"decision": plan.get("decision"), "why": plan.get("why"), "rule": plan.get("rule"),
                           "ranking": plan.get("ranking"), "preference": plan.get("preference"),
                           "safety_margin": _h(plan.get("safety_margin_raw"), ld), "interest_horizon_s": plan.get("interest_horizon_s"),
                           "scenarios": [{"id": s["id"], "label": s["label"], "price_factor": int(s["factor_wad"]) / 1e18,
                                          "shocks": s.get("shocks")} for s in plan.get("scenarios", [])],
                           "hold": {"worst_buffer": _h((plan.get("hold") or {}).get("min_buffer"), ld),
                                    "hypothetical_penalty": _h((plan.get("hold") or {}).get("hypothetical_liquidation_penalty_raw"), ld),
                                    "scenarios": [{"label": r["label"], "buffer": _h(r["buffer"], ld), "liquidatable": r["liquidatable"]}
                                                  for r in (plan.get("hold") or {}).get("scenarios", [])]},
                           "candidates": [_cand_view(c, ld, cd) for c in plan.get("candidates", [])]}
    if val:
        out["validation"] = {k: (val.get("validation") or {}).get(k) for k in ("ok", "checks", "gas_estimate", "gas_limit",
                                                                              "max_fee_per_gas", "validated_block", "stage", "reason")}
        out["validation"]["amount_changed"] = val.get("amount_changed")
    if term and term["state"] == "NO_ACTION":
        out["no_action"] = {"reason": term.get("reason"), "transactions_sent": 0}
    if term and term["state"] in ("CONFIRMED", "FAILED") and term.get("tx_hash"):
        ch = term.get("chosen") or (exe or {})
        dec = cd if ch.get("strategy") == "TOP_UP" else ld
        b, a = ver.get("before") or {}, ver.get("after") or {}
        rem = ver.get("remaining_limits") or {}
        pol = rem.get("policy") or {}
        out["execution"] = {"status": state, "tx_hash": term["tx_hash"], "block": term.get("block"), "strategy": ch.get("strategy"),
                            "amount": _h(ch.get("amount_raw"), dec), "token": (ch.get("token") or {}).get("symbol"),
                            "gas_used": term.get("gas_used"), "effective_gas_price_gwei": (term.get("effective_gas_price") or 0) / 1e9,
                            "signed_by": (exe or {}).get("keeper"), "action_id": (exe or {}).get("action_id"),
                            "verified": ver.get("verified"), "checks": ver.get("checks", []),
                            "before": {"debt": _h(b.get("debt"), ld), "collateral": _h(b.get("collateral"), cd),
                                       "ltv": None if b.get("ltv") is None else int(b["ltv"]) / 1e18, "buffer": _h(b.get("buffer"), ld),
                                       "reserve": _h(b.get("reserve"), dec)},
                            "after": {"debt": _h(a.get("debt"), ld), "collateral": _h(a.get("collateral"), cd),
                                      "ltv": None if a.get("ltv") is None else int(a["ltv"]) / 1e18, "buffer": _h(a.get("buffer"), ld),
                                      "reserve": _h(a.get("reserve"), dec)}}
        if pol:
            out["protections"] = {"strategies": [k for k, bit in engine.BITS.items() if int(pol["allowed_strategies"]) & bit],
                                  "trigger_ltv": int(pol["trigger_ltv"]) / 1e18, "min_ltv_after": int(pol["min_ltv_after"]) / 1e18,
                                  "valid_until": pol["valid_until"], "cooldown_s": pol["cooldown"], "paused": rem.get("paused"),
                                  "revoked": rem.get("revoked"), "actions_executed": rem.get("action_count")}
            out["remaining_limits"] = {
                "repay_budget_left": _h(max(int(pol["max_repay_total"]) - int(rem.get("repaid_total", 0)), 0), ld),
                "top_up_budget_left": _h(max(int(pol["max_top_up_total"]) - int(rem.get("topped_up_total", 0)), 0), cd),
                "max_repay_per_action": _h(pol["max_repay_per_action"], ld), "max_top_up_per_action": _h(pol["max_top_up_per_action"], cd),
                "max_full_repay": _h(pol["max_full_repay"], ld), "loan_reserve_left": _h(rem.get("loan_reserve"), ld),
                "collateral_reserve_left": _h(rem.get("collateral_reserve"), cd),
                "min_loan_reserve": _h(pol["min_loan_reserve"], ld), "min_collateral_reserve": _h(pol["min_collateral_reserve"], cd)}
    out["after_snapshot"] = last_snap
    return out


def live_dependencies(markets: dict) -> dict:
    """LIVE read-only: the protected markets' oracle dependencies now, on Ethereum mainnet (never a transaction)."""
    for url in LIVE_RPCS:
        try:
            rpc = RPC(url, timeout=12, retries=0)
            blk = rpc.block("latest")
            out = {}
            for name, mid in markets.items():
                mp = contracts.market_params(rpc, contracts.MORPHO_BLUE, mid, blk["number"])
                loan = {"address": mp["loan_token"], "symbol": contracts.erc20_meta(rpc, mp["loan_token"])["symbol"]}
                coll = {"address": mp["collateral_token"], "symbol": contracts.erc20_meta(rpc, mp["collateral_token"])["symbol"]}
                d = dependencies.resolve(rpc, mp["oracle"], blk["number"], blk["timestamp"], loan, coll)
                out[name] = {"oracle": d["oracle"], "feeds": d["feeds"], "assumptions": d["assumptions"], "stale": d["stale"]}
            return {"status": "LIVE", "block": blk["number"], "timestamp": blk["timestamp"], "rpc": url, "markets": out,
                    "note": "read-only eth_call on Ethereum mainnet; no transaction"}
        except Exception as e:  # noqa: BLE001 - try the next public endpoint, then report unavailability
            last = f"{type(e).__name__}: {e}"[:200]
    return {"status": "unavailable", "error": last}


def payload(demo: Path = DEMO, live: bool = False) -> dict:
    sp = demo / "summary.json"
    if not sp.exists():
        return {"schema": "faultline.countermove/1", "status": "no_run",
                "message": "no recorded fork run: run `python scripts/countermove_fork_demo.py` first"}
    summary = json.loads(sp.read_text(encoding="utf-8"))
    es = _entries(demo)
    cfg_p = demo / "keeper_config_pre_crisis.json"
    pcfgs = {p["id"]: p for p in json.loads(cfg_p.read_text(encoding="utf-8"))["positions"]} if cfg_p.exists() else {}
    for extra in sorted(demo.glob("keeper_config_*.json")):  # positions armed later (S5) have their own pre-crisis config
        for p in json.loads(extra.read_text(encoding="utf-8"))["positions"]:
            pcfgs.setdefault(p["id"], p)
    positions = [position_view(sc, [e for e in es if e["position"] == sc["position_id"]], pcfgs.get(sc["position_id"]))
                 for sc in summary["scenarios"]]
    body = {"schema": "faultline.countermove/1", "status": "ok", "source": "recorded local mainnet-fork run",
            "environment": summary["environment"], "all_expected": summary.get("all_expected"),
            "generated_at": summary.get("generated_at"), "served_at": time.time(),
            "keeper_runs": [{"tag": r["tag"], "seconds": r["seconds"], "command": r["command"],
                             "results": r["results"]} for r in summary.get("keeper_runs", [])],
            "positions": positions,
            "labels": {"LIVE": "read now from Ethereum mainnet (read-only)",
                       "SIMULATED": "local Anvil fork of mainnet at a pinned block, test funds, controlled shock",
                       "CONFIRMED": "transaction mined on the local fork AND every verification check passed",
                       "FAILED": "reverted, unverified or did not execute", "NO_ACTION": "no transaction sent, reason given"}}
    if live:
        body["live"] = live_dependencies(summary["environment"]["markets"])
    return _js(body)


# ---- policy draft: the USER signs it, FAULTLINE only validates and encodes ------------------------------------------
def policy_draft(q: dict) -> dict:
    """Validate a policy against the same rules as RescueVault.setPolicy and return the calldata for the USER's wallet."""
    ld, cd = int(q.get("loan_decimals", 6)), int(q.get("collateral_decimals", 18))
    lltv = float(q.get("lltv", 0.86))
    strategies = [s for s in str(q.get("strategies", "REPAY,TOP_UP")).split(",") if s]
    pol = {"allowed_strategies": sum(engine.BITS[s] for s in strategies if s in engine.BITS),
           "valid_until": int(time.time()) + int(float(q.get("valid_days", 30)) * 86_400),
           "cooldown": int(q.get("cooldown_s", 3_600)),
           "trigger_ltv": int(float(q.get("trigger_ltv", 0.82)) * 1e18),
           "min_ltv_after": int(float(q.get("min_ltv_after", 0.4)) * 1e18),
           "max_repay_per_action": int(float(q.get("max_repay_per_action", 0)) * 10 ** ld),
           "max_top_up_per_action": int(float(q.get("max_top_up_per_action", 0)) * 10 ** cd),
           "max_full_repay": int(float(q.get("max_full_repay", 0)) * 10 ** ld),
           "max_repay_total": int(float(q.get("max_repay_total", 0)) * 10 ** ld),
           "max_top_up_total": int(float(q.get("max_top_up_total", 0)) * 10 ** cd),
           "min_loan_reserve": int(float(q.get("min_loan_reserve", 0)) * 10 ** ld),
           "min_collateral_reserve": int(float(q.get("min_collateral_reserve", 0)) * 10 ** cd)}
    errors = []
    if pol["allowed_strategies"] == 0:
        errors.append("choose at least one strategy")
    if not 0 < pol["trigger_ltv"] < int(lltv * 1e18):
        errors.append("trigger LTV must be above 0 and below the market LLTV")
    if pol["min_ltv_after"] >= pol["trigger_ltv"]:
        errors.append("the LTV floor must be below the trigger")
    if pol["max_repay_per_action"] > pol["max_repay_total"] or pol["max_full_repay"] > pol["max_repay_total"]:
        errors.append("per-action / full-repay caps cannot exceed the cumulative repay budget")
    if pol["max_top_up_per_action"] > pol["max_top_up_total"]:
        errors.append("per-action top-up cap cannot exceed the cumulative top-up budget")
    # Accepted by the contract, but such a strategy can never execute: say so instead of silently signing a dead policy.
    warnings = []
    for s, caps in (("REPAY", ("max_repay_per_action", "max_repay_total")), ("TOP_UP", ("max_top_up_per_action", "max_top_up_total")),
                    ("FULL_REPAY", ("max_full_repay", "max_repay_total"))):
        if s in strategies and any(pol[c] == 0 for c in caps):
            warnings.append(f"{s} is allowed but its cap is 0: the keeper can never use it")
    if strategies and len(warnings) == len([s for s in set(strategies) if s in engine.BITS]):
        warnings.append("no allowed strategy can act: this policy would never protect the position")
    data = abi.encode_call("setPolicy((uint8,uint64,uint32,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256))",
                           [[pol[k] for k in contracts.POLICY_FIELDS]]) if not errors else None
    return _js({"valid": not errors, "errors": errors, "warnings": warnings, "policy": pol, "calldata": data,
                "signer": "the position owner, with their own wallet, BEFORE any crisis (FAULTLINE never holds this key)",
                "pause_calldata": abi.encode_call("setPaused(bool)", [True]), "resume_calldata": abi.encode_call("setPaused(bool)", [False]),
                "revoke_calldata": abi.encode_call("revoke()", [])})
