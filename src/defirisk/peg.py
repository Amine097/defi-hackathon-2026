"""Peg / basis check (spec §7-8, minimal): how far a stablecoin-like token has traded from its reference over the
last N days, from DefiLlama daily prices (coins.llama.fi/chart). Missing data is reported, never filled in."""
from __future__ import annotations

import time

from .http import get_json

CHART = "https://coins.llama.fi/chart/{coins}"
MIN_POINTS = 20


def price_history(addresses: list[str], window_days: int = 90, chain: str = "ethereum") -> dict[str, list[float]]:
    """{address: [daily prices oldest -> newest]}; {} on any failure. start is rounded to the day so the cache key is stable."""
    if not addresses:
        return {}
    start = (int(time.time()) // 86400 - window_days) * 86400
    coins = ",".join(f"{chain}:{a}" for a in addresses)
    try:
        r = get_json(CHART.format(coins=coins), params={"start": start, "span": window_days, "period": "1d"}, timeout=30)
    except Exception:
        return {}
    out = {}
    for k, v in (r.get("coins") or {}).items():
        pts = sorted(v.get("prices") or [], key=lambda p: p.get("timestamp", 0))
        out[k.split(":", 1)[-1].lower()] = [p["price"] for p in pts if isinstance(p.get("price"), (int, float))]
    return out


def peg_stats(prices: list[float] | None, reference: float | list[float] | None = 1.0, window_days: int = 90,
              kind: str = "peg") -> dict:
    """kind='peg': deviation of price from $1. kind='basis': price vs fair value (reference = fair price, latest only)."""
    base = {"window_days": window_days, "source": "DefiLlama coins API (coins.llama.fi/chart, daily)", "kind": kind}
    if not prices or reference is None:
        return {**base, "insufficient_data": True, "max_dev_pct": None, "latest_dev_pct": None, "n_points": len(prices or []),
                "reason": "no price history" if not prices else "no reference value to compare against"}
    if kind == "basis":
        return {**base, "insufficient_data": False, "n_points": len(prices), "max_dev_pct": None,
                "latest_dev_pct": (prices[-1] / reference - 1) * 100,
                "reason": "latest only: the historical exchange rate is not read, so no max over the window"}
    if len(prices) < MIN_POINTS:
        return {**base, "insufficient_data": True, "max_dev_pct": None, "latest_dev_pct": (prices[-1] / reference - 1) * 100,
                "n_points": len(prices), "reason": f"only {len(prices)} daily prices (< {MIN_POINTS})"}
    devs = [(p / reference - 1) * 100 for p in prices]
    worst = max(devs, key=abs)
    return {**base, "insufficient_data": False, "max_dev_pct": worst, "max_abs_dev_pct": abs(worst),
            "latest_dev_pct": devs[-1], "min_price": min(prices), "n_points": len(prices)}


def annotate(lin, window_days: int = 90) -> dict[str, dict]:
    """Peg stats for stablecoin-like tokens of a lineage, basis for vault wrappers of them. {token id: stats}."""
    from .lineage import is_stable_like
    toks = lin.tokens
    stable = [t for t, v in toks.items() if not t.startswith("base:") and is_stable_like(v)]
    wrappers = [(e["parent"], e["child"], e.get("rate")) for e in lin.edges
                if e.get("rate") and e["child"] in stable]
    hist = price_history(sorted(set(stable) | {w for w, _, _ in wrappers}), window_days)
    out = {t: peg_stats(hist.get(t), 1.0, window_days) for t in stable}
    for w, child, rate in wrappers:
        ph, ch = hist.get(w), hist.get(child)
        fair = rate * ch[-1] if ch else None
        out[w] = peg_stats(ph, fair, window_days, kind="basis")
        out[w]["reference"] = f"{rate:.4f} {toks[child]['symbol']} per share (ERC-4626 convertToAssets)"
    for t, v in toks.items():
        if t not in out and v.get("type") == "yield_bearing":
            out[t] = {**peg_stats(None, None, window_days), "reason": "yield-bearing token without an on-chain exchange "
                      "rate: there is no fair value to measure a peg against"}
    return out
