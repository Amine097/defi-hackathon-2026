"""Verifier: an action is CONFIRMED only when the chain agrees with the plan.

Checks on the mined receipt: status 1; the vault's RescueExecuted event for THIS action id and strategy; the Morpho Blue
Repay / SupplyCollateral event for the beneficiary; the Morpho position re-read at the receipt block (debt / collateral
deltas, borrow shares); the reserve balance moved by exactly the amount; the policy counters; the LTV and the liquidation
buffer improved; the post-action LTV respects the keeper's bound. Any mismatch -> FAILED (verification), never hidden.
"""
from __future__ import annotations

from .. import morpho
from . import contracts, reader


def _check(rows: list, name: str, ok: bool, **detail) -> bool:
    rows.append({"check": name, "ok": bool(ok), **detail})
    return bool(ok)


def verify(rpc, vault: str, chosen: dict, receipt: dict) -> dict:
    rows: list = []
    blk = int(receipt["blockNumber"], 16)
    _check(rows, "receipt status = 1 (mined, not reverted)", int(receipt["status"], 16) == 1, block=blk,
           tx_hash=receipt["transactionHash"], gas_used=int(receipt["gasUsed"], 16))
    ev = None
    for lg in receipt.get("logs", []):
        if lg["address"].lower() == vault.lower() and lg["topics"][0] == contracts.RESCUE_EXECUTED_TOPIC:
            ev = contracts.decode_rescue_event({**lg, "blockNumber": receipt["blockNumber"]})
    _check(rows, "RescueExecuted event emitted by the vault", ev is not None)
    if ev is None:
        return {"verified": False, "checks": rows, "event": None, "block": blk}
    _check(rows, "event action id = planned action id", ev["action_id"].lower() == chosen["action_id"].lower())
    _check(rows, "event strategy = planned strategy", ev["strategy"] == chosen["strategy"])
    before_pos, before_v = reader.read(rpc, vault, blk - 1)
    after_pos, after_v = reader.read(rpc, vault, blk)
    s = chosen["strategy"]
    moved_tok = after_v["loan_token"] if s != "TOP_UP" else after_v["collateral_token"]
    res_key = "loan_reserve" if s != "TOP_UP" else "collateral_reserve"
    moved = before_v[res_key] - after_v[res_key]
    _check(rows, "reserve decreased by exactly the event amount", moved == ev["assets"], token=moved_tok,
           before=before_v[res_key], after=after_v[res_key], assets=ev["assets"])
    morpho_topic = contracts.MORPHO_SUPPLY_COLLATERAL_TOPIC if s == "TOP_UP" else contracts.MORPHO_REPAY_TOPIC
    mev = [lg for lg in receipt.get("logs", []) if lg["address"].lower() == after_pos["morpho"].lower()
           and lg["topics"][0] == morpho_topic and lg["topics"][1].lower() == after_pos["market_id"].lower()
           and ("0x" + lg["topics"][3][-40:]).lower() == after_pos["beneficiary"].lower()]
    _check(rows, f"Morpho {'SupplyCollateral' if s == 'TOP_UP' else 'Repay'} event on behalf of the beneficiary", bool(mev))
    if s == "REPAY":
        _check(rows, "event amount = planned amount", ev["assets"] == chosen["amount_raw"])
        _check(rows, "debt decreased by the repaid amount (+-2 wei share rounding)",
               abs((ev["debt_before"] - ev["debt_after"]) - ev["assets"]) <= 2, debt_before=ev["debt_before"], debt_after=ev["debt_after"])
        _check(rows, "collateral unchanged", after_pos["collateral"] == before_pos["collateral"])
        _check(rows, "re-read debt = event debt after (+-1)", abs(after_pos["debt"] - ev["debt_after"]) <= 1, reread=after_pos["debt"])
        _check(rows, "repaidTotal increased by the amount", after_v["repaid_total"] - before_v["repaid_total"] == ev["assets"])
    elif s == "TOP_UP":
        _check(rows, "event amount = planned amount", ev["assets"] == chosen["amount_raw"])
        _check(rows, "collateral increased by exactly the amount", after_pos["collateral"] - before_pos["collateral"] == ev["assets"],
               collateral_before=before_pos["collateral"], collateral_after=after_pos["collateral"])
        _check(rows, "borrow shares unchanged (debt not modified)", after_pos["borrow_shares"] == before_pos["borrow_shares"])
        _check(rows, "toppedUpTotal increased by the amount", after_v["topped_up_total"] - before_v["topped_up_total"] == ev["assets"])
    else:
        _check(rows, "borrow shares = 0 (debt fully repaid)", after_pos["borrow_shares"] == 0)
        _check(rows, "collateral unchanged (not sold, not withdrawn)", after_pos["collateral"] == before_pos["collateral"])
        _check(rows, "repaid amount within the keeper bound", ev["assets"] <= chosen["keeper_bound"], bound=chosen["keeper_bound"])
    _check(rows, "LTV improved (event)", ev["ltv_after"] < ev["ltv_before"], ltv_before=ev["ltv_before"], ltv_after=ev["ltv_after"])
    if s != "FULL_REPAY":
        _check(rows, "LTV after <= keeper bound", ev["ltv_after"] <= chosen["keeper_bound"], bound=chosen["keeper_bound"])
    buf_b = morpho.max_borrow(before_pos["collateral"], before_pos["price"], before_pos["lltv"]) - before_pos["debt"]
    buf_a = morpho.max_borrow(after_pos["collateral"], after_pos["price"], after_pos["lltv"]) - after_pos["debt"]
    _check(rows, "liquidation buffer increased", buf_a > buf_b, buffer_before=buf_b, buffer_after=buf_a)
    _check(rows, "vault holds no Morpho position of its own",
           sum(contracts.position(rpc, after_pos["morpho"], after_pos["market_id"], vault, blk).values()) == 0)
    return {"verified": all(r["ok"] for r in rows), "checks": rows, "event": ev, "block": blk,
            "before": {"debt": before_pos["debt"], "collateral": before_pos["collateral"], "price": before_pos["price"],
                       "ltv": ev["ltv_before"], "buffer": buf_b, "reserve": before_v[res_key]},
            "after": {"debt": after_pos["debt"], "collateral": after_pos["collateral"], "price": after_pos["price"],
                      "ltv": ev["ltv_after"], "buffer": buf_a, "reserve": after_v[res_key]},
            "remaining_limits": {"repaid_total": after_v["repaid_total"], "topped_up_total": after_v["topped_up_total"],
                                 "policy": after_v["policy"], "loan_reserve": after_v["loan_reserve"],
                                 "collateral_reserve": after_v["collateral_reserve"], "paused": after_v["paused"],
                                 "revoked": after_v["revoked"], "action_count": after_v["action_count"]}}
