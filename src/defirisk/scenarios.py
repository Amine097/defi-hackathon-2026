"""Scenarios (owner: B/C): stress overrides applied to a graph copy, then re-simulated."""
from copy import deepcopy
from dataclasses import dataclass

from .models import DepGraph


@dataclass
class Scenario:
    name: str
    description: str
    overrides: dict  # node id -> {"p_fail": float, "loss_given_failure": float}


SCENARIOS = [  # overrides are keyed by node role (or id), resolved per graph by resolve()
    Scenario("Underlying depeg", "Underlying yield-bearing stablecoin depegs", {"underlying": {"p_fail": 1.0, "loss_given_failure": 0.3}}),
    Scenario("Oracle failure", "PT oracle misprices collateral", {"oracle": {"p_fail": 1.0}}),
    Scenario("Liquidity crisis", "AMM liquidity dries up", {"amm": {"p_fail": 1.0, "loss_given_failure": 0.5}}),
]


def resolve(g: DepGraph, s: Scenario) -> dict:
    """Map role/id keys to the concrete node ids of this graph."""
    out = {}
    for n in g.nodes:
        for key in (n.id, n.meta.get("role")):
            if key in s.overrides:
                out[n.id] = s.overrides[key]
    return out


def apply(g: DepGraph, s: Scenario) -> DepGraph:
    """Return a copy of g with the scenario overrides applied. TODO: also shrink exit pool liquidity."""
    g2 = deepcopy(g)
    ov = resolve(g, s)
    for n in g2.nodes:
        for k, v in ov.get(n.id, {}).items():
            setattr(n, k, v)
    return g2
