"""Watcher reads: one protected position + its RescueVault, pinned to ONE block, with interest accrued to that block.

Debt follows Morpho Blue exactly: market totals accrued with the IRM rate (wTaylorCompounded) to the block timestamp,
then toAssetsUp(borrowShares). Only pure math is reused from morpho.py; every read goes through the given RPC.
"""
from __future__ import annotations

from .. import morpho
from . import contracts

_META: dict = {}


def token_meta(rpc, token: str) -> dict:
    key = (rpc.url, token.lower())
    if key not in _META:
        _META[key] = contracts.erc20_meta(rpc, token)
    return _META[key]


def read(rpc, vault_address: str, block: str | int = "latest") -> tuple[dict, dict]:
    """(position, vault) at one block. position: collateral, borrow_shares, debt (accrued), price, lltv, rate_per_s,
    block, timestamp, token metadata. vault: contracts.read_vault()."""
    b = rpc.block(block)
    blk, ts = b["number"], b["timestamp"]
    v = contracts.read_vault(rpc, vault_address, blk)
    mid, mo, user = v["market_id"], v["morpho"], v["beneficiary"]
    params = contracts.market_params(rpc, mo, mid, blk)
    st = contracts.market_state(rpc, mo, mid, blk)
    rate = contracts.borrow_rate(rpc, params, st, blk)
    acc = morpho.accrue(st, rate, ts)
    p = contracts.position(rpc, mo, mid, user, blk)
    debt = morpho.to_assets_up(p["borrow_shares"], acc["total_borrow_assets"], acc["total_borrow_shares"])
    price = contracts.oracle_price(rpc, params["oracle"], blk)
    loan, coll = token_meta(rpc, params["loan_token"]), token_meta(rpc, params["collateral_token"])
    pos = {"block": blk, "timestamp": ts, "block_hash": b["hash"], "base_fee": b["base_fee"], "market_id": mid, "morpho": mo,
           "beneficiary": user, "collateral": p["collateral"], "borrow_shares": p["borrow_shares"], "debt": debt,
           "price": price, "lltv": params["lltv_raw"], "rate_per_s": rate, "oracle": params["oracle"], "irm": params["irm"],
           "loan_token": params["loan_token"], "collateral_token": params["collateral_token"],
           "loan_symbol": loan["symbol"], "loan_decimals": loan["decimals"],
           "collateral_symbol": coll["symbol"], "collateral_decimals": coll["decimals"],
           "interest_accrued_seconds": acc["accrued_seconds"], "market_totals": {k: acc[k] for k in (
               "total_supply_assets", "total_borrow_assets", "total_borrow_shares")},
           "source": f"Morpho Blue {mo} market/position/idToMarketParams + IRM borrowRateView + oracle price() @ block {blk}"}
    if params["oracle"].lower() != v["oracle"].lower() or params["lltv_raw"] != v["lltv"]:
        raise ValueError("RescueVault market parameters do not match Morpho's registry: refusing to act")
    return pos, v
