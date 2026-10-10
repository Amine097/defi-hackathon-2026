"""Failure propagation + Monte Carlo (owner: B/C)."""
from dataclasses import dataclass

import networkx as nx
import numpy as np

from .models import DepGraph


@dataclass
class SimResult:
    expected_loss_usd: float
    var95_usd: float
    loss_samples: np.ndarray
    node_contrib: dict  # node id -> expected loss attributable to it


def to_nx(g: DepGraph) -> nx.DiGraph:
    G = nx.DiGraph()
    for n in g.nodes:
        G.add_node(n.id, obj=n)
    for e in g.edges:
        G.add_edge(e.src, e.dst, transmission=e.transmission, reason=e.reason)
    return G


def simulate(g: DepGraph, n_sims: int = 20000, seed: int = 0) -> SimResult:
    """Each node fails independently; loss flows to the position along edges.

    Position loss fraction = 1 - prod over failed nodes (1 - L_n * T_path),
    where T_path is the best transmission product from the position to node.
    """
    rng = np.random.default_rng(seed)
    G = to_nx(g)
    root = g.position.id
    # best transmission from root to each node (max product over simple paths)
    trans = {}
    for n in g.nodes:
        if not nx.has_path(G, root, n.id):
            continue
        best = 0.0
        for path in nx.all_simple_paths(G, root, n.id):
            t = 1.0
            for a, b in zip(path, path[1:]):
                t *= G[a][b]["transmission"]
            best = max(best, t)
        trans[n.id] = best

    ids = [n.id for n in g.nodes if n.id in trans]
    p = np.array([G.nodes[i]["obj"].p_fail for i in ids])
    hit = np.array([G.nodes[i]["obj"].loss_given_failure * trans[i] for i in ids])
    fails = rng.random((n_sims, len(ids))) < p
    survive = np.where(fails, 1 - hit, 1.0).prod(axis=1)
    losses = (1 - survive) * g.position.value_usd
    contrib = {
        i: float(p[k] * hit[k] * g.position.value_usd) for k, i in enumerate(ids)
    }
    return SimResult(
        float(losses.mean()), float(np.percentile(losses, 95)), losses, contrib
    )
