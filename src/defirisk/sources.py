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

    Returns {"amount_out_raw", "price_impact", "fee_usd", "gas_used", "aggregator", "method"}.
    """
    r = get_json(f"{PENDLE}/v2/sdk/{chain_id}/convert", params={
        "receiver": "0x000000000000000000000000000000000000dEaD", "slippage": "0.01", "enableAggregator": "true",
        "tokensIn": token_in.lower(), "amountsIn": str(int(amount_in_raw)), "tokensOut": token_out.lower()}, timeout=30)
    route = (r.get("routes") or [None])[0]
    if not route or not route.get("outputs"):
        raise RuntimeError("Pendle SDK returned no route")
    data = route.get("data") or {}
    return {"amount_out_raw": int(route["outputs"][0]["amount"]), "price_impact": data.get("priceImpact"),
            "fee_usd": (data.get("fee") or {}).get("usd"), "gas_used": int(data.get("gasUsed") or 0),
            "aggregator": data.get("aggregatorType"), "method": (route.get("contractParamInfo") or {}).get("method")}


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


def eth_call(to: str, data: str) -> str | None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]}
    r = _rpc_call(body, revert_ok=True)
    return r["result"] if r and r.get("result") not in (None, "0x") else None


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
