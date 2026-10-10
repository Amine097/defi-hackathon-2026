"""python -m defirisk.cli [position_ref]"""
import sys

from .decision import decide, exit_cost
from .discovery import discover
from .propagation import simulate


def run(ref: str = "mock", use_mock: bool = True):
    g = discover(ref, use_mock)
    sim = simulate(g)
    cost = exit_cost(g.position.value_usd, g.position.meta.get("exit_pool_liquidity_usd", 1e7))
    return g, sim, decide(g, sim, cost)


if __name__ == "__main__":
    _, _, d = run(sys.argv[1] if len(sys.argv) > 1 else "mock")
    print(f"{d.verdict}\n{d.explanation}")
