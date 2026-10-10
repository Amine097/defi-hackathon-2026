"""Phase 1 - Vault Risk Analyzer: offline, deterministic tests (V01-V26) on dated fixtures recorded from public sources
(scripts/record_vault_fixture.py) plus synthetic variants of them. No network: every test here runs with the fixture
inputs of the pure vault_model.assess() step. Live checks are in tests/test_vault_live.py (DEFIRISK_LIVE_TESTS=1)."""
import copy
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from defirisk import vault_model as vm  # noqa: E402
from defirisk import vault_reader as vr  # noqa: E402
from defirisk.data import http, sources  # noqa: E402
from defirisk.vault_input import VaultError, address_from_url, parse_address, parse_request, to_checksum  # noqa: E402

BELEM = "0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec"
CONFIDENTIAL = "0xc207d3f66537D7F66456808379A0E560cF20Da36"
YIELD = "0xE0181090c22579B6A217f1522cbf8c9f1F0C1965"
STEAKHOUSE_V1 = "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB"
FIX = {a: ROOT / "data" / "fixtures" / f"vault_{a.lower()}.json" for a in (BELEM, CONFIDENTIAL, YIELD, STEAKHOUSE_V1)}


def load(addr):
    return json.loads(FIX[addr].read_text(encoding="utf-8"))


def run(fx, monkeypatch, req=None, snap=None, rd=None, prov=None, offline=False):
    """Replay assess() + payload() on fixture inputs with the clock frozen just after the recording."""
    monkeypatch.setattr(http, "now", lambda: fx["recorded_at"] + 5)
    if offline:
        monkeypatch.setenv("DEFIRISK_OFFLINE", "1")
    else:
        monkeypatch.delenv("DEFIRISK_OFFLINE", raising=False)
    req = req or copy.deepcopy(fx["req"])
    snap = snap or copy.deepcopy(fx["snap"])
    rd = rd or copy.deepcopy(fx["rd"])
    prov = prov or {**fx["prov"], "cached": 0, "live": max(fx["prov"].get("live", 0), 1), "mode": "live"}
    body = vm.assess(req, snap, rd, prov)
    return vm._js_safe(vm.payload(req, snap, rd, prov, body))


@pytest.fixture(scope="module")
def fixtures():
    return {a: load(a) for a in FIX}


# ---- V01-V03, V21: input contract and errors -----------------------------------------------------------------------
@pytest.mark.parametrize("raw,msg", [
    (None, "required"), ("", "required"), ("0x123", "40 hexadecimal"), ("0x" + "g" * 40, "40 hexadecimal"),
    ("D6d4b804014EF27836dBe9f8f6Bf6c71251548Ec", "40 hexadecimal"), (BELEM + "00", "40 hexadecimal"),
    ("0xD6D4b804014EF27836dBe9f8f6Bf6c71251548Ec", "checksum"), ("0x" + "0" * 40, "zero address"),
    ("x" * 300, "too long"),
])
def test_v01_invalid_addresses_rejected(raw, msg):
    with pytest.raises(ValueError, match=msg):
        parse_address(raw)


def test_v01_checksum_roundtrip():
    assert to_checksum(BELEM.lower()) == BELEM
    assert parse_address(BELEM) == {"address": BELEM, "checksum": "verified"}
    assert parse_address(BELEM.lower())["checksum"] == "not_provided"


def test_v01_eoa_and_non_vault_contract(monkeypatch):
    monkeypatch.setattr(sources, "_rpc", lambda m, p: "0x")
    with pytest.raises(VaultError) as e:
        vr.detect(BELEM, 1)
    assert (e.value.code, e.value.status) == ("not_found", 404)
    monkeypatch.setattr(sources, "_rpc", lambda m, p: "0x6080")
    monkeypatch.setattr(vr, "_call", lambda *a: [0])  # no factory registers it
    with pytest.raises(VaultError) as e:
        vr.detect(BELEM, 1)
    assert (e.value.code, e.value.status) == ("unsupported_contract", 422)
    monkeypatch.setattr(sources, "_rpc", lambda m, p: None)  # RPC down: not "not found"
    with pytest.raises(VaultError) as e:
        vr.detect(BELEM, 1)
    assert e.value.status == 503


def test_v04_detection_by_factory(monkeypatch):
    monkeypatch.setattr(sources, "_rpc", lambda m, p: "0x6080")
    v2f = next(iter(vr.FACTORY_V2))
    monkeypatch.setattr(vr, "_call", lambda to, sig, *a: [1] if (to, sig) == (v2f, "isVaultV2(address)") else [0])
    assert vr.detect(BELEM, 1)["version"] == "v2"
    v1f = next(iter(vr.FACTORY_V1))
    monkeypatch.setattr(vr, "_call", lambda to, sig, *a: [1] if (to, sig) == (v1f, "isMetaMorpho(address)") else [0])
    assert vr.detect(STEAKHOUSE_V1, 1)["version"] == "v1"


def test_v04_fixture_versions(fixtures):
    assert fixtures[BELEM]["snap"]["version"] == "v2" and fixtures[BELEM]["snap"]["factory"] in vr.FACTORY_V2
    assert fixtures[STEAKHOUSE_V1]["snap"]["version"] == "v1" and fixtures[STEAKHOUSE_V1]["snap"]["factory"] in vr.FACTORY_V1


def test_v02_chain_must_be_ethereum():
    assert parse_request({"address": BELEM})["chain_id"] == 1
    for c in ("8453", "137", "abc", "0"):
        with pytest.raises(ValueError):
            parse_request({"address": BELEM, "chain_id": c})


@pytest.mark.parametrize("v", ["0", "-5", "nan", "inf", "-inf", "1e400", "1e12", "999", "abc", "1,000", "0x10"])
def test_v03_value_bounds(v):
    with pytest.raises(ValueError):
        parse_request({"address": BELEM, "value_usd": v})


def test_v03_other_parameters():
    assert parse_request({"address": BELEM})["value_usd"] == 100_000
    for q in ({"horizon_days": "0"}, {"horizon_days": "366"}, {"horizon_days": "1.5"}, {"severity": "1.2"},
              {"severity": "nan"}, {"shock": "x" * 200}, {"shock": "<script>"}):
        with pytest.raises(ValueError):
            parse_request({"address": BELEM, **q})


def test_v01_url_input_no_ssrf():
    assert address_from_url(f"https://app.morpho.org/ethereum/vault/{BELEM}/belem-rwa-eurcv") == BELEM
    assert address_from_url(f"https://etherscan.io/address/{BELEM}") == BELEM
    for u in (f"https://evil.com/{BELEM}", f"file:///{BELEM}", f"https://app.morpho.org.evil.com/{BELEM}",
              f"https://app.morpho.org/x/{BELEM}/{CONFIDENTIAL}", "https://app.morpho.org/ethereum/vault/"):
        with pytest.raises(ValueError):
            address_from_url(u)


def test_v21_http_status_and_no_leak(monkeypatch):
    import vault as api
    assert api.respond("/api/vault?address=0x12")[0] == 400
    s, b = api.respond("/api/vault?address=" + BELEM + "&chain_id=10")
    assert s == 400 and b["error"]["code"] == "invalid_input"

    def boom(req):
        raise RuntimeError("https://rpc.example/v2/SECRETKEY123 exploded")
    monkeypatch.setattr(vm, "analyze", boom)
    s, b = api.respond("/api/vault?address=" + BELEM)
    assert s == 500 and "SECRETKEY" not in json.dumps(b) and "Traceback" not in json.dumps(b)

    def notfound(req):
        raise VaultError("not_found", 404, "no contract")
    monkeypatch.setattr(vm, "analyze", notfound)
    assert api.respond("/api/vault?address=" + BELEM)[0] == 404

    def down(req):
        raise vr.SourceDown("Ethereum JSON-RPC")
    monkeypatch.setattr(vm, "analyze", down)
    s, b = api.respond("/api/vault?address=" + BELEM)
    assert s == 503 and b["error"]["code"] == "source_unavailable"


def test_v21_payload_contract(fixtures, monkeypatch):
    p = run(fixtures[BELEM], monkeypatch)
    for k in ("input", "vault", "snapshot", "allocations", "dependencies", "risk", "exit", "decision", "assumptions",
              "warnings", "provenance", "mode", "as_of_block", "timestamp", "age_s"):
        assert k in p, k
    txt = json.dumps(p, allow_nan=False)  # strict JSON (no NaN / inf)

    def big_ints(o):
        if isinstance(o, bool):
            return []
        if isinstance(o, int):
            return [o] if abs(o) > 2 ** 53 else []
        if isinstance(o, dict):
            return [x for v in o.values() for x in big_ints(v)]
        if isinstance(o, list):
            return [x for v in o for x in big_ints(v)]
        return []
    assert big_ints(json.loads(txt)) == []  # raw on-chain integers are strings (JS-safe)
    assert p["mode"] in ("live", "mixed", "cache", "offline") and p["mode"] != "mock"


def test_v21_invalid_scenario(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    with pytest.raises(VaultError) as e:
        run(fx, monkeypatch, req={**fx["req"], "shock": "collateral:0xdeadbeef"})
    assert e.value.status == 400 and e.value.code == "invalid_scenario"
    assert all(i.split(":")[0] in ("vault", "chain", "morpho_blue", "asset", "fx", "adapter", "market", "collateral", "oracle",
                                   "unattributed") for i in e.value.detail["valid_ids"])


# ---- V05-V07, V10: discovery and reconciliation on the recorded vaults ---------------------------------------------
@pytest.mark.parametrize("addr", list(FIX))
def test_v10_reconciliation(fixtures, monkeypatch, addr):
    p = run(fixtures[addr], monkeypatch)
    al = p["allocations"]
    ta = int(p["snapshot"]["total_assets_raw"])
    s = sum(int(i["supply_raw"]) for i in al["items"]) + int(al["idle_raw"]) + int(al["reconciliation"]["unattributed_raw"])
    assert abs(s - ta) / ta <= 0.005
    assert abs(sum(i["share_of_vault"] for i in al["items"]) + al["idle_share"] + al["unattributed_share"] - 1) <= 0.005
    assert al["coverage"] >= 0.95 and al["displayed"].startswith("all markets")
    assert len(al["items"]) == len(fixtures[addr]["snap"]["markets"])  # no top-N truncation
    assert all(c["ok"] for c in p["snapshot"]["cross_checks"])


def test_v05_belem_identity(fixtures, monkeypatch):
    p = run(fixtures[BELEM], monkeypatch)
    assert p["vault"]["address"] == BELEM and p["vault"]["version"] == "v2"
    assert p["vault"]["asset"]["symbol"] == "EURCV" and p["vault"]["asset"]["decimals"] == 18
    assert p["vault"]["liquidity_adapter"] and p["vault"]["liquidity_market"]
    assert p["decision"]["verdict"] in ("STAY", "EXIT", "REVIEW")


def test_v07_graph_changes_with_address(fixtures, monkeypatch):
    ids = {a: {n["id"] for n in run(fixtures[a], monkeypatch)["dependencies"]["nodes"]} for a in FIX}
    keys = list(ids)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            assert ids[keys[i]] != ids[keys[j]]
    for a in FIX:
        assert f"vault:{a}" in ids[a]
    src = "".join((ROOT / "src" / "defirisk" / f).read_text(encoding="utf-8") for f in ("vault_model.py", "vault_reader.py"))
    for a in (BELEM, CONFIDENTIAL, YIELD, STEAKHOUSE_V1):
        assert a.lower()[2:] not in src.lower(), "no vault address hardcoded in the analyzer"


# ---- V08 / V09 / V17 / V26: withdrawal ------------------------------------------------------------------------------
def test_v09_v2_max_redeem_zero_is_not_zero_liquidity(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    assert fx["rd"]["sim"]["max_redeem_contract"] == 0  # VaultV2 by design
    p = run(fx, monkeypatch)
    cap = p["exit"]["capacity"]
    assert cap["ordinary_assets"] > 0 and p["exit"]["withdrawal_feasibility"] == "full"
    assert cap["rows"] and cap["rows"][0]["path"] == "liquidity adapter"
    assert cap["api_cross_check"]["ok"]


def test_v09_closed_gate_blocks_ordinary_exit(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    snap = copy.deepcopy(fx["snap"])
    snap["gates"]["withdraw_open"] = False
    p = run(fx, monkeypatch, snap=snap)
    assert p["exit"]["withdrawal_feasibility"] == "zero" and p["decision"]["verdict"] != "EXIT"


def test_v08_v1_withdraw_queue(fixtures, monkeypatch):
    fx = fixtures[STEAKHOUSE_V1]
    p = run(fx, monkeypatch)
    rows = p["exit"]["capacity"]["rows"]
    assert [r["path"] for r in rows] == [f"withdrawQueue[{i}]" for i in range(len(rows))]
    total = sum(int(r["available_raw"]) for r in rows)  # MetaMorpho: the vault's own token balance is not withdrawable
    assert int(fx["snap"]["idle_raw"]) > 0 and abs(total - p["exit"]["capacity"]["ordinary_assets"] * 10 ** 6) <= 1
    by_id = {m["id"]: m for m in fx["snap"]["markets"]}
    for r in rows:  # never more than the vault supplies nor than the market's free liquidity
        m = by_id[r["market"]]
        assert int(r["available_raw"]) <= min(m["vault_supply_raw"], m["liquidity_raw"])
    assert p["exit"]["capacity"]["api_cross_check"]["ok"]  # contract maxWithdraw walk agrees


def _set_exposure(fx, value_usd, sim_status):
    req = {**fx["req"], "value_usd": value_usd}
    rd = copy.deepcopy(fx["rd"])
    px = fx["snap"]["asset_price"]["price_usd"]
    rd["assets_raw"] = int(value_usd / px * 10 ** fx["snap"]["asset_decimals"])
    rd["sim"] = {**rd["sim"], "status": sim_status}
    if sim_status == "simulated":
        rd["sim"]["assets_out_raw"] = rd["assets_raw"]
    return req, rd


def test_v17_partial_zero_unknown(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    cap_usd = run(fx, monkeypatch)["exit"]["capacity"]["ordinary_usd"]
    req, rd = _set_exposure(fx, 1_000_000, "reverted")
    p = run(fx, monkeypatch, req=req, rd=rd)
    e = p["exit"]
    assert e["withdrawal_feasibility"] == "partial"
    assert e["immediately_withdrawable_usd"] == pytest.approx(cap_usd, rel=1e-9)
    assert e["immediately_withdrawable_usd"] + e["blocked_or_deferred_usd"] == pytest.approx(1_000_000, rel=1e-6)
    snap = copy.deepcopy(fx["snap"])
    for m in snap["markets"]:
        m["liquidity_raw"] = 0
    snap["idle_raw"] = 0
    p = run(fx, monkeypatch, snap=snap)
    assert p["exit"]["withdrawal_feasibility"] == "zero" and p["exit"]["immediately_withdrawable_usd"] == 0
    req, rd = _set_exposure(fx, 100_000, "unavailable")
    p = run(fx, monkeypatch, req=req, rd=rd)
    assert p["exit"]["withdrawal_feasibility"] == "unknown" and p["decision"]["verdict"] == "REVIEW"


def _carry(fx, apy):
    snap = copy.deepcopy(fx["snap"])
    for m in snap["markets"]:
        m["supply_apy"] = apy
    return snap


def test_v26_partial_exit_never_executable_exit(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    snap = _carry(fx, 0.0)  # no carry -> the exit side is just gas: the point verdict is EXIT
    full = run(fx, monkeypatch, snap=snap)
    assert full["decision"]["verdict"] == "EXIT"
    req, rd = _set_exposure(fx, 1_000_000, "reverted")
    p = run(fx, monkeypatch, req=req, snap=snap, rd=rd)
    d = p["decision"]
    assert d["point_verdict"] == "EXIT" and d["verdict"] == "REVIEW" and d["withdrawal_feasibility"] == "partial"
    assert "partial: exit $" in d["lean"] and any("not fully executable" in r for r in d["reasons"])


# ---- V11 / V12: dedup and depositor P&L ---------------------------------------------------------------------------------
def test_v11_shared_dependency_one_node_no_double_count(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    snap = copy.deepcopy(fx["snap"])
    big = max(snap["markets"], key=lambda m: m["vault_supply_raw"])
    twin = copy.deepcopy(big)
    twin["id"] = "0x" + "ab" * 32
    big["vault_supply_raw"] //= 2
    twin["vault_supply_raw"] = big["vault_supply_raw"]
    snap["markets"].append(twin)
    pri = fx["rd"]["priors"]
    g1, _ = vm.build_graph(fx["req"], fx["snap"], pri)
    g2, _ = vm.build_graph(fx["req"], snap, pri)
    cid = f"collateral:{big['collateral_token']}"
    assert [n.id for n in g2.nodes].count(cid) == 1
    assert [n.id for n in g2.nodes].count(f"oracle:{big['oracle']}") == 1
    assert sum(1 for e in g2.edges if e.dst == cid) == 2
    l1 = vm.conditional_loss(g1, {cid: 0.4})["usd"]
    l2 = vm.conditional_loss(g2, {cid: 0.4})["usd"]
    assert l2 == pytest.approx(l1, rel=0.01)  # the same exposure split in two markets is counted once


def test_v12_liquidation_without_shortfall_costs_depositor_nothing(fixtures):
    m = max(fixtures[BELEM]["snap"]["markets"], key=lambda m: m["vault_supply_raw"])
    small = vm.bad_debt_fraction(m, 0.15)
    assert small["liquidated"] > 0 and small["fraction"] == 0.0  # borrowers liquidated, suppliers whole
    assert vm.bad_debt_fraction(m, 0.5)["fraction"] > 0  # only a deep jump leaves bad debt


def test_v12_unindexed_debt_without_list_is_valued_at_lltv(fixtures):
    """No indexed sample: central = high = every position at the LLTV (the previous rule), low = no bad debt."""
    m = copy.deepcopy(max(fixtures[BELEM]["snap"]["markets"], key=lambda m: m["vault_supply_raw"]))
    m["borrowers"] = {"status": "unavailable", "items": []}
    worst = vm.bad_debt_fraction(m, 0.3)
    assert worst["unindexed_debt_raw"] == m["total_borrow_raw"] and worst["indexed_share"] == 0
    assert worst["fraction"] == worst["fraction_high"] > 0 and worst["fraction_low"] == 0
    assert worst["fraction"] >= vm.bad_debt_fraction(max(load(BELEM)["snap"]["markets"], key=lambda x: x["vault_supply_raw"]), 0.3)["fraction"]


def _partial_list(m, keep):
    """Synthetic partial coverage: drop the smallest indexed borrowers so they become unindexed debt."""
    m = copy.deepcopy(m)
    items = sorted(m["borrowers"]["items"], key=lambda i: -i["debt_raw"])[:keep]
    m["borrowers"] = {**m["borrowers"], "items": items}
    return m


def test_v12_partial_coverage_band(fixtures):
    """Item 2 (review H): unindexed debt is a band, not a point at the LLTV. low <= central <= high, high = the old
    all-at-LLTV figure, central = indexed rate shrunk toward the LLTV by the unindexed share."""
    full = max(fixtures[STEAKHOUSE_V1]["snap"]["markets"], key=lambda m: m["vault_supply_raw"])  # cbBTC, 50 borrowers
    m = _partial_list(full, 10)
    drop = 0.4
    r = vm.bad_debt_fraction(m, drop)
    assert 0 < r["indexed_share"] < 1 and r["unindexed_debt_raw"] > 0
    assert r["fraction_low"] <= r["fraction"] <= r["fraction_high"]
    # high reproduces the previous single assumption (all unindexed debt at the LLTV)
    rest = r["unindexed_debt_raw"]
    at_lltv = vm.morpho.liquidation_outcome({"collateral_value_usd_oracle": rest / m["lltv"], "debt_value_usd": rest,
                                             "lltv": m["lltv"], "liquidation_incentive_factor": m["lif"]}, drop)["lender_bad_debt_usd"]
    idx_bd = r["fraction_low"] * m["total_supply_raw"]
    assert r["fraction_high"] == pytest.approx((idx_bd + at_lltv) / m["total_supply_raw"], rel=1e-9)
    u = r["unindexed_rate"]
    c = r["indexed_share"]
    assert u["central"] == pytest.approx(c * u["indexed"] + (1 - c) * u["at_lltv"], rel=1e-12)
    assert u["high"] >= u["central"] >= u["low"] == 0
    # the band only spans the unindexed debt: width = unindexed debt x worst rate
    assert r["fraction_high"] - r["fraction_low"] == pytest.approx(rest * u["high"] / m["total_supply_raw"], rel=1e-9)
    more = vm.bad_debt_fraction(_partial_list(full, 30), drop)
    assert more["indexed_share"] > c and more["unindexed_debt_raw"] < rest
    # full list: no band from coverage
    f = vm.bad_debt_fraction(full, drop)
    if f["unindexed_debt_raw"] == 0:
        assert f["fraction_low"] == f["fraction"] == f["fraction_high"]


def test_v12_coverage_band_reaches_the_uncertainty_band(fixtures, monkeypatch):
    """The band is reported through uncertainty.loss_band: the collateral edge carries an explicit [low, high]; the
    high end of the loss band does not drop (worst case kept as the high end), the central does not rise."""
    from defirisk import uncertainty
    fx = fixtures[STEAKHOUSE_V1]
    snap = copy.deepcopy(fx["snap"])
    mi = max(range(len(snap["markets"])), key=lambda i: snap["markets"][i]["vault_supply_raw"])
    snap["markets"][mi] = _partial_list(snap["markets"][mi], 10)
    g, emeta = vm.build_graph(fx["req"], snap, fx["rd"]["priors"])
    m = snap["markets"][mi]
    key = uncertainty.edge_key(f"market:{m['id']}", f"collateral:{m['collateral_token']}")
    band = g.position.meta["edge_bands"][key]
    e = next(e for e in g.edges if uncertainty.edge_key(e.src, e.dst) == key)
    assert band["low"] < e.transmission < band["high"]
    assert emeta[(e.src, e.dst)]["transmission_band"] == band
    assert uncertainty.edge_band(g, e, "low") == pytest.approx(band["low"] * uncertainty.T_RANGE[0])
    assert uncertainty.edge_band(g, e, "high") == pytest.approx(min(1.0, band["high"] * uncertainty.T_RANGE[1]))
    inv = next(x for x in uncertainty.inventory(g)["edges"] if (x["src"], x["dst"]) == (e.src, e.dst))
    assert inv["band_why"] and inv["low"] < inv["transmission"] < inv["high"]
    # previous behaviour = everything unindexed at the LLTV in the central, +-25% around it
    old = copy.deepcopy(g)
    old.position.meta["edge_bands"] = {}
    for oe in old.edges:
        if uncertainty.edge_key(oe.src, oe.dst) == key:
            oe.transmission = band["high"]
    new_b, old_b = uncertainty.loss_band(g), uncertainty.loss_band(old)
    assert new_b["central_usd"] < old_b["central_usd"]
    assert new_b["high_usd"] >= old_b["high_usd"] - 1e-9
    assert new_b["low_usd"] <= new_b["central_usd"] <= new_b["high_usd"]


# ---- item 3 (review H): oracle failure, both directions, explicit and bounded ---------------------------------------
def test_v12_oracle_failure_both_directions(fixtures):
    m = max(fixtures[STEAKHOUSE_V1]["snap"]["markets"], key=lambda m: m["vault_supply_raw"])
    d = 0.4
    o = vm.oracle_failure_fraction(m, d)
    ts, L, lltv, lif = m["total_supply_raw"], m["liquidity_raw"], m["lltv"], m["lif"]
    # over-pricing: free liquidity drained at once; recovery net of the liquidation incentive (central) / full (low)
    assert o["over"] == pytest.approx(L * max(0, 1 - (1 - d) / (lltv * lif)) / ts, rel=1e-12)
    assert o["over_full_recovery"] == pytest.approx(L * max(0, 1 - (1 - d) / lltv) / ts, rel=1e-12)
    assert o["over_full_recovery"] < o["over"]  # the incentive is paid out of the drained collateral
    # under-pricing: Morpho realises bad debt at the false price = a real drop of the same size
    bd = vm.bad_debt_fraction(m, d)
    assert (o["under"], o["under_low"], o["under_high"]) == (bd["fraction"], bd["fraction_low"], bd["fraction_high"])
    assert o["fraction"] == pytest.approx((o["over"] + o["under"]) / 2)
    assert o["fraction_low"] <= min(o["over"], o["under"]) <= o["fraction"] <= max(o["over"], o["under"]) <= o["fraction_high"]
    # bounded: drain capped by today's free liquidity; liquidity exhausted -> only the under-pricing channel remains
    dry = vm.oracle_failure_fraction(m, d, liquidity_factor=0.0)
    assert dry["over"] == dry["over_full_recovery"] == 0 and dry["fraction"] == pytest.approx(o["under"] / 2)
    assert o["fraction_high"] <= 1.0


def test_v12_mild_underpricing_costs_suppliers_nothing(fixtures):
    """Justification of the old exclusion, now a computed result: while reported collateral x LIF covers the debt, an
    under-pricing only moves value from borrowers to liquidators; suppliers lose 0."""
    m = max(fixtures[BELEM]["snap"]["markets"], key=lambda m: m["vault_supply_raw"])
    mild = 0.15
    assert vm.bad_debt_fraction(m, mild)["liquidated"] > 0
    o = vm.oracle_failure_fraction(m, mild)
    assert o["under"] == o["under_high"] == 0.0
    # mild over-pricing below 1 - LLTV x LIF: no drain profit, no supplier loss either
    assert vm.oracle_failure_fraction(m, (1 - m["lltv"] * m["lif"]) * 0.9)["over"] == 0.0


def test_v12_oracle_edge_band_in_graph(fixtures):
    from defirisk import uncertainty
    fx = fixtures[STEAKHOUSE_V1]
    g, emeta = vm.build_graph(fx["req"], fx["snap"], fx["rd"]["priors"])
    oe = [e for e in g.edges if e.dst.startswith("oracle:")]
    assert oe
    for e in oe:
        b = g.position.meta["edge_bands"][uncertainty.edge_key(e.src, e.dst)]
        assert b["low"] <= e.transmission <= b["high"] and "direction unknown" in e.reason
    oracle_nodes = [n for n in g.nodes if n.meta.get("role") == "oracle"]
    assert all("direction unknown" in n.meta["lgf_source"] for n in oracle_nodes)


# ---- item 1 (review H): reconciliation per adapter --------------------------------------------------------------------
def test_v10_v1_reconciliation_is_not_a_tautology(fixtures):
    """MetaMorpho V1: the pseudo-adapter is checked against the contract's totalAssets(), not against the sum of the
    same market reads; the vault's idle token balance is outside totalAssets (MetaMorpho) and is not added."""
    snap = copy.deepcopy(fixtures[STEAKHOUSE_V1]["snap"])
    assert snap["idle_raw"] > 0
    r = vr.reconcile(snap)
    row = r["adapters"][0]
    assert row["reported_raw"] == snap["total_assets_raw"] and row["within_tolerance"]
    assert r["idle_raw"] == 0 and r["idle_outside_total_assets_raw"] == snap["idle_raw"]
    assert r["gap_pct"] == pytest.approx(0.0, abs=1e-15) and r["within_tolerance"] and r["coverage"] == 1.0
    # a market missing from our reads is now visible on the adapter row (it used to be reconciled against itself)
    big = max(snap["markets"], key=lambda m: m["vault_supply_raw"])
    snap["markets"] = [m for m in snap["markets"] if m is not big]
    snap["adapters"][0]["real_assets_raw"] = sum(m["vault_supply_raw"] for m in snap["markets"])  # old tautological value
    r = vr.reconcile(snap)
    assert r["adapters"][0]["gap_raw"] == big["vault_supply_raw"] and not r["adapters"][0]["within_tolerance"]
    assert not r["within_tolerance"] and r["unattributed_raw"] == big["vault_supply_raw"]


def test_v10_per_adapter_gaps_not_masked():
    """Two V2 adapters with opposite gaps: the vault-level sum balances, but each adapter is out of tolerance, and the
    surplus read under one adapter does not fill the other's hole (unattributed stays)."""
    mk = lambda holder, supply: {"id": "0x" + "1" * 64, "holder": holder, "vault_supply_raw": supply}  # noqa: E731
    a, b = "0x" + "a" * 40, "0x" + "b" * 40
    snap = {"version": "v2", "idle_raw": 0, "total_assets_raw": 2_000,
            "adapters": [{"address": a, "type": "MorphoMarketV1AdapterV2", "real_assets_raw": 1_000, "supported": True},
                         {"address": b, "type": "MorphoMarketV1AdapterV2", "real_assets_raw": 1_000, "supported": True}],
            "markets": [mk(a, 800), mk(b, 1_200)]}
    r = vr.reconcile(snap)
    assert r["gap_pct"] == 0.0  # the old vault-level check passed
    assert [x["gap_raw"] for x in r["adapters"]] == [200, -200]
    assert not r["adapters_within_tolerance"] and not r["within_tolerance"]
    assert r["unattributed_raw"] == 200 and r["coverage"] == pytest.approx(0.9)
    # holder match is strict and case-insensitive
    snap["markets"][0]["holder"] = a.upper().replace("0X", "0x")
    assert vr.reconcile(snap)["adapters"][0]["markets_raw"] == 800


def test_v10_adapter_gap_warning_and_unattributed_node(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    snap = copy.deepcopy(fx["snap"])
    ad = snap["adapters"][0]
    ad["real_assets_raw"] = int(ad["real_assets_raw"]) * 102 // 100  # adapter reports 2% more than its markets
    snap["total_assets_raw"] = int(snap["total_assets_raw"]) + int(ad["real_assets_raw"]) // 102 * 2
    snap["reconciliation"] = vr.reconcile(snap)
    p = run(fx, monkeypatch, snap=snap)
    assert any("adapter(s)" in w for w in p["warnings"])
    assert "unattributed" in {n["id"] for n in p["dependencies"]["nodes"]}


# ---- V13 / V14: scenarios, bounds, monotonicity -------------------------------------------------------------------------
def test_v13_scenarios(fixtures, monkeypatch):
    p = run(fixtures[BELEM], monkeypatch)
    names = " | ".join(s["name"] for s in p["scenarios"])
    for k in ("Collateral crash", "Oracle failure", "Market failure", "Liquidity crisis", "Correlated", "depeg"):
        assert k in names, k
    V = p["input"]["value_usd"]
    for s in p["scenarios"]:
        assert s["label"] == "conditional_on_shock" and 0 <= s["loss_usd"] <= V
        assert s["vault"] == BELEM
        for sid, paths in s["paths"].items():
            assert paths and all(r["path"][0] == "pos" and r["path"][-1] == sid for r in paths)
    corr = next(s for s in p["scenarios"] if s["name"].startswith("Correlated"))
    single = max(s["loss_usd"] for s in p["scenarios"] if s["name"].startswith(("Collateral", "Oracle")))
    assert single <= corr["loss_usd"] <= V
    dep = next(s for s in p["scenarios"] if "depeg" in s["name"])
    assert dep["decision_neutral"] and dep["stay_loss_usd"] == dep["exit_to_asset_loss_usd"]
    liq = next(s for s in p["scenarios"] if s["name"] == "Liquidity crisis")
    assert liq["loss_usd"] == 0 and liq["withdrawal_feasibility"] in ("partial", "zero")


def test_v13_custom_shock_targets_this_vault(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    m = max(fx["snap"]["markets"], key=lambda m: m["vault_supply_raw"])
    cid = f"collateral:{m['collateral_token']}"
    p = run(fx, monkeypatch, req={**fx["req"], "shock": cid, "severity": 0.6})
    c = p["scenarios"][0]
    assert c["custom"] and c["shocked"][0]["id"] == cid and c["vault"] == BELEM
    pt = {x["drop"]: x["loss_usd"] for x in p["sensitivity"]["collateral_crash_curve"]["points"]}
    assert c["loss_usd"] == pytest.approx(pt[0.6], rel=1e-9)


@pytest.mark.parametrize("addr", list(FIX))
def test_v14_bounds_and_monotonicity(fixtures, monkeypatch, addr):
    p = run(fixtures[addr], monkeypatch)
    V = p["input"]["value_usd"]
    r = p["risk"]
    assert 0 <= r["band_usd"][0] <= r["expected_loss_usd"] <= r["band_usd"][1] <= V
    pts = [x["loss_usd"] for x in p["sensitivity"]["collateral_crash_curve"]["points"]]
    assert pts == sorted(pts) and all(0 <= x <= V for x in pts)
    for t in p["sensitivity"]["tornado_p_x0.5_x2"]:
        assert t["low_usd"] <= r["expected_loss_usd"] <= t["high_usd"]


def test_v14_linear_in_exposure(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    a = run(fx, monkeypatch)
    req, rd = _set_exposure(fx, 200_000, "simulated")
    rd["gas_usd"] = fx["rd"]["gas_usd"]
    b = run(fx, monkeypatch, req=req, rd=rd)
    assert b["risk"]["expected_loss_usd"] == pytest.approx(2 * a["risk"]["expected_loss_usd"], rel=1e-9)
    assert b["exit"]["carry"]["usd"] == pytest.approx(2 * a["exit"]["carry"]["usd"], rel=1e-9)


# ---- V15 / V16: EURCV, valuation ------------------------------------------------------------------------------------------
def test_v15_eurcv_price_fx_and_peg(fixtures, monkeypatch):
    p = run(fixtures[BELEM], monkeypatch)
    a = p["vault"]["asset"]
    assert a["currency"] == "EUR" and a["decimals"] == 18
    assert a["fx"]["pair"] == "EUR/USD" and a["price_usd"] == pytest.approx(a["fx"]["rate"] * a["peg_vs_eur"], rel=1e-12)
    assert 0.9 < a["peg_vs_eur"] < 1.1 and a["price_usd"] > 1.0  # not silently 1 EURCV = 1 USD
    neutral = {n["id"] for n in p["dependencies"]["nodes"] if n["decision_neutral"]}
    assert "fx:EURUSD" in neutral and any(i.startswith("asset:") for i in neutral)
    assert all(e["transmission"] == 0 for e in p["dependencies"]["edges"] if e["dst"] in neutral)


def test_v15_missing_fx_no_firm_usd(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    snap = copy.deepcopy(fx["snap"])
    snap["asset_price"].pop("fx")
    p = run(fx, monkeypatch, snap=snap)
    assert p["decision"]["verdict"] == "REVIEW" and any("EUR/USD" in b for b in p["decision"]["blockers"])


def test_v16_share_valuation(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    p = run(fx, monkeypatch)
    s = fx["snap"]
    shares = int(p["exit"]["shares_hypothetical"])
    assets = shares * s["share_price_raw"] / 10 ** s["decimals"]
    assert assets == pytest.approx(fx["rd"]["assets_raw"], rel=1e-9)
    assert p["exit"]["notional_assets"] * p["vault"]["asset"]["price_usd"] == pytest.approx(p["input"]["value_usd"], rel=1e-9)
    assert "HYPOTHETICAL" in p["input"]["value_semantics"]


# ---- V18 / V19: costs, carry, verdict coherence ---------------------------------------------------------------------------
@pytest.mark.parametrize("addr", list(FIX))
def test_v18_cost_breakdown(fixtures, monkeypatch, addr):
    p = run(fixtures[addr], monkeypatch)
    e, d = p["exit"], p["decision"]
    assert e["execution_cost_usd"] == pytest.approx(e["gas_usd"] + e["withdrawal_friction_usd"] + e["exit_fee_usd"])
    c = e["carry"]
    assert c["usd"] == pytest.approx(p["input"]["value_usd"] * c["net_apy_onchain"] * p["input"]["horizon_days"] / 365)
    assert d["exit_side_usd"] == pytest.approx(d["execution_cost_usd"] + d["carry_usd"])
    assert d["margin_usd"] == pytest.approx(d["expected_loss_usd"] - d["exit_side_usd"])
    assert e["usd_conversion"]["counted_in_decision"] is False
    if c["apy_cross_check"]:
        assert c["apy_cross_check"]["ok"]
    assert e["gas_usd"] > 0 and e["quote_status"] == "simulated"


def test_v18_rewards_not_counted_in_carry(fixtures, monkeypatch):
    p = run(fixtures[CONFIDENTIAL], monkeypatch)
    c = p["exit"]["carry"]
    assert c["rewards_api"] and c["rewards_usd_not_counted"] > 0
    assert c["net_apy_onchain"] == pytest.approx(c["net_apy_api"], abs=vm.APY_XCHECK_TOL)


def test_v18_horizon_scaling(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    a = run(fx, monkeypatch)
    b = run(fx, monkeypatch, req={**fx["req"], "horizon_days": 90})
    assert b["exit"]["carry"]["usd"] == pytest.approx(3 * a["exit"]["carry"]["usd"], rel=1e-9)
    assert b["risk"]["expected_loss_usd"] > a["risk"]["expected_loss_usd"]


def _check_coherent(p):
    d = p["decision"]
    assert d["colour"] == {"STAY": "green", "EXIT": "red", "REVIEW": "amber"}[d["verdict"]]
    lo, hi = d["loss_band_usd"]
    elo, ehi = d["exit_band_usd"]
    if d["verdict"] == "STAY":
        assert hi < elo and d["margin_usd"] < 0 and not d["blockers"]
    if d["verdict"] == "EXIT":
        assert lo > ehi and d["margin_usd"] > 0 and d["withdrawal_feasibility"] == "full" and not d["blockers"]
    if d["verdict"] == "REVIEW":
        assert d["lean"] and d["reasons"] and d["confidence"] == "low"
        assert d["point_verdict"] == ("EXIT" if d["margin_usd"] > 0 else "STAY")
        assert f"lean {d['point_verdict']}" in d["lean"]
    assert d["explanation"].startswith(d["verdict"])
    assert f"point verdict {d['point_verdict']}" in d["explanation"]


def test_v19_three_verdicts_coherent(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    stay = run(fx, monkeypatch, snap=_carry(fx, 0.5))
    exit_ = run(fx, monkeypatch, snap=_carry(fx, 0.0))
    review = run(fx, monkeypatch)
    assert (stay["decision"]["verdict"], exit_["decision"]["verdict"], review["decision"]["verdict"]) == ("STAY", "EXIT", "REVIEW")
    for p in (stay, exit_, review):
        _check_coherent(p)


@pytest.mark.parametrize("addr", list(FIX))
def test_v19_live_fixtures_coherent(fixtures, monkeypatch, addr):
    _check_coherent(run(fixtures[addr], monkeypatch))


UI_FIX = ROOT / "tests" / "js" / "fixtures"


def test_v19_ui_fixtures_in_sync(fixtures, monkeypatch):
    """The Node UI tests (tests/js/vault_view.test.mjs) read real backend payloads for the three verdicts.
    Regenerate with FAULTLINE_EXPORT_UI_FIXTURES=1; otherwise the committed files must match the backend."""
    import os
    fx = fixtures[BELEM]
    out = {"stay": run(fx, monkeypatch, snap=_carry(fx, 0.5)), "exit": run(fx, monkeypatch, snap=_carry(fx, 0.0)),
           "review": run(fx, monkeypatch)}
    if os.getenv("FAULTLINE_EXPORT_UI_FIXTURES") == "1":
        UI_FIX.mkdir(parents=True, exist_ok=True)
        for k, p in out.items():
            (UI_FIX / f"vault_{k}.json").write_text(json.dumps(p, allow_nan=False, indent=1), encoding="utf-8")
    for k, p in out.items():
        saved = json.loads((UI_FIX / f"vault_{k}.json").read_text(encoding="utf-8"))
        a, b = saved["decision"], p["decision"]
        assert a["verdict"] == b["verdict"] == k.upper() and a["point_verdict"] == b["point_verdict"]
        for f in ("expected_loss_usd", "exit_side_usd", "margin_usd", "carry_usd", "execution_cost_usd"):
            assert a[f] == pytest.approx(b[f], rel=1e-6, abs=1e-9), (k, f)


# ---- V20 / V24: degradation and replay ------------------------------------------------------------------------------------
def test_v20_stale_price(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    snap = copy.deepcopy(fx["snap"])
    snap["asset_price"]["age_s"] = vm.PRICE_MAX_AGE_S + 1
    p = run(fx, monkeypatch, snap=_carry(fx, 0.5) | {"asset_price": snap["asset_price"]})
    assert p["decision"]["verdict"] == "REVIEW" and any("stale" in b for b in p["decision"]["blockers"])


def test_v20_indexer_disagrees(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    snap = _carry(fx, 0.5)
    snap["api"]["data"]["totalAssets"] = str(int(int(snap["total_assets_raw"]) * 1.1))
    p = run(fx, monkeypatch, snap=snap)
    assert p["decision"]["verdict"] == "REVIEW" and any("disagree" in b for b in p["decision"]["blockers"])


def test_v20_api_down_is_a_warning_not_a_mock(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    snap = _carry(fx, 0.5)
    snap["api"] = {"status": "unavailable", "error": "timeout"}
    p = run(fx, monkeypatch, snap=snap)
    assert any("Morpho API unavailable" in w for w in p["warnings"]) and p["mode"] != "mock"


def test_v20_low_coverage(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    snap = _carry(fx, 0.5)
    snap["reconciliation"]["coverage"] = 0.8
    p = run(fx, monkeypatch, snap=snap)
    assert p["decision"]["verdict"] == "REVIEW" and any("attributed" in b for b in p["decision"]["blockers"])


def test_v20_stale_simulation(fixtures, monkeypatch):
    fx = fixtures[CONFIDENTIAL]
    rd = copy.deepcopy(fx["rd"])
    rd["sim"]["fetched_at"] = fx["recorded_at"] - 3600
    p = run(fx, monkeypatch, snap=_carry(fx, 0.5), rd=rd)
    assert p["decision"]["verdict"] == "REVIEW" and any("exit_quote" in b for b in p["decision"]["blockers"])


def test_v24_offline_replay_deterministic_and_labelled(fixtures, monkeypatch):
    fx = fixtures[BELEM]
    a = run(fx, monkeypatch)
    b = run(fx, monkeypatch)
    strip = lambda p: {k: v for k, v in p.items() if k not in ("age_s",)}  # noqa: E731
    assert json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)
    h = fx["live_headline"]
    assert a["as_of_block"] == h["as_of_block"]
    assert a["decision"]["expected_loss_usd"] == pytest.approx(h["expected_loss_usd"], rel=1e-9)
    assert a["decision"]["exit_side_usd"] == pytest.approx(h["exit_side_usd"], rel=1e-9)
    assert a["decision"]["point_verdict"] == h["point_verdict"]
    off = run(fx, monkeypatch, offline=True)
    assert off["mode"] == "offline" and off["decision"]["verdict"] == "REVIEW"
    assert any("replay" in b for b in off["decision"]["blockers"])
    assert off["decision"]["freshness"]["label"] == "replay"


def test_v22_engine_default_unchanged():
    """Path-sum aggregation is opt-in (vault graphs only): a Phase 0.5 graph still uses the best path."""
    from defirisk.core.models import DepGraph, Edge, Node, Position
    from defirisk.core.propagation import best_paths
    g = DepGraph(Position("pos", "p", "ethereum", 100.0, 30, {}), [Node("pos", "protocol", "p", 0, 0, {}),
                 Node("a", "protocol", "a", 0, 0, {}), Node("b", "protocol", "b", 0, 0, {}), Node("x", "protocol", "x", 0.1, 1, {})],
                 [Edge("pos", "a", 0.6, ""), Edge("pos", "b", 0.6, ""), Edge("a", "x", 1, ""), Edge("b", "x", 1, "")])
    assert best_paths(g)["x"][0] == pytest.approx(0.6)
    g.position.meta["path_aggregation"] = "sum"
    assert best_paths(g)["x"][0] == pytest.approx(1.0)  # capped at 100%
