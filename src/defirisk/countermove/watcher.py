"""Watcher service: runs without any browser, one cycle per protected position per tick.

    WATCHING -> DETECTED -> PLANNING -> VALIDATING -> EXECUTING -> CONFIRMED | FAILED | NO_ACTION

* WATCHING   read the position, its RescueVault and the oracle's real dependencies at one block (interest accrued).
* DETECTED   the on-chain LTV crossed the owner's trigger, or a configured dependency scenario breaks the margin.
* PLANNING   Countermove engine: exact minimal amounts, ordered constraints, explicit choice or NO_ACTION.
* VALIDATING fresh re-read at the latest block + re-plan (same strategy required), stale-feed check, eth_call
             simulation from the keeper, gas / fee caps, keeper gas funds. Any failure -> NO_ACTION (nothing sent).
* EXECUTING  sign (Foundry cast, encrypted keystore), journal the tx hash BEFORE broadcast, broadcast, wait for the receipt.
* CONFIRMED  receipt + events + re-read Morpho state match the plan (verifier). FAILED otherwise, with the reason.
RPC errors / timeouts end the cycle without any transaction. A pending (signed, maybe broadcast) action is resolved
from the chain before anything else is planned: never re-sent blindly. Run:
    FAULTLINE_KEEPER_KEYSTORE=<keystore file> FAULTLINE_KEEPER_PASSWORD_FILE=<file> \
        python -m defirisk.countermove --config <file> [--once | --interval 3]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from . import contracts, dependencies, engine, reader, verifier
from .chain import RPC, RPCError, RevertError
from .executor import GuardedExecutor
from .journal import Journal

TERMINAL = ("CONFIRMED", "FAILED", "NO_ACTION")


def engine_config(pcfg: dict, loan_decimals: int) -> engine.EngineConfig:
    e = pcfg.get("engine", {})
    margin = int(Decimal(str(e.get("safety_margin", "0"))) * 10 ** loan_decimals)
    return engine.EngineConfig(safety_margin_raw=margin, interest_horizon_s=int(e.get("interest_horizon_s", 86_400)),
                               allow_partial=bool(e.get("allow_partial", False)), ranking=e.get("ranking", "min_capital"),
                               preference=tuple(e.get("preference", ("REPAY", "TOP_UP", "FULL_REPAY"))),
                               ltv_bound_slack_wad=int(e.get("ltv_bound_slack_wad", 2 * 10 ** 15)),
                               full_repay_slack_bps=int(e.get("full_repay_slack_bps", 10)))


def _h(raw: int | None, dec: int) -> float | None:
    return None if raw is None else raw / 10 ** dec


def summarize(pos: dict, v: dict, deps: dict) -> dict:
    """Human-readable snapshot for the journal / UI (raw integers kept alongside)."""
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    val = engine.collateral_value(pos["collateral"], pos["price"])
    mb = engine.max_borrow(pos["collateral"], pos["price"], pos["lltv"])
    pol = v["policy"]
    return {"block": pos["block"], "timestamp": pos["timestamp"], "market_id": pos["market_id"],
            "beneficiary": pos["beneficiary"], "loan": {"symbol": pos["loan_symbol"], "decimals": ld, "address": pos["loan_token"]},
            "collateral": {"symbol": pos["collateral_symbol"], "decimals": cd, "address": pos["collateral_token"]},
            "collateral_amount": _h(pos["collateral"], cd), "collateral_value": _h(val, ld), "debt": _h(pos["debt"], ld),
            "ltv": (engine.ltv_wad(pos["debt"], pos["collateral"], pos["price"]) or 0) / 1e18, "lltv": pos["lltv"] / 1e18,
            "buffer": _h(mb - pos["debt"], ld), "healthy": mb >= pos["debt"],
            "borrow_apr_onchain": (pos["rate_per_s"] or 0) * 365 * 86400 / 1e18,
            "oracle_price_raw": pos["price"],
            "raw": {"collateral": pos["collateral"], "debt": pos["debt"], "borrow_shares": pos["borrow_shares"], "price": pos["price"],
                    "lltv": pos["lltv"], "rate_per_s": pos["rate_per_s"]},
            "vault": {"address": v["address"], "keeper": v["keeper"], "paused": v["paused"], "revoked": v["revoked"],
                      "policy_nonce": v["policy_nonce"], "loan_reserve": _h(v["loan_reserve"], ld),
                      "collateral_reserve": _h(v["collateral_reserve"], cd), "repaid_total": _h(v["repaid_total"], ld),
                      "topped_up_total": _h(v["topped_up_total"], cd), "last_action_at": v["last_action_at"],
                      "action_count": v["action_count"],
                      "policy": {**pol, "trigger_ltv_pct": pol["trigger_ltv"] / 1e18, "min_ltv_after_pct": pol["min_ltv_after"] / 1e18,
                                 "max_repay_per_action_h": _h(pol["max_repay_per_action"], ld),
                                 "max_top_up_per_action_h": _h(pol["max_top_up_per_action"], cd),
                                 "max_full_repay_h": _h(pol["max_full_repay"], ld), "max_repay_total_h": _h(pol["max_repay_total"], ld),
                                 "max_top_up_total_h": _h(pol["max_top_up_total"], cd),
                                 "min_loan_reserve_h": _h(pol["min_loan_reserve"], ld),
                                 "min_collateral_reserve_h": _h(pol["min_collateral_reserve"], cd),
                                 "strategies": [k for k, b in engine.BITS.items() if pol["allowed_strategies"] & b]}},
            "dependencies": {"oracle": deps["oracle"], "feeds": deps["feeds"], "vaults": deps["vaults"],
                             "assumptions": deps["assumptions"], "stale": deps["stale"], "simulated": deps["simulated"],
                             "graph": deps["graph"]}}


def _slim_deps(deps: dict) -> dict:
    return {"block": deps["block"], "oracle": {"price": deps["oracle"].get("price")},
            "feeds": [{"id": f["id"], "role": f["role"], "side": f["side"], "answer": f.get("answer"),
                       "description": f.get("description")} for f in deps["feeds"]]}


class Watcher:
    def __init__(self, cfg: dict, rpc: RPC, journal: Journal, signer=None, limits: dict | None = None):
        self.cfg, self.rpc, self.journal = cfg, rpc, journal
        self.executor = GuardedExecutor(rpc, signer, limits or cfg.get("limits"))

    # ---- journal helpers ----------------------------------------------------------------------------------------
    def _log(self, p: dict, state: str, **data) -> dict:
        rec = self.journal.append(p["id"], state, label=p.get("label"), vault=p["rescue_vault"], **data)
        extra = {}
        if state in TERMINAL:
            extra["last_terminal"] = {"state": state, "at": rec["ts"], "reason": data.get("reason"),
                                      "tx_hash": data.get("tx_hash")}
        self.journal.update(p["id"], state=state, last_event=rec, **extra)
        return rec

    def tick(self) -> list[dict]:
        out = []
        for p in self.cfg["positions"]:
            try:
                out.append(self.cycle(p))
            except RPCError as e:
                out.append(self._log(p, "WATCHING", event="rpc_error", error=str(e)[:300],
                                     note="RPC unavailable or timed out: no decision, no transaction this cycle"))
            except Exception as e:  # noqa: BLE001 - a keeper bug must never crash the service silently
                out.append(self._log(p, "WATCHING", event="internal_error", error=f"{type(e).__name__}: {e}"[:300],
                                     note="cycle aborted before any transaction"))
        return out

    # ---- one cycle ---------------------------------------------------------------------------------------------
    def _observe(self, p: dict, block="latest"):
        pos, v = reader.read(self.rpc, p["rescue_vault"], block)
        loan = {"address": pos["loan_token"], "symbol": pos["loan_symbol"], "decimals": pos["loan_decimals"]}
        coll = {"address": pos["collateral_token"], "symbol": pos["collateral_symbol"], "decimals": pos["collateral_decimals"]}
        ages = {k.lower(): int(x) for k, x in (p.get("max_feed_age_s") or {}).items()}
        deps = dependencies.resolve(self.rpc, pos["oracle"], pos["block"], pos["timestamp"], loan, coll, ages)
        scen = dependencies.build_scenarios(deps, p.get("scenarios", []))
        ecfg = engine_config(p, pos["loan_decimals"])
        pl = engine.plan(pos, v, scen, ecfg, keeper=self.executor.keeper)
        return pos, v, deps, scen, ecfg, pl

    def cycle(self, p: dict) -> dict:
        pid, vault = p["id"], p["rescue_vault"]
        pend = self.journal.pending(pid)
        if pend:
            return self._resolve_pending(p, pend)
        st = self.journal.state().get(pid, {})
        last = st.get("last_terminal") or {}
        backoff = float(p.get("retry_after_failed_s", self.cfg.get("retry_after_failed_s", 60)))
        if last.get("state") == "FAILED" and time.time() - last.get("at", 0) < backoff:
            return self._log(p, "WATCHING", event="backoff", note=f"last action FAILED {time.time() - last['at']:.0f}s ago: "
                             f"waiting {backoff:.0f}s before re-planning (no repeated blind attempts)")
        pos, v, deps, scen, ecfg, pl = self._observe(p)
        ref = st.get("reference_deps")
        ref_desc = {f["id"]: f.get("description") for f in (ref or {}).get("feeds", [])}
        for f in deps["feeds"]:
            if f.get("simulated") and ref_desc.get(f["id"]):
                f["original_description"] = ref_desc[f["id"]]
        snap = summarize(pos, v, deps)
        if pl["decision"] == "HOLD" and pl["hold"]["meets_target"]:
            self.journal.update(pid, reference_deps=_slim_deps(deps), last_snapshot=snap)
            return self._log(p, "WATCHING", decision="HOLD", why=pl["why"], snapshot=snap)
        realert = float(p.get("realert_s", self.cfg.get("realert_s", 300)))
        if (last.get("state") == "NO_ACTION" and last.get("reason") == pl.get("why") and pl["decision"] != "EXECUTE"
                and time.time() - last.get("at", 0) < realert):
            return self._log(p, "WATCHING", event="alert_persists", reason=pl["why"], snapshot=snap)
        move = dependencies.attribute_move(deps, ref)
        self._log(p, "DETECTED", snapshot=snap, movers=move,
                  trigger={"ltv": pl["ltv_now"], "trigger_ltv": pl["trigger_ltv"], "trigger_met": pl["trigger_met"],
                           "scenario_breaches": [r for r in pl["hold"]["scenarios"] if not r["meets_margin"]]},
                  stale=deps["stale"], simulated_dependencies=deps["simulated"])
        self._log(p, "PLANNING", plan=pl)
        if deps["stale"]:
            return self._log(p, "NO_ACTION", reason=f"stale or unreadable oracle feed(s) {deps['stale']}: refusing to act on "
                             "a price that may be wrong", decision="NO_ACTION", plan_decision=pl["decision"])
        if pl["decision"] != "EXECUTE":
            return self._log(p, "NO_ACTION", reason=pl["why"], decision=pl["decision"], alert=pl.get("alert", False))
        # VALIDATING: fresh state at the latest block, same deterministic engine, then the exact calldata simulation
        pos2, v2, deps2, _, _, pl2 = self._observe(p)
        if deps2["stale"]:
            return self._log(p, "NO_ACTION", reason=f"feeds became stale during validation {deps2['stale']}")
        if pl2["decision"] != "EXECUTE":
            return self._log(p, "NO_ACTION", reason="conditions changed during validation: " + pl2["why"], plan=pl2)
        if pl2["chosen"]["strategy"] != pl["chosen"]["strategy"]:
            return self._log(p, "NO_ACTION", reason=f"plan unstable: {pl['chosen']['strategy']} at block {pl['block']} became "
                             f"{pl2['chosen']['strategy']} at block {pl2['block']}; re-planning next cycle", plan=pl2)
        chosen = pl2["chosen"]
        val = self.executor.validate(vault, chosen)
        self._log(p, "VALIDATING", validation=val, chosen=chosen, planned_block=pl["block"], validated_block=pl2["block"],
                  amount_changed=chosen["amount_raw"] != pl["chosen"]["amount_raw"])
        if not val["ok"]:
            return self._log(p, "NO_ACTION", reason=f"validation failed at {val.get('stage')}: {val.get('reason')}",
                             validation=val)

        def on_signed(pending: dict) -> None:
            self.journal.set_pending(pid, {**pending, "chosen": chosen, "from_block": pos2["block"]})
            self._log(p, "EXECUTING", tx_hash=pending["tx_hash"], nonce=pending["nonce"], action_id=pending["action_id"],
                      strategy=chosen["strategy"], amount_raw=chosen["amount_raw"], keeper=pending["keeper"],
                      note="signed by the keeper; journaled before broadcast; no user signature involved")

        res = self.executor.send(vault, chosen, val, on_signed)
        return self._finish(p, chosen, res)

    def _finish(self, p: dict, chosen: dict, res: dict) -> dict:
        pid, vault = p["id"], p["rescue_vault"]
        if res["status"] == "mined":
            rc = res["receipt"]
            gas = {"gas_used": int(rc["gasUsed"], 16), "effective_gas_price": int(rc.get("effectiveGasPrice", "0x0"), 16)}
            if int(rc["status"], 16) != 1:
                self.journal.set_pending(pid, None)
                return self._log(p, "FAILED", tx_hash=rc["transactionHash"], block=int(rc["blockNumber"], 16), **gas,
                                 reason="transaction reverted on-chain: " + self._revert_reason(vault, chosen, rc))
            ver = verifier.verify(self.rpc, vault, chosen, rc)
            self.journal.set_pending(pid, None)
            if ver["verified"]:
                return self._log(p, "CONFIRMED", tx_hash=rc["transactionHash"], block=ver["block"], **gas, chosen=chosen,
                                 verification=ver, how=res.get("how", "receipt"))
            return self._log(p, "FAILED", tx_hash=rc["transactionHash"], **gas, verification=ver,
                             reason="mined, but the re-read on-chain state does not match the plan")
        r = self.executor.resolve(res["pending"], (self.journal.pending(pid) or {}).get("from_block", 0))
        r["ambiguity"] = res.get("reason")
        return self._apply_resolution(p, chosen, r)

    def _apply_resolution(self, p: dict, chosen: dict, r: dict) -> dict:
        pid = p["id"]
        if r["status"] == "mined":
            return self._finish(p, chosen, r)
        if r["status"] == "still_pending":
            return self._log(p, "EXECUTING", note="transaction still pending: waiting, not re-sending", resolution=r)
        if r["status"] == "executed_unverified":
            self.journal.set_pending(pid, None)
            return self._log(p, "FAILED", reason="action id consumed on-chain but no event found: manual review", resolution=r)
        self.journal.set_pending(pid, None)
        return self._log(p, "FAILED", reason=f"the signed action did not execute ({r['status']}): {r['how']}; it will be "
                         "re-planned from fresh state with a new action id", resolution=r)

    def _resolve_pending(self, p: dict, pend: dict) -> dict:
        self._log(p, "EXECUTING", note="pending action found after restart / previous cycle: resolving from the chain "
                  "before any new plan", tx_hash=pend.get("tx_hash"), action_id=pend.get("action_id"))
        r = self.executor.resolve(pend, pend.get("from_block", 0))
        return self._apply_resolution(p, pend.get("chosen") or {}, r)

    def _revert_reason(self, vault: str, chosen: dict, rc: dict) -> str:
        try:
            self.rpc.eth_call(vault, self.executor.calldata(chosen), int(rc["blockNumber"], 16) - 1, sender=self.executor.keeper)
            return "unknown (simulation at the previous block succeeds: state changed inside the block)"
        except RevertError as e:
            d = contracts.decode_revert(e.data)
            return f"{d['error']}{tuple(d['args']) if d['args'] else ''}"
        except RPCError as e:
            return f"unknown ({e})"

    def run(self, interval_s: float = 3.0, max_ticks: int | None = None, until_terminal: bool = False) -> list[dict]:
        out, n = [], 0
        while max_ticks is None or n < max_ticks:
            res = self.tick()
            out.extend(res)
            n += 1
            if until_terminal and all(r.get("state") in TERMINAL for r in res):
                break
            time.sleep(interval_s)
        return out


def load_config(path: str | Path) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    for p in cfg["positions"]:
        if not p.get("id") or not p.get("rescue_vault"):
            raise ValueError("every position needs an id and a rescue_vault address")
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FAULTLINE Autonomous Countermove keeper (local test chain only)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--journal-dir")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--max-ticks", type=int)
    ap.add_argument("--until-terminal", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    rpc = RPC(cfg["rpc_url"])
    if os.environ.get("FAULTLINE_KEEPER_KEY"):
        raise SystemExit("FAULTLINE_KEEPER_KEY (plaintext key) is no longer accepted: use an encrypted keystore via "
                         "FAULTLINE_KEEPER_KEYSTORE + FAULTLINE_KEEPER_PASSWORD_FILE (see docs/FAULTLINE_PHASE2_DEMO_GUIDE.md)")
    from .signer import KEYSTORE_ENV, PASSWORD_FILE_ENV, KeystoreSigner
    signer = None
    if os.environ.get(KEYSTORE_ENV) or os.environ.get(PASSWORD_FILE_ENV):
        rpc.assert_local()  # never even unlock the keystore for a non-local chain
        signer = KeystoreSigner.from_env()
    journal = Journal(a.journal_dir or cfg.get("journal_dir", "data/countermove/journal"))
    w = Watcher(cfg, rpc, journal, signer)
    print(f"FAULTLINE keeper {'(watch-only)' if signer is None else signer.address} on chain {rpc.chain_id()} -> {journal.dir}",
          file=sys.stderr)
    res = w.run(a.interval, 1 if a.once else a.max_ticks, a.until_terminal)
    for r in res:
        print(json.dumps({"position": r.get("position"), "state": r.get("state"), "reason": r.get("reason") or r.get("why"),
                          "tx_hash": r.get("tx_hash")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
