"""Freshness policy per data type (H05). Clock = http.now (injectable in tests).

Decisive inputs (exit quote, on-chain state used for the decision) block a firm STAY/EXIT when stale; context inputs
(market metadata, priors) only raise warnings. A cache replay is labelled as such and never presented as live.
"""
from __future__ import annotations

from . import http

TTL_S = {
    "exit_quote": 60,          # a swap quote is an executable price only for a few blocks
    "onchain_state": 120,      # ~10 blocks: oracle price, debt, block of the snapshot
    "market_data": 15 * 60,    # Pendle / Morpho API metadata: liquidity, implied APY, LLTV, supply
    "priors": 7 * 86400,       # DefiLlama hacks / protocols / stablecoin price history (slow-moving statistics)
}
DECISIVE = {"exit_quote", "onchain_state"}
WHY = {
    "exit_quote": "quotes move with every swap; past 60 s it is no longer the price you can execute",
    "onchain_state": "oracle price and debt change every block; 120 s ~ 10 blocks",
    "market_data": "pool/market aggregates drift slowly; 15 min keeps the graph context current",
    "priors": "multi-year incident / depeg statistics; a week-old copy changes nothing material",
}


def item(kind: str, fetched_at: float | None, source: str, as_of_block: int | None = None, replay: bool = False) -> dict:
    now = http.now()
    age = None if fetched_at is None else max(now - fetched_at, 0.0)
    stale = age is None or age > TTL_S[kind]
    return {"kind": kind, "source": source, "fetched_at": fetched_at, "age_seconds": age, "max_age_seconds": TTL_S[kind],
            "stale": stale, "decisive": kind in DECISIVE, "as_of_block": as_of_block, "replay": replay,
            "policy": WHY[kind]}


def evaluate(g, ex: dict, prov: dict, block_ts: int | None = None, extra: list[dict] | None = None) -> dict:
    """Freshness of every decisive / context input of one analysis. Returns items, blockers and a label."""
    m = g.position.meta
    block_ts = m.get("block_timestamp") if block_ts is None else block_ts
    replay = prov.get("cached", 0) > 0
    cache_ts = prov.get("oldest_cache_ts")
    items = []
    if not m.get("real"):
        return {"items": [], "blockers": ["mock demo graph: not real data, no firm verdict"], "label": "mock",
                "policy_ttl_s": TTL_S}
    if ex.get("method") == "pendle_sdk_quote":
        items.append(item("exit_quote", ex.get("quote_fetched_at"), f"Pendle SDK convert [{ex.get('quote_status')}]",
                          ex.get("quote_block"), replay=ex.get("quote_status") == "replayed_cache"))
    items.append(item("onchain_state", block_ts, "Ethereum JSON-RPC eth_blockNumber/eth_call", m.get("block_number"),
                      replay=replay))
    ctx_ts = cache_ts if replay else m.get("observed_at")
    items.append(item("market_data", ctx_ts, "Pendle API + Morpho GraphQL", replay=replay))
    items.append(item("priors", ctx_ts, "DefiLlama hacks / protocols / stablecoin prices", replay=replay))
    items += extra or []
    blockers = []
    for it in items:
        if it["decisive"] and it["stale"]:
            age = "unknown age" if it["age_seconds"] is None else f"{it['age_seconds']:,.0f}s old > {it['max_age_seconds']}s"
            blockers.append(f"stale {it['kind']} ({age}{', cache replay' if it['replay'] else ''}): no firm verdict")
    if ex.get("method", "").startswith("approximation"):
        blockers.append("exit cost is an approximation (no executable quote): no firm verdict")
    if ex.get("quote_status") == "simulation_mismatch":
        blockers.append("SDK quote and on-chain re-execution disagree: worse value kept, verdict not firm")
    label = "replay" if replay else ("stale" if blockers else "fresh")
    return {"items": items, "blockers": blockers, "label": label, "policy_ttl_s": TTL_S,
            "warnings": [f"{it['kind']} older than {it['max_age_seconds']}s" for it in items if it["stale"] and not it["decisive"]]}
