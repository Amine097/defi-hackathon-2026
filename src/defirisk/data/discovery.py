"""Dependency discovery from real public data.

position_ref:
  'auto'                      -> biggest Morpho Blue market (mainnet) that takes a Pendle PT as collateral
  'pendle:1:<market address>' -> that Pendle market, paired with its biggest Morpho market
  'morpho:1:<market id>'      -> that Morpho Blue market, if it takes a Pendle PT as collateral (listed, supply >= $1M)

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
import re
import time
from collections import deque
from pathlib import Path

from . import exposure, http, lineage, peg, priors, sources
from ..core.models import DepGraph, Edge, Node, Position

MOCK = Path(__file__).resolve().parents[3] / "data" / "mock_graph.json"
STABLES = {"USDC", "USDT", "DAI", "USDS", "USDE", "PYUSD", "FRAX", "LUSD", "GHO", "USD0"}
LOAN_ISSUERS = {"USDC": "circle usdc", "USDT": "tether", "DAI": "makerdao", "USDS": "sky", "PYUSD": "paypal", "GHO": "aave"}
_MARKET_ID = re.compile(r"0x[0-9a-f]{64}")


class UnsupportedMarket(RuntimeError):
    """The ref is well formed but the market is not in the supported set (listed Morpho market, Pendle PT collateral)."""


def _check_ref(ref: str, chain_id: int) -> None:
    parts = ref.split(":")
    if ref.startswith("pendle:") and (len(parts) != 3 or parts[1] != str(chain_id)):
        raise ValueError(f"unsupported ref '{ref}': use pendle:1:<market address> (Ethereum mainnet only for now: other "
                         "chains need their own RPC, Morpho deployment and gas pricing)")
    if ref.startswith("morpho:") and (len(parts) != 3 or parts[1] != str(chain_id) or not _MARKET_ID.fullmatch(parts[2].lower())):
        raise ValueError(f"unsupported ref '{ref}': use morpho:1:<Morpho Blue market id, 0x + 64 hex> (Ethereum mainnet only)")
    if parts[0] not in ("auto", "pendle", "morpho"):
        raise ValueError(f"unsupported ref '{ref}': use auto, pendle:1:<market address> or morpho:1:<market id>")


def lookup(ref: str, chain_id: int = 1) -> dict:
    """Cheap identification for the app's select screen: is this Morpho market id in the supported set, and what is it?
    Uses the same market lists as discover_real (Pendle API active markets x Morpho API PT-collateral markets)."""
    _check_ref(ref, chain_id)
    pm, mm, _all, _by_pt = _select(ref, chain_id)
    return {"kind": "pt_market", "lookup": True, "chain_id": chain_id, "market_id": mm["marketId"].lower(), "ref": f"morpho:{chain_id}:{mm['marketId'].lower()}",
            "pt_symbol": mm["collateralAsset"]["symbol"], "loan_symbol": mm["loanAsset"]["symbol"], "lltv": int(mm["lltv"]) / 1e18,
            "supply_usd": (mm.get("state") or {}).get("supplyAssetsUsd"), "pendle_market": pm["address"], "expiry": pm.get("expiry"),
            "label": f"{mm['collateralAsset']['symbol']} / {mm['loanAsset']['symbol']}",
            "source": "Pendle API active markets x Morpho Blue API (listed, supply >= $1M); analysis not run yet"}


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
    if ref.startswith("morpho:"):
        mid = ref.split(":")[-1].lower()
        mm = next((m for m in morpho if str(m.get("marketId", "")).lower() == mid), None)
        if mm is None:
            raise UnsupportedMarket(f"{mid} is not a listed Morpho Blue market (supply >= $1M) that takes an active Pendle PT "
                                    f"as collateral on chain {chain_id}")
        return by_pt[mm["collateralAsset"]["address"].lower()], mm, morpho, by_pt
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
    """Quality of the market oracle's inputs: EVERY feed (base/quote, 1 and 2) is read on-chain, not only the first."""
    feeds = _feed_addresses(market)
    data = (market.get("oracle") or {}).get("data") or {}
    q = {"feeds": feeds, "n_feeds": len(feeds), "single_feed": len(feeds) <= 1 and not data.get("baseOracleVault"),
         "oracle_type": (market.get("oracle") or {}).get("type"), "description": "", "provider": "unknown",
         "updated_age_s": None, "computed_on_read": None, "deviation_vs_pendle_pct": None, "reads_pendle": False,
         "feed_details": [], "providers": [], "vaults": [v for v in (data.get("baseOracleVault"), data.get("quoteOracleVault"))
                                                          if v]}
    infos = []
    for addr in feeds:
        try:
            info = sources.read_feed(addr)
        except Exception:  # noqa: BLE001 - one unreadable feed must not hide the others
            info = None
        infos.append(info)
        row = {"address": addr, "readable": bool(info)}
        if info:
            row.update(description=info["description"], provider=_provider(info["description"]), answer=info["answer"])
            if os.getenv("DEFIRISK_OFFLINE") != "1":  # cached eth_call results would give a misleading age
                row["updated_age_s"] = max(0, int(time.time()) - info["updated_at"])
        q["feed_details"].append(row)
    q["providers"] = sorted({r["provider"] for r in q["feed_details"] if r.get("provider")})
    q["unreadable_feeds"] = [r["address"] for r in q["feed_details"] if not r["readable"]]
    info = infos[0] if infos else None
    if info:
        q["description"] = info["description"]
        q["provider"] = _provider(info["description"])
        q["reads_pendle"] = any("pendle" in (i or {}).get("description", "").lower() for i in infos)
        ages = [r["updated_age_s"] for r in q["feed_details"] if r.get("updated_age_s") is not None]
        if ages:
            q["updated_age_s"] = max(ages)  # the stalest input bounds the oracle's freshness
            q["computed_on_read"] = all(a < 300 for a in ages)
        if pt_price_usd and market["loanAsset"]["symbol"].upper() in STABLES and info["answer"] > 0 and len(feeds) == 1:
            q["deviation_vs_pendle_pct"] = (info["answer"] - pt_price_usd) / pt_price_usd * 100
    return q


def _quality_multiplier(q: dict) -> tuple[float, list[str]]:
    mult, notes = 1.0, []
    if q["single_feed"]:
        mult *= 1.5; notes.append("single price feed x1.5")
    if q["computed_on_read"]:
        mult *= 1.5; notes.append("feed is computed on read (no heartbeat/staleness guard) x1.5")
    if q.get("unreadable_feeds"):
        mult *= 1.5; notes.append(f"{len(q['unreadable_feeds'])} oracle input(s) unreadable on-chain x1.5")
    dev = q["deviation_vs_pendle_pct"]
    if dev is not None and abs(dev) > 2:
        mult *= 1.5; notes.append(f"feed deviates {dev:+.1f}% from Pendle PT price x1.5")
    return mult, notes


def _pendle_details(rows: list[dict], by_pt: dict) -> dict:
    """marketId -> Pendle market detail (has 'protocol', 'accountingAsset'; the active-markets list does not)."""
    out, seen = {}, {}
    for m in rows:
        addr = by_pt[m["collateralAsset"]["address"].lower()]["address"].lower()
        if addr not in seen:
            try:
                seen[addr] = sources.pendle_market(addr)
            except Exception:
                seen[addr] = None
        out[m["marketId"]] = seen[addr]
    return out


def _concentration(morpho: list[dict], by_pt: dict, ours: dict, quality: dict, details: dict | None = None) -> list[dict]:
    """How much of the Morpho PT lending book shares each of our dependencies (hidden concentration)."""
    rows = morpho[:12]
    details = _pendle_details(rows, by_pt) if details is None else details
    total = sum(m["state"]["supplyAssetsUsd"] or 0 for m in rows) or 1
    providers = {}
    for m in rows:
        feeds = _feed_addresses(m)
        info = sources.read_feed(feeds[0]) if feeds else None
        providers[m["marketId"]] = _provider(info["description"]) if info else "unknown"

    def issuer(m):  # the active-markets list has no 'protocol': use the market detail, then the Pendle market name
        d = details.get(m["marketId"]) or {}
        return d.get("protocol") or by_pt[m["collateralAsset"]["address"].lower()].get("name") \
            or m["collateralAsset"]["symbol"].split("-")[1]

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


def _portfolio_lookthrough(morpho: list[dict], ours: dict, details: dict) -> tuple[dict | None, dict]:
    """Look-through of every top Morpho PT market -> (shared exposure across them, {pendle address: Lineage})."""
    lins, markets = {}, []
    for m in morpho[:12]:
        d = details.get(m["marketId"])
        if not d:
            continue
        key = d["address"].lower()
        try:
            if key not in lins:
                lins[key] = lineage.trace_pendle(d)
            lt = exposure.lookthrough(lins[key])
        except Exception:
            continue
        markets.append({"label": f"{m['collateralAsset']['symbol']} / {m['loanAsset']['symbol']}",
                        "supply_usd": m["state"]["supplyAssetsUsd"] or 0, "lookthrough": lt,
                        "is_mine": m["marketId"] == ours["marketId"]})
    return (exposure.shared_exposure(markets) if markets else None), lins


def _lookthrough_rows(shared: dict | None, nodes: list[Node]) -> list[dict]:
    """Concentration rows for shared tokens / base assets that our position also reaches (look-through)."""
    if not shared:
        return []
    by_tok = {n.meta["token_id"]: n.id for n in nodes if n.meta.get("token_id")}
    out = []
    for r in shared["rows"]:
        if not r["in_position"]:
            continue
        out.append({"node": by_tok.get(r["id"]), "kind": "lookthrough",
                    "label": f"Look-through: {r['symbol']}", "markets": r["markets"], "of_markets": shared["markets"],
                    "supply_usd": r["supply_usd"], "share_pct": r["share_pct"], "size_known": r["unsized_markets"] == 0,
                    "routes": r["routes"], "sentence": r["sentence"]})
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


BOOK_SIZE = 10


def _book_markets(morpho: list[dict], by_pt: dict, details: dict, ours: dict, rates: dict, protocols: list[dict],
                  stable_prior, H: int, sev: dict | None, morpho_llama, pendle_llama) -> list[dict]:
    """Real pockets for the book view: the largest listed Morpho markets taking a Pendle PT as collateral (ours first),
    each with its PRINCIPAL dependencies (collateral without debt) under shared keys, so a dependency common to several
    pockets is one key: chain, Morpho Blue singleton, Pendle PT/SY contracts, underlying, issuer, backing stablecoin.
    Same priors as the main graph (DefiLlama base rate x modifiers, calibrated severity, stablecoin history)."""
    lgf_hack = sev["mean"] if sev else None
    p_chain, why_chain = priors.p_chain(H)
    p_morpho, why_morpho = priors.p_protocol(rates, morpho_llama, H, share=0.5)
    p_pendle, why_pendle = priors.p_protocol(rates, pendle_llama, H, share=0.5)
    rows = [ours] + [m for m in morpho if m["marketId"] != ours["marketId"]]
    out, seen = [], set()
    for m in rows:
        d = details.get(m["marketId"])
        if not d or m["marketId"] in seen:
            continue
        seen.add(m["marketId"])
        pa = by_pt.get(m["collateralAsset"]["address"].lower()) or {}
        und, acc = d["underlyingAsset"], d["accountingAsset"]
        issuer_name = d.get("protocol") or und["symbol"]
        ill = sources.llama_find_protocol(issuer_name, protocols) or sources.llama_find_protocol(und["symbol"], protocols)
        has_backing = acc["address"].lower() != und["address"].lower()
        backing_stable = has_backing and acc["symbol"].upper() in STABLES
        u_share = 0.25 if has_backing and not backing_stable else 0.5
        p_iss, why_iss = priors.p_protocol(rates, ill, H, share=0.5)
        p_und, why_und = priors.p_protocol(rates, ill, H, share=u_share)

        def dep(key, label, p, why, role, T, lgf=None, node_id=None):
            lg = lgf if lgf is not None else (lgf_hack if (lgf_hack and role in priors.HACK_ROLES) else priors.LGF.get(role, 0.5))
            return {"key": key, "label": label, "role": role, "p_fail": p, "lgf": lg, "transmission": T, "source": why,
                    "node_id": node_id}

        deps = [dep("chain:ethereum", "Ethereum", p_chain, why_chain, "chain", 1.0, node_id="chain"),
                dep("morpho_blue", "Morpho Blue (protocol)", p_morpho, why_morpho, "morpho_blue", 1.0, node_id="morpho"),
                dep(f"pendle_core:{d['address'].lower()}", f"Pendle PT / SY contracts ({d['pt']['symbol']})", p_pendle,
                    why_pendle, "pendle_core", 1.0, node_id="pendle_core"),
                dep(f"underlying:{und['address'].lower()}", f"{und['symbol']} (yield source)", p_und, why_und, "underlying",
                    0.9, node_id="underlying"),
                dep(f"issuer:{_slug(issuer_name)}", f"{issuer_name} (issuer)", p_iss, why_iss, "issuer", 0.72,
                    node_id="issuer")]
        if backing_stable:
            p_s, lgf_s, why_s = stable_prior(acc["symbol"])
            deps.append(dep(f"stable:{acc['symbol'].upper()}", f"{acc['symbol']} (stablecoin)", p_s, why_s, "stablecoin",
                            0.72, lgf=lgf_s, node_id=f"usd_{acc['symbol'].lower()}"))
        elif has_backing:
            p_b, why_b = priors.p_protocol(rates, ill, H, share=0.25)
            deps.append(dep(f"backing:{acc['address'].lower()}", f"{acc['symbol']} (backing asset)", p_b, why_b, "backing",
                            0.72, node_id="backing"))
        pt = d["pt"]
        out.append({"market_id": m["marketId"], "label": f"{pt['symbol']} / {m['loanAsset']['symbol']}",
                    "is_mine": m["marketId"] == ours["marketId"], "pendle_market": d["address"], "expiry": d.get("expiry"),
                    "loan_symbol": m["loanAsset"]["symbol"], "loan_address": m["loanAsset"]["address"],
                    "morpho_supply_usd": m["state"].get("supplyAssetsUsd"),
                    "pool_liquidity_usd": (pa.get("details") or {}).get("liquidity"),
                    "implied_apy": (pa.get("details") or {}).get("impliedApy"),
                    "exit_route": {"pt": pt["address"], "pt_decimals": pt.get("decimals", 18),
                                   "pt_price_usd": (pt.get("price") or {}).get("usd"), "out": m["loanAsset"]["address"],
                                   "out_symbol": m["loanAsset"]["symbol"], "chain_id": 1},
                    "dependencies": deps})
        if len(out) >= BOOK_SIZE:
            break
    return out


def _attach_lineage(nodes: list[Node], edges: list[Edge], lin, lt: dict, pegs: dict, node) -> None:
    """Add the lineage tokens below the existing underlying/backing nodes (existing nodes are reused by address)."""
    by_addr = {str(n.meta.get("address", "")).lower(): n.id for n in nodes if n.meta.get("address")}
    pct = {r["id"]: r for r in lt["tokens"]} | {r["id"]: r for r in lt["base_assets"]}
    skip = {lin.root} | {e["child"] for e in lin.edges if e["parent"] == lin.root}  # PT and SY = the Pendle market node
    ids: dict[str, str] = {}
    by_id = {n.id: n for n in nodes}

    def nid(tid):
        if tid in ids:
            return ids[tid]
        t = lin.tokens[tid]
        if tid in by_addr:
            ids[tid] = by_addr[tid]
            by_id[ids[tid]].meta.setdefault("token_id", tid)
            r = pct.get(tid) or {}
            by_id[ids[tid]].meta.setdefault("lookthrough_pct", r.get("pct"))
            by_id[ids[tid]].meta.setdefault("lookthrough_routes", r.get("routes"))
            return ids[tid]
        base = tid.startswith("base:")
        new = ("base_" if base else "lin_") + _slug(tid[5:] if base else t["symbol"])
        while new in by_id:
            new += "_"
        stable = base or lineage.is_stable_like(t)
        lg = 0.3 if stable else 0.5
        r = pct.get(tid) or {}
        n = node(new, "yield_source", f"{t['symbol']} (base asset)" if base else f"{t['symbol']} (backing token)", 0.0,
                 "look-through only: discovered by token lineage; p_fail 0 because its risk is already carried by the "
                 "parent token's prior (no double counting)", "base_asset" if base else "lineage_token", lgf=lg,
                 lgf_why=f"what-if severity only ({lg:.0%}) for shocking this look-through node",
                 token_type=t["type"], token_id=tid, lookthrough_pct=r.get("pct"), lookthrough_routes=r.get("routes"),
                 **({"address": tid} if tid.startswith("0x") else {}),
                 **({k: t[k] for k in ("issuer", "note", "rate") if t.get(k) is not None}))
        nodes.append(n)
        by_id[new] = n
        ids[tid] = new
        return new

    for e in lin.edges:
        if e["parent"] in skip:
            continue
        p, c = nid(e["parent"]), nid(e["child"])
        ln = by_id[c].meta.setdefault("lineage", [])
        info = {"parent": by_id[p].label, "parent_id": p, "weight": e["weight"], "source": e["source"],
                "source_url": e.get("source_url"), "as_of": e["as_of"], "confidence": e["confidence"], "via": e["via"]}
        if info not in ln:
            ln.append(info)
        if e.get("cycle"):
            by_id[c].meta["cycle"] = True
        if not any(x.src == p and x.dst == c for x in edges):
            w = e["weight"]
            edges.append(Edge(p, c, w if w is not None else 0.5,
                              (e["via"] or f"backed by {lin.tokens[e['child']]['symbol']}")
                              + (f" (share {w:.0%})" if w is not None else
                                 " (share unknown: 0.5 used for the what-if animation only, not a data point)")))
    for tid, stats in pegs.items():
        if tid in skip:
            continue
        if tid in ids or tid in by_addr:
            by_id[nid(tid)].meta["peg"] = stats


# ---------------------------------------------------------------------------
def discover_real(ref: str, value_usd: float, horizon_days: int) -> DepGraph:
    chain_id = 1
    _check_ref(ref, chain_id)
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

    sev = priors.hack_severity()

    def node(nid, layer, label, p, why, role, lgf=None, lgf_why=None, **meta):
        band = None
        if lgf is None and sev and role in priors.HACK_ROLES:
            lgf, band = sev["mean"], {"low": sev["low"], "high": sev["high"], "p90": sev["p90"]}
            lgf_why = sev["source"] + (f"; {lgf_why}" if lgf_why else "")
        lg = priors.LGF.get(role, 0.5) if lgf is None else lgf
        return Node(nid, layer, label, round(p, 6), round(lg, 4),
                    {"role": role, "source": why, "chain": "ethereum",
                     "lgf_source": lgf_why or f"structural assumption: loss-given-failure {lg:.0%} for role '{role}' (priors.LGF)",
                     **({"lgf_band": band} if band else {}), **meta})

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
        hist.setdefault("dep", {})[sym] = dep
        return priors.p_stablecoin(dep, H, sym)

    nodes: list[Node] = [Node("pos", "protocol", "Position", 0.0, 0.0, {"role": "position"})]
    edges: list[Edge] = []

    def stable_node(sym, address):
        nid = f"usd_{sym.lower()}"
        if not any(n.id == nid for n in nodes):
            p, lgf, why = stable_prior(sym)
            dep = (hist.get("dep") or {}).get(sym)
            nodes.append(node(nid, "yield_source", f"{sym} (stablecoin)", p, why, "stablecoin", lgf=lgf,
                              lgf_why=(f"measured: mean depth of past {sym} depegs (DefiLlama prices)" if lgf else None),
                              address=address,
                              depeg_stats={k: dep[k] for k in ("episodes", "years", "severity", "min_price")} if dep else None))
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

    p, why = priors.p_protocol(rates, pendle_llama, H, share=0.5)
    nodes.append(node("pendle_core", "amm", f"Pendle PT / SY contracts ({pt_sym})", p,
                      why + "; x0.5 = PT/SY contract share of Pendle risk (rest on the AMM pool)", "pendle_core",
                      address=pend["pt"]["address"], sy=(pend.get("sy") or {}).get("address"), expiry=pend["expiry"],
                      url=f"https://app.pendle.finance/trade/markets/{pm['address']}/swap?view=pt&chain=ethereum"))
    p, why = priors.p_protocol(rates, pendle_llama, H, share=0.5)
    nodes.append(node("amm", "amm", f"Pendle AMM pool {pt_sym}", p, why + "; x0.5 = AMM-pool share of Pendle risk", "amm",
                      lgf_why="exit channel: an AMM failure changes the cost / timing of selling before maturity, not the "
                              "PT's redemption value; priced on the exit side (stressed exit liquidity)",
                      address=pm["address"],
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
                      feeds=q["feed_details"], providers=q["providers"], oracle_vaults=q["vaults"],
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

    def E(s, d, t, r, channel="principal"):
        edges.append(Edge(s, d, t, r, channel))

    E("pos", "pendle_core", 1.0, f"holds {pt_sym}: redeems at maturity through Pendle's PT/SY contracts")
    E("pos", "amm", 1.0, f"sells {pt_sym} before maturity through the Pendle AMM (exit route)", "exit")
    E("pos", "morpho", 1.0, f"the {pt_sym} collateral is held by the Morpho Blue singleton contract")
    E("pos", "lending", 1.0, f"{pt_sym} posted as collateral on this market: its oracle and parameters act through the "
                             f"debt (liquidation); without debt, market losses fall on lenders and borrowers", "debt")
    E("pendle_core", "underlying", 0.9, f"SY wraps {underlying['symbol']}")
    E("amm", "pendle_core", 1.0, "the pool trades the PT")
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
    for src in ("pendle_core", "amm", "lending"):
        E(src, "chain", 1.0, "settles on Ethereum")

    # recursive token lineage + look-through (never fatal: the base graph stands on its own)
    details = _pendle_details(morpho_all[:12], by_pt)
    details[mm["marketId"]] = pend
    try:
        book_markets = _book_markets(morpho_all, by_pt, details, mm, rates, protocols, stable_prior, H, sev,
                                     morpho_llama, pendle_llama)
    except Exception as e:  # the book is a view on top of the analysis: never fatal
        book_markets = {"error": f"{type(e).__name__}: {e}"[:300]}
    shared, lins, lt, lin_err = None, {}, None, None
    try:
        shared, lins = _portfolio_lookthrough(morpho_all, mm, details)
        lin = lins.get(pm["address"].lower()) or lineage.trace_pendle(pend)
        lt = exposure.lookthrough(lin)
        try:
            pegs = peg.annotate(lin)
        except Exception:
            pegs = {}
        _attach_lineage(nodes, edges, lin, lt, pegs, node)
    except Exception as e:
        lin_err = f"{type(e).__name__}: {e}"[:300]

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
    block_ts, ref_rates = None, None
    if block:
        try:
            b = sources.eth_block(block)
            block_ts = b and b["timestamp"]
        except Exception:
            pass
        try:  # reference rate for the carry (USDC supply APY on the same Morpho market), non-fatal
            from ..morpho import market_rates
            ref_rates = market_rates(mm["marketId"], block)
        except Exception as e:
            ref_rates = {"error": f"{type(e).__name__}: {e}"[:200]}
    route =  {"pt": pend["pt"]["address"], "pt_decimals": pend["pt"].get("decimals", 18), "pt_price_usd": pt_price,
             "out": mm["loanAsset"]["address"], "out_symbol": loan_sym, "chain_id": chain_id}
    pos = Position("pos", f"{pt_sym} on Morpho ({loan_sym})", "ethereum", value_usd, H, {
        "exit_pool_liquidity_usd": liq, "ref": ref, "real": True, "pendle_market": pm["address"],
        "exposure_role": "collateral_only",
        "morpho_market": mm["marketId"], "observed_at": http.now(), "block_number": block, "block_timestamp": block_ts,
        "reference_rates": ref_rates,
        "concentration": _concentration(morpho_all, by_pt, mm, q, details) + _lookthrough_rows(shared, nodes),
        "lookthrough": lt and {k: lt[k] for k in ("root", "tokens", "base_assets", "cycles")},
        "coverage": lt and lt["coverage"],
        "shared_exposure": shared,
        "book_markets": book_markets,
        **({"lineage_error": lin_err} if lin_err else {}),
        "data_sources": ["Pendle API v1/v2 + SDK convert (exit quote)", "Morpho Blue GraphQL", "DefiLlama /hacks /protocols",
                         "DefiLlama stablecoin prices", "Ethereum JSON-RPC (eth_call, eth_gasPrice, eth_blockNumber)",
                         "ERC-4626 asset()/convertToAssets (token lineage)", "data/registry.json (issuer reserves, sourced)",
                         "DefiLlama coins chart (peg/basis)"],
        "prior_method": rates["source"],
        "prior_upper_annual": rates.get("annual_per_protocol_upper"),
        "prior_central_annual": rates.get("annual_per_protocol"),
        "exit_route": route,
    })
    g = DepGraph(pos, nodes, edges)
    if os.environ.get("DEFIRISK_NO_QUOTE") != "1":
        from ..core.decision import quote_exit
        try:
            pos.meta["exit_quote"] = quote_exit(route, value_usd)
        except Exception as e:  # recorded, decision falls back to the flagged approximation
            pos.meta["exit_quote_error"] = f"{type(e).__name__}: {e}"[:300]
    return g
