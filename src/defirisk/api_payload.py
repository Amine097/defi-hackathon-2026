"""JSON payload for the web UI (used by api/analyze.py). Keep it pure so it can be tested."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from . import leverage, uncertainty
from .data import http
from .cli import run
from .core.decision import decide, exit_cost_for
from .core.portfolio import Pocket, evaluate_book
from .core.propagation import best_paths, simulate
from .core.scenarios import SCENARIOS, apply, resolve, shock

GLOBAL_ASSUMPTIONS = [
    "Central expected loss = V(1 - prod(1 - p_i x LGF_i x T_i)): exact ONLY under independent failures + best-path "
    "transmission; bracketed by dependence-free bounds [V max p_i h_i, V min(1, sum p_i h_i)] and a parameter band "
    "(decision.loss_band). VaR95 from a Monte Carlo (20,000 draws, seed 0). A correlated joint scenario is reported.",
    "Loss reaching the position = loss-given-failure x best path transmission; edge transmissions are expert weights.",
    "Failure priors: DefiLlama hack history restricted to the protocol cohort (TVL >= $10M), adjusted by audits/TVL/age; "
    "stablecoins use their own DefiLlama price history (depeg = price < $0.98).",
    "Position size is an input (default $1M) on a real, live market. Default mode = unlevered exposure (no debt, "
    "liquidation NOT_APPLICABLE); borrower=0x..|auto analyses a real Morpho borrower (debt, HF, liquidation) on-chain.",
    "Scenario losses are CONDITIONAL on the shock happening (p = 1); the baseline STAY loss is probability-weighted.",
    "Stressed exit: slippage scales with 1 / liquidity factor (liquidity crisis = liquidity x0.5).",
    "Exiting forgoes the PT excess carry: V x (PT implied APY - USDC supply APY on the same Morpho market) x H/365, "
    "added to the exit side with a +-50% band; if unknown it is excluded and confidence is downgraded. The same exit "
    "side (execution + carry) is used by the headline margin, break-even, scenarios, stress table, sensitivity and book.",
    "Verdict: EXIT if loss_low > exit_high, STAY if loss_high < exit_low, else REVIEW (lean = point comparison). "
    "Stale (quote > 60 s, chain state > 120 s), replayed or approximated inputs force REVIEW.",
]


def _carry_rate(d) -> float:
    """Excess carry forgone by exiting, as a fraction of position value over the horizon (0 if unknown)."""
    c = d.carry or {}
    return c["usd"] / d.value_usd if c.get("status") == "estimated" and d.value_usd else 0.0


def _with_carry(ex: dict, value_usd: float, rate: float) -> dict:
    """exit_cost_for() dict + carry forgone, so decide() compares loss against execution + carry (same basis as the
    headline verdict)."""
    return {**ex, "carry_usd": value_usd * rate, "total_usd": ex["usd"] + value_usd * rate}


def _sensitivity(g, sim, d, ex, upper_ratio):
    rows = []
    exit_side = ex.get("total_usd", ex["usd"])
    mults = [0.5, 2.0] + ([round(upper_ratio, 2)] if upper_ratio and upper_ratio > 1 else [])
    for k in sorted(set(mults)):
        g2 = deepcopy(g)
        for n in g2.nodes:
            n.p_fail = min(1.0, n.p_fail * k)
        s2 = simulate(g2)
        rows.append({"p_fail_multiplier": k, "expected_loss_usd": s2.expected_loss_usd, "exit_total_usd": exit_side,
                     "verdict": "EXIT" if s2.expected_loss_usd > exit_side else "STAY"})
    return {"rows": rows, "breakeven_risk_multiplier": d.breakeven_risk_multiplier,
            "note": "All failure probabilities scaled together; exit side (execution + carry forgone) unchanged. "
                    "Point comparison on central values (no bands). "
                    "Upper multiplier = all-incident base rate / cohort base rate."}


def _stress_table(g, ex):
    paths = best_paths(g)
    exit_side = ex.get("total_usd", ex["usd"])
    rows = []
    for n in g.nodes:
        if n.id == g.position.id or n.id not in paths:
            continue
        sim = simulate(apply(g, shock(g, n.id)))
        t, path = paths[n.id]
        rows.append({"id": n.id, "label": n.label, "severity": n.loss_given_failure, "transmission": t, "path": path,
                     "hops": len(path) - 1, "direct": len(path) == 2, "conditional_loss_usd": sim.expected_loss_usd,
                     "exit_total_usd": exit_side,
                     "verdict_if_shocked": "EXIT" if sim.expected_loss_usd > exit_side else "STAY"})
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
                  shock_node: str | None = None, severity: float | None = None, borrower: str | None = None) -> dict:
    http.reset_provenance()
    g, sim, d = run(ref, use_mock, value_usd)
    rate = _carry_rate(d)
    ex = _with_carry(exit_cost_for(g), g.position.value_usd, rate)
    scenarios = []
    for s in SCENARIOS:
        g2 = apply(g, s)
        ex2 = _with_carry(exit_cost_for(g, None, s.exit_liquidity_factor), g.position.value_usd, rate)
        d2 = decide(g2, simulate(g2), ex2, loss_type="conditional")
        scenarios.append({"name": s.name, "description": s.description, "overrides": resolve(g, s),
                          "loss_type": "conditional_on_shock", "conditional_loss_usd": d2.expected_loss_usd,
                          "expected_loss_usd": d2.expected_loss_usd,  # legacy key; same conditional value
                          "exit": ex2, "exit_cost_usd": ex2["usd"], "carry_usd": ex2["carry_usd"],
                          "exit_total_usd": ex2["total_usd"], "margin_usd": d2.margin_usd,
                          "verdict": d2.verdict, "verdict_basis": "point comparison (conditional loss vs execution + carry)",
                          "explanation": d2.explanation})
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
                  "exit_cost_usd": ex["usd"], "carry_usd": ex["carry_usd"], "exit_total_usd": ex["total_usd"],
                  "margin_usd": d2.margin_usd, "verdict": d2.verdict,
                  "verdict_basis": "point comparison (conditional loss vs execution + carry)", "explanation": d2.explanation}

    pocket_g = deepcopy(g)
    pocket_value = book_usd * 0.1
    pq = exit_cost_for(pocket_g, pocket_value)
    if pq.get("method") == "pendle_sdk_quote":
        pocket_g.position.meta["exit_quote"] = pq
    pockets = [Pocket(f"P{i}", 0.1, deepcopy(pocket_g)) for i in range(10)]
    book = evaluate_book(pockets, book_usd, SCENARIOS[0], affected={"P0"}, carry_rate=rate)
    hit = next(p for p in book.pockets if p.affected)
    try:
        liquidation = leverage.analyze(g, sim, scenarios, borrower)
    except Exception as e:  # borrower analysis is optional: report, never break the main signal
        liquidation = {"mode": "error", "borrower": borrower, "error": f"{type(e).__name__}: {e}"[:300]}
    prov = http.provenance()
    return {
        "position": asdict(g.position),
        "nodes": [asdict(n) for n in g.nodes],
        "edges": [asdict(e) for e in g.edges],
        "node_contrib_usd": sim.node_contrib,
        "var95_usd": sim.var95_usd,
        "mc_mean_usd": sim.mc_mean_usd,
        "decision": asdict(d),
        "exit": ex,  # usd = execution only; carry_usd / total_usd = exit side used by every verdict
        "scenarios": scenarios,
        "custom_shock": custom,
        "stress_table": _stress_table(g, ex),
        "sensitivity": _sensitivity(g, sim, d, ex, (g.position.meta.get("prior_upper_annual") or 0) /
                                    (g.position.meta.get("prior_central_annual") or float("inf"))),
        "assumptions": _assumptions(g),
        "uncertainty": uncertainty.inventory(g),
        "liquidation": liquidation,
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
