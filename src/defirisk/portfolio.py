"""Portfolio view (owner: C): a book of pockets, one gets hit, compare STAY vs EXIT per pocket.

Mirrors the brief: e.g. 10 pockets x 10%, one affected, unwinding costs 11% slippage.
"""
from dataclasses import dataclass

from .decision import exit_cost
from .models import DepGraph
from .propagation import simulate
from .scenarios import Scenario, apply


@dataclass
class Pocket:
    label: str
    weight: float  # share of the book, weights should sum to 1
    graph: DepGraph  # position.value_usd is overwritten from book size * weight


@dataclass
class PocketResult:
    label: str
    value_usd: float
    affected: bool
    stay_loss_usd: float  # expected loss if we stay (uncertain)
    exit_cost_usd: float  # certain cost if we unwind
    verdict: str


@dataclass
class BookResult:
    pockets: list
    total_stay_loss_usd: float  # if we stay in everything
    total_optimal_usd: float  # sum of min(stay loss, exit cost) per pocket
    pct_of_book: float


def evaluate_book(pockets: list[Pocket], book_usd: float, scenario: Scenario | None = None,
                  affected: set[str] | None = None) -> BookResult:
    """scenario is applied only to pockets whose label is in `affected` (all if None)."""
    results, stay_total, optimal = [], 0.0, 0.0
    for p in pockets:
        g = p.graph
        g.position.value_usd = book_usd * p.weight
        hit = scenario is not None and (affected is None or p.label in affected)
        sim = simulate(apply(g, scenario) if hit else g)
        cost = exit_cost(g.position.value_usd, g.position.meta.get("exit_pool_liquidity_usd", 1e7))
        results.append(PocketResult(p.label, g.position.value_usd, hit, sim.expected_loss_usd,
                                    cost, "EXIT" if sim.expected_loss_usd > cost else "STAY"))
        stay_total += sim.expected_loss_usd
        optimal += min(sim.expected_loss_usd, cost)
    return BookResult(results, stay_total, optimal, optimal / book_usd)
