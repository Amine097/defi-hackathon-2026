"""python -m defirisk.cli [position_ref|mock] [value_usd]

  python -m defirisk.cli auto 1000000   -> live discovery + STAY/EXIT for a $1M position
  python -m defirisk.cli mock           -> offline demo graph (data/mock_graph.json, NOT real data)
"""
import sys

from .decision import decide_robust, exit_cost_for
from .discovery import discover
from .propagation import simulate


def run(ref: str = "mock", use_mock: bool | None = None, value_usd: float = 1_000_000, horizon_days: int = 30):
    use_mock = (ref == "mock") if use_mock is None else use_mock
    g = discover(ref, use_mock, value_usd, horizon_days)
    if use_mock:
        g.position.value_usd = value_usd
    sim = simulate(g)
    return g, sim, decide_robust(g, sim, exit_cost_for(g))


def summary(g, sim, d) -> str:
    m = g.position.meta
    lines = [f"POSITION  {g.position.label}  ${g.position.value_usd:,.0f}  horizon {g.position.horizon_days}d  "
             f"({'REAL on-chain data' if m.get('real') else 'MOCK demo data'})",
             f"  pendle={m.get('pendle_market')} morpho={m.get('morpho_market')} block={m.get('block_number')}",
             "DEPENDENCIES (depth, hidden, p_fail over horizon, loss-given-failure)"]
    for n in sorted(g.nodes, key=lambda n: (n.meta.get("depth") or 0)):
        if n.id == g.position.id:
            continue
        lines.append(f"  [{n.meta.get('depth')}{'*' if n.meta.get('hidden') else ' '}] {n.label:<45} "
                     f"p={n.p_fail:.4%} lgf={n.loss_given_failure:.0%}  <- {n.meta.get('source', '')[:70]}")
    lines += [f"STAY loss (expected) ${d.expected_loss_usd:,.0f} ({d.stay_loss_pct:.2%}); VaR95 ${sim.var95_usd:,.0f}",
              f"EXIT cost ${d.exit_cost_usd:,.0f} ({d.exit_cost_pct:.2%}) via {d.exit_method}",
              f"LOSS BAND ${d.loss_band['low_usd']:,.0f} - ${d.loss_band['high_usd']:,.0f}; EXIT BAND (incl. carry) "
              f"${d.exit_band['low_usd']:,.0f} - ${d.exit_band['high_usd']:,.0f}",
              f"VERDICT {d.verdict} (confidence {d.confidence}; point comparison {d.point_verdict})", d.explanation]
    return "\n".join(lines)


if __name__ == "__main__":
    ref = sys.argv[1] if len(sys.argv) > 1 else "mock"
    value = float(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000
    print(summary(*run(ref, None, value)))
