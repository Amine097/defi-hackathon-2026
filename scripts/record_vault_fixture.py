"""Record a dated offline fixture of a vault analysis (Phase 1, V24).

    PYTHONPATH=src python scripts/record_vault_fixture.py 0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec [value_usd] [suffix]

Writes data/fixtures/vault_<address>[_<suffix>].json = the exact inputs of the pure `vault_model.assess()` step (on-chain
snapshot, request-dependent reads incl. the redeem / forceDeallocate multicall simulations, provenance) plus the live
payload's headline figures, so tests can replay the model deterministically without network. Read-only: no transaction
is sent.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defirisk import vault_model as vm  # noqa: E402
from defirisk import vault_reader as vr  # noqa: E402
from defirisk.data import http  # noqa: E402
from defirisk.vault_input import parse_request  # noqa: E402


def record(address: str, value_usd: str = "100000", suffix: str = "") -> Path:
    req = parse_request({"address": address, "value_usd": value_usd})
    http.reset_provenance()
    snap = vr.snapshot(req["address"])
    rd = vm.reads(req, snap)
    prov = http.provenance()
    recorded_at = http.now()
    inputs = json.loads(json.dumps({"req": req, "snap": snap, "rd": rd, "prov": prov}))  # frozen before assess()
    live = vm._js_safe(vm.payload(req, snap, rd, prov, vm.assess(req, snap, rd, prov)))
    d = live["decision"]
    out = {"schema": "faultline.vault-fixture/1", "recorded_at": recorded_at,
           "recorded_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(recorded_at)),
           "note": "dated snapshot recorded from public sources (RPC, Morpho API, DefiLlama, Chainlink); replay is labelled offline",
           **inputs,
           "live_headline": {"as_of_block": live["as_of_block"], "verdict": d["verdict"], "point_verdict": d["point_verdict"],
                             "expected_loss_usd": d["expected_loss_usd"], "exit_side_usd": d["exit_side_usd"],
                             "margin_usd": d["margin_usd"], "withdrawal_feasibility": d["withdrawal_feasibility"],
                             "executable_route": d.get("executable_route"),
                             "coverage": live["allocations"]["coverage"], "markets": len(live["allocations"]["items"])}}
    path = ROOT / "data" / "fixtures" / f"vault_{req['address'].lower()}{('_' + suffix) if suffix else ''}.json"
    path.write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = record(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "100000", sys.argv[3] if len(sys.argv) > 3 else "")
    print(f"wrote {p.relative_to(ROOT)}")
