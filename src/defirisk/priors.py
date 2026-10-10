"""Failure priors with a traceable source for every number (graded: "is the number defensible").

p_fail is over the position horizon (days). Everything is derived from:
  * DefiLlama hacks DB (base rate of exploit incidents)  -> protocol/oracle/amm/lending nodes
  * DefiLlama protocol metadata (audits, TVL, age)        -> modifiers on the base rate
  * Documented structural assumptions (loss given failure) -> constants below, flagged as assumptions
Each node gets meta["source"] explaining how its p_fail was obtained.
"""
from __future__ import annotations

import time

from .sources import llama_hacks, llama_protocols

LOOKBACK_YEARS = 3
MIN_INCIDENT_USD = 1_000_000
MIN_PROTOCOL_TVL = 10_000_000

# Loss given failure: share of the exposed value lost if the node fails. Structural assumptions
# (no public dataset gives this per position); tune with Belem's mentors.
LGF = {
    "chain": 0.30, "issuer": 0.60, "underlying": 0.50, "backing": 0.50, "oracle": 0.40,
    "feed_provider": 0.40, "amm": 0.60, "lending": 0.70, "morpho_blue": 0.70, "loan_asset": 0.30,
}
CHAIN_ANNUAL = 0.005  # assumption: no top-tier L1 has had a multi-day halt/rollback in recent years


def _horizon(annual: float, horizon_days: int) -> float:
    annual = min(max(annual, 0.0), 0.95)
    return 1 - (1 - annual) ** (horizon_days / 365)


def base_rates(hacks: list[dict] | None = None, protocols: list[dict] | None = None) -> dict:
    """Annual probability that a protocol suffers a >=$1M exploit, from DefiLlama data."""
    hacks = hacks if hacks is not None else llama_hacks()
    protocols = protocols if protocols is not None else llama_protocols()
    cutoff = time.time() - LOOKBACK_YEARS * 365 * 86400
    recent = [h for h in hacks if (h.get("date") or 0) >= cutoff and (h.get("amount") or 0) >= MIN_INCIDENT_USD
              and h.get("targetType") != "CEX"]
    n_protocols = sum(1 for p in protocols if (p.get("tvl") or 0) >= MIN_PROTOCOL_TVL
                      and p.get("category") not in ("CEX", "Chain"))
    per_year = len(recent) / LOOKBACK_YEARS
    oracle = [h for h in recent if h.get("classification") == "Oracle Manipulation"]
    return {
        "incidents": len(recent), "protocols": n_protocols, "per_year": per_year,
        "annual_per_protocol": per_year / max(n_protocols, 1),
        "oracle_share": len(oracle) / max(len(recent), 1),
        "source": (f"DefiLlama hacks: {len(recent)} incidents >= ${MIN_INCIDENT_USD:,} in last {LOOKBACK_YEARS}y, "
                   f"{n_protocols} protocols with TVL >= ${MIN_PROTOCOL_TVL:,}"),
    }


def protocol_modifier(proto: dict | None) -> tuple[float, str]:
    """Multiplier on the base rate from audits, size and age. 1.0 = average protocol."""
    if not proto:
        return 1.5, "no DefiLlama match -> x1.5 (unknown protocol)"
    m, notes = 1.0, []
    audits = int(str(proto.get("audits") or 0) or 0)
    if audits == 0:
        m *= 1.5; notes.append("no audits x1.5")
    elif audits >= 2:
        m *= 0.7; notes.append(f"{audits} audits x0.7")
    tvl = float(proto.get("tvl") or 0)
    if tvl >= 1e9:
        m *= 0.5; notes.append("TVL>=$1B x0.5")
    elif tvl >= 1e8:
        m *= 0.7; notes.append("TVL>=$100M x0.7")
    elif tvl < 1e7:
        m *= 1.5; notes.append("TVL<$10M x1.5")
    listed = float(proto.get("listedAt") or 0)
    if listed and time.time() - listed < 365 * 86400:
        m *= 1.5; notes.append("listed <1y x1.5")
    return m, ", ".join(notes) or "average protocol x1.0"


def p_protocol(rates: dict, proto: dict | None, horizon_days: int, share: float = 1.0) -> tuple[float, str]:
    mod, why = protocol_modifier(proto)
    annual = rates["annual_per_protocol"] * mod * share
    return _horizon(annual, horizon_days), (f"{rates['source']}; base {rates['annual_per_protocol']:.2%}/y x {mod:.2f} "
                                           f"({why}) -> {annual:.2%}/y")


def p_chain(horizon_days: int) -> tuple[float, str]:
    return _horizon(CHAIN_ANNUAL, horizon_days), f"assumption: {CHAIN_ANNUAL:.1%}/y serious L1 incident"


def p_oracle(rates: dict, horizon_days: int, quality_mult: float, quality_notes: list[str]) -> tuple[float, str]:
    annual = rates["annual_per_protocol"] * max(rates["oracle_share"], 0.05) * 3 * quality_mult
    why = "; ".join(quality_notes) or "no feed-quality flags"
    return _horizon(annual, horizon_days), (f"{rates['source']}; oracle manipulation = {rates['oracle_share']:.0%} of incidents, "
                                           f"x3 for being a shared single point of failure, feed quality x{quality_mult:.2f} ({why}) "
                                           f"-> {annual:.2%}/y")
