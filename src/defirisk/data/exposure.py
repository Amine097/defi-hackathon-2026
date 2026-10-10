"""Look-through exposure (spec §6, §11): what share of a position ends up in each token / base asset, and how much
of it we could NOT trace. Weights multiply along a path and add across paths (capped at 100%); an edge with an
unknown weight sends the untraced share of its parent to UNKNOWN with a reason."""
from __future__ import annotations

from .lineage import BASES, Lineage

ORANGE, RED = 0.20, 0.40
PENDLE_TYPES = ("pendle_pt", "pendle_sy")


def lookthrough(lin: Lineage) -> dict:
    tok = lin.tokens
    exp: dict[str, float] = {}
    reached: dict[str, list[str]] = {}
    routes: dict[str, list[list[str]]] = {}
    unknown: list[dict] = []

    def walk(tid: str, amount: float, path: list[str], depth: int = 0):
        exp[tid] = exp.get(tid, 0.0) + amount
        routes.setdefault(tid, []).append(path)
        kids = [e for e in lin.children(tid) if not e.get("cycle")]
        if tid.startswith("base:"):
            return
        if not kids or depth > 12:
            unknown.append({"token": tok[tid]["symbol"], "share": amount,
                            "reason": tok[tid].get("note") or f"no on-chain or registry breakdown of {tok[tid]['symbol']}"})
            return
        known = [e for e in kids if e["weight"] is not None]
        unk = [e for e in kids if e["weight"] is None]
        s = min(1.0, sum(e["weight"] for e in known))
        for e in known:
            walk(e["child"], amount * e["weight"] / max(s, 1.0), path + [e["child"]], depth + 1)
        if s < 1.0 - 1e-9:
            names = ", ".join(tok[e["child"]]["symbol"] for e in unk)
            reason = (f"{tok[tid]['symbol']} is backed partly by {names} but the split is not published"
                      if unk else f"{tok[tid]['symbol']}: {1 - s:.0%} of its backing is not described")
            if tok[tid].get("note") and not known:
                reason += f" ({tok[tid]['note']})"
            unknown.append({"token": tok[tid]["symbol"], "share": amount * (1 - s), "reason": reason,
                            "reaches": [tok[e["child"]]["symbol"] for e in unk]})
            for e in unk:  # dependency exists, size unknown
                reached.setdefault(e["child"], []).append(tok[tid]["symbol"])
                routes.setdefault(e["child"], []).append(path + [e["child"]])
                _mark(lin, e["child"], reached, routes, path + [e["child"]])

    walk(lin.root, 1.0, [lin.root])
    unknown_share = min(1.0, sum(u["share"] for u in unknown))
    bases = {b: min(1.0, v) for b, v in exp.items() if b.startswith("base:")}
    traced = min(1.0, sum(bases.values()))

    def row(tid):
        t = tok[tid]
        pct = min(1.0, exp[tid]) if tid in exp else None
        return {"id": tid, "symbol": t["symbol"], "type": t["type"], "pct": pct, "size_known": pct is not None,
                "routes": [" → ".join(tok[x]["symbol"] for x in r) for r in routes.get(tid, [])][:4]}

    tokens = [row(t) for t in tok if t != lin.root and not t.startswith("base:")]
    tokens.sort(key=lambda r: (-(r["pct"] or 0), r["symbol"]))
    base_rows = [{"id": b, "label": BASES.get(b, b), "pct": bases.get(b), "size_known": b in bases}
                 for b in tok if b.startswith("base:")]
    if unknown_share > 1e-9:
        base_rows.append({"id": "base:UNKNOWN", "label": BASES["base:UNKNOWN"], "pct": unknown_share, "size_known": True})
    base_rows.sort(key=lambda r: -(r["pct"] or 0))
    sev = "RED" if unknown_share >= RED - 1e-9 else "ORANGE" if unknown_share >= ORANGE - 1e-9 else "GREEN"
    root_sym = tok[lin.root]["symbol"]
    if unknown_share < 1e-9:
        summary = f"100% of {root_sym} is traced down to base assets."
    else:
        why = "; ".join(sorted({u["reason"] for u in unknown}))
        summary = (f"{traced:.0%} of {root_sym} is traced to base assets. {unknown_share:.0%} is unknown: {why}.")
    return {"root": root_sym, "tokens": tokens, "base_assets": base_rows,
            "coverage": {"traced_pct": traced, "unknown_pct": unknown_share, "severity": sev, "summary": summary,
                         "unknown_reasons": [{**u, "share": round(u["share"], 6)} for u in unknown]},
            "cycles": lin.cycles}


def _mark(lin, tid, reached, routes, path, depth=0):
    if depth > 12:
        return
    for e in lin.children(tid):
        if e.get("cycle"):
            continue
        reached.setdefault(e["child"], []).append(lin.tokens[tid]["symbol"])
        routes.setdefault(e["child"], []).append(path + [e["child"]])
        _mark(lin, e["child"], reached, routes, path + [e["child"]], depth + 1)


def shared_exposure(markets: list[dict], top: int = 8) -> dict:
    """markets: [{'label', 'supply_usd', 'lookthrough': lookthrough(...) result}]. Portfolio view across lending
    markets: which tokens / base assets many markets reach, through which PTs, and how much supply sits on top."""
    total = sum(m["supply_usd"] or 0 for m in markets) or 1.0
    agg: dict[str, dict] = {}
    for m in markets:
        lt = m["lookthrough"]
        items = [(r["id"], r["symbol"], r["pct"], r["routes"], r["type"]) for r in lt["tokens"]] + \
                [(r["id"], r["label"], r["pct"], [], "base") for r in lt["base_assets"]]
        for tid, sym, pct, rts, typ in items:
            a = agg.setdefault(tid, {"id": tid, "symbol": sym, "type": typ, "markets": 0, "supply_usd": 0.0,
                                     "unsized_markets": 0, "routes": [], "is_base": tid.startswith("base:"),
                                     "in_position": False})
            a["markets"] += 1
            if pct is None:
                a["unsized_markets"] += 1
            else:
                a["supply_usd"] += (m["supply_usd"] or 0) * pct
            route = rts[0] if rts else f"{lt['root']} → … → {sym}"
            a["routes"].append({"market": m["label"], "route": route, "pct": pct})
            if m.get("is_mine"):
                a["in_position"] = True
    rows = [a for a in agg.values() if a["markets"] >= 2 and a["id"] != "base:UNKNOWN" and a["type"] not in PENDLE_TYPES]
    for a in rows:
        a["share_pct"] = a["supply_usd"] / total * 100
        pts = len({r["route"].split(" → ")[0] for r in a["routes"]})
        a["distinct_pts"] = pts
        size = (f"~{a['share_pct']:.0f}% of supply" if a["unsized_markets"] < a["markets"] else "share of supply unknown")
        via = "the same PT" if pts == 1 else f"{pts} different PTs"
        a["sentence"] = (f"{a['markets']} of {len(markets)} Morpho PT markets reach {a['symbol']} through {via} ({size}"
                         + (f"; {a['unsized_markets']} with unknown size" if 0 < a["unsized_markets"] < a["markets"] else "")
                         + ").")
    rows.sort(key=lambda a: (-a["in_position"], -a["supply_usd"], -a["markets"]))
    unk = sum((m["supply_usd"] or 0) * next((r["pct"] for r in m["lookthrough"]["base_assets"] if r["id"] == "base:UNKNOWN"), 0)
              for m in markets)
    return {"markets": len(markets), "total_supply_usd": total, "rows": rows[:top],
            "unknown_supply_pct": unk / total * 100,
            "markets_detail": [{"label": m["label"], "supply_usd": m["supply_usd"],
                                "traced_pct": m["lookthrough"]["coverage"]["traced_pct"]} for m in markets]}
