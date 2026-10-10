"""Scenarios (owner: B/C): stress overrides applied to a graph copy, then re-simulated."""
from copy import deepcopy
from dataclasses import dataclass

from .models import DepGraph


@dataclass
class Scenario:
    name: str
    description: str
    overrides: dict  # node id -> {"p_fail": float, "loss_given_failure": float}


SCENARIOS = [
    Scenario("USDe depeg", "Underlying yield-bearing stablecoin depegs", {"susde": {"p_fail": 1.0, "loss_given_failure": 0.3}}),
    Scenario("Oracle failure", "PT oracle misprices collateral", {"oracle": {"p_fail": 1.0}}),
    Scenario("Liquidity crisis", "AMM liquidity dries up", {"pendle": {"p_fail": 1.0, "loss_given_failure": 0.5}}),
]


def apply(g: DepGraph, s: Scenario) -> DepGraph:
    """Return a copy of g with the scenario overrides applied. TODO: also shrink exit pool liquidity."""
    g2 = deepcopy(g)
    for n in g2.nodes:
        for k, v in s.overrides.get(n.id, {}).items():
            setattr(n, k, v)
    return g2
