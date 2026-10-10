"""JSON payload for the web UI (used by api/analyze.py). Keep it pure so it can be tested."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from . import http
from .cli import run
from .decision import decide, exit_cost_for
from .portfolio import Pocket, evaluate_book
from .propagation import best_paths, simulate
from .scenarios import SCENARIOS, apply, resolve, shock

GLOBAL_ASSUMPTIONS = [
    "Dependencies fail independently; expected loss = exact closed form 1 - prod(1 - p_i x LGF_i x T_i); "
    "VaR95 from a Monte Carlo (20,000 draws, seed 0); correlation only via shared nodes in the graph.",
    "Loss reaching the position = loss-given-failure x best path transmission; edge transmissions are expert weights.",
    "Failure priors: DefiLlama hack history restricted to the protocol cohort (TVL >= $10M), adjusted by audits/TVL/age; "
    "stablecoins use their own DefiLlama price history (depeg = price < $0.98).",
    "Position size is an input (default $1M) on a real, live market; the position is collateral only (no debt / LTV modelled).",
    "Scenario losses are CONDITIONAL on the shock happening (p = 1); the baseline STAY loss is probability-weighted.",
    "Stressed exit: slippage scales with 1 / liquidity factor (liquidity crisis = liquidity x0.5).",
    "Exit proceeds are assumed redeployed at a similar yield: the PT carry forgone by exiting is not counted as a cost.",
]


def _sensitivity(g, sim, d, ex, upper_ratio):
    rows = []
    mults = [0.5, 2.0] + ([round(upper_ratio, 2)] if upper_ratio and upper_ratio > 1 else [])
    for k in sorted(set(mults)):
        g2 = deepcopy(g)
        for n in g2.nodes:
            n.p_fail = min(1.0, n.p_fail * k)
        s2 = simulate(g2)
        rows.append({"p_fail_multiplier": k, "expected_loss_usd": s2.expected_loss_usd,
                     "verdict": "EXIT" if s2.expected_loss_usd > ex["usd"] else "STAY"})
    return {"rows": rows, "breakeven_risk_multiplier": d.breakeven_risk_multiplier,
            "note": "All failure probabilities scaled together; exit cost unchanged. "
                    "Upper multiplier = all-incident base rate / cohort base rate."}


def _stress_table(g, ex):
    paths = best_paths(g)
    rows = []
    for n in g.nodes:
        if n.id == g.position.id or n.id not in paths:
            continue
        sim = simulate(apply(g, shock(g, n.id)))
        t, path = paths[n.id]
        rows.append({"id": n.id, "label": n.label, "severity": n.loss_given_failure, "transmission": t, "path": path,
                     "hops": len(path) - 1, "direct": len(path) == 2, "conditional_loss_usd": sim.expected_loss_usd,
                     "verdict_if_shocked": "EXIT" if sim.expected_loss_usd > ex["usd"] else "STAY"})
    return sorted(rows, key=lambda r: -r["conditional_loss_usd"])


def _assumptions(g):
    out = list(GLOBAL_ASSUMPTIONS)
    for n in g.nodes:
        src = n.meta.get("source", "")
        if "assumption" in src or "unknown" in src:
            out.append(f"{n.label}: {src}")
        lgf = n.meta.get("lgf_source", "")
        if lgf.startswith("structural assumption"):
            out.append(f"{n.label}: {lgf}")
    return out


def build_payload(ref: str = "mock", use_mock: bool = True, book_usd: float = 10_000_000, value_usd: float = 1_000_000,
                  shock_node: str | None = None, severity: float | None = None) -> dict:
    http.reset_provenance()
    g, sim, d = run(ref, use_mock, value_usd)
    ex = exit_cost_for(g)
    scenarios = []
    for s in SCENARIOS:
        g2 = apply(g, s)
        ex2 = exit_cost_for(g, None, s.exit_liquidity_factor)
        d2 = decide(g2, simulate(g2), ex2, loss_type="conditional")
        scenarios.append({"name": s.name, "description": s.description, "overrides": resolve(g, s),
                          "loss_type": "conditional_on_shock", "conditional_loss_usd": d2.expected_loss_usd,
                          "expected_loss_usd": d2.expected_loss_usd,  # legacy key; same conditional value
                          "exit": ex2, "exit_cost_usd": ex2["usd"], "verdict": d2.verdict, "explanation": d2.explanation})
    custom = None
    if shock_node:
        try:
            s = shock(g, shock_node, severity)
        except ValueError as e:
            s, custom = None, {"node": shock_node, "error": str(e)}
    if shock_node and custom is None:
        g2 = apply(g, s)
        d2 = decide(g2, simulate(g2), ex, loss_type="conditional")
        custom = {"name": s.name, "description": s.description, "node": shock_node, "severity": s.overrides[shock_node]["loss_given_failure"],
                  "loss_type": "conditional_on_shock", "conditional_loss_usd": d2.expected_loss_usd,
                  "exit_cost_usd": ex["usd"], "verdict": d2.verdict, "explanation": d2.explanation}

    pocket_g = deepcopy(g)
    pocket_value = book_usd * 0.1
    pq = exit_cost_for(pocket_g, pocket_value)
    if pq.get("method") == "pendle_sdk_quote":
        pocket_g.position.meta["exit_quote"] = pq
    pockets = [Pocket(f"P{i}", 0.1, deepcopy(pocket_g)) for i in range(10)]
    book = evaluate_book(pockets, book_usd, SCENARIOS[0], affected={"P0"})
    hit = next(p for p in book.pockets if p.affected)
    prov = http.provenance()
    return {
        "position": asdict(g.position),
        "nodes": [asdict(n) for n in g.nodes],
        "edges": [asdict(e) for e in g.edges],
        "node_contrib_usd": sim.node_contrib,
        "var95_usd": sim.var95_usd,
        "mc_mean_usd": sim.mc_mean_usd,
        "decision": asdict(d),
        "exit": ex,
        "scenarios": scenarios,
        "custom_shock": custom,
        "stress_table": _stress_table(g, ex),
        "sensitivity": _sensitivity(g, sim, d, ex, (g.position.meta.get("prior_upper_annual") or 0) /
                                    (g.position.meta.get("prior_central_annual") or float("inf"))),
        "assumptions": _assumptions(g),
        "provenance": prov,
        "source": "mock" if use_mock else prov["mode"],
        "data_as_of": g.position.meta.get("observed_at") if prov["mode"] == "live" else prov["oldest_cache_ts"],
        "book": {"scenario": book.scenario, "affected": ["P0"], "book_usd": book_usd,
                 "pockets": [asdict(p) for p in book.pockets],
                 "total_stay_loss_usd": book.total_stay_loss_usd,
                 "total_optimal_usd": book.total_optimal_usd, "pct_of_book": book.pct_of_book,
                 "hit_pocket_exit_cost_pct_of_pocket": hit.exit_cost_usd / hit.value_usd,
                 "hit_pocket_exit_cost_pct_of_book": hit.exit_cost_usd / book_usd},
    }
