"""Failure priors with a traceable source for every number (graded: "is the number defensible").

p_fail is over the position horizon (days). Everything is derived from:
  * DefiLlama hacks DB (base rate of exploit incidents)  -> protocol/oracle/amm/lending nodes
  * DefiLlama protocol metadata (audits, TVL, age)        -> modifiers on the base rate
  * Documented structural assumptions (loss given failure) -> constants below, flagged as assumptions
Each node gets meta["source"] explaining how its p_fail was obtained.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .sources import llama_hacks, llama_protocols, llama_stablecoin_price_history

LOOKBACK_YEARS = 3
MIN_INCIDENT_USD = 1_000_000
MIN_PROTOCOL_TVL = 10_000_000

# Loss given failure: share of the exposed value lost if the node fails. Structural assumptions
# (no public dataset gives this per position); tune with Belem's mentors.
LGF = {
    "chain": 0.30, "issuer": 0.60, "underlying": 0.50, "backing": 0.50, "oracle": 0.40,
    "feed_provider": 0.40, "amm": 0.60, "pendle_core": 0.60, "lending": 0.70, "morpho_blue": 0.70, "loan_asset": 0.30,
    "stablecoin": 0.30,
}
CHAIN_ANNUAL = 0.005  # assumption: no top-tier L1 has had a multi-day halt/rollback in recent years
STABLE_FALLBACK_ANNUAL = 0.10  # assumption, only used when a stablecoin has no DefiLlama price history

# Roles whose failure probability comes from the DefiLlama exploit base rate: their loss-given-failure is calibrated on
# the SAME incidents (share of TVL lost), see scripts/calibrate_lgf.py -> data/calibration/hack_severity.json.
HACK_ROLES = {"issuer", "underlying", "backing", "pendle_core", "amm", "lending", "morpho_blue", "oracle",
              "feed_provider", "loan_asset"}
SEVERITY_FILE = Path(__file__).resolve().parents[3] / "data" / "calibration" / "hack_severity.json"


def hack_severity() -> dict | None:
    """Calibrated exploit severity (mean share of TVL lost, bootstrap CI of the mean), or None if not calibrated."""
    try:
        d = json.loads(SEVERITY_FILE.read_text(encoding="utf-8"))
        s = d["summary"]
        return {"mean": s["mean"], "low": s["mean_ci95"][0], "high": s["mean_ci95"][1], "median": s["median"],
                "p90": s["p90"], "n": s["n"], "generated_at": d["generated_at"],
                "source": (f"calibrated: mean share of TVL lost in {s['n']} DefiLlama exploits (cohort, "
                           f"{LOOKBACK_YEARS}y) = {s['mean']:.1%} (95% CI {s['mean_ci95'][0]:.1%}-{s['mean_ci95'][1]:.1%}; "
                           f"median {s['median']:.1%}, p90 {s['p90']:.1%}); data/calibration/hack_severity.json")}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def _horizon(annual: float, horizon_days: int) -> float:
    annual = min(max(annual, 0.0), 0.95)
    return 1 - (1 - annual) ** (horizon_days / 365)


def base_rates(hacks: list[dict] | None = None, protocols: list[dict] | None = None) -> dict:
    """Annual probability that a protocol suffers a >=$1M exploit, from DefiLlama data.

    Central estimate is cohort-consistent: incidents whose DefiLlama protocol id belongs to the same cohort
    as the denominator (protocols with TVL >= MIN_PROTOCOL_TVL). Dividing *all* incidents (most hit small or
    unlisted protocols) by only the large protocols would overstate the rate ~10x. Survivorship bias (a hacked
    protocol may since have dropped below the TVL bar) pushes the central estimate down, so a broad upper bound
    (all incidents / all protocols with TVL >= $1M) is reported alongside for sensitivity.
    """
    hacks = hacks if hacks is not None else llama_hacks()
    protocols = protocols if protocols is not None else llama_protocols()
    cutoff = time.time() - LOOKBACK_YEARS * 365 * 86400
    recent = [h for h in hacks if (h.get("date") or 0) >= cutoff and (h.get("amount") or 0) >= MIN_INCIDENT_USD
              and h.get("targetType") != "CEX"]
    defi = [p for p in protocols if p.get("category") not in ("CEX", "Chain")]
    cohort = {str(p.get("id")) for p in defi if (p.get("tvl") or 0) >= MIN_PROTOCOL_TVL}
    broad_n = sum(1 for p in defi if (p.get("tvl") or 0) >= MIN_INCIDENT_USD)
    in_cohort = [h for h in recent if h.get("defillamaId") is not None and str(h["defillamaId"]) in cohort]
    n_protocols = len(cohort)
    oracle = [h for h in recent if h.get("classification") == "Oracle Manipulation"]
    annual = len(in_cohort) / LOOKBACK_YEARS / max(n_protocols, 1)
    upper = len(recent) / LOOKBACK_YEARS / max(broad_n, 1)
    return {
        "incidents": len(recent), "incidents_in_cohort": len(in_cohort), "protocols": n_protocols,
        "per_year": len(in_cohort) / LOOKBACK_YEARS,
        "annual_per_protocol": annual, "annual_per_protocol_upper": max(upper, annual),
        "oracle_share": len(oracle) / max(len(recent), 1),
        "source": (f"DefiLlama hacks: {len(in_cohort)} incidents >= ${MIN_INCIDENT_USD:,} in last {LOOKBACK_YEARS}y on the "
                   f"{n_protocols} protocols with TVL >= ${MIN_PROTOCOL_TVL:,} (upper bound: {len(recent)} incidents / "
                   f"{broad_n} protocols with TVL >= ${MIN_INCIDENT_USD:,} = {upper:.2%}/y)"),
    }


def stablecoin_depeg(gecko_id: str, history: list[dict] | None = None, threshold: float = 0.02) -> dict | None:
    """Depeg frequency and severity of a USD stablecoin from DefiLlama's daily price history.

    An episode = consecutive days with price < 1 - threshold. Severity = mean of (1 - min price) per episode.
    """
    history = history if history is not None else llama_stablecoin_price_history()
    pts = sorted((d["date"], d["prices"][gecko_id]) for d in history
                 if d.get("date") and gecko_id in (d.get("prices") or {}) and d["prices"][gecko_id])
    if len(pts) < 365:
        return None
    years = (pts[-1][0] - pts[0][0]) / (365 * 86400)
    episodes, cur = [], None
    for _, price in pts:
        if price < 1 - threshold:
            cur = min(cur, price) if cur is not None else price
        elif cur is not None:
            episodes.append(cur); cur = None
    if cur is not None:
        episodes.append(cur)
    severity = sum(1 - p for p in episodes) / len(episodes) if episodes else 0.0
    return {"episodes": len(episodes), "years": years, "annual": len(episodes) / years, "severity": severity,
            "min_price": min(p for _, p in pts), "gecko_id": gecko_id}


def p_stablecoin(depeg: dict | None, horizon_days: int, symbol: str) -> tuple[float, float | None, str]:
    """(p_fail over horizon, loss_given_failure or None to keep the role default, source)."""
    if not depeg:
        return _horizon(STABLE_FALLBACK_ANNUAL, horizon_days), None, (
            f"assumption: {STABLE_FALLBACK_ANNUAL:.0%}/y depeg (no DefiLlama price history for {symbol})")
    # A history with zero episodes still has a non-zero chance: use 0.5 episode over the window (rule of three-like floor).
    annual = max(depeg["annual"], 0.5 / max(depeg["years"], 1))
    lgf = max(depeg["severity"], 0.02) if depeg["episodes"] else None
    return _horizon(annual, horizon_days), lgf, (
        f"DefiLlama stablecoin prices ({depeg['gecko_id']}, {depeg['years']:.1f}y daily): {depeg['episodes']} depeg "
        f"episode(s) below $0.98 -> {annual:.2%}/y; mean depth {depeg['severity']:.1%}, min ${depeg['min_price']:.3f}")


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
