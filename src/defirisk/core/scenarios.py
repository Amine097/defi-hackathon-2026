"""Scenarios (owner: B/C): stress overrides applied to a graph copy, then re-simulated.

A scenario forces one or more dependencies to fail (p_fail = 1) with a given severity (loss_given_failure).
The resulting loss is CONDITIONAL on the shock happening; it is not a probability-weighted expected loss.
Override values below are hypotheses chosen for the demo, shown as such in the payload.
"""
from copy import deepcopy
from dataclasses import dataclass

from .models import DepGraph


@dataclass
class Scenario:
    name: str
    description: str
    overrides: dict  # node id or role -> {"p_fail": float, "loss_given_failure": float}
    exit_liquidity_factor: float = 1.0  # < 1 = exit liquidity shrinks during the scenario (stressed exit cost)


SCENARIOS = [  # overrides are keyed by node role (or id), resolved per graph by resolve()
    Scenario("Underlying depeg", "Underlying yield-bearing asset loses 30% of its value (hypothesis: severity 0.3)",
             {"underlying": {"p_fail": 1.0, "loss_given_failure": 0.3}}),
    Scenario("Oracle failure", "PT oracle misprices collateral (severity = node default)", {"oracle": {"p_fail": 1.0}}),
    Scenario("Liquidity crisis", "Pendle AMM impaired (severity 0.5) and exit liquidity halves (hypothesis)",
             {"amm": {"p_fail": 1.0, "loss_given_failure": 0.5}}, exit_liquidity_factor=0.5),
    Scenario("Correlated: depeg + oracle + liquidity",
             "Joint stress (hypothesis): underlying loses 30%, the PT oracle misprices (node default severity) and the "
             "Pendle AMM is impaired (0.5) with exit liquidity halved - failures that tend to happen together",
             {"underlying": {"p_fail": 1.0, "loss_given_failure": 0.3}, "oracle": {"p_fail": 1.0},
              "amm": {"p_fail": 1.0, "loss_given_failure": 0.5}}, exit_liquidity_factor=0.5),
]


def shock(g: DepGraph, node_id: str, severity: float | None = None) -> Scenario:
    """Ad-hoc shock on any dependency: it fails for sure, with `severity` (default: the node's own LGF)."""
    node = next((n for n in g.nodes if n.id == node_id), None)
    if node is None or node_id == g.position.id:
        raise ValueError(f"unknown dependency '{node_id}'")
    sev = node.loss_given_failure if severity is None else float(severity)
    if not 0 <= sev <= 1:
        raise ValueError("severity must be within [0, 1]")
    return Scenario(f"Shock: {node.label}", f"{node.label} fails, losing {sev:.0%} of the value it carries",
                    {node_id: {"p_fail": 1.0, "loss_given_failure": sev}})


def resolve(g: DepGraph, s: Scenario) -> dict:
    """Map role/id keys to the concrete node ids of this graph."""
    out = {}
    for n in g.nodes:
        for key in (n.id, n.meta.get("role")):
            if key in s.overrides:
                out[n.id] = s.overrides[key]
    return out


def apply(g: DepGraph, s: Scenario) -> DepGraph:
    """Return a copy of g with the scenario overrides applied (exit liquidity stress is handled in decision)."""
    g2 = deepcopy(g)
    ov = resolve(g, s)
    for n in g2.nodes:
        for k, v in ov.get(n.id, {}).items():
            setattr(n, k, v)
    return g2
