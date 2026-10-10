"""Dependency discovery from real public data.

position_ref:
  'auto'                      -> biggest Morpho Blue market (mainnet) that takes a Pendle PT as collateral
  'pendle:1:<market address>' -> that Pendle market, paired with its biggest Morpho market

Pipeline (the five layers of the Belem brief + hidden second-order dependencies):
  L4 Pendle API   market -> SY -> underlying / accounting asset, liquidity, expiry
  L2 Pendle+Llama underlying yield source and its ISSUER (audits, TVL, age)
  L5 Morpho API   lending market holding the PT (LLTV, utilisation, bad debt, supplying vaults)
  L3 Morpho+RPC   oracle contract -> price feed -> feed provider; on-chain feed-quality checks
  L1 chain        settlement chain
  hidden          loan asset, lending protocol, feed provider, issuer backing + who else shares them
"""
from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path

from . import priors, sources
from .models import DepGraph, Edge, Node, Position

MOCK = Path(__file__).resolve().parents[2] / "data" / "mock_graph.json"
STABLES = {"USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "FRAX", "LUSD", "GHO", "USD0"}
LOAN_ISSUERS = {"USDC": "circle usdc", "USDT": "tether", "DAI": "makerdao", "USDS": "sky", "PYUSD": "paypal", "GHO": "aave"}


def discover(position_ref: str = "auto", use_mock: bool = True, value_usd: float = 1_000_000, horizon_days: int = 30) -> DepGraph:
    if use_mock:
        return DepGraph.load(str(MOCK))
    return discover_real(position_ref, value_usd, horizon_days)


# ---------------------------------------------------------------------------
def _select(ref: str, chain_id: int):
    pendle_ms = sources.pendle_active_markets(chain_id)
    by_pt = {sources.strip_chain(m["pt"]): m for m in pendle_ms}
    morpho = sources.morpho_markets_for_collateral(list(by_pt), chain_id, min_supply_usd=1_000_000)
    morpho = [m for m in morpho if m.get("listed") and m["collateralAsset"]["address"].lower() in by_pt]
    if not morpho:
        raise RuntimeError("no listed Morpho market with a Pendle PT as collateral")
    if ref.startswith("pendle:"):
        addr = ref.split(":")[-1].lower()
        pm = next((m for m in pendle_ms if m["address"].lower() == addr), None)
        if pm is None:
            raise RuntimeError(f"{addr} is not an active Pendle market on chain {chain_id}")
        mine = [m for m in morpho if m["collateralAsset"]["address"].lower() == sources.strip_chain(pm["pt"])]
        if not mine:
            raise RuntimeError(f"no listed Morpho market uses the PT of {addr} as collateral")
        return pm, mine[0], morpho, by_pt
    mm = morpho[0]
    return by_pt[mm["collateralAsset"]["address"].lower()], mm, morpho, by_pt


def _feed_addresses(market: dict) -> list[str]:
    data = (market.get("oracle") or {}).get("data") or {}
    return [data[k]["address"] for k in ("baseFeedOne", "baseFeedTwo", "quoteFeedOne", "quoteFeedTwo") if data.get(k)]


def _provider(description: str) -> str:
    return (description.split(" ")[0] if description else "unknown").strip() or "unknown"


def _feed_quality(market: dict, pt_price_usd: float | None) -> dict:
    feeds = _feed_addresses(market)
    data = (market.get("oracle") or {}).get("data") or {}
    q = {"feeds": feeds, "n_feeds": len(feeds), "single_feed": len(feeds) <= 1 and not data.get("baseOracleVault"),
         "oracle_type": (market.get("oracle") or {}).get("type"), "description": "", "provider": "unknown",
         "updated_age_s": None, "computed_on_read": None, "deviation_vs_pendle_pct": None, "reads_pendle": False}
    info = sources.read_feed(feeds[0]) if feeds else None
    if info:
        q["description"] = info["description"]
        q["provider"] = _provider(info["description"])
        q["reads_pendle"] = "pendle" in info["description"].lower()
        if os.getenv("DEFIRISK_OFFLINE") != "1":  # cached eth_call results would give a misleading age
            q["updated_age_s"] = max(0, int(time.time()) - info["updated_at"])
            q["computed_on_read"] = q["updated_age_s"] < 300
        if pt_price_usd and market["loanAsset"]["symbol"].upper() in STABLES and info["answer"] > 0:
            q["deviation_vs_pendle_pct"] = (info["answer"] - pt_price_usd) / pt_price_usd * 100
    return q


def _quality_multiplier(q: dict) -> tuple[float, list[str]]:
    mult, notes = 1.0, []
    if q["single_feed"]:
        mult *= 1.5; notes.append("single price feed x1.5")
    if q["computed_on_read"]:
        mult *= 1.5; notes.append("feed is computed on read (no heartbeat/staleness guard) x1.5")
    dev = q["deviation_vs_pendle_pct"]
    if dev is not None and abs(dev) > 2:
        mult *= 1.5; notes.append(f"feed deviates {dev:+.1f}% from Pendle PT price x1.5")
    return mult, notes


def _concentration(morpho: list[dict], by_pt: dict, ours: dict, quality: dict) -> list[dict]:
    """How much of the Morpho PT lending book shares each of our dependencies (hidden concentration)."""
    rows = morpho[:12]
    total = sum(m["state"]["supplyAssetsUsd"] or 0 for m in rows) or 1
    providers = {}
    for m in rows:
        feeds = _feed_addresses(m)
        info = sources.read_feed(feeds[0]) if feeds else None
        providers[m["marketId"]] = _provider(info["description"]) if info else "unknown"

    def issuer(m):
        pm = by_pt[m["collateralAsset"]["address"].lower()]
        return pm.get("protocol") or m["collateralAsset"]["symbol"].split("-")[1]

    groups = [
        ("feed", "Price feed provider", lambda m: providers[m["marketId"]], quality["provider"]),
        ("loan", "Loan asset", lambda m: m["loanAsset"]["symbol"], ours["loanAsset"]["symbol"]),
        ("issuer", "PT issuer / protocol", issuer, issuer(ours)),
    ]
    out = []
    for key, label, fn, mine in groups:
        same = [m for m in rows if fn(m) == mine]
        usd = sum(m["state"]["supplyAssetsUsd"] or 0 for m in same)
        out.append({"node": key, "label": f"{label}: {mine}", "markets": len(same), "of_markets": len(rows),
                    "supply_usd": usd, "share_pct": usd / total * 100})
    return out


# ---------------------------------------------------------------------------
def discover_real(ref: str, value_usd: float, horizon_days: int) -> DepGraph:
    chain_id = 1
    pm, mm, morpho_all, by_pt = _select(ref, chain_id)
    pend = sources.pendle_market(pm["address"], chain_id)
    pdata = sources.pendle_market_data(pm["address"], chain_id)
    protocols = sources.llama_protocols()
    rates = priors.base_rates(protocols=protocols)
    H = horizon_days

    pt_sym = pend["pt"]["symbol"]
    pt_price = (pend["pt"].get("price") or {}).get("usd")
    underlying = pend["underlyingAsset"]
    accounting = pend["accountingAsset"]
    issuer_name = pend.get("protocol") or underlying["symbol"]
    issuer_llama = sources.llama_find_protocol(issuer_name, protocols) or sources.llama_find_protocol(underlying["symbol"], protocols)
    morpho_llama = sources.llama_find_protocol("morpho", protocols)
    pendle_llama = sources.llama_find_protocol("pendle", protocols)
    loan_sym = mm["loanAsset"]["symbol"]
    loan_llama = sources.llama_find_protocol(LOAN_ISSUERS.get(loan_sym.upper(), loan_sym), protocols)
    q = _feed_quality(mm, pt_price)
    mult, qnotes = _quality_multiplier(q)
    ms = mm["state"]
    liq = pdata["liquidity"]["usd"]

    def node(nid, layer, label, p, why, role, lgf=None, lgf_why=None, **meta):
        lg = priors.LGF.get(role, 0.5) if lgf is None else lgf
        return Node(nid, layer, label, round(p, 6), round(lg, 4),
                    {"role": role, "source": why, "chain": "ethereum",
                     "lgf_source": lgf_why or f"structural assumption: loss-given-failure {lg:.0%} for role '{role}' (priors.LGF)",
                     **meta})

    def llama_meta(p):
        return {"tvl_usd": p.get("tvl"), "audits": p.get("audits"), "url": p.get("url"),
                "llama_slug": p.get("slug")} if p else {}

    hist = {}

    def stable_prior(sym):
        try:
            gid = sources.llama_stablecoin_gecko_id(sym)
            if gid and "h" not in hist:
                hist["h"] = sources.llama_stablecoin_price_history()
            dep = priors.stablecoin_depeg(gid, hist["h"]) if gid else None
        except Exception:
            dep = None
        return priors.p_stablecoin(dep, H, sym)

    nodes: list[Node] = [Node("pos", "protocol", "Position", 0.0, 0.0, {"role": "position"})]
    edges: list[Edge] = []

    def stable_node(sym, address):
        nid = f"usd_{sym.lower()}"
        if not any(n.id == nid for n in nodes):
            p, lgf, why = stable_prior(sym)
            nodes.append(node(nid, "yield_source", f"{sym} (stablecoin)", p, why, "stablecoin", lgf=lgf,
                              lgf_why=(f"measured: mean depth of past {sym} depegs (DefiLlama prices)" if lgf else None),
                              address=address))
        return nid

    p, why = priors.p_chain(H)
    nodes.append(node("chain", "chain", "Ethereum", p, why, "chain"))

    # Issuer-entity risk is split across the issuer and its tokens so the total equals ONE protocol prior
    # (failures are simulated independently; giving each node the full rate would count the issuer 2-3 times).
    has_backing = accounting["address"].lower() != underlying["address"].lower()
    backing_stable = has_backing and accounting["symbol"].upper() in STABLES
    split = {"issuer": 0.5, "underlying": 0.25 if has_backing and not backing_stable else 0.5,
             "backing": 0.25 if has_backing and not backing_stable else 0.0}
    p, why = priors.p_protocol(rates, issuer_llama, H, share=split["issuer"])
    nodes.append(node("issuer", "yield_source", f"{issuer_name} (issuer)", p, why + f"; x{split['issuer']} = entity share of issuer risk",
                      "issuer", **llama_meta(issuer_llama), categories=pend.get("categoryIds")))
    p, why = priors.p_protocol(rates, issuer_llama, H, share=split["underlying"])
    nodes.append(node("underlying", "yield_source", f"{underlying['symbol']} (yield source)", p,
                      why + f"; x{split['underlying']} = token-level share of issuer risk", "underlying",
                      address=underlying["address"], price_usd=(underlying.get("price") or {}).get("usd")))
    backing_id = None
    if backing_stable:
        backing_id = stable_node(accounting["symbol"], accounting["address"])
    elif has_backing:
        backing_id = "backing"
        p, why = priors.p_protocol(rates, issuer_llama, H, share=split["backing"])
        nodes.append(node("backing", "yield_source", f"{accounting['symbol']} (backing asset)", p,
                          why + f"; x{split['backing']} = backing share of issuer risk", "backing", address=accounting["address"],
                          price_usd=(accounting.get("price") or {}).get("usd")))

    p, why = priors.p_protocol(rates, pendle_llama, H)
    nodes.append(node("amm", "amm", f"Pendle market {pt_sym}", p, why, "amm", address=pm["address"],
                      expiry=pend["expiry"], liquidity_usd=liq, tvl_usd=pdata["totalTvl"]["usd"],
                      pt_discount=pdata.get("ptDiscount"), implied_apy=pdata.get("impliedApy"),
                      url=f"https://app.pendle.finance/trade/markets/{pm['address']}/swap?view=pt&chain=ethereum"))

    p, why = priors.p_oracle(rates, H, mult, qnotes)
    has_feed = q["provider"] != "unknown"
    o_share = 0.5 if has_feed else 1.0
    nodes.append(node("oracle", "oracle", f"Morpho oracle ({q['oracle_type'] or 'unknown'})", p * o_share,
                      why + (f"; x{o_share} = oracle-contract share (rest on the feed provider)" if has_feed else ""), "oracle",
                      address=mm["oracle"]["address"], twap_window=None, single_feed=q["single_feed"],
                      sources=q["n_feeds"], heartbeat=None if q["computed_on_read"] else "unknown",
                      provider=q["provider"], feed=q["description"], computed_on_read=q["computed_on_read"],
                      deviation_vs_pendle_pct=q["deviation_vs_pendle_pct"], quality_flags=qnotes))
    if has_feed:
        nodes.append(node("feed", "oracle", f"{q['provider']} (feed provider)", p * 0.5,
                          why + "; x0.5 = provider-level share", "feed_provider",
                          address=(q["feeds"] or [None])[0], description=q["description"]))

    bad = (mm.get("badDebt") or {}).get("usd") or 0
    warns = [w["type"] for w in mm.get("warnings") or []]
    p, why = priors.p_protocol(rates, morpho_llama, H, share=0.5)
    nodes.append(node("lending", "lending", f"Morpho market {pt_sym}/{loan_sym}", p, why + "; x0.5 = isolated-market share of Morpho risk",
                      "lending",
                      market_id=mm["marketId"], lltv=int(mm["lltv"]) / 1e18, utilization=ms["utilization"],
                      supply_usd=ms["supplyAssetsUsd"], borrow_usd=ms["borrowAssetsUsd"], liquidity_usd=ms["liquidityAssetsUsd"],
                      bad_debt_usd=bad, warnings=warns,
                      supplying_vaults=[{"name": v["name"], "address": v["address"],
                                         "total_assets_usd": (v.get("state") or {}).get("totalAssetsUsd")}
                                        for v in mm.get("supplyingVaults") or []],
                      url=f"https://app.morpho.org/ethereum/market/{mm['marketId']}"))
    p, why = priors.p_protocol(rates, morpho_llama, H, share=0.5)
    nodes.append(node("morpho", "protocol", "Morpho Blue (protocol)", p, why + "; x0.5 = singleton-contract share",
                      "morpho_blue", **llama_meta(morpho_llama)))
    if loan_sym.upper() in STABLES:
        loan_id = stable_node(loan_sym, mm["loanAsset"]["address"])
    else:
        loan_id = "loan"
        p, why = priors.p_protocol(rates, loan_llama, H, share=0.5)
        nodes.append(node("loan", "protocol", f"{loan_sym} (loan asset)", p, why + "; x0.5 = depeg share", "loan_asset",
                          address=mm["loanAsset"]["address"], **llama_meta(loan_llama)))

    def E(s, d, t, r):
        edges.append(Edge(s, d, t, r))

    E("pos", "amm", 1.0, f"holds {pt_sym}; exits through the Pendle AMM")
    E("pos", "lending", 1.0, f"{pt_sym} posted as collateral on Morpho")
    E("amm", "underlying", 0.9, f"SY wraps {underlying['symbol']}")
    E("underlying", "issuer", 0.8, f"{underlying['symbol']} is issued/managed by {issuer_name}")
    if backing_stable:
        E("underlying", backing_id, 0.8, f"{underlying['symbol']} is accounted in / redeemable for {accounting['symbol']} "
                                         f"(Pendle SY accounting asset)")
    elif has_backing:
        E("underlying", "backing", 0.8, f"{underlying['symbol']} is a claim on {accounting['symbol']} (Pendle SY accounting asset)")
        E("backing", "issuer", 0.8, f"{accounting['symbol']} is also managed by {issuer_name}")
    E("lending", "oracle", 0.8, "liquidations and borrow limits use this oracle")
    E("oracle", "amm", 0.7 if q["reads_pendle"] else 0.4,
      "feed reads the Pendle market" if q["reads_pendle"] else "oracle prices the PT off market data")
    if has_feed:
        E("oracle", "feed", 0.9, f"price comes from the {q['provider']} feed")
        E("feed", "chain", 0.5, "feed publishes on Ethereum")
    E("lending", "morpho", 0.7, "market is a Morpho Blue singleton market")
    E("lending", loan_id, 0.3, f"market liquidity is denominated in {loan_sym}")
    for src in ("amm", "lending"):
        E(src, "chain", 1.0, "settles on Ethereum")

    # second-order ("hidden") = not directly touched by the position
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.src, []).append(e.dst)
    depth = {"pos": 0}
    dq = deque(["pos"])
    while dq:
        u = dq.popleft()
        for v in adj.get(u, []):
            if v not in depth:
                depth[v] = depth[u] + 1
                dq.append(v)
    for n in nodes:
        n.meta["depth"] = depth.get(n.id)
        n.meta["hidden"] = (depth.get(n.id) or 0) >= 2

    try:
        block = sources.eth_block_number()
    except Exception:
        block = None
    route = {"pt": pend["pt"]["address"], "pt_decimals": pend["pt"].get("decimals", 18), "pt_price_usd": pt_price,
             "out": mm["loanAsset"]["address"], "out_symbol": loan_sym, "chain_id": chain_id}
    pos = Position("pos", f"{pt_sym} on Morpho ({loan_sym})", "ethereum", value_usd, H, {
        "exit_pool_liquidity_usd": liq, "ref": ref, "real": True, "pendle_market": pm["address"],
        "morpho_market": mm["marketId"], "observed_at": int(time.time()), "block_number": block,
        "concentration": _concentration(morpho_all, by_pt, mm, q),
        "data_sources": ["Pendle API v1/v2 + SDK convert (exit quote)", "Morpho Blue GraphQL", "DefiLlama /hacks /protocols",
                         "DefiLlama stablecoin prices", "Ethereum JSON-RPC (eth_call, eth_gasPrice, eth_blockNumber)"],
        "prior_method": rates["source"],
        "prior_upper_annual": rates.get("annual_per_protocol_upper"),
        "prior_central_annual": rates.get("annual_per_protocol"),
        "exit_route": route,
    })
    g = DepGraph(pos, nodes, edges)
    if os.environ.get("DEFIRISK_NO_QUOTE") != "1":
        from .decision import quote_exit
        try:
            pos.meta["exit_quote"] = quote_exit(route, value_usd)
        except Exception as e:  # recorded, decision falls back to the flagged approximation
            pos.meta["exit_quote_error"] = f"{type(e).__name__}: {e}"[:300]
    return g
