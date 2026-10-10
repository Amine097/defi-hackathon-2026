"""GET /api/countermove contract: built from the recorded local mainnet-fork run (data/countermove/demo/latest),
every CONFIRMED backed by a tx hash + passed verification, NO_ACTION without any transaction, JS-safe integers, and the
policy-draft validator applying the same rules as RescueVault.setPolicy. The Node view tests read the exported payload."""
import json
import os
import sys
from pathlib import Path

import pytest

from defirisk.countermove import api as cm

ROOT = Path(__file__).resolve().parents[1]
UI_FIX = ROOT / "tests" / "js" / "fixtures" / "countermove.json"
HAVE_RUN = (cm.DEMO / "summary.json").exists()
pytestmark = pytest.mark.skipif(not HAVE_RUN, reason="no recorded fork run (scripts/countermove_fork_demo.py)")


@pytest.fixture(scope="module")
def payload():
    return cm.payload()


def _big_ints(o):
    if isinstance(o, bool):
        return []
    if isinstance(o, int):
        return [o] if abs(o) > 2 ** 53 else []
    if isinstance(o, dict):
        return [x for v in o.values() for x in _big_ints(v)]
    if isinstance(o, list):
        return [x for v in o for x in _big_ints(v)]
    return []


def test_payload_contract(payload):
    assert payload["schema"] == "faultline.countermove/1" and payload["status"] == "ok"
    json.dumps(payload, allow_nan=False)
    assert _big_ints(payload) == []
    env = payload["environment"]
    assert env["chain_id"] == 31337 and "fork" in env["kind"] and "SIMULATED" in env["kind"]
    assert any("no transaction was sent to Ethereum mainnet" in n for n in env["notes"])
    assert payload["all_expected"] is True


def test_three_mandatory_outcomes_and_full_repay(payload):
    by = {p["scenario"]: p for p in payload["positions"]}
    assert (by["S1"]["status"], by["S1"]["execution"]["strategy"]) == ("CONFIRMED", "REPAY")
    assert (by["S2"]["status"], by["S2"]["execution"]["strategy"]) == ("CONFIRMED", "TOP_UP")
    assert by["S3"]["status"] == "NO_ACTION" and "execution" not in by["S3"] and by["S3"]["no_action"]["transactions_sent"] == 0
    assert (by["S4"]["status"], by["S4"]["execution"]["strategy"]) == ("CONFIRMED", "FULL_REPAY")
    s1, s2, s4 = by["S1"]["execution"], by["S2"]["execution"], by["S4"]["execution"]
    assert s1["after"]["debt"] < s1["before"]["debt"] and s1["after"]["collateral"] == s1["before"]["collateral"]
    assert s2["after"]["collateral"] > s2["before"]["collateral"] and s2["after"]["debt"] == pytest.approx(s2["before"]["debt"], abs=1e-3)
    assert s4["after"]["debt"] == 0 and s4["after"]["collateral"] == s4["before"]["collateral"]
    for e in (s1, s2, s4):
        assert e["after"]["ltv"] < e["before"]["ltv"] and e["after"]["buffer"] > e["before"]["buffer"]


def test_confirmed_means_proof(payload):
    for p in payload["positions"]:
        assert p["user_signed_during_crisis"] is False and p["user_nonce"]["after_arming"] == p["user_nonce"]["at_end"]
        if p["status"] == "CONFIRMED":
            e = p["execution"]
            assert e["tx_hash"].startswith("0x") and len(e["tx_hash"]) == 66 and e["verified"] is True
            assert e["checks"] and all(c["ok"] for c in e["checks"])
            assert e["signed_by"].lower() == payload["environment"]["keeper"].lower()


def test_dependency_and_comparison_are_explained(payload):
    for p in payload["positions"]:
        c = p["crisis"]
        assert c["trigger_met"] and c["ltv"] >= c["trigger_ltv"]
        assert c["movers"] and c["movers"][0]["simulated"] and "SIMULATED" in c["movers"][0]["label"]
        cands = {x["strategy"]: x for x in p["decision"]["candidates"]}
        assert set(cands) == {"REPAY", "TOP_UP", "FULL_REPAY"}
        for x in cands.values():
            assert x["status"] == "eligible" or (x["rejected_at"] in ("security", "feasibility", "buffer") and x["reasons"])
    s1 = next(p for p in payload["positions"] if p["scenario"] == "S1")
    hit9 = next(r for r in s1["reserve_requirements"] if r["first_hit"] == 0.09)
    assert hit9["min_repay"] == pytest.approx(s1["execution"]["amount"], rel=1e-5)  # same engine, same numbers


def test_policy_draft_rules_match_the_contract():
    ok = cm.policy_draft({"strategies": "REPAY,TOP_UP", "trigger_ltv": "0.82", "min_ltv_after": "0.4", "max_repay_per_action": "5000",
                          "max_repay_total": "20000", "max_top_up_per_action": "1", "max_top_up_total": "1"})
    assert ok["valid"] and ok["calldata"].startswith("0x") and len(ok["calldata"]) == 2 + 8 + 12 * 64
    for bad, msg in (({"trigger_ltv": "0.9"}, "below the market LLTV"), ({"min_ltv_after": "0.85"}, "floor"),
                     ({"max_repay_per_action": "30000", "max_repay_total": "20000"}, "cumulative"),
                     ({"strategies": ""}, "at least one")):
        r = cm.policy_draft({"trigger_ltv": "0.82", "min_ltv_after": "0.4", **bad})
        assert not r["valid"] and any(msg in e for e in r["errors"]) and r["calldata"] is None
    assert "never holds" in ok["signer"]


def test_http_handler_and_ui_fixture_in_sync(payload):
    sys.path.insert(0, str(ROOT / "api"))
    import countermove as handler
    status, body = handler.respond("/api/countermove")
    assert status == 200 and body["status"] == "ok"
    status, body = handler.respond("/api/countermove/policy-draft?trigger_ltv=0.5&min_ltv_after=0.6")
    assert status == 200 and not body["valid"]
    if os.getenv("FAULTLINE_EXPORT_UI_FIXTURES") == "1":
        UI_FIX.write_text(json.dumps(payload, indent=1, allow_nan=False), encoding="utf-8")
    saved = json.loads(UI_FIX.read_text(encoding="utf-8"))
    assert [(p["scenario"], p["status"]) for p in saved["positions"]] == [(p["scenario"], p["status"]) for p in payload["positions"]]
    for a, b in zip(saved["positions"], payload["positions"]):
        assert (a.get("execution") or {}).get("tx_hash") == (b.get("execution") or {}).get("tx_hash")


@pytest.mark.skipif(os.getenv("DEFIRISK_LIVE_TESTS") != "1", reason="set DEFIRISK_LIVE_TESTS=1 to read mainnet")
def test_live_dependencies_read_only():
    live = cm.live_dependencies({"weETH/USDC": "0x85252bb8485c99bba46fe149c7dd2aad83672640f53c630890673cf1848ba16e",
                                 "cbBTC/USDC": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64"})
    assert live["status"] == "LIVE" and live["block"] > 26_000_000
    descs = {f.get("description") for m in live["markets"].values() for f in m["feeds"]}
    assert "BTC / USD" in descs and "ETH / USD" in descs
    assert all(not f.get("simulated") for m in live["markets"].values() for f in m["feeds"])
