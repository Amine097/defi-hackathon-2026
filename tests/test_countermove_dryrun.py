"""Countermove DRY-RUN on a real mainnet borrower (GET /api/countermove?action=dry-run, python -m defirisk.countermove
dry-run): offline against a fake mainnet RPC (every read answered from a fixture, any write impossible), plus one
read-only live test behind DEFIRISK_LIVE_TESTS=1. Nothing is ever signed or sent: the payload has no transaction field."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

from defirisk import morpho
from defirisk.countermove import contracts, dryrun, engine
from defirisk.countermove.chain import RPCError, RevertError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
import countermove as handler  # noqa: E402

ZERO = "0x" + "0" * 40
MID = "0x" + "11" * 32
MORPHO = contracts.MORPHO_BLUE.lower()
USDC_T, CBBTC_T, ORACLE, IRM, FEED = ("0x" + c * 40 for c in "12345")
HEALTHY, AT_RISK, EMPTY = ("0x" + c * 40 for c in "abc")
TS, BLOCK = 1_800_000_000, 24_000_000
PRICE = 10 ** 39  # 1 cbBTC (8 dec) = 100,000 USDC (6 dec), Morpho oracle scale 1e36
RATE = 1_585_489_599  # ~5% APR per second (WAD)
SHARES = {HEALTHY: 7 * 10 ** 17, AT_RISK: 84 * 10 ** 16, EMPTY: 0}  # 700,000 / 840,000 USDC of debt
COLL = {HEALTHY: 10 ** 9, AT_RISK: 10 ** 9, EMPTY: 0}  # 10 cbBTC
FORBIDDEN = re.compile(r"(^|_)(tx|txs|tx_hash|calldata|action_id|nonce|signature|raw_transaction)($|_)", re.I)


class FakeMainnet:
    """Answers eth_call reads from a fixture; has no way to send anything (no send_raw / eth_sendRawTransaction)."""
    url = "https://fake-mainnet.invalid/v2/SECRETKEY"

    def __init__(self, feed_age=600, chain=1):
        self.feed_age, self.chain, self.reads = feed_age, chain, []

    def chain_id(self):
        return self.chain

    def block(self, tag="latest"):
        return {"number": BLOCK, "timestamp": TS, "base_fee": 10 ** 9, "hash": "0x" + "ab" * 32}

    def read(self, to, signature, args=None, out="uint256", block="latest"):
        to, args = to.lower(), args or []
        self.reads.append((to, signature))
        upd = TS - self.feed_age
        table = {
            (MORPHO, "idToMarketParams(bytes32)"):
                lambda: [USDC_T, CBBTC_T, ORACLE, IRM, 86 * 10 ** 16] if args[0].lower() == MID else [ZERO] * 4 + [0],
            (MORPHO, "market(bytes32)"): lambda: [2 * 10 ** 14, 2 * 10 ** 20, 10 ** 14, 10 ** 20, TS, 0],
            (MORPHO, "position(bytes32,address)"): lambda: [0, SHARES.get(args[1].lower(), 0), COLL.get(args[1].lower(), 0)],
            (ORACLE, "price()"): lambda: PRICE, (ORACLE, "SCALE_FACTOR()"): lambda: 10 ** 34,
            (ORACLE, "BASE_FEED_1()"): lambda: FEED,
            (FEED, "description()"): lambda: "BTC / USD", (FEED, "decimals()"): lambda: 8,
            (FEED, "latestRoundData()"): lambda: [7, 100_000 * 10 ** 8, upd, upd, 7],
            (USDC_T, "symbol()"): lambda: "USDC", (USDC_T, "decimals()"): lambda: 6,
            (CBBTC_T, "symbol()"): lambda: "cbBTC", (CBBTC_T, "decimals()"): lambda: 8,
        }
        for role in ("BASE_FEED_2()", "QUOTE_FEED_1()", "QUOTE_FEED_2()", "BASE_VAULT()", "QUOTE_VAULT()"):
            table[(ORACLE, role)] = lambda: ZERO
        if to == IRM and signature.startswith("borrowRateView("):
            return RATE
        if (to, signature) not in table:
            raise RevertError(f"{signature} reverted on {to}")
        return table[(to, signature)]()


class DownRPC:
    url = "https://down.invalid/key123"

    def chain_id(self):
        raise RPCError("eth_chainId: ConnectionError")


def run(fake=None, **q):
    return dryrun.run({"market": MID, **q}, rpcs=[fake or FakeMainnet()])


def keys(o):
    if isinstance(o, dict):
        return [k for k in o] + [x for v in o.values() for x in keys(v)]
    if isinstance(o, list):
        return [x for v in o for x in keys(v)]
    return []


def assert_no_tx(out):
    json.dumps(out, allow_nan=False)
    bad = [k for k in keys(out) if FORBIDDEN.search(k)]
    assert bad == [], bad


# ---- outcomes ----------------------------------------------------------------------------------------------------------
def test_healthy_borrower_is_watching_and_labelled():
    fake = FakeMainnet()
    out = run(fake, borrower=HEALTHY)
    assert out["schema"] == "faultline.countermove.dryrun/1" and out["mode"] == "DRY-RUN"
    assert set(out["labels"]) == {"LIVE", "DRY-RUN"}
    for sec in ("environment", "market", "position", "dependencies"):
        assert out[sec]["label"] == "LIVE"
    for sec in ("hypothetical", "watcher", "decision"):
        assert out[sec]["label"] == "DRY-RUN"
    env = out["environment"]
    assert env["block"] == BLOCK and env["read_only"] and not env["signed"] and not env["broadcast"]
    assert env["rpc_host"] == "fake-mainnet.invalid" and "SECRETKEY" not in json.dumps(out)
    p = out["position"]
    assert p["debt"] == pytest.approx(700_000, rel=1e-6) and p["collateral"] == 10 and p["ltv"] == pytest.approx(0.70, rel=1e-6)
    assert p["lltv"] == 0.86 and p["buffer"] == pytest.approx(160_000, rel=1e-5) and p["healthy"]
    assert p["drop_to_liquidation"] == pytest.approx(1 - 0.70 / 0.86, abs=1e-4)
    f = out["dependencies"]["feeds"][0]
    assert (f["description"], f["freshness"], f["age_s"]) == ("BTC / USD", "fresh", 600)
    assert out["dependencies"]["stale"] == [] and out["dependencies"]["oracle"]["type"] == "MorphoChainlinkOracleV2"
    w = out["watcher"]
    assert (w["state"], w["outcome"], w["path"]) == ("WATCHING", "HOLD", ["WATCHING"])
    assert out["decision"]["decision"] == "HOLD" and out["decision"]["chosen"] is None
    h = out["hypothetical"]
    assert h["policy"]["trigger_ltv"] == pytest.approx(0.82) and h["policy"]["min_ltv_after"] == pytest.approx(0.40)
    assert h["reserves"]["loan"] == pytest.approx(70_000, rel=1e-6) and h["reserves"]["collateral"] == 1
    assert {"loan_reserve", "collateral_reserve", "trigger_ltv", "safety_margin", "strategies"} <= set(h["defaults_used"])
    assert [r["first_hit"] for r in out["reserve_requirements"]] == [0.05, 0.09, 0.12, 0.15]
    hit15 = out["reserve_requirements"][-1]
    assert hit15["ltv_after_hit"] == pytest.approx(0.70 / 0.85, rel=1e-4) and hit15["trigger_met_after_hit"]
    assert_no_tx(out)
    assert all(sig.split("(")[0] not in ("sendRawTransaction", "transfer", "approve") for _, sig in fake.reads)


def test_at_risk_borrower_detected_and_engine_would_repay_the_exact_minimum():
    out = run(borrower=AT_RISK)
    w = out["watcher"]
    assert w["state"] == "DETECTED" and w["outcome"] == "WOULD_EXECUTE" and w["trigger"]["trigger_met"]
    assert w["trigger"]["ltv"] == pytest.approx(0.84, rel=1e-5) and w["path"][-1] == "WOULD_EXECUTE"
    assert any("skipped" in s for s in w["path"]) and w["signed"] is False and w["broadcast"] is False
    d = out["decision"]
    assert d["decision"] == "EXECUTE" and d["chosen"]["strategy"] == "REPAY" and d["chosen"]["token"] == "USDC"
    assert {c["strategy"] for c in d["candidates"]} == {"REPAY", "TOP_UP", "FULL_REPAY"}
    top = next(c for c in d["candidates"] if c["strategy"] == "TOP_UP")
    assert top["status"] == "eligible" and top["capital_committed"] > d["chosen"]["capital_committed"]
    # same engine, same numbers: the chosen amount is the engine's exact minimum for this position and scenario set
    pos = {"collateral": 10 ** 9, "debt": int(round(out["position"]["debt"] * 10 ** 6)), "price": PRICE,
           "lltv": 86 * 10 ** 16, "rate_per_s": RATE}
    sc = [engine.Scenario("now", "now", engine.WAD), engine.Scenario("f", "f", 92 * 10 ** 16)]
    cfg = engine.EngineConfig(safety_margin_raw=pos["debt"] // 100, interest_horizon_s=86_400)
    assert d["chosen"]["amount"] == pytest.approx(engine.min_repay(pos, sc, cfg) / 1e6, abs=1e-6)
    assert d["chosen"]["ltv_after"] < 0.84 and d["chosen"]["meets_target"]
    assert out["hypothetical"]["scenarios"][1]["label"] == "cbBTC oracle price -8% follow-on"
    assert_no_tx(out)


def test_hypothetical_reserves_and_policy_drive_the_choice():
    no_usdc = run(borrower=AT_RISK, loan_reserve="0")
    assert no_usdc["decision"]["chosen"]["strategy"] == "TOP_UP" and no_usdc["decision"]["chosen"]["token"] == "cbBTC"
    tiny = run(borrower=AT_RISK, strategies="REPAY", loan_reserve="1000")
    assert tiny["watcher"]["outcome"] == "NO_ACTION" and tiny["decision"]["decision"] == "NO_ACTION"
    rep = next(c for c in tiny["decision"]["candidates"] if c["strategy"] == "REPAY")
    assert rep["status"] == "rejected" and any("reserve holds" in r for r in rep["reasons"])
    full = run(borrower=AT_RISK, strategies="FULL_REPAY", loan_reserve="900000")
    assert full["decision"]["chosen"]["strategy"] == "FULL_REPAY" and full["hypothetical"]["policy"]["max_full_repay"] == 900_000
    healthy_low_trigger = run(borrower=HEALTHY, trigger_ltv="0.6", min_ltv_after="0.3", follow_on_drop="0.25")
    assert healthy_low_trigger["watcher"]["state"] == "DETECTED"
    assert "follow_on_drop" not in healthy_low_trigger["hypothetical"]["defaults_used"]


def test_stale_feed_is_no_action_and_no_debt_is_nothing_to_protect():
    out = run(FakeMainnet(feed_age=20_000), borrower=AT_RISK)
    assert out["dependencies"]["stale"] and out["dependencies"]["feeds"][0]["freshness"] == "stale"
    assert out["watcher"]["state"] == "DETECTED" and out["watcher"]["outcome"] == "NO_ACTION"
    assert "stale" in out["watcher"]["reason"]
    empty = run(borrower=EMPTY)
    assert empty["position"]["has_debt"] is False and empty["watcher"]["outcome"] == "NOTHING_TO_PROTECT"
    assert empty["decision"] is None and empty["reserve_requirements"] == []


def test_auto_borrower_from_the_morpho_api(monkeypatch):
    calls = []

    def top(market_id, first=5):
        calls.append((market_id, first))
        return [{"address": AT_RISK, "borrow_assets_api": 840_000 * 10 ** 6, "collateral_api": 10 ** 9, "health_factor_api": 1.02},
                {"address": HEALTHY, "borrow_assets_api": 700_000 * 10 ** 6, "collateral_api": 10 ** 9, "health_factor_api": 1.2}]

    out = dryrun.run({"market": MID, "borrower": "auto"}, rpcs=[FakeMainnet()], top=top)
    assert out["borrower"]["source"] == "auto" and out["borrower"]["rank"] == 1
    assert out["borrower"]["address"] == dryrun.checksum(AT_RISK) and calls[0][0] == MID
    assert "borrower" in out["hypothetical"]["defaults_used"] and out["watcher"]["state"] == "DETECTED"
    second = dryrun.run({"market": MID, "rank": "2"}, rpcs=[FakeMainnet()], top=top)
    assert second["borrower"]["address"] == dryrun.checksum(HEALTHY) and second["watcher"]["state"] == "WATCHING"
    with pytest.raises(dryrun.DryRunError) as e:
        dryrun.run({"market": MID, "rank": "3"}, rpcs=[FakeMainnet()], top=top)
    assert e.value.status == 404 and e.value.code == "no_borrower"

    def down(*a, **k):
        raise RuntimeError("Morpho API down")

    with pytest.raises(dryrun.DryRunError) as e:
        dryrun.run({"market": MID}, rpcs=[FakeMainnet()], top=down)
    assert e.value.status == 503 and e.value.code == "morpho_api_unavailable"
    monkeypatch.setattr(morpho, "top_borrowers", top)  # default client path (no injected `top`)
    assert dryrun.run({"market": MID}, rpcs=[FakeMainnet()])["borrower"]["address"] == dryrun.checksum(AT_RISK)


# ---- HTTP contract: validation, structured JSON errors, no HTML ---------------------------------------------------------
@pytest.fixture
def fake_endpoints(monkeypatch):
    monkeypatch.setattr(dryrun, "endpoints", lambda: [FakeMainnet()])


def http(query: str):
    status, body = handler.respond("/api/countermove?action=dry-run&" + query)
    json.dumps(body, allow_nan=False)
    return status, body


def test_http_dry_run_ok(fake_endpoints):
    status, body = http(f"market={MID}&borrower={AT_RISK}&trigger_ltv=0.8&loan_reserve=100000")
    assert status == 200 and body["schema"] == "faultline.countermove.dryrun/1"
    assert body["hypothetical"]["policy"]["trigger_ltv"] == pytest.approx(0.8)
    assert body["hypothetical"]["reserves"]["loan"] == 100_000
    assert_no_tx(body)
    status, body = handler.respond("/api/countermove/dry-run?market=" + MID + "&borrower=" + HEALTHY)  # local dev alias
    assert status == 200 and body["watcher"]["state"] == "WATCHING"


@pytest.mark.parametrize("query,status,field", [
    ("market=0x1234", 400, "market"),
    ("market=" + "0x" + "g" * 64, 400, "market"),
    (f"market={MID}&borrower=0x123", 400, "borrower"),
    (f"market={MID}&borrower=0xAbCdEf0000000000000000000000000000000000", 400, "borrower"),  # wrong EIP-55 checksum
    (f"market={MID}&borrower={ZERO}", 400, "borrower"),
    (f"market={MID}&borrower={AT_RISK}&trigger_ltv=1.5", 400, "trigger_ltv"),
    (f"market={MID}&borrower={AT_RISK}&trigger_ltv=nan", 400, "trigger_ltv"),
    (f"market={MID}&borrower={AT_RISK}&trigger_ltv=abc", 400, "trigger_ltv"),
    (f"market={MID}&borrower={AT_RISK}&loan_reserve=-1", 400, "loan_reserve"),
    (f"market={MID}&borrower={AT_RISK}&collateral_reserve=inf", 400, "collateral_reserve"),
    (f"market={MID}&borrower={AT_RISK}&strategies=REPAY,YOLO", 400, "strategies"),
    (f"market={MID}&borrower={AT_RISK}&follow_on_drop=0.99", 400, "follow_on_drop"),
    (f"market={MID}&borrower={AT_RISK}&rank=0", 400, "rank"),
    (f"market={MID}&borrower={AT_RISK}&cooldown_s=1.5", 400, "cooldown_s"),
    (f"market={MID}&borrower={AT_RISK}&allow_partial=maybe", 400, "allow_partial"),
    (f"market={MID}&borrower={AT_RISK}&ranking=random", 400, "ranking"),
    (f"market={MID}&borrower={AT_RISK}&follow_on_dependency=ETH / USD", 400, "follow_on_dependency"),
    (f"market={'0x' + '22' * 32}&borrower={AT_RISK}", 404, "market"),
])
def test_http_invalid_inputs_are_structured_json(fake_endpoints, query, status, field):
    st, body = http(query)
    assert st == status and body["error"]["status"] == status and body["error"]["field"] == field
    assert body["error"]["code"] in ("invalid_input", "market_not_found") and body["error"]["message"]


def test_policy_rules_are_the_contract_rules(fake_endpoints):
    st, body = http(f"market={MID}&borrower={AT_RISK}&trigger_ltv=0.9")  # >= LLTV 86%
    assert st == 400 and body["error"]["code"] == "invalid_policy" and any("LLTV" in e for e in body["error"]["errors"])
    st, body = http(f"market={MID}&borrower={AT_RISK}&trigger_ltv=0.5&min_ltv_after=0.6")
    assert st == 400 and any("floor" in e for e in body["error"]["errors"])
    st, body = http(f"market={MID}&borrower={AT_RISK}&max_repay_per_action=10&max_repay_total=5")
    assert st == 400 and any("cumulative" in e for e in body["error"]["errors"])
    st, body = http(f"market={MID}&borrower={AT_RISK}&max_top_up_total=0&max_top_up_per_action=0&loan_reserve=0&foo=1")
    assert st == 200 and any("TOP_UP" in w for w in body["hypothetical"]["warnings"])
    assert any("foo" in w for w in body["hypothetical"]["warnings"])


def test_http_unknown_action_and_mainnet_down(monkeypatch):
    st, body = handler.respond("/api/countermove?action=sign-everything")
    assert st == 400 and body["error"]["field"] == "action"
    monkeypatch.setattr(dryrun, "endpoints", lambda: [DownRPC(), FakeMainnet(chain=31337)])
    st, body = http(f"market={MID}&borrower={AT_RISK}")
    assert st == 503 and body["error"]["code"] == "mainnet_unavailable" and len(body["error"]["attempts"]) == 2
    assert "key123" not in json.dumps(body) and "not Ethereum mainnet" in body["error"]["attempts"][1]


def test_cli_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(dryrun, "endpoints", lambda: [FakeMainnet()])
    assert dryrun.main(["--market", MID, "--borrower", AT_RISK, "--set", "loan_reserve=0", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"]["chosen"]["strategy"] == "TOP_UP"
    assert dryrun.main(["--market", MID, "--borrower", AT_RISK]) == 0
    text = capsys.readouterr().out
    assert "DRY-RUN (nothing signed or sent)" in text and "WOULD_EXECUTE" in text and "REPAY" in text
    assert dryrun.main(["--market", "0x12", "--borrower", AT_RISK]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["field"] == "market"


# ---- live, read-only ----------------------------------------------------------------------------------------------------
@pytest.mark.skipif(os.getenv("DEFIRISK_LIVE_TESTS") != "1", reason="set DEFIRISK_LIVE_TESTS=1 to read mainnet")
def test_live_dry_run_on_the_largest_cbbtc_usdc_borrower():
    out = dryrun.run({"market": "cbBTC/USDC", "borrower": "auto"})
    assert out["environment"]["block"] > 26_000_000 and out["environment"]["chain_id"] == 1
    assert out["market"]["id"] == dryrun.MARKETS["cbBTC/USDC"] and out["market"]["lltv"] == 0.86
    assert out["position"]["has_debt"] and out["position"]["debt"] > 0 and 0 < out["position"]["ltv"] < 0.86
    assert "BTC / USD" in {f.get("description") for f in out["dependencies"]["feeds"]}
    assert not out["dependencies"]["simulated"]
    assert out["watcher"]["state"] in ("WATCHING", "DETECTED") and len(out["reserve_requirements"]) == 4
    assert_no_tx(out)
