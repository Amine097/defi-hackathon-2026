"""Collect live Phase 1 evidence for audit/BELEM_PHASE1_EVIDENCE.json (read-only public sources; no keys, no tx).

    $env:PYTHONPATH='src'; python scripts/collect_vault_evidence.py   # JSON on stdout; embedded in audit/BELEM_PHASE1_EVIDENCE.json (live_runs)

Prints one compact record per case: block, timestamps, version, asset, coverage, cross-checks, allocations, verdict,
margins, withdrawal. Values move with the chain; the invariants (not the USD figures) are what the tests assert.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defirisk import vault_model as vm  # noqa: E402
from defirisk.vault_input import parse_request  # noqa: E402

CASES = [
    ("belem", "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec", 100_000, 30),
    ("belem_1m_partial", "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec", 1_000_000, 90),
    ("confidential_usdc_v2", "0xc207d3f66537D7F66456808379A0E560cF20Da36", 100_000, 30),
    ("usdc_yield_v2", "0xE0181090c22579B6A217f1522cbf8c9f1F0C1965", 100_000, 30),
    ("steakhouse_usdc_v1", "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB", 100_000, 30),
]


def record(name, addr, value, horizon):
    t0 = time.time()
    p = vm.analyze(parse_request({"address": addr, "value_usd": str(value), "horizon_days": str(horizon)}))
    d, e, al, v = p["decision"], p["exit"], p["allocations"], p["vault"]
    return {
        "case": name, "address": addr, "chain_id": 1, "elapsed_s": round(time.time() - t0, 1),
        "as_of_block": p["as_of_block"], "block_timestamp": p["snapshot"]["block_timestamp"], "mode": p["mode"],
        "payload_sha256": hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest(),
        "vault": {"name": v["name"], "version": v["version"], "factory": v["factory"], "detection": v["detection"],
                  "asset": {k: v["asset"][k] for k in ("address", "symbol", "decimals", "currency", "price_usd", "price_source")}},
        "allocations": {"markets": len(al["items"]), "coverage": al["coverage"], "idle_share": al["idle_share"],
                        "unattributed_share": al["unattributed_share"], "displayed": al["displayed"],
                        "top": [{"collateral": i["collateral_symbol"], "share": round(i["share_of_vault"], 4), "market": i["market_id"]}
                                for i in sorted(al["items"], key=lambda i: -i["share_of_vault"])[:4]]},
        "cross_checks": [{k: c.get(k) for k in ("field", "rel_diff", "abs_diff", "tolerance", "ok", "source", "defillama", "morpho_api") if k in c} for c in p["snapshot"]["cross_checks"]],
        "graph": {"nodes": len(p["dependencies"]["nodes"]), "edges": len(p["dependencies"]["edges"]),
                  "shared_nodes": sum(1 for n in p["dependencies"]["nodes"] if len(n.get("exposed_allocations") or []) > 1)},
        "risk": {"expected_loss_usd": round(p["risk"]["expected_loss_usd"], 2), "band_usd": [round(x, 2) for x in p["risk"]["band_usd"]]},
        "scenarios": [{"name": s["name"], "loss_usd": round(s["loss_usd"], 2)} for s in p["scenarios"]],
        "exit": {"feasibility": e["withdrawal_feasibility"], "immediately_withdrawable_usd": round(e["immediately_withdrawable_usd"], 2),
                 "blocked_or_deferred_usd": round(e["blocked_or_deferred_usd"], 2), "quote_status": e["quote_status"],
                 "simulation_status": (e["simulation"] or {}).get("status"), "gas_usd": e["gas_usd"],
                 "friction_usd": e["withdrawal_friction_usd"], "exit_fee_usd": e["exit_fee_usd"],
                 "capacity_ordinary_usd": e["capacity"]["ordinary_usd"], "capacity_api_cross_check_ok": (e["capacity"].get("api_cross_check") or {}).get("ok"),
                 "carry_usd": e["carry"]["usd"], "net_apy_onchain": e["carry"]["net_apy_onchain"],
                 "net_apy_api_excl_rewards": e["carry"]["net_apy_api"], "usd_conversion_status": e["usd_conversion"].get("status")},
        "decision": {k: d[k] for k in ("verdict", "colour", "point_verdict", "confidence", "lean", "reasons", "blockers",
                                       "expected_loss_usd", "execution_cost_usd", "carry_usd", "exit_side_usd", "margin_usd",
                                       "breakeven_risk_multiplier", "withdrawal_feasibility")} | {"freshness": d["freshness"]["label"]},
        "warnings": p["warnings"],
    }


if __name__ == "__main__":
    out = []
    for c in CASES:
        try:
            out.append(record(*c))
        except Exception as ex:  # noqa: BLE001 - record the blocker instead of hiding it
            out.append({"case": c[0], "address": c[1], "error": f"{type(ex).__name__}: {ex}"[:300]})
    print(json.dumps({"collected_at": time.time(), "collected_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "runs": out}, indent=1, default=str))
