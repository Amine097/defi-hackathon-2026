"""JSON payload for the web UI (used by api/analyze.py). Keep it pure so it can be tested."""
from copy import deepcopy
from dataclasses import asdict

from .cli import run
from .decision import decide, exit_cost
from .portfolio import Pocket, evaluate_book
from .propagation import simulate
from .scenarios import SCENARIOS, apply, resolve


def build_payload(ref: str = "mock", use_mock: bool = True, book_usd: float = 10_000_000) -> dict:
    g, sim, d = run(ref, use_mock)
    cost = d.exit_cost_usd
    scenarios = []
    for s in SCENARIOS:
        g2 = apply(g, s)
        d2 = decide(g2, simulate(g2), cost)
        scenarios.append({"name": s.name, "description": s.description, "overrides": resolve(g, s),
                          "expected_loss_usd": d2.expected_loss_usd, "verdict": d2.verdict})
    pockets = [Pocket(f"P{i}", 0.1, deepcopy(g)) for i in range(10)]
    book = evaluate_book(pockets, book_usd, SCENARIOS[0], affected={"P0"})
    return {
        "position": asdict(g.position),
        "nodes": [asdict(n) for n in g.nodes],
        "edges": [asdict(e) for e in g.edges],
        "node_contrib_usd": sim.node_contrib,
        "decision": asdict(d),
        "scenarios": scenarios,
        "book": {"pockets": [asdict(p) for p in book.pockets],
                 "total_stay_loss_usd": book.total_stay_loss_usd,
                 "total_optimal_usd": book.total_optimal_usd, "pct_of_book": book.pct_of_book},
    }
