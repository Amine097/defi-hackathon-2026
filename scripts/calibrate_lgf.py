"""Calibrate loss-given-failure from real exploits: share of a protocol's TVL lost in each DefiLlama hack.

Same incident set as the failure base rate (priors.base_rates): last 3 years, >= $1M, not CEX, protocol in the cohort
(DefiLlama protocols with TVL >= $10M). For each incident: loss share = (amount - returned funds) / TVL the day before
the hack (DefiLlama /protocol/{slug} history), capped at 100%. The distribution is written to
data/calibration/hack_severity.json and read by priors.hack_severity() at analysis time (no network call at runtime).

    $env:PYTHONPATH='src'; python scripts/calibrate_lgf.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defirisk.data import http, priors, sources  # noqa: E402

OUT = ROOT / "data" / "calibration" / "hack_severity.json"


def tvl_before(slug: str, ts: float) -> tuple[float | None, int | None]:
    d = http.get_json(f"{sources.LLAMA}/protocol/{slug}", timeout=60)
    pts = [p for p in d.get("tvl") or [] if p.get("date") and p["date"] < ts]
    if not pts:
        return None, None
    last = max(pts, key=lambda p: p["date"])
    return float(last.get("totalLiquidityUSD") or 0) or None, int(last["date"])


def quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> int:
    hacks, protocols = sources.llama_hacks(), sources.llama_protocols()
    cutoff = time.time() - priors.LOOKBACK_YEARS * 365 * 86400
    cohort = {str(p.get("id")): p for p in protocols
              if p.get("category") not in ("CEX", "Chain") and (p.get("tvl") or 0) >= priors.MIN_PROTOCOL_TVL}
    rows, skipped = [], []
    for h in hacks:
        if not ((h.get("date") or 0) >= cutoff and (h.get("amount") or 0) >= priors.MIN_INCIDENT_USD
                and h.get("targetType") != "CEX" and h.get("defillamaId") is not None and str(h["defillamaId"]) in cohort):
            continue
        p = cohort[str(h["defillamaId"])]
        try:
            tvl, tvl_date = tvl_before(p["slug"], h["date"])
        except Exception as e:  # noqa: BLE001
            skipped.append({"name": h["name"], "reason": f"TVL history unavailable: {type(e).__name__}"})
            continue
        if not tvl:
            skipped.append({"name": h["name"], "reason": "no TVL point before the hack"})
            continue
        lost = max(float(h["amount"]) - float(h.get("returnedFunds") or 0), 0.0)
        rows.append({"name": h["name"], "slug": p["slug"], "category": p.get("category"), "date": int(h["date"]),
                     "classification": h.get("classification"), "amount_usd": float(h["amount"]),
                     "returned_usd": float(h.get("returnedFunds") or 0), "tvl_before_usd": tvl, "tvl_date": tvl_date,
                     "loss_share": min(lost / tvl, 1.0)})
    if not rows:
        print("no incident could be calibrated", file=sys.stderr)
        return 1
    s = [r["loss_share"] for r in rows]
    rng = random.Random(0)
    boots = sorted(statistics.fmean(rng.choices(s, k=len(s))) for _ in range(10_000))
    summary = {"n": len(s), "mean": statistics.fmean(s), "median": statistics.median(s), "p25": quantile(s, 0.25),
               "p75": quantile(s, 0.75), "p90": quantile(s, 0.9), "max": max(s), "min": min(s),
               "mean_ci95": [quantile(boots, 0.025), quantile(boots, 0.975)],
               "mean_ci_method": "bootstrap of the mean, 10,000 resamples, seed 0"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema": "faultline.hack_severity/1", "generated_at": int(time.time()),
        "method": "loss share = (amount - returned funds) / protocol TVL the day before the hack, capped at 1",
        "selection": (f"DefiLlama /hacks: last {priors.LOOKBACK_YEARS}y, >= ${priors.MIN_INCIDENT_USD:,}, not CEX, protocol "
                      f"in the cohort (DefiLlama /protocols TVL >= ${priors.MIN_PROTOCOL_TVL:,}, not CEX/Chain) - the "
                      "same incidents as the failure base rate"),
        "sources": ["https://api.llama.fi/hacks", "https://api.llama.fi/protocols", "https://api.llama.fi/protocol/{slug}"],
        "summary": summary, "incidents": sorted(rows, key=lambda r: -r["loss_share"]), "skipped": skipped,
    }, indent=1), encoding="utf-8")
    print(f"{len(rows)} incidents ({len(skipped)} skipped): mean {summary['mean']:.1%} (95% CI {summary['mean_ci95'][0]:.1%}-"
          f"{summary['mean_ci95'][1]:.1%}), median {summary['median']:.1%}, "
          f"IQR {summary['p25']:.1%}-{summary['p75']:.1%}, p90 {summary['p90']:.1%} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
