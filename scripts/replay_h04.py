"""H04 historical replays without look-ahead -> data/fixtures/replay_h04.json (consumed offline by tests).

1. USDC / SVB (March 2023): the depeg prior is computed ONLY from DefiLlama daily prices strictly before the cutoff
   (2023-03-11 00:00 UTC, the first day SVB exposure was public), then compared with what happened in the next 30 days.
2. Morpho liquidation: borrower state read at block N-1 (before the Liquidate tx in block N) -> was the position
   predicted liquidatable, and does the Morpho formula reproduce the seized collateral of the real event?

python scripts/replay_h04.py   (needs network: DefiLlama + an archive-capable Ethereum RPC)
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defirisk import morpho, priors, sources  # noqa: E402

CUTOFF = int(dt.datetime(2023, 3, 11, tzinfo=dt.timezone.utc).timestamp())
END = CUTOFF + 30 * 86400
MARKET = "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64"
LIQ_TX = "0x906a5315a31c4b3e2956524a819069367d625ee532871ddcef98ee6edd729e0d"


def main():
    gid = sources.llama_stablecoin_gecko_id("USDC")
    hist = sources.llama_stablecoin_price_history()
    series = sorted((d["date"], d["prices"][gid]) for d in hist
                    if d.get("date") and (d.get("prices") or {}).get(gid) and d["date"] < END)
    v = morpho.verify_liquidation(LIQ_TX)
    pre = morpho.borrower_state(v["market_id"], v["borrower"], v["block"] - 1)
    out = {
        "generated_at": int(dt.datetime.now(dt.timezone.utc).timestamp()),
        "usdc_svb": {"gecko_id": gid, "cutoff": CUTOFF, "horizon_end": END,
                     "source": "https://stablecoins.llama.fi/stablecoinprices (daily close)",
                     "series": [[t, p] for t, p in series]},
        "liquidation": {"tx": LIQ_TX, "block": v["block"], "borrower": v["borrower"], "market_id": v["market_id"],
                        "repaid_assets": v["repaid_assets"], "seized_assets": v["seized_assets"],
                        "oracle_price_raw_at_block": v["oracle_price_raw"], "lltv": v["lltv"],
                        "predicted_seized_assets": v["predicted_seized_assets"],
                        "pre_block": pre["as_of_block"],
                        "pre_state": {k: pre[k] for k in ("health_factor", "healthy", "debt_assets", "collateral_amount",
                                                          "oracle_price", "distance_to_liquidation_pct",
                                                          "liquidation_oracle_price")}},
    }
    path = ROOT / "data" / "fixtures" / "replay_h04.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    pre_pts = [x for x in series if x[0] < CUTOFF]
    print("prior from", len(pre_pts), "pre-cutoff days:", priors.stablecoin_depeg(gid, [{"date": t, "prices": {gid: p}} for t, p in pre_pts]))
    print("pre-liquidation state:", out["liquidation"]["pre_state"])
    print("wrote", path)


if __name__ == "__main__":
    main()
