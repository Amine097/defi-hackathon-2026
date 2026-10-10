"""Vault depositor risk model (P1-03 / P1-04 / P1-05): graph specific to the requested vault, depositor P&L, feasible
withdrawal, exit cost and the STAY / EXIT / REVIEW signal. Reuses the Phase 0.5 engine (propagation, uncertainty
bands, robust_signal, freshness, priors) - no second engine.

P&L ownership (depositor of vault shares, hypothetical notional `value_usd`):
  * a borrower liquidation is NOT a depositor loss: suppliers lose only the BAD DEBT left after liquidations
    (morpho.liquidation_outcome on every on-chain borrower position, at a jump drop of the collateral);
  * an oracle that over-prices collateral lets borrowers drain the market's free liquidity against collateral worth
    less than the debt: loss = liquidity x max(0, 1 - (1 - d) / LLTV); under-pricing only hurts borrowers (excluded);
  * Morpho Blue / vault contracts / chain: protocol priors (Phase 0.5) on the share of assets they hold;
  * the deposit asset (and EUR/USD for a EUR asset) is held whether the manager stays or redeems: decision-neutral,
    shown as context and as a what-if scenario, transmission 0 in the STAY/EXIT comparison.
Losses are fractions of the vault's assets (per share), so 0 <= loss <= value_usd (no extra liability).
"""
from __future__ import annotations

import math
import os
import re
from copy import deepcopy

from . import freshness, morpho, uncertainty
from .core.models import DepGraph, Edge, Node, Position
from .core.propagation import best_paths, simulate, to_nx
from .data import http, priors, sources
from .vault_input import VaultError
from . import vault_reader as vr

COLLATERAL_SEVERITY = priors.LGF["underlying"]  # 50% jump drop of a collateral when it "fails" (assumption)
ORACLE_SEVERITY = priors.LGF["oracle"]  # 40% over-pricing when an oracle fails (assumption)
MARKET_SEVERITY = priors.LGF["lending"]
SCENARIO_CRASH = 0.4  # scenario hypotheses (labelled conditional_on_shock)
SCENARIO_DEPEG = 0.10
COVERAGE_MIN = 0.95
PRICE_MAX_AGE_S = 3600  # DefiLlama coins refresh ~ every few minutes; > 1 h = stale for a USD conversion
FX_MAX_AGE_S = 26 * 3600  # Chainlink EUR/USD heartbeat 24 h (+ margin)
PRICE_XCHECK_TOL = 0.01
TOTAL_XCHECK_TOL = 0.02
CAPACITY_XCHECK_TOL = 0.01
APY_XCHECK_TOL = 0.005  # 50 bp absolute: API APY is a short average, on-chain is instantaneous
HYPOTHETICAL = ("value_usd is a HYPOTHETICAL exposure converted to vault shares at the pinned block's share price; it "
                "is not proof that anyone holds these shares")


# ---- network reads that depend on the request (exit simulation, gas, conversion, priors) ------------------------
def reads(req: dict, snap: dict) -> dict:
    from .core.decision import _gas_usd
    px = snap["asset_price"].get("price_usd")
    out = {"priors": priors_ctx(snap, req["horizon_days"])}
    if not px:
        out["sim"] = {"status": "unavailable", "reason": "deposit asset USD price unavailable"}
        return out
    ad, dec = snap["asset_decimals"], snap["decimals"]
    assets_raw = int(req["value_usd"] / px * 10 ** ad)
    cap = capacity(snap)
    out["assets_raw"] = assets_raw
    shares = assets_raw * 10 ** dec // snap["share_price_raw"] if snap["share_price_raw"] else 0
    sim = vr.simulate_redeem(snap["address"], snap["version"], shares, snap["as_of_block"])
    out["sim"] = sim
    if sim["status"] == "reverted" and cap["ordinary_raw"] and cap["ordinary_raw"] < assets_raw:
        part = cap["ordinary_raw"] * 999 // 1000
        psh = part * 10 ** dec // snap["share_price_raw"]
        out["sim_partial"] = dict(vr.simulate_redeem(snap["address"], snap["version"], psh, snap["as_of_block"]),
                                  assets_requested_raw=part)
    gas_units = (sim.get("gas_estimate") or (out.get("sim_partial") or {}).get("gas_estimate"))
    if snap["version"] == "v1":
        out["max_withdraw_v1"] = vr.max_withdraw_v1(snap["address"], snap["total_supply_raw"], snap["as_of_block"])
    if gas_units:
        out["gas_usd"], out["gas_why"] = _gas_usd(gas_units)
        out["gas_units"] = gas_units
    imm = min(assets_raw, cap["ordinary_raw"])
    if snap["asset_symbol"] and snap["asset_symbol"].upper() != "USDC" and imm > 0:
        out["conversion"] = vr.conversion_quote(snap["asset_address"], imm, px, ad)
    else:
        out["conversion"] = {"status": "not_needed", "reason": "the vault asset is USDC (USD conversion = holding it)"}
    return out


def _issuer(symbol: str, protocols: list[dict]) -> dict | None:
    """DefiLlama protocol for a collateral token ONLY when its symbol equals the protocol's name or slug (e.g. WBTC).
    A substring match (WETH -> 'SuperSweth Vault') is not a verified issuer link: the generic prior is used instead."""
    key = re.sub(r"[^a-z0-9]", "", (symbol or "").lower())
    if not key:
        return None
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
    hits = [p for p in protocols if key in (norm(p.get("name")), norm(p.get("slug")))]
    return max(hits, key=lambda p: p.get("tvl") or 0) if hits else None


def priors_ctx(snap: dict, H: int) -> dict:
    protocols = sources.llama_protocols()
    rates = priors.base_rates(protocols=protocols)
    proto = {"morpho": _strip(sources.llama_find_protocol("morpho", protocols))}
    proto.update({m["collateral_symbol"]: _strip(_issuer(m["collateral_symbol"], protocols))
                  for m in snap["markets"] if m["collateral_symbol"]})
    stable, hist = {}, None
    for sym in {snap["asset_symbol"]} | {m["collateral_symbol"] for m in snap["markets"] if m["collateral_symbol"]}:
        if not sym:
            continue
        try:
            gid = sources.llama_stablecoin_gecko_id(sym)
            if not gid:
                continue  # not a DefiLlama-tracked USD stablecoin: priced as an issued token (issuer prior)
            if hist is None:
                hist = sources.llama_stablecoin_price_history()
            stable[sym] = priors.stablecoin_depeg(gid, hist)
        except Exception:
            continue
    return {"rates": rates, "proto": proto, "stable": stable}


def _strip(p: dict | None) -> dict | None:
    return {k: p.get(k) for k in ("name", "slug", "tvl", "audits", "listedAt", "url", "category")} if p else None


# ---- liquidity -------------------------------------------------------------------------------------------------
def capacity(snap: dict, liquidity_factor: float = 1.0) -> dict:
    """Ordinary (standard) withdrawal capacity, in raw asset units, from on-chain state at the pinned block.
    V2: idle + liquidity adapter's position in the liquidityData market, capped by that market's free liquidity
        (maxWithdraw/maxRedeem return 0 by design and are NOT used). Gates closed -> 0.
    V1: idle + sum over the withdrawQueue of min(vault supply, market liquidity)."""
    idle = snap["idle_raw"]
    rows = []
    if snap["version"] == "v2":
        if not snap["gates"].get("withdraw_open", True):
            return {"ordinary_raw": 0, "idle_raw": idle, "rows": [], "rule": "withdrawal gate set: ordinary exit blocked",
                    "force_raw": 0, "force_rows": []}
        liq_m = snap.get("liquidity_market")
        ordinary = idle
        force_rows = []
        for m in snap["markets"]:
            avail = min(m["vault_supply_raw"], int(m["liquidity_raw"] * liquidity_factor))
            if m["id"] == liq_m and m.get("holder", "").lower() == (snap.get("liquidity_adapter") or "").lower():
                ordinary += avail
                rows.append({"market": m["id"], "collateral": m["collateral_symbol"], "available_raw": avail, "path": "liquidity adapter"})
            elif avail > 0:
                ad = next((a for a in snap["adapters"] if a["address"] == m.get("holder")), {})
                force_rows.append({"market": m["id"], "collateral": m["collateral_symbol"], "available_raw": avail,
                                   "penalty": ad.get("force_deallocate_penalty")})
        return {"ordinary_raw": ordinary, "idle_raw": idle, "rows": rows, "force_raw": sum(r["available_raw"] for r in force_rows),
                "force_rows": force_rows,
                "rule": "idle + min(liquidity-adapter supply, free liquidity) of the liquidityData market (VaultV2 exit path)"}
    ordinary = idle
    for m in sorted(snap["markets"], key=lambda m: m.get("withdraw_queue_index", 0)):
        avail = min(m["vault_supply_raw"], int(m["liquidity_raw"] * liquidity_factor))
        ordinary += avail
        rows.append({"market": m["id"], "collateral": m["collateral_symbol"], "available_raw": avail,
                     "path": f"withdrawQueue[{m.get('withdraw_queue_index')}]"})
    return {"ordinary_raw": ordinary, "idle_raw": idle, "rows": rows, "force_raw": 0, "force_rows": [],
            "rule": "idle + sum over withdrawQueue of min(vault supply, free liquidity) (MetaMorpho V1)"}


# ---- market loss mechanics (fractions of the market's total supply) ---------------------------------------------
def bad_debt_fraction(m: dict, drop: float) -> dict:
    """Bad debt left to suppliers after a jump drop `drop` of the collateral (oracle tracks the drop), as a fraction
    of the market's total supply. Borrowers not covered by the indexed list are assumed to sit AT the LLTV (worst)."""
    ts = m["total_supply_raw"]
    if not ts or not m["total_borrow_raw"] or not m["collateral_token"]:
        return {"fraction": 0.0, "bad_debt_raw": 0, "liquidated": 0, "borrowers": 0, "assumed_at_lltv_raw": 0}
    lif = m["lif"]
    bd, liq, n = 0.0, 0, 0
    b = m.get("borrowers") or {}
    covered = 0
    for it in b.get("items", []):
        if it["collateral_value_raw"] is None:
            continue
        st = {"collateral_value_usd_oracle": it["collateral_value_raw"], "debt_value_usd": it["debt_raw"],
              "lltv": m["lltv"], "liquidation_incentive_factor": lif}
        o = morpho.liquidation_outcome(st, drop)
        bd += o["lender_bad_debt_usd"]
        liq += o["liquidated"]
        n += 1
        covered += it["debt_raw"]
    rest = max(m["total_borrow_raw"] - covered, 0)
    if rest:
        st = {"collateral_value_usd_oracle": rest / m["lltv"], "debt_value_usd": rest, "lltv": m["lltv"],
              "liquidation_incentive_factor": lif}
        bd += morpho.liquidation_outcome(st, drop)["lender_bad_debt_usd"]
    return {"fraction": min(bd / ts, 1.0), "bad_debt_raw": int(bd), "liquidated": liq, "borrowers": n,
            "assumed_at_lltv_raw": rest}


def oracle_drain_fraction(m: dict, overpricing: float, liquidity_factor: float = 1.0) -> float:
    """Oracle reports collateral worth 1/(1-d) x its value: borrowers can take the free liquidity L against collateral
    truly worth L (1-d) / LLTV; suppliers lose L x max(0, 1 - (1-d)/LLTV)."""
    ts = m["total_supply_raw"]
    if not ts or not m["collateral_token"]:
        return 0.0
    L = m["liquidity_raw"] * liquidity_factor
    return min(L * max(0.0, 1 - (1 - overpricing) / m["lltv"]) / ts, 1.0)


# ---- graph -----------------------------------------------------------------------------------------------------
def _node(nid, layer, label, p, why, role, lgf, lgf_why, **meta):
    return Node(nid, layer, label, round(p, 8), round(lgf, 4),
                {"role": role, "source": why, "lgf_source": lgf_why, "chain": "ethereum", **meta})


def build_graph(req: dict, snap: dict, pri: dict, sev: dict | None = None, liquidity_factor: float = 1.0) -> tuple[DepGraph, dict]:
    """Depositor dependency graph of THIS vault. sev: node id -> severity override (collateral drop / oracle
    over-pricing / market loss): the mechanistic transmissions are recomputed at that severity (bad debt is convex)."""
    sev = sev or {}
    H, V = req["horizon_days"], req["value_usd"]
    rates = pri["rates"]
    TA = snap["total_assets_raw"]
    blk = snap["as_of_block"]
    vid, pos = f"vault:{snap['address']}", "pos"
    meta = {"real": True, "block_number": blk, "block_timestamp": snap["block_timestamp"], "observed_at": snap["observed_at"],
            "path_aggregation": "sum", "kind": "vault_depositor"}
    g = DepGraph(Position(pos, f"{snap['symbol']} depositor (hypothetical ${V:,.0f})", "ethereum", V, H, meta), [], [])
    emeta: dict = {}

    def E(s, d, t, reason, relation, source, conf, ttype):
        g.edges.append(Edge(s, d, max(min(t, 1.0), 0.0), reason))
        emeta[(s, d)] = {"relation_type": relation, "source": source, "as_of_block": blk, "confidence": conf,
                         "transmission_type": ttype}

    def add(n):
        if not any(x.id == n.id for x in g.nodes):
            g.nodes.append(n)
        return n.id

    morpho_p = pri["proto"].get("morpho")
    g.nodes.append(Node(pos, "protocol", "Depositor position", 0.0, 0.0, {"role": "position"}))
    p, why = priors.p_protocol(rates, morpho_p, H, share=0.5)
    add(_node(vid, "protocol", f"{snap['name']} (Morpho Vault {snap['version'].upper()})", p,
              why + "; x0.5 = vault contracts + adapters + curator share of Morpho risk", "lending", MARKET_SEVERITY,
              f"structural assumption: loss-given-failure {MARKET_SEVERITY:.0%} for a vault contract / curator failure (priors.LGF)",
              address=snap["address"], version=snap["version"], factory=snap["factory"]))
    E(pos, vid, 1.0, "measured: depositor holds vault shares (share price convertToAssets at the pinned block)",
      "holds_shares", "VaultV2/MetaMorpho convertToAssets", "high", "mechanistic")
    p, why = priors.p_chain(H)
    add(_node("chain:1", "chain", "Ethereum", p, why, "chain", priors.LGF["chain"],
              f"structural assumption: loss-given-failure {priors.LGF['chain']:.0%} (priors.LGF)"))
    E(pos, "chain:1", 1.0, "vault, markets and redemption settle on Ethereum", "settles_on", "chain_id 1", "high", "assumption")
    p, why = priors.p_protocol(rates, morpho_p, H, share=0.5)
    add(_node("morpho_blue", "protocol", "Morpho Blue (singleton)", p, why + "; x0.5 = singleton-contract share",
              "morpho_blue", priors.LGF["morpho_blue"],
              f"structural assumption: loss-given-failure {priors.LGF['morpho_blue']:.0%} (priors.LGF)", address=morpho.MORPHO_BLUE))

    # deposit asset + FX: held whether staying or redeeming -> context (transmission 0 in the decision)
    asym = snap["asset_symbol"]
    aid = f"asset:{snap['asset_address']}"
    dep = pri["stable"].get(asym)
    p, lgf, why = priors.p_stablecoin(dep, H, asym)
    add(_node(aid, "yield_source", f"{asym} (deposit asset)", p, why, "stablecoin", lgf or priors.LGF["stablecoin"],
              f"measured: mean depth of past {asym} depegs" if lgf else "structural assumption: 30% (priors.LGF stablecoin)",
              address=snap["asset_address"], decision_neutral=True))
    E(pos, aid, 0.0, f"decision-neutral: redeeming returns {asym}, so its depeg hits STAY and EXIT alike "
      "(shown as a what-if scenario, not in the STAY/EXIT margin)", "denominated_in", "VaultV2.asset()", "high", "mechanistic")
    if vr.currency_of(asym) == "EUR":
        add(Node("fx:EURUSD", "oracle", "EUR/USD exchange rate", 0.0, 0.0,
                 {"role": "fx", "source": "look-through only: FX is a valuation convention, not a failure",
                  "lgf_source": "", "decision_neutral": True, "feed": vr.EUR_USD_FEED}))
        E(aid, "fx:EURUSD", 0.0, "EUR-denominated: USD value moves with EUR/USD (decision-neutral unless converting to USD)",
          "valued_in", "Chainlink EUR/USD", "high", "mechanistic")

    attributed = 0
    for ad in snap["adapters"]:
        aid_ = f"adapter:{ad['address']}" if snap["version"] == "v2" else None
        mk = [m for m in snap["markets"] if snap["version"] == "v1" or m.get("holder") == ad["address"]]
        in_mk = sum(m["vault_supply_raw"] for m in mk)
        if not ad.get("supported"):
            continue
        attributed += in_mk
        parent = vid
        if aid_:
            add(Node(aid_, "lending", f"Adapter {ad['type']}", 0.0, 0.0,
                     {"role": "adapter", "source": "look-through only: adapter risk carried by the vault and its markets",
                      "lgf_source": "", "address": ad["address"], "type": ad["type"],
                      "force_deallocate_penalty": ad.get("force_deallocate_penalty")}))
            E(vid, aid_, in_mk / TA if TA else 0.0, f"measured: adapter holds {in_mk / TA:.2%} of totalAssets in Morpho markets",
              "allocates_to", "adapter marketIds + Morpho position()", "high", "mechanistic")
            parent = aid_
        base = in_mk if aid_ else TA
        for m in mk:
            mid = f"market:{m['id']}"
            share = m["vault_supply_raw"] / base if base else 0.0
            add(Node(mid, "lending", f"Morpho market {m['collateral_symbol'] or 'idle'}/{asym} (LLTV {m['lltv']:.1%})", 0.0,
                     sev.get(mid, MARKET_SEVERITY),
                     {"role": "market", "source": "look-through only: market risk carried by its collateral, oracle and "
                      "Morpho Blue nodes (shock it for an isolated market failure)",
                      "lgf_source": "structural assumption (shock only)", "market_id": m["id"], "lltv": m["lltv"]}))
            E(parent, mid, share, f"measured: {share:.2%} of the {'adapter' if aid_ else 'vault'} supplied to this market",
              "supplies", "Morpho Blue position(id, holder)", "high", "mechanistic")
            E(mid, "morpho_blue", 1.0, "market lives in the Morpho Blue singleton", "hosted_by", "Morpho Blue", "high", "mechanistic")
            if m["collateral_token"]:
                cid = f"collateral:{m['collateral_token']}"
                csym = m["collateral_symbol"] or m["collateral_token"][:10]
                if csym in pri["stable"]:  # DefiLlama-tracked USD stablecoin: observed depeg history
                    cp, clgf, cwhy = priors.p_stablecoin(pri["stable"][csym], H, csym)
                    clgf = clgf or COLLATERAL_SEVERITY
                    lwhy = (f"measured: mean depth of past {csym} depegs" if pri["stable"][csym] and pri["stable"][csym]["episodes"]
                            else f"assumption: {clgf:.0%} drop when the collateral fails")
                    ckind = "stablecoin"
                else:
                    cp, cwhy = priors.p_protocol(rates, pri["proto"].get(csym), H, share=0.5)
                    cwhy += "; x0.5 = token-level share of issuer / wrapper impairment"
                    clgf, lwhy = COLLATERAL_SEVERITY, f"assumption: collateral loses {COLLATERAL_SEVERITY:.0%} in a jump (no time to liquidate)"
                    ckind = "issued_token"
                if cid not in [n.id for n in g.nodes]:
                    add(_node(cid, "yield_source", f"{csym} (collateral)", cp, cwhy, "collateral", sev.get(cid, clgf), lwhy,
                              address=m["collateral_token"], collateral_kind=ckind))
                s = next(n for n in g.nodes if n.id == cid).loss_given_failure
                bd = bad_debt_fraction(m, s)
                E(mid, cid, bd["fraction"] / s if s else 0.0,
                  f"model: a {s:.0%} jump drop leaves bad debt = {bd['fraction']:.2%} of market supply after liquidating "
                  f"{bd['liquidated']}/{bd['borrowers']} on-chain borrower positions (LIF {m['lif']:.3f}); transmission = bad "
                  "debt / (supply x drop). Liquidations alone cost suppliers nothing.",
                  "collateralized_by", "Morpho Blue idToMarketParams + borrower positions (API list, on-chain totals/oracle)",
                  "medium" if (m.get("borrowers") or {}).get("status") == "ok" else "low", "mechanistic")
                if int(m["oracle"], 16):
                    oid = f"oracle:{m['oracle']}"
                    if oid not in [n.id for n in g.nodes]:
                        op, owhy = priors.p_oracle(rates, H, 1.0, ["vault oracle: feed quality not individually assessed (assumption x1.0)"])
                        add(_node(oid, "oracle", f"Oracle {m['oracle'][:10]}...", op, owhy, "oracle", sev.get(oid, ORACLE_SEVERITY),
                                  f"assumption: oracle over-prices collateral by {ORACLE_SEVERITY:.0%} when it fails", address=m["oracle"]))
                    d = next(n for n in g.nodes if n.id == oid).loss_given_failure
                    fr = oracle_drain_fraction(m, d, liquidity_factor)
                    E(mid, oid, fr / d if d else 0.0,
                      f"model: over-pricing by {d:.0%} lets borrowers drain free liquidity against collateral worth "
                      f"(1-{d:.0%})/LLTV of the debt -> loss {fr:.2%} of market supply; under-pricing only hurts borrowers",
                      "priced_by", "Morpho Blue idToMarketParams.oracle + market liquidity", "medium", "mechanistic")
    un = max(TA - attributed - snap["idle_raw"], 0)
    if un > TA * 1e-6:
        p, why = priors.p_protocol(rates, None, H)
        add(_node("unattributed", "protocol", "Unattributed allocation", p, why + " (unknown component: x1.5)", "unattributed",
                  1.0, "assumption: an unidentified allocation is lost entirely if it fails"))
        E(vid, "unattributed", un / TA, f"measured: {un / TA:.2%} of totalAssets not resolved to a known market (kept, not zero risk)",
          "allocates_to", "totalAssets - resolved - idle", "low", "assumption")
    return g, emeta


# ---- paths / exposure --------------------------------------------------------------------------------------------
def routes(g: DepGraph, nid: str, top: int = 5) -> list[dict]:
    import networkx as nx
    G = to_nx(g)
    if not nx.has_path(G, g.position.id, nid):
        return []
    out = []
    for path in nx.all_simple_paths(G, g.position.id, nid):
        t = math.prod(G[a][b]["transmission"] for a, b in zip(path, path[1:]))
        out.append({"path": path, "transmission": t})
    return sorted(out, key=lambda r: -r["transmission"])[:top]


def conditional_loss(g: DepGraph, shocks: dict) -> dict:
    """Loss GIVEN the shocks happen (p = 1, other risks ignored): V (1 - prod(1 - sev x T_sum))."""
    tm = {k: v[0] for k, v in best_paths(g).items()}
    V = g.position.value_usd
    x = [(nid, g_node.loss_given_failure * tm.get(nid, 0.0)) for nid in shocks
         for g_node in g.nodes if g_node.id == nid]
    frac = 1 - math.prod(1 - h for _, h in x)
    return {"usd": V * frac, "pct": frac, "by_node": {nid: V * h for nid, h in x}}


# ---- assessment (pure: no network) -------------------------------------------------------------------------------
def assess(req: dict, snap: dict, rd: dict, prov: dict) -> dict:
    V, H = req["value_usd"], req["horizon_days"]
    ad = snap["asset_decimals"]
    px = snap["asset_price"].get("price_usd")
    warnings = list(snap.get("warnings", []))
    blockers = []
    rec = snap["reconciliation"]
    TA = snap["total_assets_raw"]
    unit = lambda raw: raw / 10 ** ad  # noqa: E731
    usd = lambda raw: unit(raw) * px if px else None  # noqa: E731

    # --- data quality / cross-checks
    if not px:
        blockers.append("deposit asset USD price unavailable: no firm USD figure")
    else:
        age = snap["asset_price"].get("age_s")
        if age is None or age > PRICE_MAX_AGE_S:
            blockers.append(f"deposit asset price stale ({age or 0:,.0f}s > {PRICE_MAX_AGE_S}s)")
    fx = snap["asset_price"].get("fx")
    if vr.currency_of(snap["asset_symbol"]) == "EUR":
        if not fx:
            blockers.append("EUR/USD rate unavailable: no firm USD value for a EUR-denominated vault")
        elif http.now() - fx["updated_at"] > FX_MAX_AGE_S:
            blockers.append(f"EUR/USD feed stale (> {FX_MAX_AGE_S}s)")
    api = snap.get("api") or {}
    xchecks = []
    if api.get("status") == "ok":
        a = api["data"]
        ta_api = int(float(a.get("totalAssets") or 0))
        diff = abs(ta_api - TA) / TA if TA else 0.0
        xchecks.append({"field": "totalAssets", "onchain_raw": str(TA), "api_raw": str(ta_api), "rel_diff": diff, "tolerance": TOTAL_XCHECK_TOL,
                        "ok": diff <= TOTAL_XCHECK_TOL, "source": api.get("source")})
        if diff > TOTAL_XCHECK_TOL:
            blockers.append(f"indexer and RPC disagree on totalAssets by {diff:.1%}: data not reconciled")
        if (a.get("asset") or {}).get("address", "").lower() != snap["asset_address"].lower():
            blockers.append("indexer reports a different deposit asset than the contract")
        api_px = ((a.get("asset") or {}).get("price") or {}).get("usd")
        if api_px and px:
            d = abs(api_px - px) / px
            xchecks.append({"field": "asset_price_usd", "defillama": px, "morpho_api": api_px, "rel_diff": d,
                            "tolerance": PRICE_XCHECK_TOL, "ok": d <= PRICE_XCHECK_TOL})
            if d > PRICE_XCHECK_TOL:
                blockers.append(f"two price sources disagree by {d:.1%} on {snap['asset_symbol']}")
    else:
        warnings.append(f"Morpho API unavailable ({api.get('error', 'n/a')}): no indexer cross-check; on-chain reads used")
    if rec["coverage"] < COVERAGE_MIN:
        blockers.append(f"only {rec['coverage']:.1%} of totalAssets attributed (< {COVERAGE_MIN:.0%})")
    elif not rec["within_tolerance"]:
        warnings.append(f"reconciliation gap {rec['gap_pct']:.2%} beyond {rec['tolerance']:.1%} tolerance")
    for m in snap["markets"]:
        b = m.get("borrowers") or {}
        if m["total_borrow_raw"] and b.get("status") != "ok" and m["vault_supply_raw"] > 0.01 * TA:
            warnings.append(f"borrower list unavailable for market {m['id'][:10]} ({m['collateral_symbol']}): all its debt "
                            "assumed at the LLTV (conservative)")

    # --- allocations
    allocs = []
    for m in sorted(snap["markets"], key=lambda m: -m["vault_supply_raw"]):
        b = m.get("borrowers") or {}
        allocs.append({
            "market_id": m["id"], "adapter": m.get("holder"), "loan_token": m["loan_token"], "collateral_token": m["collateral_token"],
            "collateral_symbol": m["collateral_symbol"], "oracle": m["oracle"], "irm": m["irm"], "lltv": m["lltv"],
            "supply_raw": str(m["vault_supply_raw"]), "supply_assets": unit(m["vault_supply_raw"]), "supply_usd": usd(m["vault_supply_raw"]),
            "share_of_vault": m["vault_supply_raw"] / TA if TA else 0.0,
            "market_total_supply": unit(m["total_supply_raw"]), "market_total_borrow": unit(m["total_borrow_raw"]),
            "market_liquidity": unit(m["liquidity_raw"]), "vault_share_of_market": m["vault_supply_raw"] / m["total_supply_raw"] if m["total_supply_raw"] else 0.0,
            "utilization": m["utilization"], "supply_apy": m["supply_apy"], "borrow_apy": m["borrow_apy"],
            "borrowers_indexed": len(b.get("items", [])), "borrow_coverage": b.get("coverage"), "borrowers_status": b.get("status", "n/a"),
            "largest_borrower_share": (max((i["debt_raw"] for i in b.get("items", [])), default=0) / m["total_borrow_raw"]) if m["total_borrow_raw"] else 0.0,
            "source": m["source"], "as_of_block": snap["as_of_block"],
            "url": f"https://app.morpho.org/ethereum/market/{m['id']}"})
    allocations = {"items": allocs, "idle_raw": str(snap["idle_raw"]), "idle_assets": unit(snap["idle_raw"]), "idle_usd": usd(snap["idle_raw"]),
                   "idle_share": snap["idle_raw"] / TA if TA else 0.0, "total_assets": unit(TA), "total_assets_usd": usd(TA),
                   "unattributed_assets": unit(rec["unattributed_raw"]), "unattributed_share": rec["unattributed_pct"],
                   "coverage": rec["coverage"], "reconciliation": {**rec, "adapters": [{**r, "reported_raw": str(r["reported_raw"]),
                                                                                       "markets_raw": str(r["markets_raw"]),
                                                                                       "gap_raw": None if r["gap_raw"] is None else str(r["gap_raw"])}
                                                                                      for r in rec["adapters"]],
                                                                    "markets_raw": str(rec["markets_raw"]), "idle_raw": str(rec["idle_raw"]),
                                                                    "total_assets_raw": str(rec["total_assets_raw"]),
                                                                    "unattributed_raw": str(rec["unattributed_raw"])},
                   "unit": snap["asset_symbol"], "decimals": ad, "displayed": "all markets (no truncation)"}

    # --- graph + risk
    g, emeta = build_graph(req, snap, rd["priors"])
    sim = simulate(g)
    lb = uncertainty.loss_band(g)
    paths = best_paths(g)
    nodes = []
    for n in g.nodes:
        if n.id == g.position.id:
            continue
        t = paths.get(n.id, (0.0, None))[0]
        exposed = sorted({p for r in routes(g, n.id, 50) for p in r["path"] if p.startswith("market:")})
        nodes.append({"id": n.id, "label": n.label, "role": n.meta.get("role"), "layer": n.layer, "p_fail_horizon": n.p_fail,
                      "loss_given_failure": n.loss_given_failure, "affected_fraction": t,
                      "affected_usd_if_fails": V * t * n.loss_given_failure,
                      "expected_loss_usd": sim.node_contrib.get(n.id, 0.0), "exposed_allocations": exposed,
                      "decision_neutral": bool(n.meta.get("decision_neutral")),
                      "source": n.meta.get("source"), "lgf_source": n.meta.get("lgf_source"),
                      **{k: n.meta[k] for k in ("address", "market_id", "lltv", "type", "version", "collateral_kind") if k in n.meta}})
    edges = [{"src": e.src, "dst": e.dst, "transmission": e.transmission, "why": e.reason, **emeta[(e.src, e.dst)]} for e in g.edges]
    drivers = sorted((n for n in nodes if n["expected_loss_usd"] > 0), key=lambda n: -n["expected_loss_usd"])[:5]
    risk = {"horizon_days": H, "expected_loss_usd": lb["central_usd"], "expected_loss_pct": lb["central_usd"] / V,
            "label": "expected (probability-weighted over the horizon)", "band_usd": [lb["low_usd"], lb["high_usd"]],
            "dependence_bounds_usd": lb["dependence_bounds_at_central_usd"], "var95_usd": sim.var95_usd,
            "mc_mean_usd": sim.mc_mean_usd, "formula": lb["formula"] + " Paths are SUMMED over a vault's allocations (each "
            "share of assets is exposed once; capped at 100%).", "drivers": [{"id": d["id"], "label": d["label"],
                                                                         "expected_loss_usd": d["expected_loss_usd"],
                                                                         "paths": routes(g, d["id"], 3)} for d in drivers],
            "parameters": uncertainty.inventory(g), "loss_bounds": "0 <= loss <= value_usd (no liability beyond the shares)"}

    # --- exit side
    cap = capacity(snap)
    A = rd.get("assets_raw") or 0
    imm = min(A, cap["ordinary_raw"])
    blocked = max(A - imm, 0)
    sim_r = rd.get("sim") or {}
    if not px or sim_r.get("status") == "unavailable":
        feas = "unknown"
    elif cap["ordinary_raw"] <= 0:
        feas = "zero"
    elif A <= cap["ordinary_raw"] and sim_r.get("status") == "simulated":
        feas = "full"
    elif A <= cap["ordinary_raw"]:
        feas = "unknown"
        blockers.append(f"redeem simulation {sim_r.get('status')} although on-chain capacity covers the amount")
    else:
        feas = "partial"
    if sim_r.get("status") == "simulated" and A > cap["ordinary_raw"] * (1 + CAPACITY_XCHECK_TOL):
        warnings.append("redeem simulation succeeded above the computed ordinary capacity: capacity model is conservative")
    wo = snap.get("withdrawal_options_api") or {}
    cap_check = None
    if wo.get("status") == "ok":
        api_cap = wo["idle_raw"] + wo["liquidity_adapter_available_raw"]
        d = abs(api_cap - cap["ordinary_raw"]) / max(cap["ordinary_raw"], 1)
        cap_check = {"onchain_raw": str(cap["ordinary_raw"]), "api_raw": str(api_cap), "rel_diff": d, "ok": d <= CAPACITY_XCHECK_TOL,
                     "source": wo["source"]}
        if d > CAPACITY_XCHECK_TOL:
            warnings.append(f"Morpho withdrawal-options API differs from on-chain capacity by {d:.1%} (indexer lag?)")
    mw = rd.get("max_withdraw_v1") or {}
    if snap["version"] == "v1" and mw.get("status") == "ok":
        d = abs(mw["max_withdraw_raw"] - cap["ordinary_raw"]) / max(cap["ordinary_raw"], 1)
        cap_check = {"onchain_raw": str(cap["ordinary_raw"]), "contract_max_withdraw_raw": str(mw["max_withdraw_raw"]),
                     "rel_diff": d, "ok": d <= CAPACITY_XCHECK_TOL, "source": mw["method"]}
        if d > CAPACITY_XCHECK_TOL:
            warnings.append(f"MetaMorpho maxWithdraw differs from the withdrawQueue capacity by {d:.1%}")
    out_raw = sim_r.get("assets_out_raw") if sim_r.get("status") == "simulated" else None
    friction_raw = max(A - out_raw, 0) if out_raw is not None else 0
    sp = rd.get("sim_partial") or {}
    if out_raw is None and sp.get("status") == "simulated":
        friction_raw = max(sp["assets_requested_raw"] - sp["assets_out_raw"], 0)
    gas_usd = rd.get("gas_usd")
    if gas_usd is None:
        gas_usd = 0.0
        if feas != "zero":
            blockers.append("gas of the redeem could not be simulated")
    exec_usd = (usd(friction_raw) or 0.0) + gas_usd
    quote_status = "simulated" if sim_r.get("status") == "simulated" else (
        "simulated_partial" if (rd.get("sim_partial") or {}).get("status") == "simulated" else "unavailable")
    ex = {"usd": exec_usd, "slippage_and_fees_usd": usd(friction_raw) or 0.0, "gas_usd": gas_usd,
          "quote_status": "simulated" if quote_status.startswith("simulated") else "unavailable", "method": "vault_redeem_eth_call"}

    fees = snap.get("fees") or {}
    gross = sum((m["vault_supply_raw"] / TA) * m["supply_apy"] for m in snap["markets"]) if TA else 0.0
    net = gross * (1 - (fees.get("performance") or 0)) - (fees.get("management_annual") or 0)
    carry_usd = V * net * H / 365
    apid = (api.get("data") or {}) if api.get("status") == "ok" else {}
    api_net_ex = apid.get("netApyExcludingRewards")
    apy_check = None
    if api_net_ex is not None:
        apy_check = {"onchain": net, "api_excluding_rewards": api_net_ex, "abs_diff": abs(net - api_net_ex),
                     "tolerance_abs": APY_XCHECK_TOL, "ok": abs(net - api_net_ex) <= APY_XCHECK_TOL}
        xchecks.append({"field": "net_apy_excl_rewards", **apy_check, "source": api.get("source")})
        if not apy_check["ok"]:
            warnings.append(f"on-chain net APY {net:.2%} differs from Morpho API (excl. rewards) {api_net_ex:.2%}")
    rewards = [{"symbol": (r.get("asset") or {}).get("symbol"), "apr": r.get("supplyApr")} for r in (apid.get("rewards") or [])]
    rewards_apr = sum(r["apr"] or 0 for r in rewards)
    cr = {"status": "estimated", "usd": carry_usd, "low_usd": carry_usd * (1 - uncertainty.CARRY_BAND),
          "high_usd": carry_usd * (1 + uncertainty.CARRY_BAND), "net_apy_onchain": net, "gross_apy_onchain": gross,
          "performance_fee": fees.get("performance"), "management_fee_annual": fees.get("management_annual"),
          "net_apy_api": api_net_ex, "net_apy_api_incl_rewards": apid.get("netApy"), "apy_cross_check": apy_check,
          "reference_apy": 0.0,
          "rewards_api": rewards, "rewards_usd_not_counted": V * rewards_apr * H / 365,
          "formula": f"V x net APY {net:.2%} (sum share_m x supply APY_m x (1 - perf fee) - mgmt fee, on-chain IRM) x {H}/365",
          "note": "forgone yield if redeemed and left un-deployed (reference 0%: assumption). Past/current APY is not a "
                  "promise; band +-50%. Counted on the EXIT side. Token incentives (rewards_api, Morpho API) are NOT "
                  "counted: off-chain programme, paid in other tokens, can stop at any time (conservative for STAY)."}
    eb = uncertainty.exit_band(ex, cr)
    conv = rd.get("conversion") or {}
    exit_ = {
        "basis": f"USD at the deposit-asset price ({snap['asset_symbol']} ${px or float('nan'):.5f}); same horizon {H}d",
        "notional_assets": unit(A), "notional_usd": V, "hypothetical": HYPOTHETICAL,
        "shares_hypothetical": str(sim_r.get("shares")) if sim_r.get("shares") is not None else None,
        "theoretical_value_usd": V,
        "immediately_withdrawable_assets": unit(imm), "immediately_withdrawable_usd": usd(imm),
        "blocked_or_deferred_assets": unit(blocked), "blocked_or_deferred_usd": usd(blocked),
        "withdrawal_feasibility": feas,
        "capacity": {"ordinary_assets": unit(cap["ordinary_raw"]), "ordinary_usd": usd(cap["ordinary_raw"]),
                     "idle_assets": unit(cap["idle_raw"]), "rows": [{**r, "available": unit(r["available_raw"]),
                                                                     "available_raw": str(r["available_raw"])} for r in cap["rows"]],
                     "rule": cap["rule"], "shared_with_other_depositors": True, "api_cross_check": cap_check,
                     "contract_max_redeem": sim_r.get("max_redeem_contract"),
                     "contract_max_redeem_note": "VaultV2 maxWithdraw/maxRedeem return 0 by design: not used as a limit"
                     if snap["version"] == "v2" else "MetaMorpho maxWithdraw is a valid bound for V1"},
        "simulation": {k: (str(v) if isinstance(v, int) and v > 2 ** 53 else v) for k, v in sim_r.items()},
        "simulation_partial": {k: (str(v) if isinstance(v, int) and v > 2 ** 53 else v) for k, v in (rd.get("sim_partial") or {}).items()} or None,
        "execution_cost_usd": exec_usd, "withdrawal_friction_usd": usd(friction_raw) or 0.0, "gas_usd": gas_usd,
        "gas_units": rd.get("gas_units"), "gas_why": rd.get("gas_why"),
        "exit_fee_usd": 0.0, "exit_fee_note": "no withdrawal fee in VaultV2 / MetaMorpho; performance and management fees are "
                                              "already in the share price (reflected in the net APY)",
        "quote_status": quote_status, "carry": cr, "exit_side_usd": eb["central_usd"], "exit_band_usd": [eb["low_usd"], eb["high_usd"]],
        "usd_conversion": {**conv, "counted_in_decision": False,
                           "why": f"redeeming returns {snap['asset_symbol']}; converting to USD is a separate treasury choice "
                                  "(indicative quote, not simulated) shown for information"},
        "force_deallocate": {"status": "nonstandard", "assets": unit(cap["force_raw"]), "usd": usd(cap["force_raw"]),
                             "rows": [{**r, "available": unit(r["available_raw"]), "available_raw": str(r["available_raw"])} for r in cap["force_rows"]],
                             "penalty_cost_usd": sum((usd(r["available_raw"]) or 0) * (r["penalty"] or 0) for r in cap["force_rows"]),
                             "api_force_deallocatable": [{"adapter": a["address"], "assets": unit(a["force_deallocatable_raw"]),
                                                          "penalty": a["penalty"]} for a in wo.get("adapters", [])],
                             "note": "forceDeallocate moves assets from non-liquidity markets to idle (permissionless, with the "
                                     "adapter penalty): NOT part of the standard exit, not simulated, not used in the verdict"},
    }

    # --- freshness + verdict
    replay = prov.get("cached", 0) > 0 or os.getenv("DEFIRISK_OFFLINE") == "1"
    items = [freshness.item("onchain_state", snap["block_timestamp"], "Ethereum JSON-RPC eth_call @ pinned block", snap["as_of_block"], replay),
             freshness.item("exit_quote", sim_r.get("fetched_at"), "eth_call redeem() simulation (state override)", snap["as_of_block"], replay),
             freshness.item("market_data", api.get("fetched_at") if api.get("status") == "ok" else None, "Morpho GraphQL (cross-check, labels, borrowers)", replay=replay),
             freshness.item("priors", snap["observed_at"], "DefiLlama hacks / protocols / stablecoin prices", replay=replay)]
    for it in items:
        if it["decisive"] and it["stale"]:
            age = "unknown age" if it["age_seconds"] is None else f"{it['age_seconds']:,.0f}s old > {it['max_age_seconds']}s"
            blockers.append(f"stale {it['kind']} ({age}{', cache replay' if it['replay'] else ''}): no firm verdict")
    if replay:
        blockers.append("cache/offline replay: figures are a dated snapshot, not live")
    fresh = {"items": items, "label": "replay" if replay else ("stale" if any(i["stale"] and i["decisive"] for i in items) else "fresh"),
             "policy_ttl_s": freshness.TTL_S, "price_max_age_s": PRICE_MAX_AGE_S}
    blockers = list(dict.fromkeys(blockers))
    sig = uncertainty.robust_signal(lb, eb, cr, blockers)
    verdict, reasons = sig["verdict"], list(sig["reasons"])
    if feas != "full" and (verdict == "EXIT" or sig["point_verdict"] == "EXIT"):
        reasons.append(f"exit not fully executable now ({feas}): only {unit(imm):,.0f} {snap['asset_symbol']} "
                       f"(${usd(imm) or 0:,.0f}) can be withdrawn immediately, {unit(blocked):,.0f} need reallocation / "
                       "forceDeallocate / waiting -> partial exit, not a 100% EXIT")
        if verdict == "EXIT":
            verdict = "REVIEW"
    if feas != "full" and verdict == "STAY":
        reasons.append(f"note: an exit would be {feas} today (immediate ${usd(imm) or 0:,.0f} of ${V:,.0f})")
    margin = lb["central_usd"] - eb["central_usd"]
    point = sig["point_verdict"]
    lean = None
    if verdict == "REVIEW":
        lean = sig["lean"] or f"lean {point} (conditional)"
        if point == "EXIT" and feas != "full":
            lean += f"; partial: exit ${usd(imm) or 0:,.0f} now"
    colour = {"STAY": "green", "EXIT": "red", "REVIEW": "amber"}[verdict]
    decision = {
        "verdict": verdict, "colour": colour, "point_verdict": point, "confidence": "low" if verdict == "REVIEW" else sig["confidence"],
        "lean": lean, "reasons": reasons, "blockers": blockers,
        "expected_loss_usd": lb["central_usd"], "loss_band_usd": [lb["low_usd"], lb["high_usd"]],
        "execution_cost_usd": exec_usd, "carry_usd": carry_usd, "exit_side_usd": eb["central_usd"],
        "exit_band_usd": [eb["low_usd"], eb["high_usd"]], "margin_usd": margin,
        "margin_convention": "margin_usd = expected_loss_usd - (execution_cost_usd + carry_usd); > 0: staying costs more "
                             "on central values (Phase 0.5 convention)",
        "margin_with_usd_conversion_usd": (margin - conv["cost_usd"]) if conv.get("status") == "indicative" else None,
        "breakeven_risk_multiplier": sig["breakeven_risk_multiplier_incl_carry"],
        "withdrawal_feasibility": feas, "horizon_days": H, "rule": sig["rule"] + " A partial / zero / unknown exit downgrades "
        "EXIT to REVIEW (never an executable 100% EXIT).",
        "explanation": _explain(verdict, point, lb, eb, exec_usd, carry_usd, margin, H, feas, imm and usd(imm), reasons),
        "freshness": fresh}

    scen = scenarios(req, snap, rd, g, cap, A, ex, cr)
    sens = sensitivity(req, snap, rd, g, lb, eb)
    if not (0 <= lb["central_usd"] <= V):
        raise AssertionError("loss outside [0, value_usd]")
    return {"allocations": allocations, "dependencies": {"nodes": nodes, "edges": edges, "path_aggregation": "sum"},
            "risk": risk, "exit": exit_, "decision": decision, "scenarios": scen, "sensitivity": sens,
            "warnings": list(dict.fromkeys(warnings)), "cross_checks": xchecks}


def _explain(verdict, point, lb, eb, exec_usd, carry_usd, margin, H, feas, imm_usd, reasons) -> str:
    head = {"STAY": "STAY: even the high estimate of the loss from staying is below the low estimate of the exit side.",
            "EXIT": "EXIT: even the low estimate of the loss from staying exceeds the high estimate of the exit side, and the "
                    "full exit is executable now.",
            "REVIEW": "REVIEW (uncertain): the estimate does not support a firm decision."}[verdict]
    return (f"{head} Staying: expected loss ${lb['central_usd']:,.0f} [${lb['low_usd']:,.0f}-${lb['high_usd']:,.0f}] over {H}d. "
            f"Exiting: execution ${exec_usd:,.2f} + forgone carry ${carry_usd:,.0f} = ${eb['central_usd']:,.0f} "
            f"[${eb['low_usd']:,.0f}-${eb['high_usd']:,.0f}]. Margin (loss - exit side) = ${margin:,.0f}: "
            f"{'staying' if margin > 0 else 'exiting'} costs more on central values (point verdict {point}). "
            f"Withdrawal feasibility: {feas}" + (f" (${imm_usd:,.0f} immediately)." if imm_usd else ".")
            + (" Why: " + "; ".join(reasons) + "." if reasons else ""))


# ---- scenarios / sensitivity ---------------------------------------------------------------------------------------
def _largest(g: DepGraph, role: str):
    tm = {k: v[0] for k, v in best_paths(g).items()}
    c = [n for n in g.nodes if n.meta.get("role") == role and tm.get(n.id, 0) > 0]
    return max(c, key=lambda n: tm[n.id]) if c else None


def _scenario(req, snap, rd, base_g, name, desc, sev: dict, liquidity_factor=1.0, cap=None, A=0, neutral=None):
    g, _ = build_graph(req, snap, rd["priors"], sev=sev, liquidity_factor=liquidity_factor)
    V = req["value_usd"]
    cl = conditional_loss(g, list(sev)) if sev else {"usd": 0.0, "pct": 0.0, "by_node": {}}
    s_g = deepcopy(g)
    for n in s_g.nodes:
        if n.id in sev:
            n.p_fail = 1.0
    exp_after = simulate(s_g).expected_loss_usd
    c2 = capacity(snap, liquidity_factor)
    px = snap["asset_price"].get("price_usd") or 0
    imm = min(A, c2["ordinary_raw"])
    ad = snap["asset_decimals"]
    out = {"name": name, "description": desc, "label": "conditional_on_shock", "shocked": [
               {"id": k, "severity": v, "label": next((n.label for n in g.nodes if n.id == k), k)} for k, v in sev.items()],
           "loss_usd": cl["usd"], "loss_pct": cl["pct"], "loss_incl_background_risk_usd": exp_after,
           "paths": {k: routes(g, k, 4) for k in sev}, "by_node_usd": cl["by_node"],
           "immediately_withdrawable_usd": imm / 10 ** ad * px, "withdrawal_feasibility":
               "full" if A <= c2["ordinary_raw"] and c2["ordinary_raw"] > 0 else ("zero" if c2["ordinary_raw"] == 0 else "partial"),
           "liquidity_factor": liquidity_factor, "vault": snap["address"]}
    if neutral:
        out.update(neutral)
    return out


def scenarios(req, snap, rd, g, cap, A, ex, cr) -> list[dict]:
    out = []
    coll = _largest(g, "collateral")
    orc = _largest(g, "oracle")
    mk = _largest(g, "market")
    if coll:
        out.append(_scenario(req, snap, rd, g, f"Collateral crash: {coll.label}",
                             f"{coll.label} drops {SCENARIO_CRASH:.0%} in a jump (hypothesis); borrowers are liquidated on-chain; "
                             "suppliers only lose the residual bad debt", {coll.id: SCENARIO_CRASH}, cap=cap, A=A))
    if orc:
        out.append(_scenario(req, snap, rd, g, f"Oracle failure: {orc.label}",
                             f"the oracle over-prices collateral by {SCENARIO_CRASH:.0%} (hypothesis); free liquidity is borrowed "
                             "against overvalued collateral", {orc.id: SCENARIO_CRASH}, cap=cap, A=A))
    if mk:
        out.append(_scenario(req, snap, rd, g, f"Market failure: {mk.label}",
                             f"isolated failure of the largest market (hypothesis: suppliers lose {MARKET_SEVERITY:.0%} of it)",
                             {mk.id: MARKET_SEVERITY}, cap=cap, A=A))
    out.append(_scenario(req, snap, rd, g, "Liquidity crisis",
                         "all markets' free liquidity is borrowed out (hypothesis): no direct loss, but the ordinary exit is "
                         "limited to idle assets", {}, liquidity_factor=0.0, cap=cap, A=A))
    corr = {n.id: SCENARIO_CRASH for n in g.nodes if n.meta.get("collateral_kind") == "issued_token"}
    if orc:
        corr[orc.id] = SCENARIO_CRASH
    if corr:
        out.append(_scenario(req, snap, rd, g, "Correlated: collateral crash + oracle failure + liquidity crisis",
                             f"every non-stable collateral drops {SCENARIO_CRASH:.0%}, the main oracle fails and liquidity "
                             "is exhausted - joint hypothesis", corr, liquidity_factor=0.0, cap=cap, A=A))
    aid = f"asset:{snap['asset_address']}"
    V = req["value_usd"]
    out.append({"name": f"Deposit asset depeg: {snap['asset_symbol']} -{SCENARIO_DEPEG:.0%}",
                "description": f"{snap['asset_symbol']} loses {SCENARIO_DEPEG:.0%} vs its peg (hypothesis)", "label": "conditional_on_shock",
                "shocked": [{"id": aid, "severity": SCENARIO_DEPEG, "label": snap["asset_symbol"]}],
                "loss_usd": V * SCENARIO_DEPEG, "loss_pct": SCENARIO_DEPEG, "decision_neutral": True,
                "stay_loss_usd": V * SCENARIO_DEPEG, "exit_to_asset_loss_usd": V * SCENARIO_DEPEG,
                "note": "redeeming returns the same asset: STAY and EXIT lose the same; only converting to USD before the depeg "
                        "avoids it (see usd_conversion)", "paths": {}, "vault": snap["address"]})
    if req.get("shock"):
        nid = req["shock"]
        n = next((x for x in g.nodes if x.id == nid), None)
        if n is None or nid == g.position.id:
            raise VaultError("invalid_scenario", 400, f"shock '{nid}' is not a dependency of vault {snap['address']}",
                             {"valid_ids": [x.id for x in g.nodes if x.id != g.position.id]})
        sev = n.loss_given_failure if req.get("severity") is None else req["severity"]
        out.insert(0, dict(_scenario(req, snap, rd, g, f"Custom shock: {n.label}", f"{n.label} fails with severity {sev:.0%}",
                                     {nid: sev}, cap=cap, A=A), custom=True))
    return out


def sensitivity(req, snap, rd, g, lb, eb) -> dict:
    V = req["value_usd"]
    rows = []
    for n in g.nodes:
        if n.p_fail <= 0:
            continue
        for k in (0.5, 2.0):
            g2 = deepcopy(g)
            nn = next(x for x in g2.nodes if x.id == n.id)
            nn.p_fail = min(nn.p_fail * k, 1.0)
            rows.append({"id": n.id, "label": n.label, "p_multiplier": k, "expected_loss_usd": simulate(g2).expected_loss_usd})
    base = lb["central_usd"]
    tornado = {}
    for r in rows:
        tornado.setdefault(r["id"], {"id": r["id"], "label": r["label"], "low_usd": base, "high_usd": base})
        t = tornado[r["id"]]
        t["low_usd"], t["high_usd"] = min(t["low_usd"], r["expected_loss_usd"]), max(t["high_usd"], r["expected_loss_usd"])
    top = sorted(tornado.values(), key=lambda t: -(t["high_usd"] - t["low_usd"]))[:6]
    coll = _largest(g, "collateral")
    crash = []
    if coll:
        for s in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8):
            g2, _ = build_graph(req, snap, rd["priors"], sev={coll.id: s})
            crash.append({"drop": s, "loss_usd": conditional_loss(g2, [coll.id])["usd"]})
    return {"base_expected_loss_usd": base, "tornado_p_x0.5_x2": top, "collateral_crash_curve": {"node": coll.id if coll else None,
            "label": coll.label if coll else None, "points": crash, "label_kind": "conditional_on_shock"},
            "breakeven_risk_multiplier": (eb["central_usd"] / base) if base > 0 else None,
            "note": "risk must be x breakeven the central estimate for the exit side to be worth paying"}


# ---- entry point ---------------------------------------------------------------------------------------------------
ASSUMPTIONS = [
    "value_usd is a hypothetical exposure: converted to vault shares at the pinned share price; no holding is claimed",
    f"collateral 'failure' = {COLLATERAL_SEVERITY:.0%} jump drop (no time to liquidate before it); suppliers lose only the bad debt "
    "left after on-chain liquidations (Morpho Blue liquidation math, LIF from LLTV)",
    "borrowers missing from the indexed list are assumed to sit at the LLTV (worst case)",
    f"oracle failure = {ORACLE_SEVERITY:.0%} over-pricing; free liquidity drained against overvalued collateral",
    "vault contracts / curator and Morpho Blue share one Morpho protocol prior (x0.5 each, Phase 0.5 split); chain prior 0.5%/y",
    "deposit asset depeg and EUR/USD are decision-neutral (held after redeeming too): shown as context / what-if",
    "carry = on-chain net APY (supply APY of each market x share, net of fees) over the horizon, reference 0%, band +-50%",
    "ordinary withdrawal capacity is shared with every other depositor and can change every block",
    "probabilities are horizon-scaled annual base rates (DefiLlama), not forecasts; this is not investment advice",
]


def _js_safe(o):
    """Integers beyond 2^53 lose precision in JavaScript: emit them as strings (raw on-chain units)."""
    if isinstance(o, bool):
        return o
    if isinstance(o, int) and abs(o) > 2 ** 53:
        return str(o)
    if isinstance(o, dict):
        return {k: _js_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_js_safe(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def analyze(req: dict) -> dict:
    http.reset_provenance()
    snap = vr.snapshot(req["address"])
    rd = reads(req, snap)
    prov = http.provenance()
    body = assess(req, snap, rd, prov)
    return _js_safe(payload(req, snap, rd, prov, body))


def payload(req, snap, rd, prov, body) -> dict:
    offline = os.getenv("DEFIRISK_OFFLINE") == "1"
    mode = "offline" if offline else prov["mode"]
    age = max(http.now() - snap["block_timestamp"], 0)
    px = snap["asset_price"]
    return {
        "schema": "faultline.vault/1",
        "input": {"address": req["address"], "checksum": req["checksum"], "chain_id": req["chain_id"], "value_usd": req["value_usd"],
                  "horizon_days": req["horizon_days"], "shock": req.get("shock"), "severity": req.get("severity"),
                  "value_semantics": HYPOTHETICAL},
        "vault": {"address": snap["address"], "name": snap["name"], "symbol": snap["symbol"], "version": snap["version"],
                  "factory": snap["factory"], "factory_name": snap["factory_name"], "chain_id": 1, "chain": "Ethereum mainnet",
                  "asset": {"address": snap["asset_address"], "symbol": snap["asset_symbol"], "decimals": snap["asset_decimals"],
                            "currency": px.get("currency"), "price_usd": px.get("price_usd"), "price_source": px.get("source"),
                            "price_age_s": px.get("age_s"), "fx": px.get("fx"), "peg_vs_eur": px.get("peg_vs_eur"),
                            "decomposition": px.get("decomposition")},
                  "share_decimals": snap["decimals"], "share_price": snap["share_price_raw"] / 10 ** snap["asset_decimals"],
                  "fees": snap["fees"], "gates": snap["gates"], "liquidity_adapter": snap.get("liquidity_adapter"),
                  "liquidity_market": snap.get("liquidity_market"),
                  "adapters": [{**a, "real_assets_raw": None if a.get("real_assets_raw") is None else str(a["real_assets_raw"]),
                                **({"inner_assets_raw": str(a["inner_assets_raw"])} if a.get("inner_assets_raw") is not None else {})}
                               for a in snap["adapters"]],
                  "detection": f"{snap['factory_name']} ({snap['factory']}) confirms the contract on-chain; code {snap['code_bytes']} bytes",
                  "url": f"https://app.morpho.org/ethereum/vault/{snap['address']}"},
        "snapshot": {"as_of_block": snap["as_of_block"], "block_timestamp": snap["block_timestamp"], "observed_at": snap["observed_at"],
                     "age_s": age, "total_assets": snap["total_assets_raw"] / 10 ** snap["asset_decimals"],
                     "total_assets_raw": str(snap["total_assets_raw"]), "total_supply_raw": str(snap["total_supply_raw"]),
                     "idle_raw": str(snap["idle_raw"]), "cross_checks": body.pop("cross_checks"),
                     "api": {k: v for k, v in (snap.get("api") or {}).items() if k != "data"},
                     "api_net_apy_excl_rewards": ((snap.get("api") or {}).get("data") or {}).get("netApyExcludingRewards"),
                     "api_net_apy_incl_rewards": ((snap.get("api") or {}).get("data") or {}).get("netApy")},
        **body,
        "assumptions": ASSUMPTIONS,
        "provenance": {**prov, "mode": mode, "rpc": "public Ethereum JSON-RPC (no key)", "indexer": sources.MORPHO,
                       "prices": "DefiLlama coins + Chainlink EUR/USD", "simulation": "eth_call with state override (read-only)"},
        "mode": mode, "as_of_block": snap["as_of_block"], "timestamp": snap["observed_at"], "age_s": age,
    }
