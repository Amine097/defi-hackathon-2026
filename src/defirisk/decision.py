"""Exit cost + STAY/EXIT verdict (owner: C)."""
from dataclasses import dataclass

from .models import DepGraph
from .propagation import SimResult


@dataclass
class Decision:
    verdict: str
    expected_loss_usd: float
    exit_cost_usd: float
    margin_usd: float
    explanation: str


def exit_cost(value_usd: float, pool_liquidity_usd: float, gas_usd: float = 15.0) -> float:
    """Constant-product style slippage approximation + gas.
    TODO: replace with real quote (Pendle router / CoW / 1inch) for real size.
    """
    slippage = value_usd / (2 * pool_liquidity_usd + value_usd)
    return value_usd * slippage + gas_usd


def decide(g: DepGraph, sim: SimResult, cost: float, risk_aversion: float = 0.0) -> Decision:
    """risk_aversion blends mean loss with VaR95 (0 = mean only, 1 = VaR95)."""
    loss = (1 - risk_aversion) * sim.expected_loss_usd + risk_aversion * sim.var95_usd
    verdict = "EXIT" if loss > cost else "STAY"
    top = sorted(sim.node_contrib.items(), key=lambda kv: -kv[1])[:3]
    why = ", ".join(f"{k} (${v:,.0f})" for k, v in top)
    return Decision(
        verdict,
        loss,
        cost,
        loss - cost,
        f"Expected {g.position.horizon_days}d loss ${loss:,.0f} vs exit cost "
        f"${cost:,.0f}. Top risk drivers: {why}.",
    )
