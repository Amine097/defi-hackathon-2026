"""JSON payload for the web UI (used by api/analyze.py). Keep it pure so it can be tested."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import asdict

from . import leverage, uncertainty
from .data import http
from .cli import run
from .core import book as book_lib
from .core.decision import decide, exit_cost_for
from .core.maturity import maturity_options
from .core.portfolio import Pocket, evaluate_book
from .core.propagation import best_paths, blocked_channels, simulate
from .core.scenarios import SCENARIOS, apply, resolve, shock

GLOBAL_ASSUMPTIONS = [
    "Central expected loss = V(1 - prod(1 - p_i x LGF_i x T_i)): exact ONLY under independent failures + best-path "
    "transmission; bracketed by dependence-free bounds [V max p_i h_i, V min(1, sum p_i h_i)] and a parameter band "
    "(decision.loss_band). VaR95 from a Monte Carlo (20,000 draws, seed 0). A correlated joint scenario is reported.",
    "Loss reaching the position = loss-given-failure x best path transmission; edge transmissions are expert weights. "
    "Loss-given-failure of exploit-type dependencies (issuer, underlying, Pendle, Morpho, oracle) is calibrated on the "
    "same DefiLlama incidents as their failure rate: mean share of TVL lost (bootstrap 95% CI as the band); chain and "
    "look-through what-if severities remain assumptions; stablecoin depth is measured on price history.",
    "Failure priors: DefiLlama hack history restricted to the protocol cohort (TVL >= $10M), adjusted by audits/TVL/age; "
    "stablecoins use their own DefiLlama price history (depeg = price < $0.98).",
    "Position size is an input (default $1M) on a real, live market. Default mode = unlevered exposure (no debt, "
    "liquidation NOT_APPLICABLE); borrower=0x..|auto analyses a real Morpho borrower (debt, HF, liquidation) on-chain.",
    "Exposure role decides which failures can reach the position: without debt, the market oracle and the Morpho market "
    "act only on borrowers (liquidation) and lenders (bad debt), so they carry no loss to the collateral; the PT's own "
    "contracts, its underlying / issuer, the Morpho Blue singleton holding the collateral and the chain do. The Pendle "
    "AMM is the exit route: its failure raises the exit cost (stressed exit liquidity), not the redemption value.",
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

    def row(parameter, setting, g2):
        s2 = simulate(g2)
        return {"parameter": parameter, "setting": setting, "expected_loss_usd": s2.expected_loss_usd,
                "exit_total_usd": exit_side, "verdict": "EXIT" if s2.expected_loss_usd > exit_side else "STAY"}

    lgf_rows, t_rows = [], []
    for which in ("low", "high"):
        g2 = deepcopy(g)
        for n in g2.nodes:
            if n.id != g2.position.id:
                n.loss_given_failure = uncertainty.classify_lgf(n)[which]
        lgf_rows.append(row("loss_given_failure", f"every LGF at its {which} bound (calibrated: 95% CI of the mean; "
                                                  "assumptions: x0.5 / x1.5)", g2))
    for k in uncertainty.T_RANGE:
        g2 = deepcopy(g)
        for e in g2.edges:
            if not e.reason.startswith("measured"):
                e.transmission = min(1.0, e.transmission * k)
        t_rows.append(row("transmission", f"every expert edge weight x{k}", g2))
    return {"rows": rows, "lgf_rows": lgf_rows, "transmission_rows": t_rows,
            "breakeven_risk_multiplier": d.breakeven_risk_multiplier,
            "note": "Each block varies one parameter family, the rest at central values; exit side (execution + carry "
                    "forgone) unchanged. Point comparison on central values (no bands). Upper p multiplier = "
                    "all-incident base rate / cohort base rate."}


CHANNEL_NOTE = {
    "debt": "no effect without debt: oracle and market failures act through liquidation (borrowers) and bad debt "
            "(lenders), not on collateral that backs no loan; analyse with borrower=0x..|auto to include them",
    "exit": "exit channel only: it raises the cost of selling before maturity (or forces holding to maturity); the PT's "
            "redemption value is unchanged; see the stressed exit cost",
}


def _channel_note(g, node_id: str) -> dict | None:
    blocked = blocked_channels(g, node_id)
    if not blocked:
        return None
    return {"blocked_by": blocked, "note": "; ".join(CHANNEL_NOTE[c] for c in blocked if c in CHANNEL_NOTE)}


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
                     "exit_total_usd": exit_side, "channel": _channel_note(g, n.id),
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
                  shock_node: str | None = None, severity: float | None = None, borrower: str | None = None,
                  exit_cost_pct: float | None = None, book_shock: str | None = None, book_severity: float | None = None,
                  weights: list[float] | None = None) -> dict:
    http.reset_provenance()
    g, sim, d = run(ref, use_mock, value_usd, borrower=borrower)
    rate = _carry_rate(d)
    ex = _with_carry(exit_cost_for(g), g.position.value_usd, rate)
    scenarios = []
    for s in SCENARIOS:
        g2 = apply(g, s)
        ex2 = _with_carry(exit_cost_for(g, None, s.exit_liquidity_factor), g.position.value_usd, rate)
        d2 = decide(g2, simulate(g2), ex2, loss_type="conditional")
        notes = {nid: _channel_note(g, nid) for nid in resolve(g, s)}
        scenarios.append({"name": s.name, "description": s.description, "overrides": resolve(g, s),
                          "channel_notes": {k: v for k, v in notes.items() if v},
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
                  "channel": _channel_note(g, shock_node),
                  "loss_type": "conditional_on_shock", "conditional_loss_usd": d2.expected_loss_usd,
                  "exit_cost_usd": ex["usd"], "carry_usd": ex["carry_usd"], "exit_total_usd": ex["total_usd"],
                  "margin_usd": d2.margin_usd, "verdict": d2.verdict,
                  "verdict_basis": "point comparison (conditional loss vs execution + carry)", "explanation": d2.explanation}

    try:
        liquidation = leverage.analyze(g, sim, scenarios, borrower)
    except Exception as e:  # borrower analysis is optional: report, never break the main signal
        liquidation = {"mode": "error", "borrower": borrower, "error": f"{type(e).__name__}: {e}"[:300]}
    book = _book(g, rate, book_usd, exit_cost_pct, book_shock, book_severity, weights,
                 shock_node if custom and "verdict" in custom else None, custom and custom.get("severity"))
    maturity = maturity_options(g, ex, d)
    prov = http.provenance()
    return {
        "position": asdict(g.position),
        "nodes": [asdict(n) for n in g.nodes],
        "edges": [asdict(e) for e in g.edges],
        "node_contrib_usd": sim.node_contrib,
        "var95_usd": sim.var95_usd,
        "mc_mean_usd": sim.mc_mean_usd,
        "decision": asdict(d),
        "maturity": maturity,
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
        "book": book,
        "incident": _incident(custom, book, maturity),
    }


def _incident(custom: dict | None, book: dict, maturity: dict) -> dict | None:
    """One answer to "X is hit at Y%: what does it do to me and to the book, stay or exit?" (shock=<node>&severity=)."""
    if not custom or "verdict" not in custom:
        return custom
    hit = [p for p in book.get("pockets", []) if p.get("affected")]
    exits = [p["label"] for p in hit if p["verdict"] == "EXIT"]
    out = {"node": custom["node"], "name": custom["name"], "severity": custom["severity"],
           "position": {k: custom[k] for k in ("conditional_loss_usd", "exit_total_usd", "verdict", "channel")},
           "book": {"applied": book.get("mode") == "real_book" and bool(book.get("shock")),
                    "pockets_hit": [p["label"] for p in hit], "pockets_to_exit": exits,
                    "book_loss_if_stay_usd": book.get("total_stay_loss_usd"),
                    "book_loss_best_usd": book.get("total_optimal_usd"), "pct_of_book": book.get("pct_of_book")},
           "hold_to_maturity": maturity.get("if_amm_fails") if custom["node"] == "amm" else None}
    ch = custom.get("channel")
    out["headline"] = (f"{custom['name']}: {ch['note']}" if ch and custom["conditional_loss_usd"] <= custom["exit_total_usd"]
                       else f"{custom['name']}: losing ${custom['conditional_loss_usd']:,.0f} if we stay vs "
                            f"${custom['exit_total_usd']:,.0f} to exit -> {custom['verdict']}"
                            + (f"; {len(hit)} pocket(s) of the book hit, exit {len(exits)}" if out["book"]["applied"] else ""))
    return out


def _legacy_book(g, rate: float, book_usd: float, exit_cost_pct: float | None) -> dict:
    """Mock graph only: ten copies of the analysed position, P0 hit by the first scenario."""
    pocket_g = deepcopy(g)
    pq = exit_cost_for(pocket_g, book_usd * 0.1)
    if pq.get("method") == "pendle_sdk_quote":
        pocket_g.position.meta["exit_quote"] = pq
    pockets = [Pocket(f"P{i}", 0.1, deepcopy(pocket_g)) for i in range(10)]
    book = evaluate_book(pockets, book_usd, SCENARIOS[0], affected={"P0"}, carry_rate=rate)
    if exit_cost_pct is not None:
        for p in book.pockets:
            p.exit_cost_usd = p.value_usd * exit_cost_pct
            p.exit_method = "given"
            p.exit_total_usd = p.exit_cost_usd + p.carry_usd
            p.verdict = "EXIT" if p.stay_loss_usd > p.exit_total_usd else "STAY"
        book.total_optimal_usd = sum(min(p.stay_loss_usd, p.exit_total_usd) for p in book.pockets)
        book.pct_of_book = book.total_optimal_usd / book_usd
    hit = next(p for p in book.pockets if p.affected)
    return {"mode": "copies_of_position", "scenario": book.scenario, "affected": ["P0"], "book_usd": book_usd,
            "exit_cost_override_pct": exit_cost_pct, "pockets": [asdict(p) for p in book.pockets],
            "total_stay_loss_usd": book.total_stay_loss_usd,
            "total_optimal_usd": book.total_optimal_usd, "pct_of_book": book.pct_of_book,
            "hit_pocket_exit_cost_pct_of_pocket": hit.exit_cost_usd / hit.value_usd,
            "hit_pocket_exit_cost_pct_of_book": hit.exit_cost_usd / book_usd}


def _book(g, rate: float, book_usd: float, exit_cost_pct: float | None, shock_key: str | None,
          severity: float | None, weights: list[float] | None, incident_node: str | None = None,
          incident_severity: float | None = None) -> dict:
    markets = g.position.meta.get("book_markets")
    if not isinstance(markets, list) or not markets or g.position.meta.get("exposure_role") == "borrower":
        out = _legacy_book(g, rate, book_usd, exit_cost_pct)
        out["note"] = ("borrower mode: the book view analyses collateral without debt; shown on copies of this position"
                       if g.position.meta.get("exposure_role") == "borrower" else
                       (markets or {}).get("error") if isinstance(markets, dict) else "no real pocket list (mock graph)")
        return out
    mine = next((m for m in markets if m.get("is_mine")), markets[0])
    if shock_key is None and incident_node:  # the incident on the analysed position also hits every pocket sharing it
        shock_key = next((d["key"] for d in mine["dependencies"] if d.get("node_id") == incident_node), None)
        severity = incident_severity if severity is None else severity
    if shock_key is None:  # the brief: one dependency is hit -> the analysed position's underlying loses 30%
        shock_key = next((d["key"] for d in mine["dependencies"] if d["role"] == "underlying"), None)
        severity = book_lib.DEFAULT_SEVERITY if severity is None else severity
    keys = {d["key"] for m in markets for d in m["dependencies"]}
    if shock_key not in keys:
        raise ValueError(f"unknown book dependency '{shock_key}' (known: {', '.join(sorted(keys))})")
    ref = (g.position.meta.get("reference_rates") or {}).get("supply_apy")
    return book_lib.evaluate(g, markets[:len(weights)] if weights else markets, book_usd, weights=weights,
                             exit_cost_pct=exit_cost_pct, shock_key=shock_key, severity=severity,
                             reference_apy=ref, quote=os.getenv("DEFIRISK_NO_QUOTE") != "1")
