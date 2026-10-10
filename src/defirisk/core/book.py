"""Real book (brief: "a book split across ten pockets of 10% each; one pocket is affected; unwinding it costs 11%").

Pockets are real positions (discovery: the largest Morpho markets taking a Pendle PT as collateral), each with its
principal dependencies under SHARED keys, so one incident can hit several pockets at once (same underlying, same
issuer, same backing stablecoin, Morpho Blue, Pendle, the chain). For each pocket:

  stay loss  = conditional on the shock if the pocket depends on the shocked key, else probability-weighted
               (V (1 - prod(1 - p_k LGF_k T_k)), the same formula as the main graph)
  exit side  = execution cost (given % if the user sets one, e.g. the brief's 11%; else an executable Pendle quote,
               stressed by the scenario's liquidity factor for affected pockets) + excess carry forgone
  verdict    = EXIT if stay loss > exit side, else STAY

The analysed position's pocket is computed on its full dependency graph (same numbers as the headline). The shared
dependency table shows, for every key, how much of the book depends on it and what the book loses if it fails.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from .decision import approx_exit_cost, exit_cost_for, quote_exit
from .models import DepGraph
from .propagation import simulate
from .scenarios import Scenario, apply

DEFAULT_SEVERITY = 0.3  # the brief's "affected" pocket: underlying loses 30% (same hypothesis as the Underlying depeg scenario)


def _light_loss(V: float, deps: list[dict], shock_key: str | None = None, severity: float | None = None) -> float:
    surv = 1.0
    for d in deps:
        p, lgf = d["p_fail"], d["lgf"]
        if shock_key and d["key"] == shock_key:
            p, lgf = 1.0, d["lgf"] if severity is None else severity
        surv *= 1 - p * lgf * d["transmission"]
    return V * (1 - surv)


def _exit(market: dict, g: DepGraph, V: float, lf: float, exit_cost_pct: float | None, quote: bool) -> dict:
    if exit_cost_pct is not None:
        return {"usd": V * exit_cost_pct, "method": "given", "basis": f"user-set exit cost {exit_cost_pct:.2%} of the pocket"}
    if market.get("is_mine"):
        ex = exit_cost_for(g, V, lf)
        return {"usd": ex["usd"], "method": ex["method"], "basis": ex.get("basis", ""), "quote_status": ex.get("quote_status")}
    route = market.get("exit_route") or {}
    err = "quotes disabled" if not quote else "no PT price"
    if quote and route.get("pt_price_usd"):
        try:
            q = quote_exit(route, V, simulate=False)
            slip = q["slippage_and_fees_usd"] / max(lf, 1e-6)
            return {"usd": slip + q["gas_usd"], "method": q["method"], "quote_status": q["quote_status"],
                    "basis": q["basis"] + (f"; STRESSED: slippage / {lf:g}" if lf != 1 else "")}
        except Exception as e:  # noqa: BLE001 - fall back to the flagged approximation
            err = f"{type(e).__name__}: {e}"[:160]
    liq = market.get("pool_liquidity_usd")
    if not liq:
        return {"usd": None, "method": "unknown", "basis": f"no quote ({err}) and no pool liquidity"}
    slip = approx_exit_cost(V, liq * lf, 0.0)
    return {"usd": slip + 15.0, "method": "approximation_constant_product", "quote_status": "approximation",
            "basis": f"APPROXIMATION value/(2 x liquidity + value), pool ${liq:,.0f} x{lf:g} ({err})"}


def evaluate(g: DepGraph, markets: list[dict], book_usd: float, *, weights: list[float] | None = None,
             exit_cost_pct: float | None = None, shock_key: str | None = None, severity: float | None = None,
             liquidity_factor: float = 1.0, reference_apy: float | None = None, quote: bool = True) -> dict:
    n = len(markets)
    if not n:
        raise ValueError("no pocket")
    w = weights or [1 / n] * n
    if len(w) != n or any(x < 0 for x in w) or abs(sum(w) - 1) > 1e-6:
        raise ValueError(f"weights must be {n} non-negative numbers summing to 1")
    H = g.position.horizon_days
    labels = {d["key"]: d["label"] for m in markets for d in m["dependencies"]}
    hits = [bool(shock_key) and any(d["key"] == shock_key and d["transmission"] > 0 for d in m["dependencies"])
            for m in markets]
    with ThreadPoolExecutor(max_workers=8) as pool:  # one executable quote per pocket: network-bound, run together
        exits = list(pool.map(lambda i: _exit(markets[i], g, book_usd * w[i], liquidity_factor if hits[i] else 1.0,
                                              exit_cost_pct, quote), range(n)))
    pockets, stay_total, optimal = [], 0.0, 0.0
    for m, wi, hit, ex in zip(markets, w, hits, exits):
        V = book_usd * wi
        deps = m["dependencies"]
        if m.get("is_mine"):
            g2 = deepcopy(g)
            g2.position.value_usd = V
            node_id = next((d["node_id"] for d in deps if d["key"] == shock_key), None) if hit else None
            if node_id and any(x.id == node_id for x in g2.nodes):
                sev = severity if severity is not None else next(x.loss_given_failure for x in g2.nodes if x.id == node_id)
                g2 = apply(g2, Scenario("book shock", "", {node_id: {"p_fail": 1.0, "loss_given_failure": sev}}))
            stay = simulate(g2).expected_loss_usd
        else:
            stay = _light_loss(V, deps, shock_key if hit else None, severity)
        imp = m.get("implied_apy")
        carry = V * (imp - reference_apy) * H / 365 if imp is not None and reference_apy is not None else 0.0
        exit_total = (ex["usd"] or 0.0) + carry
        verdict = "UNKNOWN" if ex["usd"] is None else ("EXIT" if stay > exit_total else "STAY")
        pockets.append({"label": m["label"], "market_id": m["market_id"], "pendle_market": m["pendle_market"],
                        "is_analysed_position": bool(m.get("is_mine")), "weight": wi, "value_usd": V, "affected": hit,
                        "stay_loss_usd": stay, "stay_loss_type": "conditional" if hit else "expected",
                        "exit_cost_usd": ex["usd"], "exit_method": ex["method"], "exit_basis": ex.get("basis"),
                        "quote_status": ex.get("quote_status"), "carry_usd": carry, "exit_total_usd": exit_total,
                        "verdict": verdict, "dependencies": [d["key"] for d in deps if d["transmission"] > 0]})
        stay_total += stay
        optimal += min(stay, exit_total) if ex["usd"] is not None else stay
    shared = []
    for key, label in labels.items():
        rows = [(p, d) for p, m in zip(pockets, markets) for d in m["dependencies"] if d["key"] == key and d["transmission"] > 0]
        exposed = sum(p["value_usd"] * d["transmission"] for p, d in rows)
        lgf = max(d["lgf"] for _, d in rows)
        shared.append({"key": key, "label": label, "pockets": [p["label"] for p, _ in rows], "n_pockets": len(rows),
                       "exposed_usd": exposed, "share_of_book": exposed / book_usd,
                       "loss_if_fails_usd": sum(p["value_usd"] * d["lgf"] * d["transmission"] for p, d in rows),
                       "loss_if_fails_pct_of_book": sum(p["value_usd"] * d["lgf"] * d["transmission"] for p, d in rows) / book_usd,
                       "loss_given_failure": lgf})
    shared.sort(key=lambda r: (-r["n_pockets"], -r["loss_if_fails_usd"]))
    hit_p = [p for p in pockets if p["affected"]]
    first = hit_p[0] if hit_p else None
    return {
        "mode": "real_book", "book_usd": book_usd, "n_pockets": n,
        "scenario": (f"{labels.get(shock_key, shock_key)} fails" + (f" (severity {severity:.0%})" if severity is not None else ""))
        if shock_key else "no shock (expected losses)",
        "shock": {"key": shock_key, "label": labels.get(shock_key), "severity": severity,
                  "liquidity_factor": liquidity_factor} if shock_key else None,
        "exit_cost_override_pct": exit_cost_pct, "affected": [p["label"] for p in hit_p],
        "pockets": pockets, "shared_dependencies": shared,
        "total_stay_loss_usd": stay_total, "total_optimal_usd": optimal, "pct_of_book": optimal / book_usd,
        "hit_pocket_exit_cost_pct_of_pocket": (first["exit_cost_usd"] or 0) / first["value_usd"] if first else None,
        "hit_pocket_exit_cost_pct_of_book": (first["exit_cost_usd"] or 0) / book_usd if first else None,
        "reference_apy": reference_apy,
        "assumptions": [
            "Pockets = the largest listed Morpho markets taking a Pendle PT as collateral (real, live); collateral "
            "without debt: only principal dependencies count (as in the main graph).",
            "Dependencies are keyed so that shared ones (underlying, issuer, backing stablecoin, Pendle, Morpho Blue, "
            "chain) are the same key across pockets: one incident hits every pocket that depends on it.",
            "Other pockets use the same priors and transmissions as the main graph's principal path (Pendle 1.0, "
            "underlying 0.9, issuer and backing 0.72); the analysed pocket uses its full graph.",
            "Carry forgone uses each pocket's PT implied APY minus one reference rate (the analysed market's loan-asset "
            "supply APY) for every pocket (assumption).",
        ],
    }
