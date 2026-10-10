"""Exit cost + STAY/EXIT verdict (owner: C).

Decision rule (stated in every payload): over the position horizon, compare
  * the loss of STAYING  -> probability-weighted expected loss (baseline), or the loss conditional on a shock
    (scenario / stress), from the Monte Carlo in propagation.py
  * the cost of EXITING  -> certain, paid now: slippage + fees from an executable Pendle quote at the real size,
    plus gas.
EXIT if staying costs more than exiting, else STAY. Both sides are in USD of the same position.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .models import DepGraph
from .propagation import SimResult

DEFAULT_GAS_USD = 15.0  # fallback only, when gas price / ETH price cannot be read
MORPHO_WITHDRAW_GAS = 150_000  # assumption: withdrawCollateral on Morpho Blue before selling the PT


@dataclass
class Decision:
    verdict: str
    expected_loss_usd: float
    exit_cost_usd: float
    margin_usd: float
    explanation: str
    loss_type: str = "expected"  # "expected" (probability-weighted) or "conditional" (given the shock happens)
    value_usd: float = 0.0
    horizon_days: int = 30
    stay_loss_pct: float = 0.0
    exit_cost_pct: float = 0.0
    breakeven_risk_multiplier: float | None = None
    exit_method: str = ""
    rule: str = "EXIT if loss from staying over the horizon > certain exit cost (slippage + fees + gas), else STAY"
    top_drivers: list = field(default_factory=list)


def approx_exit_cost(value_usd: float, pool_liquidity_usd: float, gas_usd: float = DEFAULT_GAS_USD) -> float:
    """Constant-product approximation. Only a fallback: Pendle's AMM is not x*y=k and the real route also uses
    aggregators, so this can be far off (observed ~50x too high vs an executable quote)."""
    slippage = value_usd / (2 * pool_liquidity_usd + value_usd)
    return value_usd * slippage + gas_usd


def exit_cost(value_usd: float, pool_liquidity_usd: float, gas_usd: float = DEFAULT_GAS_USD) -> float:
    """Backward-compatible float API (approximation)."""
    return approx_exit_cost(value_usd, pool_liquidity_usd, gas_usd)


def _gas_usd(gas_units: int) -> tuple[float, str]:
    from . import sources
    try:
        wei = sources.eth_gas_price_wei()
        eth = sources.llama_prices(["coingecko:ethereum"]).get("coingecko:ethereum", {}).get("price")
        if wei and eth:
            return gas_units * wei / 1e18 * eth, f"{gas_units:,} gas x {wei / 1e9:.3f} gwei (eth_gasPrice) x ETH ${eth:,.0f} (DefiLlama)"
    except Exception:
        pass
    return DEFAULT_GAS_USD, f"assumption: ${DEFAULT_GAS_USD:.0f} gas (gas price unavailable)"


def quote_exit(route: dict, value_usd: float) -> dict:
    """Executable exit quote for `value_usd` of the PT: sell PT -> out token via Pendle SDK.

    route = {"pt": addr, "pt_decimals": int, "pt_price_usd": float, "out": addr, "out_symbol": str, "chain_id": 1}
    """
    from . import sources
    pt_amount = value_usd / route["pt_price_usd"]
    raw = int(pt_amount * 10 ** route["pt_decimals"])
    q = sources.pendle_quote(route["pt"], raw, route["out"], route.get("chain_id", 1))
    key = f"ethereum:{route['out'].lower()}"
    px = sources.llama_prices([key]).get(key) or {}
    if not px.get("price") or px.get("decimals") is None:
        raise RuntimeError(f"no DefiLlama price for exit token {route['out']}")
    out_amount = q["amount_out_raw"] / 10 ** int(px["decimals"])
    out_usd = out_amount * px["price"]
    gas_units = q["gas_used"] + MORPHO_WITHDRAW_GAS
    gas_usd, gas_why = _gas_usd(gas_units)
    slippage_usd = max(value_usd - out_usd, 0.0)
    return {
        "usd": slippage_usd + gas_usd, "pct": (slippage_usd + gas_usd) / value_usd, "method": "pendle_sdk_quote",
        "slippage_and_fees_usd": slippage_usd, "gas_usd": gas_usd, "gas_source": gas_why,
        "price_impact": q["price_impact"], "pendle_fee_usd_included": q["fee_usd"], "aggregator": q["aggregator"],
        "contract_method": q["method"], "pt_in": pt_amount, "pt_in_raw": raw, "pt_price_usd": route["pt_price_usd"],
        "out_amount": out_amount, "out_symbol": route.get("out_symbol"), "out_price_usd": px["price"],
        "value_usd": value_usd, "liquidity_factor": 1.0,
        "basis": (f"sell {pt_amount:,.0f} PT (= ${value_usd:,.0f} at Pendle mid ${route['pt_price_usd']:.4f}) -> "
                  f"{out_amount:,.0f} {route.get('out_symbol')} (${out_usd:,.0f}) via Pendle SDK quote; cost = value - proceeds + gas"),
    }


def exit_cost_for(g: DepGraph, value_usd: float | None = None, liquidity_factor: float = 1.0) -> dict:
    """Exit cost breakdown for the position (or a resized copy). Uses the executable quote when the graph carries
    an exit route, else the flagged constant-product approximation.

    liquidity_factor < 1 models a stressed exit (e.g. 0.5 = half the liquidity): slippage is scaled by
    1/liquidity_factor (price impact ~ inversely proportional to depth for trades small vs. the pool). Assumption.
    """
    meta = g.position.meta
    value = g.position.value_usd if value_usd is None else value_usd
    base = None
    q = meta.get("exit_quote")
    if q and abs(q["value_usd"] - value) <= 1e-6 * max(value, 1):
        base = dict(q)
    elif meta.get("exit_route") and os.getenv("DEFIRISK_NO_QUOTE") != "1":
        try:
            base = quote_exit(meta["exit_route"], value)
        except Exception as e:  # keep the demo alive, but say so
            meta.setdefault("exit_quote_errors", []).append(str(e))
    if base is None:
        liq = meta.get("exit_pool_liquidity_usd")
        if not liq:
            raise RuntimeError("no exit quote and no pool liquidity: exit cost unknown")
        gas = DEFAULT_GAS_USD
        slip = approx_exit_cost(value, liq, 0.0)
        base = {"usd": slip + gas, "pct": (slip + gas) / value, "method": "approximation_constant_product",
                "slippage_and_fees_usd": slip, "gas_usd": gas, "gas_source": f"assumption: ${gas:.0f}",
                "value_usd": value, "liquidity_factor": 1.0,
                "basis": f"APPROXIMATION: value/(2*liquidity+value) with pool liquidity ${liq:,.0f} (no executable quote)"}
    if liquidity_factor != 1.0:
        slip = base["slippage_and_fees_usd"] / max(liquidity_factor, 1e-6)
        base.update(usd=slip + base["gas_usd"], pct=(slip + base["gas_usd"]) / value, slippage_and_fees_usd=slip,
                    liquidity_factor=liquidity_factor,
                    basis=base["basis"] + f"; STRESSED: slippage / {liquidity_factor:g} (assumption: liquidity x{liquidity_factor:g})")
    return base


def decide(g: DepGraph, sim: SimResult, cost, risk_aversion: float = 0.0, loss_type: str = "expected") -> Decision:
    """risk_aversion blends mean loss with VaR95 (0 = mean only, 1 = VaR95). `cost` = float USD or exit_cost_for() dict."""
    exit_info = cost if isinstance(cost, dict) else {"usd": float(cost), "method": "given"}
    c = exit_info["usd"]
    value = g.position.value_usd or 1.0
    loss = (1 - risk_aversion) * sim.expected_loss_usd + risk_aversion * sim.var95_usd
    verdict = "EXIT" if loss > c else "STAY"
    labels = {n.id: n.label for n in g.nodes}
    top = sorted(sim.node_contrib.items(), key=lambda kv: -kv[1])[:3]
    drivers = [{"id": k, "label": labels.get(k, k), "usd": v} for k, v in top]
    why = ", ".join(f"{d['label']} (${d['usd']:,.0f})" for d in drivers)
    mult = (c / loss) if loss > 0 else None
    kind = "expected" if loss_type == "expected" else "conditional (if the shock happens)"
    if verdict == "STAY":
        flip = f"Risk would have to be x{mult:.1f} higher before exiting pays." if mult else "No modelled loss."
    else:
        flip = f"Staying costs x{loss / c:.1f} the exit cost." if c > 0 else ""
    expl = (f"{verdict}: {kind} {g.position.horizon_days}d loss if we stay ${loss:,.0f} ({loss / value:.2%} of the "
            f"${value:,.0f} position) vs certain exit cost ${c:,.0f} ({c / value:.2%}, {exit_info.get('method')}). {flip} "
            f"Top risk drivers: {why}.")
    return Decision(verdict, loss, c, loss - c, expl, loss_type, value, g.position.horizon_days, loss / value, c / value,
                    mult, exit_info.get("method", ""), top_drivers=drivers)
