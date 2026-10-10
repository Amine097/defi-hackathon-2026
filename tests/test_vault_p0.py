"""Phase 2 P0 regression tests for the Morpho VAULT DEPOSITOR path (not the borrower Countermove engine).

P0-A: withdrawal routes. The ordinary redeem, the permissionless VaultV2 forceDeallocate multicall, the total amount a
      route really simulates, partial exits, unavailable liquidity, penalty + gas, and routes that are only theoretical.
      A route counts as executable ONLY if its eth_call simulation succeeded for the amount.
P0-B: one economic basis. A partial action compares loss avoided = EL x w with execution of THAT tranche + forgone
      carry x w; residual EL x (1 - w) stays exposed. No total term is mixed into a partial comparison.
Offline and deterministic: dated fixtures recorded from public sources (scripts/record_vault_fixture.py)."""
import copy
import json
from pathlib import Path

import pytest

from defirisk import abi, morpho
from defirisk import vault_model as vm
from defirisk import vault_reader as vr
from defirisk.data import http

ROOT = Path(__file__).resolve().parents[1]
FX_1M = ROOT / "data" / "fixtures" / "vault_0xd6d4b804014ef27836dbe9f8f6bf6c71251548ec_1m.json"
FX_100K = ROOT / "data" / "fixtures" / "vault_0xd6d4b804014ef27836dbe9f8f6bf6c71251548ec.json"


@pytest.fixture(scope="module")
def fx1m():
    return json.loads(FX_1M.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fx100k():
    return json.loads(FX_100K.read_text(encoding="utf-8"))


def run(fx, monkeypatch, req=None, snap=None, rd=None):
    monkeypatch.setattr(http, "now", lambda: fx["recorded_at"] + 5)
    monkeypatch.delenv("DEFIRISK_OFFLINE", raising=False)
    req = req or copy.deepcopy(fx["req"])
    snap = snap or copy.deepcopy(fx["snap"])
    rd = rd or copy.deepcopy(fx["rd"])
    prov = {**fx["prov"], "cached": 0, "live": max(fx["prov"].get("live", 0), 1), "mode": "live"}
    body = vm.assess(req, snap, rd, prov)
    return vm._js_safe(vm.payload(req, snap, rd, prov, body))


def _no_carry(snap):
    s = copy.deepcopy(snap)
    for m in s["markets"]:
        m["supply_apy"] = 0.0
    return s


def coherent(p):
    d = p["decision"]
    lo, hi = d["loss_band_usd"]
    elo, ehi = d["exit_band_usd"]
    assert d["exit_side_usd"] == pytest.approx(d["execution_cost_usd"] + d["carry_usd"])
    assert d["margin_usd"] == pytest.approx(d["expected_loss_usd"] - d["exit_side_usd"])
    assert d["point_verdict"] == ("EXIT" if d["margin_usd"] > 0 else "STAY")
    if d["verdict"] == "EXIT":
        assert lo > ehi and d["withdrawal_feasibility"] in vm.EXECUTABLE and not d["blockers"]
    if d["verdict"] == "STAY":
        assert hi < elo and not d["blockers"]
    b = d["comparison_basis"]
    assert d["expected_loss_usd"] == pytest.approx(d["position_expected_loss_usd"] * b["fraction"], rel=1e-12)
    assert d["residual_expected_loss_usd"] == pytest.approx(d["position_expected_loss_usd"] * (1 - b["fraction"]), rel=1e-9, abs=1e-9)
    assert d["explanation"].startswith(d["verdict"])


# ---- ABI encoding used by the route simulation (checked byte-for-byte against Foundry `cast calldata`) --------------
def test_abi_matches_cast_vectors():
    v1 = abi.encode_call("multicall(bytes[])", [["0x1234", "0xabcdef"]])
    assert v1 == ("0xac9650d8" + "0" * 62 + "20" + "0" * 63 + "2" + "0" * 62 + "40" + "0" * 62 + "80" + "0" * 63 + "2"
                  + "1234" + "0" * 60 + "0" * 63 + "3" + "abcdef" + "0" * 58)
    v2 = abi.encode_call("forceDeallocate(address,bytes,uint256,address)",
                         ["0xA671880d813D4cacaCA63984bc0Ab676c400A874", "0x" + "00" * 31 + "aa" + "00" * 31 + "bb", 1000,
                          "0x000000000000000000000000000000000000dEaD"])
    assert v2 == ("0xe4d38cd8000000000000000000000000a671880d813d4cacaca63984bc0ab676c400a874"
                  "0000000000000000000000000000000000000000000000000000000000000080"
                  "00000000000000000000000000000000000000000000000000000000000003e8"
                  "000000000000000000000000000000000000000000000000000000000000dead"
                  "0000000000000000000000000000000000000000000000000000000000000040"
                  "00000000000000000000000000000000000000000000000000000000000000aa"
                  "00000000000000000000000000000000000000000000000000000000000000bb")
    v3 = abi.encode_call("repay((address,address,address,address,uint256),uint256,uint256,address,bytes)",
                         [["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
                           "0x48F7E36EB6B826B2dF4B2E630B62Cd25e89E40e2", "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC",
                           860000000000000000], 100, 0, "0x000000000000000000000000000000000000dEaD", "0x"])
    assert v3 == ("0x20b76e81000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
                  "0000000000000000000000007f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
                  "00000000000000000000000048f7e36eb6b826b2df4b2e630b62cd25e89e40e2"
                  "000000000000000000000000870ac11d48b15db9a138cf899d20f13f79ba00bc"
                  "0000000000000000000000000000000000000000000000000bef55718ad60000"
                  "0000000000000000000000000000000000000000000000000000000000000064"
                  "0000000000000000000000000000000000000000000000000000000000000000"
                  "000000000000000000000000000000000000000000000000000000000000dead"
                  "0000000000000000000000000000000000000000000000000000000000000120"
                  "0000000000000000000000000000000000000000000000000000000000000000")
    assert abi.decode("int256,bool,string,uint8[]", "0x" + abi.encode_call("f(int256,bool,string,uint8[])", [-5, True, "hi", [1, 2, 3]])[10:]) \
        == [-5, True, "hi", [1, 2, 3]]


def test_market_params_data_is_morpho_market_id_preimage(fx1m):
    m = next(m for m in fx1m["snap"]["markets"] if m["collateral_symbol"] == "WBTC")
    data = bytes.fromhex(vr.market_params_data(m)[2:])
    assert len(data) == 160
    from defirisk.keccak import keccak256
    assert "0x" + keccak256(data).hex() == m["id"]  # abi.encode(MarketParams) hashes to the on-chain market id


# ---- P0-A: routes ------------------------------------------------------------------------------------------------------
def test_p0a_capacity_classifies_routes(fx1m):
    cap = vm.capacity(fx1m["snap"])
    assert cap["force_rows"] and all(r["route"] == "simulable" for r in cap["force_rows"])
    assert cap["force_simulable_raw"] == cap["force_raw"] > 0
    keys = [(r["penalty_raw"], -r["available_raw"]) for r in cap["force_rows"]]
    assert keys == sorted(keys)  # cheapest penalty first, then deepest liquidity
    snap = copy.deepcopy(fx1m["snap"])
    snap["adapters"][0]["type"] = "SomeFutureAdapter"
    cap2 = vm.capacity(snap)
    assert all(r["route"] == "theoretical" for r in cap2["force_rows"]) and cap2["force_simulable_raw"] == 0


def test_p0a_force_plan_covers_shortfall(fx1m):
    snap, A = fx1m["snap"], fx1m["rd"]["assets_raw"]
    cap = vm.capacity(snap)
    plan = vm.force_plan(snap, cap, A)
    assert plan["covers_full"] and plan["need_raw"] == A - cap["ordinary_raw"]
    assert plan["deallocated_raw"] >= plan["need_raw"]
    avail = {r["market"]: r["available_raw"] for r in cap["force_rows"]}
    for s in plan["steps"]:
        assert 0 < s["assets_raw"] <= avail[s["market"]] * 999 // 1000  # never the last 0.1% of a market's liquidity
        assert s["penalty_assets_raw"] == -(-s["assets_raw"] * s["penalty_wad"] // morpho.WAD)
    assert plan == vm.force_plan(snap, cap, A)  # deterministic


def test_p0a_belem_1m_full_via_force_deallocate(fx1m, monkeypatch):
    """Audit F1: the product said 'partial: $405k now / $595k blocked'; the multicall simulation proves $1M exits."""
    p = run(fx1m, monkeypatch)
    e, d, V = p["exit"], p["decision"], p["input"]["value_usd"]
    assert e["withdrawal_feasibility"] == "full_via_force_deallocate" and e["executable_route"] == "force_deallocate"
    assert e["immediately_withdrawable_usd"] == pytest.approx(V, rel=1e-9) and e["blocked_or_deferred_usd"] == 0
    assert e["routes"]["ordinary"]["status"] == "simulated_partial"
    assert e["routes"]["ordinary"]["capacity_usd"] < 0.5 * V  # the old answer: ordinary capacity only
    assert e["routes"]["force_deallocate"]["status"] == "simulated" and e["routes"]["unconfirmed"] == []
    assert e["simulation_force_deallocate"]["status"] == "simulated"
    rg = fx1m["rd"]["route_gas"]["force_deallocate"]
    assert e["gas_usd"] == rg["gas_usd"] and e["gas_units"] == rg["gas_units"]
    assert e["execution_cost_usd"] == pytest.approx(e["gas_usd"] + e["withdrawal_friction_usd"] + e["exit_fee_usd"])
    assert e["force_deallocate_penalty_usd"] == 0 and e["force_deallocate"]["used_in_verdict"]
    assert d["comparison_basis"]["kind"] == "full_position" and d["comparison_basis"]["fraction"] == 1.0
    assert any("only through forceDeallocate" in r for r in d["reasons"])
    h = fx1m["live_headline"]
    assert (d["withdrawal_feasibility"], d["point_verdict"]) == (h["withdrawal_feasibility"], h["point_verdict"])
    assert d["expected_loss_usd"] == pytest.approx(h["expected_loss_usd"], rel=1e-9)
    assert d["exit_side_usd"] == pytest.approx(h["exit_side_usd"], rel=1e-9)
    coherent(p)


def test_p0a_firm_exit_allowed_only_through_a_simulated_route(fx1m, monkeypatch):
    p = run(fx1m, monkeypatch, snap=_no_carry(fx1m["snap"]))
    assert p["decision"]["verdict"] == "EXIT" and p["decision"]["withdrawal_feasibility"] == "full_via_force_deallocate"
    coherent(p)
    rd = copy.deepcopy(fx1m["rd"])
    rd["sim_force"]["status"] = "reverted"
    q = run(fx1m, monkeypatch, snap=_no_carry(fx1m["snap"]), rd=rd)
    assert q["decision"]["verdict"] == "REVIEW" and q["decision"]["point_verdict"] == "EXIT"
    assert q["exit"]["withdrawal_feasibility"] == "partial"
    coherent(q)


def test_p0a_reverted_force_route_is_never_executable(fx1m, monkeypatch):
    rd = copy.deepcopy(fx1m["rd"])
    rd["sim_force"] = {**rd["sim_force"], "status": "reverted", "reason": "execution reverted: insufficient liquidity"}
    p = run(fx1m, monkeypatch, rd=rd)
    e = p["exit"]
    assert e["withdrawal_feasibility"] == "partial" and e["executable_route"] == "ordinary_partial"
    assert e["routes"]["force_deallocate"]["status"] == "reverted"
    assert [u["route"] for u in e["routes"]["unconfirmed"]] == ["forceDeallocate"]
    assert e["immediately_withdrawable_usd"] == pytest.approx(e["capacity"]["ordinary_usd"], rel=1e-9)
    assert e["immediately_withdrawable_usd"] + e["blocked_or_deferred_usd"] == pytest.approx(p["input"]["value_usd"], rel=1e-6)
    assert not e["force_deallocate"]["used_in_verdict"]
    coherent(p)


def test_p0a_unsimulated_force_route_is_theoretical(fx1m, monkeypatch):
    rd = copy.deepcopy(fx1m["rd"])
    for k in ("sim_force", "force_plan"):
        rd.pop(k)
    p = run(fx1m, monkeypatch, rd=rd)
    e = p["exit"]
    assert e["withdrawal_feasibility"] == "partial"
    assert e["force_deallocate"]["status"] == "theoretical_not_simulated"
    assert e["routes"]["unconfirmed"][0]["status"] == "theoretical_not_simulated"
    assert e["capacity"]["with_force_deallocate_usd"] > e["capacity"]["ordinary_usd"]  # shown, never counted
    assert e["immediately_withdrawable_usd"] == pytest.approx(e["capacity"]["ordinary_usd"], rel=1e-9)


def test_p0a_penalty_is_an_execution_cost(fx1m, monkeypatch):
    rd = copy.deepcopy(fx1m["rd"])
    A = rd["assets_raw"]
    pen = A // 200  # synthetic 0.5% of the position paid as forceDeallocate penalty
    rd["sim_force"].update(assets_out_raw=A - pen, penalty_assets_raw=pen)
    p = run(fx1m, monkeypatch, rd=rd)
    e = p["exit"]
    px = p["vault"]["asset"]["price_usd"]
    pen_usd = pen / 1e18 * px
    assert e["force_deallocate_penalty_usd"] == pytest.approx(pen_usd, rel=1e-9)
    assert e["withdrawal_friction_usd"] == pytest.approx(pen_usd, rel=1e-6)
    assert e["execution_cost_usd"] == pytest.approx(e["gas_usd"] + pen_usd, rel=1e-6)
    coherent(p)


def test_p0a_partial_force_route(fx1m, monkeypatch):
    rd = copy.deepcopy(fx1m["rd"])
    sf = rd.pop("sim_force")
    part = rd["assets_raw"] * 3 // 4
    pen = part // 1000
    rd["sim_force_partial"] = {**sf, "assets_requested_raw": part, "assets_out_raw": part, "penalty_assets_raw": pen}
    rd["route_gas"]["force_deallocate_partial"] = rd["route_gas"].pop("force_deallocate")
    p = run(fx1m, monkeypatch, rd=rd)
    e, d = p["exit"], p["decision"]
    assert e["withdrawal_feasibility"] == "partial" and e["executable_route"] == "force_deallocate_partial"
    assert e["routes"]["force_deallocate"]["status"] == "simulated_partial"
    assert d["comparison_basis"]["fraction"] == pytest.approx(0.75, rel=1e-9)
    px = p["vault"]["asset"]["price_usd"]
    assert e["withdrawal_friction_usd"] == pytest.approx(pen / 1e18 * px, rel=1e-6)  # penalty paid from remaining shares
    coherent(p)


def test_p0a_scenarios_report_force_capacity(fx1m, monkeypatch):
    p = run(fx1m, monkeypatch)
    V = p["input"]["value_usd"]
    crash = next(s for s in p["scenarios"] if s["name"].startswith("Collateral crash"))
    assert crash["withdrawable_with_force_deallocate_usd"] == pytest.approx(V, rel=1e-9)
    assert crash["force_deallocate_route"].startswith("confirmed")
    liq = next(s for s in p["scenarios"] if s["name"] == "Liquidity crisis")
    assert liq["withdrawable_with_force_deallocate_usd"] < V and not liq["force_deallocate_route"].startswith("confirmed")


# ---- P0-B: one economic basis -----------------------------------------------------------------------------------------
def _partial_ordinary(fx1m):
    rd = copy.deepcopy(fx1m["rd"])
    for k in ("sim_force", "force_plan"):
        rd.pop(k)
    return rd


def test_p0b_partial_terms_share_one_basis(fx1m, monkeypatch):
    """Audit F2 acceptance: w ~ 0.4; exit side = exec_w + carry x w and loss compared = EL x w; no total term."""
    rd = _partial_ordinary(fx1m)
    p = run(fx1m, monkeypatch, rd=rd)
    e, d, r = p["exit"], p["decision"], p["risk"]
    sp = rd["sim_partial"]
    w = sp["assets_requested_raw"] / rd["assets_raw"]
    assert 0.35 < w < 0.45
    b = d["comparison_basis"]
    assert b["kind"] == "executable_tranche" and b["fraction"] == pytest.approx(w, rel=1e-12)
    assert d["expected_loss_usd"] == pytest.approx(r["expected_loss_usd"] * w, rel=1e-12)  # loss avoided EL x w
    assert d["loss_band_usd"][0] == pytest.approx(r["band_usd"][0] * w, rel=1e-12)
    assert d["loss_band_usd"][1] == pytest.approx(r["band_usd"][1] * w, rel=1e-12)
    assert d["carry_usd"] == pytest.approx(e["carry"]["usd"] * w, rel=1e-12)  # carry forgone x w, not the total
    assert e["carry"]["usd"] == pytest.approx(p["input"]["value_usd"] * e["carry"]["net_apy_onchain"] * 30 / 365)
    assert d["residual_expected_loss_usd"] == pytest.approx(r["expected_loss_usd"] * (1 - w), rel=1e-9)
    px = p["vault"]["asset"]["price_usd"]
    friction = (sp["assets_requested_raw"] - sp["assets_out_raw"]) / 1e18 * px
    assert d["execution_cost_usd"] == pytest.approx(rd["route_gas"]["ordinary_partial"]["gas_usd"] + max(friction, 0), rel=1e-9)
    assert d["exit_side_usd"] == pytest.approx(d["execution_cost_usd"] + d["carry_usd"], rel=1e-12)
    assert p["sensitivity"]["breakeven_risk_multiplier"] == pytest.approx(d["exit_side_usd"] / d["expected_loss_usd"], rel=1e-9)
    assert "executable tranche" in d["explanation"]
    coherent(p)


def test_p0b_high_friction_partial_no_longer_biased_to_exit(fx1m, monkeypatch):
    """Old rule: EL (total) vs exec_w + carry (total) -> EXIT whenever EL > exec_w. Consistent rule: EL x w vs exec_w.
    With w ~ 0.4 and exec_w = 0.7 x EL, the old rule said EXIT; the tranche is actually not worth exiting."""
    rd = _partial_ordinary(fx1m)
    snap = _no_carry(fx1m["snap"])
    base = run(fx1m, monkeypatch, snap=snap, rd=rd)
    EL = base["risk"]["expected_loss_usd"]
    px = base["vault"]["asset"]["price_usd"]
    target_exec = 0.7 * EL
    gas = rd["route_gas"]["ordinary_partial"]["gas_usd"]
    fr_raw = int((target_exec - gas) / px * 1e18)
    rd["sim_partial"]["assets_out_raw"] = rd["sim_partial"]["assets_requested_raw"] - fr_raw
    p = run(fx1m, monkeypatch, snap=snap, rd=rd)
    d = p["decision"]
    assert d["execution_cost_usd"] == pytest.approx(target_exec, rel=1e-6)
    assert EL > d["execution_cost_usd"] + d["carry_usd"]  # the old mixed comparison -> EXIT
    assert d["point_verdict"] == "STAY" and d["margin_usd"] < 0  # consistent basis: EL x w < exec_w
    coherent(p)


def test_p0b_full_position_basis_unchanged(fx100k, monkeypatch):
    """Phase 1 behaviour is preserved when the full amount is executable (w = 1)."""
    p = run(fx100k, monkeypatch)
    d, h = p["decision"], fx100k["live_headline"]
    assert d["comparison_basis"] == {**d["comparison_basis"], "kind": "full_position", "fraction": 1.0}
    assert d["expected_loss_usd"] == pytest.approx(h["expected_loss_usd"], rel=1e-9)
    assert d["exit_side_usd"] == pytest.approx(h["exit_side_usd"], rel=1e-9)
    assert d["carry_usd"] == pytest.approx(p["exit"]["carry"]["usd"], rel=1e-12)
    assert d["residual_expected_loss_usd"] == 0
    assert p["exit"]["routes"]["force_deallocate"]["status"] == "not_needed"
    coherent(p)


@pytest.mark.parametrize("w_target", [0.0, 0.4, 1.0])
def test_p0b_terms_scale_with_w(fx1m, monkeypatch, w_target):
    """w in {0, 0.4, 1}: compared loss and carry are exactly EL x w and carry x w (w = 1 is the full exit)."""
    rd = _partial_ordinary(fx1m)
    A = rd["assets_raw"]
    if w_target == 1.0:
        rd["sim"] = {**rd["sim"], "status": "simulated", "assets_out_raw": A, "gas_estimate": 389054}
        rd["route_gas"]["ordinary"] = rd["route_gas"]["ordinary_partial"]
    else:
        part = max(int(A * w_target), 1)
        rd["sim_partial"].update(assets_requested_raw=part, assets_out_raw=part)
    p = run(fx1m, monkeypatch, rd=rd)
    d, r = p["decision"], p["risk"]
    w = d["comparison_basis"]["fraction"]
    assert w == pytest.approx(w_target, abs=1e-12)
    assert d["expected_loss_usd"] == pytest.approx(r["expected_loss_usd"] * w, abs=1e-9)
    assert d["carry_usd"] == pytest.approx(p["exit"]["carry"]["usd"] * w, abs=1e-9)
    coherent(p)

UI_FIX = ROOT / "tests" / "js" / "fixtures"


def test_p0_ui_fixtures_in_sync(fx1m, monkeypatch):
    """Node UI tests read real backend payloads for the forceDeallocate route and a partial tranche.
    Regenerate with FAULTLINE_EXPORT_UI_FIXTURES=1; otherwise the committed files must match the backend."""
    import os
    out = {"force": run(fx1m, monkeypatch), "partial": run(fx1m, monkeypatch, rd=_partial_ordinary(fx1m))}
    if os.getenv("FAULTLINE_EXPORT_UI_FIXTURES") == "1":
        for k, p in out.items():
            (UI_FIX / f"vault_{k}.json").write_text(json.dumps(p, allow_nan=False, indent=1), encoding="utf-8")
    for k, p in out.items():
        saved = json.loads((UI_FIX / f"vault_{k}.json").read_text(encoding="utf-8"))
        a, b = saved["decision"], p["decision"]
        assert a["withdrawal_feasibility"] == b["withdrawal_feasibility"] and a["comparison_basis"]["kind"] == b["comparison_basis"]["kind"]
        for f in ("expected_loss_usd", "exit_side_usd", "margin_usd", "carry_usd", "execution_cost_usd"):
            assert a[f] == pytest.approx(b[f], rel=1e-6, abs=1e-9), (k, f)
