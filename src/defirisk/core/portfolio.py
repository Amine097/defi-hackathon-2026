"""Portfolio view (owner: C): a book of pockets, one gets hit, compare STAY vs EXIT per pocket.

Mirrors the brief: e.g. 10 pockets x 10%, one affected, unwinding costs 11% slippage.
"""
from dataclasses import dataclass

from .decision import exit_cost_for
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
    stay_loss_usd: float  # loss if we stay: conditional on the scenario for affected pockets, expected otherwise
    exit_cost_usd: float  # certain cost if we unwind (stressed for affected pockets if the scenario says so)
    verdict: str
    stay_loss_type: str = "expected"
    exit_method: str = ""


@dataclass
class BookResult:
    pockets: list
    total_stay_loss_usd: float  # if we stay in everything
    total_optimal_usd: float  # sum of min(stay loss, exit cost) per pocket
    pct_of_book: float
    scenario: str = ""


def evaluate_book(pockets: list[Pocket], book_usd: float, scenario: Scenario | None = None,
                  affected: set[str] | None = None) -> BookResult:
    """scenario is applied only to pockets whose label is in `affected` (all if None).

    All amounts are USD; pct_of_book divides by the whole book (a pocket's exit cost of 11% on a 10% pocket
    is 1.1% of the book)."""
    results, stay_total, optimal = [], 0.0, 0.0
    for p in pockets:
        g = p.graph
        g.position.value_usd = book_usd * p.weight
        hit = scenario is not None and (affected is None or p.label in affected)
        sim = simulate(apply(g, scenario) if hit else g)
        ex = exit_cost_for(g, g.position.value_usd, scenario.exit_liquidity_factor if hit else 1.0)
        cost = ex["usd"]
        results.append(PocketResult(p.label, g.position.value_usd, hit, sim.expected_loss_usd,
                                    cost, "EXIT" if sim.expected_loss_usd > cost else "STAY",
                                    "conditional" if hit else "expected", ex["method"]))
        stay_total += sim.expected_loss_usd
        optimal += min(sim.expected_loss_usd, cost)
    return BookResult(results, stay_total, optimal, optimal / book_usd, scenario.name if scenario else "")
