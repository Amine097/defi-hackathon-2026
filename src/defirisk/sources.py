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


def llama_find_protocol(name: str, protocols: list[dict] | None = None) -> dict | None:
    """Best-effort name match; prefers the highest-TVL protocol whose name or slug contains `name`."""
    protocols = protocols if protocols is not None else llama_protocols()
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if not key:
        return None
    hits = [p for p in protocols if key in re.sub(r"[^a-z0-9]", "", (p.get("name") or "").lower())
            or key == re.sub(r"[^a-z0-9]", "", (p.get("slug") or "").lower())]
    return max(hits, key=lambda p: p.get("tvl") or 0) if hits else None


# ---- JSON-RPC (eth_call) --------------------------------------------------
def eth_call(to: str, data: str) -> str | None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]}
    for url in RPCS:
        try:
            r = post_json(url, body, timeout=20)
        except Exception:
            continue
        if r.get("result") not in (None, "0x"):
            return r["result"]
        if r.get("error"):
            return None
    return None


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
