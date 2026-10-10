"""Thin clients for the public data sources used by discovery. All calls go through http.py (disk cache + offline)."""
from __future__ import annotations

import os
import re

from .http import get_json, post_json

PENDLE = "https://api-v2.pendle.finance/core"
MORPHO = "https://blue-api.morpho.org/graphql"
LLAMA = "https://api.llama.fi"
RPCS = [u for u in [os.getenv("ETH_RPC_URL"), "https://eth.drpc.org",
                    "https://eth-mainnet.public.blastapi.io"] if u]

CHAIN_IDS = {"ethereum": 1}
DEAD = "0x000000000000000000000000000000000000dEaD"


# ---- Pendle ---------------------------------------------------------------
def pendle_active_markets(chain_id: int = 1) -> list[dict]:
    return get_json(f"{PENDLE}/v1/{chain_id}/markets/active", timeout=30)["markets"]


def pendle_market(address: str, chain_id: int = 1) -> dict:
    return get_json(f"{PENDLE}/v1/{chain_id}/markets/{address.lower()}", timeout=30)


def pendle_market_data(address: str, chain_id: int = 1) -> dict:
    return get_json(f"{PENDLE}/v2/{chain_id}/markets/{address.lower()}/data", timeout=30)


def strip_chain(asset_id: str) -> str:
    """'1-0xabc' -> '0xabc'"""
    return asset_id.split("-", 1)[-1].lower()


def pendle_quote(token_in: str, amount_in_raw: int, token_out: str, chain_id: int = 1) -> dict:
    """Executable swap quote from Pendle's hosted SDK (routes through the PT AMM + aggregators).

    Returns amount out, Pendle-reported price impact / fee (informational), gas, route and the built transaction
    (`tx`: router + calldata, receiver 0xdEaD) so the quote can be re-executed with eth_call (simulate_swap).
    `fetched_at` / `from_cache` say how old the quote is: a quote is perishable (see QUOTE_TTL_S in decision.py).
    """
    from . import http
    r = get_json(f"{PENDLE}/v2/sdk/{chain_id}/convert", params={
        "receiver": DEAD, "slippage": "0.01", "enableAggregator": "true",
        "tokensIn": token_in.lower(), "amountsIn": str(int(amount_in_raw)), "tokensOut": token_out.lower()}, timeout=30)
    meta = dict(http.LAST)
    route = (r.get("routes") or [None])[0]
    if not route or not route.get("outputs"):
        raise RuntimeError("Pendle SDK returned no route")
    data = route.get("data") or {}
    tx = route.get("tx") or {}
    return {"amount_out_raw": int(route["outputs"][0]["amount"]), "price_impact": data.get("priceImpact"),
            "price_impact_breakdown": data.get("priceImpactBreakDown"),
            "fee_usd": (data.get("fee") or {}).get("usd"), "gas_used": int(data.get("gasUsed") or 0),
            "aggregator": data.get("aggregatorType"), "method": (route.get("contractParamInfo") or {}).get("method"),
            "tx": {"to": tx.get("to"), "data": tx.get("data")} if tx.get("to") and tx.get("data") else None,
            "fetched_at": meta.get("fetched_at"), "from_cache": bool(meta.get("cached"))}


# ---- Morpho (GraphQL) -----------------------------------------------------
_MARKET_FIELDS = """
  marketId lltv listed
  collateralAsset{ symbol address name }
  loanAsset{ symbol address }
  state{ supplyAssetsUsd borrowAssetsUsd liquidityAssetsUsd collateralAssetsUsd utilization }
  oracle{ address type data{ __typename ... on MorphoChainlinkOracleV2Data{
      baseFeedOne{address} baseFeedTwo{address} quoteFeedOne{address} quoteFeedTwo{address} baseOracleVault{address} } } }
  warnings{ type level }
  badDebt{ usd }
  supplyingVaults{ address name state{ totalAssetsUsd } }
"""


def morpho_markets_for_collateral(collaterals: list[str], chain_id: int = 1, min_supply_usd: float = 0, first: int = 50) -> list[dict]:
    """Morpho Blue markets whose collateral is one of the given token addresses, biggest first."""
    body = {"query": """query($c:[String!]!,$chain:[Int!],$min:Float,$first:Int){
      markets(first:$first, orderBy:SupplyAssetsUsd, orderDirection:Desc,
        where:{chainId_in:$chain, collateralAssetAddress_in:$c, supplyAssetsUsd_gte:$min}){ items{ %s } } }""" % _MARKET_FIELDS,
            "variables": {"c": collaterals, "chain": [chain_id], "min": min_supply_usd, "first": first}}
    r = post_json(MORPHO, body, timeout=30)
    if r.get("errors"):
        raise RuntimeError(f"Morpho API: {r['errors'][0]['message']}")
    return r["data"]["markets"]["items"]


# ---- DefiLlama ------------------------------------------------------------
def llama_protocols() -> list[dict]:
    return get_json(f"{LLAMA}/protocols", timeout=40)


def llama_hacks() -> list[dict]:
    return get_json(f"{LLAMA}/hacks", timeout=40)


def llama_prices(coins: list[str]) -> dict:
    """{'ethereum:0x..' | 'coingecko:ethereum': {'price', 'decimals', 'symbol', 'timestamp'}}"""
    return get_json(f"https://coins.llama.fi/prices/current/{','.join(coins)}", timeout=20).get("coins", {})


def llama_stablecoin_price_history() -> list[dict]:
    """Daily prices of all tracked stablecoins: [{'date': unix, 'prices': {gecko_id: price}}]."""
    return get_json("https://stablecoins.llama.fi/stablecoinprices", timeout=40)


def llama_stablecoin_gecko_id(symbol: str) -> str | None:
    """USD-pegged stablecoin with this symbol and the largest supply -> its CoinGecko id (key of the price history)."""
    assets = get_json("https://stablecoins.llama.fi/stablecoins", timeout=40).get("peggedAssets", [])
    hits = [a for a in assets if (a.get("symbol") or "").upper() == symbol.upper() and a.get("pegType") == "peggedUSD"
            and a.get("gecko_id")]
    best = max(hits, key=lambda a: (a.get("circulating") or {}).get("peggedUSD") or 0, default=None)
    return best["gecko_id"] if best else None


def llama_find_protocol(name: str, protocols: list[dict] | None = None) -> dict | None:
    """Best-effort name match; prefers the highest-TVL protocol whose name or slug contains `name`."""
    protocols = protocols if protocols is not None else llama_protocols()
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if not key:
        return None
    hits = [p for p in protocols if key in re.sub(r"[^a-z0-9]", "", (p.get("name") or "").lower())
            or key == re.sub(r"[^a-z0-9]", "", (p.get("slug") or "").lower())]
    if not hits and "." in name:  # domain-style names (e.g. Pendle's "re.xyz"): match the protocol's website domain
        dom = name.lower().strip()
        hits = [p for p in protocols if re.search(r"(^|[/.])" + re.escape(dom) + r"(/|$)",
                                                  re.sub(r"^https?://", "", (p.get("url") or "").lower()))]
    return max(hits, key=lambda p: p.get("tvl") or 0) if hits else None


# ---- JSON-RPC (eth_call) --------------------------------------------------
def _rpc_call(body: dict, revert_ok: bool = False):
    """Try every RPC live first, then any cached copy. Returns the JSON-RPC response dict or None.
    revert_ok: an execution error (contract revert) is a real answer, not an endpoint failure."""
    for use_cache in (False, True):
        for url in RPCS:
            try:
                r = post_json(url, body, timeout=20, use_cache=use_cache)
            except Exception:
                continue
            err = r.get("error")
            if r.get("result") is not None or (err and revert_ok and "revert" in str(err).lower()):
                return r
    return None


def eth_call(to: str, data: str, block: str | int = "latest") -> str | None:
    tag = hex(block) if isinstance(block, int) else block
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, tag]}
    r = _rpc_call(body, revert_ok=True)
    return r["result"] if r and r.get("result") not in (None, "0x") else None


def eth_block(number: int | str = "latest") -> dict | None:
    """{'number', 'timestamp'} of a block (used to pin every on-chain read of one analysis to the same block)."""
    tag = hex(number) if isinstance(number, int) else number
    b = _rpc("eth_getBlockByNumber", [tag, False])
    return {"number": int(b["number"], 16), "timestamp": int(b["timestamp"], 16)} if b else None


def _w(x: int | str) -> bytes:
    return (int(x, 16) if isinstance(x, str) else int(x)).to_bytes(32, "big")


def _override_rpc(method: str, params: list) -> dict | None:
    """Live-only JSON-RPC with a state override (never served from cache: a simulation must be fresh)."""
    for url in RPCS:
        try:
            r = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60, use_cache=False)
        except Exception:
            continue
        if r.get("result") is not None or "revert" in str(r.get("error", "")).lower():
            return r
    return None


def erc20_override(token: str, holder: str, amount: int, spender: str, slots: tuple[int, int] | None = None, block: str = "latest") -> dict | None:
    """State override giving `holder` a balance of `amount` and an allowance to `spender`. Finds the solidity mapping
    slots (balance, allowance) by probing balanceOf() under the override, so it works for standard ERC20 layouts."""
    from .keccak import keccak256
    def bal_slot(s): return "0x" + keccak256(_w(holder) + _w(s)).hex()
    def alw_slot(s): return "0x" + keccak256(_w(spender) + keccak256(_w(holder) + _w(s))).hex()
    cands = [slots] if slots else [(b, a) for b in range(0, 10) for a in (b + 1,)]
    for b, a in cands:
        ov = {token: {"stateDiff": {bal_slot(b): "0x" + _w(amount).hex(), alw_slot(a): "0x" + _w(2 ** 255).hex()}}}
        bal = _override_rpc("eth_call", [{"to": token, "data": "0x70a08231" + _w(holder).hex()}, block, ov])
        alw = _override_rpc("eth_call", [{"to": token, "data": "0xdd62ed3e" + _w(holder).hex() + _w(spender).hex()}, block, ov])
        if bal is None:
            return None  # no RPC supports eth_call overrides right now
        ok = bal.get("result") and int(bal["result"], 16) == amount and alw and alw.get("result") and int(alw["result"], 16) >= 2 ** 254
        if ok:
            return {"override": ov, "slots": (b, a)}
    return None


def simulate_swap(tx: dict, token_in: str, amount_in_raw: int, block: int | None = None) -> dict:
    """Execute the SDK-built swap with eth_call (no transaction is sent) at a pinned block, from 0xdEaD funded with
    the PT through a state override. Returns the on-chain amount out (first return word of the Pendle router call)
    and an eth_estimateGas, or {'status': 'unavailable', 'reason'}."""
    tag = hex(block) if block else "latest"
    ov = erc20_override(token_in, DEAD, amount_in_raw, tx["to"], block=tag)
    if not ov:
        return {"status": "unavailable", "reason": "no RPC accepted eth_call state overrides / ERC20 slots not found"}
    call = {"from": DEAD, "to": tx["to"], "data": tx["data"]}
    r = _override_rpc("eth_call", [dict(call, gas=hex(15_000_000)), tag, ov["override"]])
    if not r or not r.get("result") or r["result"] == "0x":
        return {"status": "reverted", "reason": str((r or {}).get("error"))[:300]}
    out = _words(r["result"])[0]
    g = _override_rpc("eth_estimateGas", [call, tag, ov["override"]])
    gas = int(g["result"], 16) if g and g.get("result") else None
    return {"status": "simulated", "amount_out_raw": out, "gas_estimate": gas, "block": block, "storage_slots": ov["slots"]}


def _rpc(method: str, params: list):
    r = _rpc_call({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return r["result"] if r else None


def eth_gas_price_wei() -> int | None:
    r = _rpc("eth_gasPrice", [])
    return int(r, 16) if r else None


def eth_block_number() -> int | None:
    r = _rpc("eth_blockNumber", [])
    return int(r, 16) if r else None


def _words(hexstr: str) -> list[int]:
    h = hexstr[2:]
    return [int(h[i:i + 64], 16) for i in range(0, len(h), 64)]


def read_feed(feed: str) -> dict | None:
    """Chainlink-style aggregator: description(), decimals(), latestRoundData()."""
    desc_raw = eth_call(feed, "0x7284e416")
    dec_raw = eth_call(feed, "0x313ce567")
    rd_raw = eth_call(feed, "0xfeaf968c")
    if not (dec_raw and rd_raw):
        return None
    description = ""
    if desc_raw:
        b = bytes.fromhex(desc_raw[2:])
        n = int.from_bytes(b[32:64], "big")
        description = b[64:64 + n].decode("utf-8", "ignore")
    dec = _words(dec_raw)[0]
    w = _words(rd_raw)
    return {"description": description, "decimals": dec, "answer": w[1] / 10 ** dec, "updated_at": w[3]}
