"""Shared schema. Every module speaks this; agree on changes as a team."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json

LAYERS = ["chain", "yield_source", "oracle", "amm", "lending", "protocol"]

# What an edge carries from a dependency to the position. Whether it reaches the position depends on the position's
# exposure role (position.meta["exposure_role"]):
#   principal -> always: the dependency can impair the value the position redeems into (token, contract custody, chain)
#   debt      -> only with debt ("borrower"): oracle / market failures act through liquidation; without debt they fall
#                on lenders (bad debt) and borrowers, not on idle collateral
#   exit      -> never a loss on the held value: it changes the cost / timing of exiting (e.g. the AMM a PT is sold
#                through before maturity); priced on the exit side (stressed exit liquidity), not in the staying loss
CHANNELS = ("principal", "debt", "exit")
ROLES = ("collateral_only", "borrower")


def channel_active(channel: str, position: "Position") -> bool:
    if channel == "exit":
        return False
    if channel == "debt":
        return position.meta.get("exposure_role") == "borrower"
    return True


def edge_weight(e: "Edge", position: "Position") -> float:
    """Transmission used by the loss model: the edge's weight if its channel reaches this position, else 0."""
    return e.transmission if channel_active(e.channel, position) else 0.0


@dataclass
class Node:
    id: str
    layer: str  # one of LAYERS
    label: str
    p_fail: float  # probability of failure over the horizon
    loss_given_failure: float  # fraction of exposed value lost if it fails (0-1)
    meta: dict = field(default_factory=dict)  # addresses, tvl, source urls...


@dataclass
class Edge:
    src: str  # the dependent
    dst: str  # the dependency; if dst fails, src is hit
    transmission: float = 1.0  # fraction of dst's loss passed to src (0-1)
    reason: str = ""
    channel: str = "principal"  # one of CHANNELS


@dataclass
class Position:
    id: str
    label: str
    chain: str
    value_usd: float
    horizon_days: int = 30
    meta: dict = field(default_factory=dict)


@dataclass
class DepGraph:
    position: Position
    nodes: list[Node]
    edges: list[Edge]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @staticmethod
    def from_dict(d: dict) -> "DepGraph":
        return DepGraph(
            Position(**d["position"]),
            [Node(**n) for n in d["nodes"]],
            [Edge(**e) for e in d["edges"]],
        )

    @staticmethod
    def load(path: str) -> "DepGraph":
        with open(path, encoding="utf-8") as f:
            return DepGraph.from_dict(json.load(f))
