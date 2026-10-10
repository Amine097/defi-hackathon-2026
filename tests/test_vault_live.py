"""Phase 1 - Vault Risk Analyzer: LIVE checks against public Ethereum sources (RPC, Morpho API, DefiLlama, Chainlink).
Skipped unless DEFIRISK_LIVE_TESTS=1. Assertions are invariants (structure, coherence, cross-checks), never exact USD
figures, because the chain moves between runs."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

LIVE = os.getenv("DEFIRISK_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set DEFIRISK_LIVE_TESTS=1 to hit the real APIs")

BELEM = "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec"
EURCV = "0x5F7827FDeb7c20b443265Fc2F40845B715385Ff2"
CONFIDENTIAL = "0xc207d3f66537D7F66456808379A0E560cF20Da36"
YIELD = "0xE0181090c22579B6A217f1522cbf8c9f1F0C1965"
STEAKHOUSE_V1 = "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB"


def _req(addr, value=100_000, horizon=30, **kw):
    from defirisk.vault_input import parse_request
    return parse_request({"address": addr, "value_usd": str(value), "horizon_days": str(horizon), **kw})


@pytest.fixture(scope="module")
def results():
    from defirisk import vault_model as vm
    os.environ.pop("DEFIRISK_OFFLINE", None)
    return {a: vm.analyze(_req(a)) for a in (BELEM, CONFIDENTIAL, YIELD, STEAKHOUSE_V1)}


def _common(p, addr, version):
    json.dumps(p, allow_nan=False)
    assert p["vault"]["address"] == addr and p["vault"]["version"] == version and p["vault"]["chain_id"] == 1
    assert p["mode"] == "live" and p["as_of_block"] > 20_000_000
    assert p["decision"]["freshness"]["label"] == "fresh"
    al = p["allocations"]
    assert al["coverage"] >= 0.95 and len(al["items"]) >= 1
    assert abs(sum(i["share_of_vault"] for i in al["items"]) + al["idle_share"] + al["unattributed_share"] - 1) <= 0.005
    assert all(c["ok"] for c in p["snapshot"]["cross_checks"]), p["snapshot"]["cross_checks"]
    d = p["decision"]
    assert d["verdict"] in ("STAY", "EXIT", "REVIEW") and d["colour"] == {"STAY": "green", "EXIT": "red", "REVIEW": "amber"}[d["verdict"]]
    assert d["explanation"].startswith(d["verdict"])
    assert abs(d["margin_usd"] - (d["expected_loss_usd"] - (d["execution_cost_usd"] + d["carry_usd"]))) < 1e-6
    lo, hi = d["loss_band_usd"]
    assert lo <= d["expected_loss_usd"] <= hi
    if d["verdict"] == "REVIEW":
        assert d["confidence"] == "low" and d["reasons"]
    if d["verdict"] == "EXIT":
        assert d["withdrawal_feasibility"] in ("full", "full_via_force_deallocate")
    for s in p["scenarios"]:
        assert 0 <= s["loss_usd"] <= p["input"]["value_usd"]
    roles = {n["role"] for n in p["dependencies"]["nodes"]}
    assert {"market", "oracle", "morpho_blue", "chain"} <= roles and roles & {"collateral", "stablecoin"}


def test_live_belem_onchain_identity(results):
    p = results[BELEM]
    _common(p, BELEM, "v2")
    assert p["vault"]["asset"]["address"] == EURCV.lower() and p["vault"]["asset"]["symbol"] == "EURCV"
    assert p["vault"]["asset"]["decimals"] == 18 and p["vault"]["asset"]["currency"] == "EUR"
    assert p["vault"]["factory"].lower() == "0xa1d94f746defa1928926b84fb2596c06926c0405"
    sim = p["exit"]["simulation"]
    assert sim["status"] in ("simulated", "reverted")
    assert any("mGLOeuro" in (a.get("collateral_symbol") or "") for a in p["allocations"]["items"])


def test_live_two_other_v2_vaults(results):
    for a in (CONFIDENTIAL, YIELD):
        _common(results[a], a, "v2")
    assert results[CONFIDENTIAL]["vault"]["asset"]["symbol"] != "EURCV"


def test_live_v1_metamorpho(results):
    p = results[STEAKHOUSE_V1]
    _common(p, STEAKHOUSE_V1, "v1")
    assert p["vault"]["asset"]["decimals"] == 6
    cc = p["exit"]["capacity"]["api_cross_check"]
    assert cc is None or cc["ok"]


def test_live_carry_from_onchain_apy(results):
    for a, p in results.items():
        cr = p["exit"]["carry"]
        x = cr.get("apy_cross_check")
        assert x is None or x["ok"], (a, x)
        assert cr["status"] and cr["net_apy_onchain"] is not None
        if cr["net_apy_api"] is not None and cr["net_apy_api_incl_rewards"] is not None:
            assert cr["net_apy_api"] <= cr["net_apy_api_incl_rewards"] + 1e-9


def test_live_belem_large_position_partial():
    """P0-A: a position above the ordinary capacity is either confirmed whole through the forceDeallocate multicall
    simulation, or reported partial with the unavailable remainder (never an unsimulated route counted as executable)."""
    from defirisk import vault_model as vm
    p = vm.analyze(_req(BELEM, value=1_000_000))
    _common(p, BELEM, "v2")
    e = p["exit"]
    if e["withdrawal_feasibility"] not in ("full", "full_via_force_deallocate"):
        assert p["decision"]["verdict"] in ("REVIEW", "STAY")
        assert e["blocked_or_deferred_usd"] > 0
    if e["withdrawal_feasibility"] == "full_via_force_deallocate":
        assert e["routes"]["force_deallocate"]["status"] == "simulated"
        assert e["simulation_force_deallocate"]["status"] == "simulated"


def test_live_belem_1m_force_deallocate_route():
    """Audit F1 acceptance: Belem $1M exits through VaultV2.multicall([forceDeallocate..., redeem]) (eth_call, status
    ok), immediately withdrawable >= 99.9% of V, penalty = the on-chain forceDeallocatePenalty of the adapters used."""
    from defirisk import vault_model as vm
    p = vm.analyze(_req(BELEM, value=1_000_000))
    e, V = p["exit"], 1_000_000
    if e["routes"]["ordinary"]["status"] == "simulated":
        pytest.skip("ordinary liquidity currently covers $1M: the forceDeallocate route is not needed at this block")
    assert e["withdrawal_feasibility"] == "full_via_force_deallocate", e["routes"]
    assert e["executable_route"] == "force_deallocate" and e["immediately_withdrawable_usd"] >= 0.999 * V
    f = e["force_deallocate"]
    assert f["simulation"]["status"] == "simulated" and f["plan"]["covers_full"]
    rates = {a["address"].lower(): a["force_deallocate_penalty"] for a in p["vault"]["adapters"]}
    for s in f["plan"]["steps"]:
        assert s["penalty_rate"] == pytest.approx(rates[s["adapter"].lower()], abs=1e-18)
    assert e["force_deallocate_penalty_usd"] == pytest.approx(sum(s["penalty_usd"] for s in f["plan"]["steps"]), abs=1e-9)
    assert e["execution_cost_usd"] == pytest.approx(e["gas_usd"] + e["withdrawal_friction_usd"])
    assert p["decision"]["comparison_basis"]["kind"] == "full_position"


@pytest.mark.parametrize("qs,code,err", [
    ("address=0x123", 400, "invalid_input"),
    ("address=0x000000000000000000000000000000000000dEaD", 404, None),
    ("address=0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", 422, None),
    (f"address={BELEM}&chain_id=8453", 400, "invalid_input"),
    (f"address={BELEM}&value_usd=5", 400, "invalid_input"),
])
def test_live_http_errors(qs, code, err):
    import vault as api
    status, body = api.respond("/api/vault?" + qs)
    assert status == code, body
    assert "error" in body
    if err:
        assert body["error"]["code"] == err if isinstance(body["error"], dict) else body.get("code") == err


def test_live_http_ok_and_url_input():
    import vault as api
    url = f"https://app.morpho.org/ethereum/vault/{BELEM}/belem"
    status, body = api.respond(f"/api/vault?url={url}&value_usd=250000&horizon_days=60")
    assert status == 200, body
    assert body["vault"]["address"] == BELEM and body["input"]["horizon_days"] == 60
