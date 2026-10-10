"""Failure propagation + Monte Carlo (owner: B/C)."""
from dataclasses import dataclass

import networkx as nx
import numpy as np

from .models import DepGraph


@dataclass
class SimResult:
    expected_loss_usd: float  # exact closed form under independence
    var95_usd: float  # Monte Carlo
    loss_samples: np.ndarray
    node_contrib: dict  # node id -> expected loss attributable to it (first order: p x LGF x path)
    mc_mean_usd: float = 0.0  # Monte Carlo estimate of the mean, for cross-checking


def to_nx(g: DepGraph) -> nx.DiGraph:
    G = nx.DiGraph()
    for n in g.nodes:
        G.add_node(n.id, obj=n)
    for e in g.edges:
        G.add_edge(e.src, e.dst, transmission=e.transmission, reason=e.reason)
    return G


def best_paths(g: DepGraph) -> dict:
    """node id -> (best transmission product from the position, that path as a list of node ids)."""
    G = to_nx(g)
    root = g.position.id
    out = {}
    for n in g.nodes:
        if n.id == root or not nx.has_path(G, root, n.id):
            continue
        best, best_path = 0.0, None
        for path in nx.all_simple_paths(G, root, n.id):
            t = 1.0
            for a, b in zip(path, path[1:]):
                t *= G[a][b]["transmission"]
            if t > best:
                best, best_path = t, path
        out[n.id] = (best, best_path)
    return out


def simulate(g: DepGraph, n_sims: int = 20000, seed: int = 0) -> SimResult:
    """Each node fails independently; loss flows to the position along edges.

    Position loss fraction = 1 - prod over failed nodes (1 - L_n * T_path),
    where T_path is the best transmission product from the position to node.
    """
    rng = np.random.default_rng(seed)
    G = to_nx(g)
    trans = {k: v[0] for k, v in best_paths(g).items()}

    ids = [n.id for n in g.nodes if n.id in trans]
    p = np.array([G.nodes[i]["obj"].p_fail for i in ids])
    hit = np.array([G.nodes[i]["obj"].loss_given_failure * trans[i] for i in ids])
    fails = rng.random((n_sims, len(ids))) < p
    survive = np.where(fails, 1 - hit, 1.0).prod(axis=1)
    losses = (1 - survive) * g.position.value_usd
    contrib = {
        i: float(p[k] * hit[k] * g.position.value_usd) for k, i in enumerate(ids)
    }
    # Independent failures -> E[1 - prod(1 - h_i 1_i)] = 1 - prod(1 - p_i h_i): exact, no Monte Carlo noise
    # (rare events with p ~ 1e-4 make the 20k-draw mean wobble by ~10% across seeds). MC kept for VaR95.
    exact = float((1 - np.prod(1 - p * hit)) * g.position.value_usd)
    return SimResult(
        exact, float(np.percentile(losses, 95)), losses, contrib, float(losses.mean())
    )
