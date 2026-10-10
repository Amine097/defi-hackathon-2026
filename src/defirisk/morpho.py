"""Morpho Blue borrower positions and liquidation mechanics (H02).

Two distinct economic entities, never mixed:
  * Mode A `unlevered_exposure`: PT held / posted without debt -> liquidation NOT_APPLICABLE (a market LLTV is not
    evidence that the position borrows).
  * Mode B `borrower_position`: a real account with non-zero debt on a Morpho Blue market, read on-chain at one pinned
    block (position, market totals with accrued interest, oracle price, LLTV).

Integer arithmetic follows Morpho Blue v1 (src/libraries/SharesMathLib.sol, MathLib.sol, Morpho.sol):
  VIRTUAL_SHARES = 1e6, VIRTUAL_ASSETS = 1; borrow assets = toAssetsUp(shares); maxBorrow = wMulDown(mulDivDown(
  collateral, price, 1e36), lltv); healthy iff maxBorrow >= borrowed; LIF = min(1.15, 1 / (1 - 0.3 (1 - lltv)));
  liquidation: seized = mulDivDown(wMulDown(repaid, LIF), 1e36, price).
"""
from __future__ import annotations

from . import sources
from .keccak import selector, topic

MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
WAD = 10**18
ORACLE_PRICE_SCALE = 10**36
VIRTUAL_SHARES = 10**6
VIRTUAL_ASSETS = 1
MAX_LIF = 115 * 10**16
LIQUIDATION_CURSOR = 3 * 10**17
LIQUIDATE_TOPIC = topic("Liquidate(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)")


# ---- Morpho MathLib / SharesMathLib (integers) ---------------------------------------------------------------
def mul_div_down(x: int, y: int, d: int) -> int:
    return x * y // d


def mul_div_up(x: int, y: int, d: int) -> int:
    return (x * y + d - 1) // d


def w_mul_down(x: int, y: int) -> int:
    return mul_div_down(x, y, WAD)


def w_div_down(x: int, y: int) -> int:
    return mul_div_down(x, WAD, y)


def to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    return mul_div_up(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)


def to_assets_down(shares: int, total_assets: int, total_shares: int) -> int:
    return mul_div_down(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)


def w_taylor_compounded(x: int, n: int) -> int:
    first = x * n
    second = mul_div_down(first, first, 2 * WAD)
    third = mul_div_down(second, first, 3 * WAD)
    return first + second + third


def liquidation_incentive_factor(lltv: int) -> int:
    return min(MAX_LIF, w_div_down(WAD, WAD - w_mul_down(LIQUIDATION_CURSOR, WAD - lltv)))


def max_borrow(collateral: int, price: int, lltv: int) -> int:
    return w_mul_down(mul_div_down(collateral, price, ORACLE_PRICE_SCALE), lltv)


# ---- on-chain reads (one pinned block) -----------------------------------------------------------------------
def _addr(word: int) -> str:
    return "0x" + f"{word:064x}"[-40:]


def _call(to: str, data: str, block: int) -> list[int]:
    r = sources.eth_call(to, data, block)
    if not r:
        raise RuntimeError(f"eth_call {data[:10]} on {to} returned nothing at block {block}")
    return sources._words(r)


def read_market(market_id: str, block: int) -> dict:
    mid = market_id[2:].lower()
    p = _call(MORPHO_BLUE, selector("idToMarketParams(bytes32)") + mid, block)
    m = _call(MORPHO_BLUE, selector("market(bytes32)") + mid, block)
    params = {"loan_token": _addr(p[0]), "collateral_token": _addr(p[1]), "oracle": _addr(p[2]), "irm": _addr(p[3]),
              "lltv": p[4]}
    state = {"total_supply_assets": m[0], "total_supply_shares": m[1], "total_borrow_assets": m[2],
             "total_borrow_shares": m[3], "last_update": m[4], "fee": m[5]}
    return {"params": params, "state": state}


def borrow_rate_view(params: dict, state: dict, block: int) -> int | None:
    """AdaptiveCurveIrm.borrowRateView(MarketParams, Market) -> per-second rate (WAD). None if the IRM is 0x0."""
    if int(params["irm"], 16) == 0:
        return 0
    args = [int(params["loan_token"], 16), int(params["collateral_token"], 16), int(params["oracle"], 16),
            int(params["irm"], 16), params["lltv"], state["total_supply_assets"], state["total_supply_shares"],
            state["total_borrow_assets"], state["total_borrow_shares"], state["last_update"], state["fee"]]
    sig = "borrowRateView((address,address,address,address,uint256),(uint128,uint128,uint128,uint128,uint128,uint128))"
    try:
        return _call(params["irm"], selector(sig) + "".join(f"{a:064x}" for a in args), block)[0]
    except RuntimeError:
        return None


def accrue(state: dict, rate: int | None, timestamp: int) -> dict:
    """Morpho._accrueInterest view: borrow totals at `timestamp` (supply-side fee shares do not change debt)."""
    s = dict(state)
    elapsed = max(timestamp - s["last_update"], 0)
    if elapsed and rate:
        interest = w_mul_down(s["total_borrow_assets"], w_taylor_compounded(rate, elapsed))
        s["total_borrow_assets"] += interest
        s["total_supply_assets"] += interest
    s["accrued_seconds"] = elapsed
    return s


def read_position(market_id: str, user: str, block: int) -> dict:
    w = _call(MORPHO_BLUE, selector("position(bytes32,address)") + market_id[2:].lower() + user[2:].lower().rjust(64, "0"), block)
    return {"supply_shares": w[0], "borrow_shares": w[1], "collateral": w[2]}


def oracle_price(oracle: str, block: int) -> int:
    return _call(oracle, selector("price()"), block)[0]


def _decimals(token: str, block: int) -> int:
    return _call(token, selector("decimals()"), block)[0]


def borrower_state(market_id: str, user: str, block: int | None = None, loan_price_usd: float = 1.0) -> dict:
    """Mode B snapshot. Every value is read at the same block; units are native integers + human floats."""
    blk = sources.eth_block(block if block else "latest")
    if not blk:
        raise RuntimeError("no RPC block")
    block, ts = blk["number"], blk["timestamp"]
    mk = read_market(market_id, block)
    pos = read_position(market_id, user, block)
    price = oracle_price(mk["params"]["oracle"], block)
    rate = borrow_rate_view(mk["params"], mk["state"], block)
    st = accrue(mk["state"], rate, ts)
    dec_loan = _decimals(mk["params"]["loan_token"], block)
    dec_coll = _decimals(mk["params"]["collateral_token"], block)
    s = compute_state(pos["collateral"], pos["borrow_shares"], st["total_borrow_assets"], st["total_borrow_shares"],
                      price, mk["params"]["lltv"], dec_loan, dec_coll, loan_price_usd)
    s.update(mode="borrower_position", market_id=market_id, borrower=user, as_of_block=block, block_timestamp=ts,
             oracle=mk["params"]["oracle"], oracle_price_raw=price, loan_token=mk["params"]["loan_token"],
             collateral_token=mk["params"]["collateral_token"], borrow_shares=pos["borrow_shares"],
             collateral_raw=pos["collateral"], borrow_rate_per_s=rate, interest_accrued_seconds=st["accrued_seconds"],
             market_totals={k: st[k] for k in ("total_borrow_assets", "total_borrow_shares", "total_supply_assets")},
             sources={"position/market/idToMarketParams": f"Morpho Blue {MORPHO_BLUE} eth_call @ block {block}",
                      "price": f"oracle {mk['params']['oracle']}.price() @ block {block} (scale 1e36)",
                      "interest": "IRM borrowRateView + Morpho wTaylorCompounded to the block timestamp"
                      + ("" if rate is not None else " (IRM unreadable: not accrued since lastUpdate)")})
    if pos["borrow_shares"] == 0:
        s["mode"] = "unlevered_exposure"
        s["note"] = "no debt at this block: liquidation not applicable"
    return s


def compute_state(collateral: int, borrow_shares: int, total_borrow_assets: int, total_borrow_shares: int, price: int,
                  lltv: int, dec_loan: int, dec_coll: int, loan_price_usd: float = 1.0) -> dict:
    debt = to_assets_up(borrow_shares, total_borrow_assets, total_borrow_shares)
    mb = max_borrow(collateral, price, lltv)
    coll_value = mul_div_down(collateral, price, ORACLE_PRICE_SCALE)  # in loan-token raw units, at the oracle price
    lif = liquidation_incentive_factor(lltv)
    lu = 10**dec_loan
    # oracle price (loan raw per collateral raw x 1e36) at which maxBorrow == debt
    p_star = (debt * ORACLE_PRICE_SCALE * WAD) / (collateral * lltv) if collateral else None
    return {
        "collateral_amount": collateral / 10**dec_coll, "debt_assets": debt / lu, "debt_assets_raw": debt,
        "debt_value_usd": debt / lu * loan_price_usd,
        "collateral_value_loan_units": coll_value / lu, "collateral_value_usd_oracle": coll_value / lu * loan_price_usd,
        "lltv": lltv / WAD, "max_borrow": mb / lu, "ltv": (debt / coll_value) if coll_value else None,
        "health_factor": (mb / debt) if debt else None, "healthy": mb >= debt,
        "liquidation_buffer_usd": (mb - debt) / lu * loan_price_usd,
        "oracle_price": price / ORACLE_PRICE_SCALE * 10**(dec_coll - dec_loan),
        "liquidation_oracle_price": (p_star / ORACLE_PRICE_SCALE * 10**(dec_coll - dec_loan)) if p_star else None,
        "distance_to_liquidation_pct": (1 - p_star / price) if p_star and price else None,
        "equity_usd_oracle": (coll_value - debt) / lu * loan_price_usd,
        "liquidation_incentive_factor": lif / WAD, "loan_decimals": dec_loan, "collateral_decimals": dec_coll,
    }


def liquidation_outcome(state: dict, oracle_drop: float, economic_drop: float | None = None) -> dict:
    """P&L of a collateral price shock for the borrower and the lenders (USD at the loan token price).

    oracle_drop: fall of the oracle price (drives eligibility). economic_drop: fall of the realisable collateral value
    (defaults to the oracle drop; they can diverge, e.g. a stale oracle). Convention: liquidators close the whole debt
    when eligible (worst case for the borrower, allowed by Morpho Blue). Borrower is non-recourse: loss <= equity.
    """
    economic_drop = oracle_drop if economic_drop is None else economic_drop
    v0 = state["collateral_value_usd_oracle"]
    d = state["debt_value_usd"]
    lltv, lif = state["lltv"], state["liquidation_incentive_factor"]
    eq0 = max(v0 - d, 0.0)
    v_oracle = v0 * (1 - oracle_drop)
    v_econ = v0 * (1 - economic_drop)
    liquidated = d > 0 and v_oracle * lltv < d
    eq_no_liq = max(v_econ - d, 0.0)  # what the borrower keeps if only the price moves
    seized_oracle = repaid = bad_debt = 0.0
    eq_after = eq_no_liq
    if liquidated:
        seized_oracle = min(d * lif, v_oracle)
        repaid = seized_oracle / lif
        frac = seized_oracle / v_oracle if v_oracle else 1.0
        bad_debt = d - repaid if frac >= 1.0 - 1e-12 else 0.0  # all collateral gone: Morpho socialises the rest
        eq_after = 0.0 if bad_debt else max((1 - frac) * v_econ - (d - repaid), 0.0)
    borrower_loss = eq0 - eq_after
    price_part = eq0 - eq_no_liq
    return {"oracle_drop": oracle_drop, "economic_drop": economic_drop, "liquidated": liquidated,
            "health_factor_after": (v_oracle * lltv / d) if d else None,
            "borrower_equity_before_usd": eq0, "borrower_equity_after_usd": eq_after,
            "borrower_loss_usd": borrower_loss, "of_which_price_move_usd": price_part,
            "of_which_liquidation_penalty_usd": borrower_loss - price_part,
            "debt_repaid_usd": repaid, "collateral_seized_usd_oracle": seized_oracle,
            "lender_bad_debt_usd": bad_debt,
            "owner": "borrower_loss -> borrower equity; lender_bad_debt -> market suppliers (not added to the borrower)"}

def market_rates(market_id: str, block: int | None = None) -> dict:
    """On-chain borrow / supply APY of a Morpho Blue market at a block: IRM borrowRateView, utilisation, fee.
    supply APY = (e^(borrowRate x 1y) - 1) x utilisation x (1 - fee)  (Morpho: suppliers earn interest net of fee)."""
    import math
    blk = sources.eth_block(block if block else "latest")
    if not blk:
        raise RuntimeError("no RPC block")
    mk = read_market(market_id, blk["number"])
    rate = borrow_rate_view(mk["params"], mk["state"], blk["number"])
    if rate is None:
        raise RuntimeError("IRM borrowRateView unreadable")
    st = mk["state"]
    util = st["total_borrow_assets"] / st["total_supply_assets"] if st["total_supply_assets"] else 0.0
    borrow_apy = math.expm1(rate / WAD * 365 * 86400)
    return {"borrow_apy": borrow_apy, "supply_apy": borrow_apy * util * (1 - st["fee"] / WAD), "utilization": util,
            "as_of_block": blk["number"], "block_timestamp": blk["timestamp"],
            "source": f"Morpho Blue market({market_id[:10]}..) + IRM borrowRateView @ block {blk['number']}"}


def unlevered(reason: str = "no borrower address given: the position is analysed as collateral without debt") -> dict:
    return {"mode": "unlevered_exposure", "liquidation": "NOT_APPLICABLE", "debt_assets": None,
            "reason": reason + "; a market LLTV is not evidence of debt, so no liquidation probability is shown"}


# ---- discovery of real borrowers + independent check on historical liquidations -------------------------------
def top_borrowers(market_id: str, first: int = 5, chain_id: int = 1) -> list[dict]:
    from .http import post_json
    q = """query($m:[String!],$c:[Int!],$f:Int){ marketPositions(first:$f, orderBy:BorrowShares, orderDirection:Desc,
      where:{marketUniqueKey_in:$m, chainId_in:$c}){ items{ user{address} state{ borrowAssets collateral } healthFactor } } }"""
    r = post_json(sources.MORPHO, {"query": q, "variables": {"m": [market_id], "c": [chain_id], "f": first}}, timeout=30)
    if r.get("errors"):
        raise RuntimeError(f"Morpho API: {r['errors'][0]['message']}")
    return [{"address": i["user"]["address"], "borrow_assets_api": int(i["state"]["borrowAssets"] or 0),
             "collateral_api": int(i["state"]["collateral"] or 0), "health_factor_api": i["healthFactor"]}
            for i in r["data"]["marketPositions"]["items"] if int(i["state"]["borrowAssets"] or 0) > 0]


def recent_liquidations(market_id: str, first: int = 5, chain_id: int = 1) -> list[dict]:
    from .http import post_json
    q = """query($m:[String!],$c:[Int!],$f:Int){ marketTransactions(first:$f, orderBy:Timestamp, orderDirection:Desc,
      where:{marketUniqueKey_in:$m, chainId_in:$c, type_in:[Liquidation]}){ items{ txHash blockNumber timestamp
      user{address} data{ ... on MarketTransactionLiquidationData{ seizedAssets repaidAssets badDebtAssets } } } } }"""
    r = post_json(sources.MORPHO, {"query": q, "variables": {"m": [market_id], "c": [chain_id], "f": first}}, timeout=30)
    if r.get("errors"):
        raise RuntimeError(f"Morpho API: {r['errors'][0]['message']}")
    return [{"tx": i["txHash"], "block": i["blockNumber"], "timestamp": i["timestamp"], "borrower": i["user"]["address"]}
            for i in r["data"]["marketTransactions"]["items"]]


def verify_liquidation(tx_hash: str) -> dict:
    """Independent check of the liquidation arithmetic on a real Liquidate event: decode the receipt log, read the
    oracle price and LLTV at that block, and compare seized collateral with repaid x LIF / price (Morpho formula)."""
    rc = sources._rpc("eth_getTransactionReceipt", [tx_hash])
    if not rc:
        raise RuntimeError("receipt unavailable")
    block = int(rc["blockNumber"], 16)
    for lg in rc["logs"]:
        if lg["topics"][0].lower() == LIQUIDATE_TOPIC and lg["address"].lower() == MORPHO_BLUE.lower():
            market_id = lg["topics"][1]
            repaid, repaid_shares, seized, bad_assets, bad_shares = sources._words(lg["data"])[:5]
            mk = read_market(market_id, block)
            price = oracle_price(mk["params"]["oracle"], block)
            lif = liquidation_incentive_factor(mk["params"]["lltv"])
            predicted_seized = mul_div_down(w_mul_down(repaid, lif), ORACLE_PRICE_SCALE, price)
            return {"tx": tx_hash, "block": block, "market_id": market_id, "borrower": "0x" + lg["topics"][3][-40:],
                    "repaid_assets": repaid, "seized_assets": seized, "bad_debt_assets": bad_assets,
                    "oracle_price_raw": price, "lltv": mk["params"]["lltv"] / WAD, "lif": lif / WAD,
                    "predicted_seized_assets": predicted_seized,
                    "relative_error": abs(predicted_seized - seized) / max(seized, 1),
                    "note": "oracle price read at the end of the liquidation block (same-block state)"}
    raise RuntimeError("no Morpho Liquidate log in this transaction")
