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
QUOTE_TTL_S = 60  # a swap quote is perishable: older than this, it is no longer an executable price
SIM_TOLERANCE = 0.005  # SDK amount vs eth_call re-execution: >0.5% apart = mismatch, keep the worse one


@dataclass
class Decision:
    verdict: str
    expected_loss_usd: float
    exit_cost_usd: float  # execution only: swap fees + price impact + gas
    margin_usd: float  # expected_loss_usd - exit_total_usd (> 0: staying costs more on central values)
    explanation: str
    loss_type: str = "expected"  # "expected" (probability-weighted) or "conditional" (given the shock happens)
    value_usd: float = 0.0
    horizon_days: int = 30
    stay_loss_pct: float = 0.0
    exit_cost_pct: float = 0.0
    breakeven_risk_multiplier: float | None = None
    exit_method: str = ""
    rule: str = "EXIT if loss from staying over the horizon > exit side (execution: slippage + fees + gas, + carry forgone if known), else STAY"
    top_drivers: list = field(default_factory=list)
    point_verdict: str | None = None  # central comparison incl. carry (no uncertainty); verdict may be REVIEW
    point_verdict_execution_only: str | None = None  # legacy rule: loss vs execution cost, carry ignored
    confidence: str | None = None
    lean: str | None = None
    reasons: list = field(default_factory=list)
    loss_band: dict | None = None
    exit_band: dict | None = None
    carry: dict | None = None
    freshness: dict | None = None
    exit_total_usd: float | None = None  # exit side of the comparison: execution + carry forgone (central)
    carry_usd: float | None = None  # excess carry forgone by exiting over the horizon (None = not counted)
    margin_usd_execution_only: float | None = None  # legacy: loss - execution cost, carry ignored
    breakeven_risk_multiplier_execution_only: float | None = None


def approx_exit_cost(value_usd: float, pool_liquidity_usd: float, gas_usd: float = DEFAULT_GAS_USD) -> float:
    """Constant-product approximation. Only a fallback: Pendle's AMM is not x*y=k and the real route also uses
    aggregators, so this can be far off (observed ~50x too high vs an executable quote)."""
    slippage = value_usd / (2 * pool_liquidity_usd + value_usd)
    return value_usd * slippage + gas_usd


def exit_cost(value_usd: float, pool_liquidity_usd: float, gas_usd: float = DEFAULT_GAS_USD) -> float:
    """Backward-compatible float API (approximation)."""
    return approx_exit_cost(value_usd, pool_liquidity_usd, gas_usd)


def _gas_usd(gas_units: int) -> tuple[float, str]:
    from ..data import sources
    try:
        wei = sources.eth_gas_price_wei()
        eth = sources.llama_prices(["coingecko:ethereum"]).get("coingecko:ethereum", {}).get("price")
        if wei and eth:
            return gas_units * wei / 1e18 * eth, f"{gas_units:,} gas x {wei / 1e9:.3f} gwei (eth_gasPrice) x ETH ${eth:,.0f} (DefiLlama)"
    except Exception:
        pass
    return DEFAULT_GAS_USD, f"assumption: ${DEFAULT_GAS_USD:.0f} gas (gas price unavailable)"


def quote_exit(route: dict, value_usd: float, simulate: bool | None = None) -> dict:
    """Executable exit quote for `value_usd` of the PT: sell PT -> out token via Pendle SDK, then (if possible)
    re-executed on-chain with eth_call at a pinned block to confirm the proceeds (no transaction is sent).

    route = {"pt": addr, "pt_decimals": int, "pt_price_usd": float, "out": addr, "out_symbol": str, "chain_id": 1}
    Cost = value at Pendle mid - USD proceeds + gas. Proceeds are the router's own output, so the Pendle fee, the
    AMM price impact and the aggregator leg are already inside them: they are reported, never added again.
    """
    from ..data import http, sources
    pt_amount = value_usd / route["pt_price_usd"]
    raw = int(pt_amount * 10 ** route["pt_decimals"])
    q = sources.pendle_quote(route["pt"], raw, route["out"], route.get("chain_id", 1))
    key = f"ethereum:{route['out'].lower()}"
    px = sources.llama_prices([key]).get(key) or {}
    if not px.get("price") or px.get("decimals") is None:
        raise RuntimeError(f"no DefiLlama price for exit token {route['out']}")
    dec_out = int(px["decimals"])
    if simulate is None:
        simulate = os.getenv("DEFIRISK_NO_SIM") != "1" and os.getenv("DEFIRISK_OFFLINE") != "1"
    sim = {"status": "not_run"}
    block = None
    if simulate and q.get("tx") and not q.get("from_cache"):
        try:
            blk = sources.eth_block("latest")
            block = blk["number"] if blk else None
            sim = sources.simulate_swap(q["tx"], route["pt"], raw, block)
        except Exception as e:
            sim = {"status": "unavailable", "reason": str(e)[:200]}
    out_raw = q["amount_out_raw"]
    if sim.get("status") == "simulated":
        dev = abs(sim["amount_out_raw"] - out_raw) / max(out_raw, 1)
        sim["deviation_vs_sdk"] = dev
        if dev > SIM_TOLERANCE:
            out_raw = min(out_raw, sim["amount_out_raw"])  # conservative: keep the worse of the two
        status = "simulated" if dev <= SIM_TOLERANCE else "simulation_mismatch"
    else:
        status = "indicative"
    if q.get("from_cache"):
        status = "replayed_cache"
    fetched = q.get("fetched_at") or http.now()
    age = max(http.now() - fetched, 0.0)
    if age > QUOTE_TTL_S and status != "replayed_cache":
        status = "stale"
    out_amount = out_raw / 10 ** dec_out
    out_usd = out_amount * px["price"]
    swap_gas = sim.get("gas_estimate") or q["gas_used"]
    gas_units = swap_gas + MORPHO_WITHDRAW_GAS
    gas_usd, gas_why = _gas_usd(gas_units)
    if sim.get("gas_estimate"):
        gas_why += " (swap gas from eth_estimateGas on the simulated tx)"
    raw_gap = value_usd - out_usd
    slippage_usd = max(raw_gap, 0.0)
    fee = q["fee_usd"] or 0.0
    return {
        "usd": slippage_usd + gas_usd, "pct": (slippage_usd + gas_usd) / value_usd, "method": "pendle_sdk_quote",
        "slippage_and_fees_usd": slippage_usd, "gas_usd": gas_usd, "gas_source": gas_why, "gas_units": gas_units,
        "price_impact": q["price_impact"], "pendle_fee_usd_included": q["fee_usd"], "aggregator": q["aggregator"],
        "contract_method": q["method"], "pt_in": pt_amount, "pt_in_raw": raw, "pt_price_usd": route["pt_price_usd"],
        "out_amount": out_amount, "out_amount_raw": out_raw, "out_decimals": dec_out,
        "out_symbol": route.get("out_symbol"), "out_price_usd": px["price"],
        "value_usd": value_usd, "liquidity_factor": 1.0,
        "quote_status": status, "quote_fetched_at": fetched, "quote_age_s": age, "quote_ttl_s": QUOTE_TTL_S,
        "quote_block": block, "simulation": sim, "sdk_amount_out_raw": q["amount_out_raw"],
        "decomposition": {
            "value_at_mid_usd": value_usd, "proceeds_usd": out_usd,
            "execution_shortfall_usd": raw_gap,
            "of_which_pendle_fee_usd": fee,
            "of_which_out_token_off_peg_usd": out_amount * (1 - px["price"]),
            "of_which_price_impact_and_route_usd": raw_gap - fee - out_amount * (1 - px["price"]),
            "gas_usd": gas_usd, "total_exit_cost_usd": slippage_usd + gas_usd,
            "note": "fee and price impact are inside the proceeds (router output); listed for explanation, not added",
        },
        "basis": (f"sell {pt_amount:,.0f} PT (= ${value_usd:,.0f} at Pendle mid ${route['pt_price_usd']:.4f}) -> "
                  f"{out_amount:,.0f} {route.get('out_symbol')} (${out_usd:,.0f}) via Pendle SDK quote [{status}"
                  + (f", eth_call at block {block}" if status == "simulated" else "") + "]; cost = value - proceeds + gas"),
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
    """risk_aversion blends mean loss with VaR95 (0 = mean only, 1 = VaR95). `cost` = float USD or exit_cost_for() dict.
    If the dict carries `carry_usd` (excess yield forgone by exiting), it is added to the exit side of the comparison:
    exit side = execution (swap fees + price impact + gas) + carry. margin = loss - exit side (> 0 means staying costs more)."""
    exit_info = cost if isinstance(cost, dict) else {"usd": float(cost), "method": "given"}
    c = exit_info["usd"]
    carry = float(exit_info.get("carry_usd") or 0.0)
    total = c + carry
    value = g.position.value_usd or 1.0
    loss = (1 - risk_aversion) * sim.expected_loss_usd + risk_aversion * sim.var95_usd
    verdict = "EXIT" if loss > total else "STAY"
    labels = {n.id: n.label for n in g.nodes}
    top = sorted(sim.node_contrib.items(), key=lambda kv: -kv[1])[:3]
    drivers = [{"id": k, "label": labels.get(k, k), "usd": v} for k, v in top]
    why = ", ".join(f"{d['label']} (${d['usd']:,.0f})" for d in drivers)
    mult = (total / loss) if loss > 0 else None
    kind = "expected" if loss_type == "expected" else "conditional (if the shock happens)"
    if verdict == "STAY":
        flip = f"Risk would have to be x{mult:.1f} higher before exiting pays." if mult else "No modelled loss."
    else:
        flip = f"Staying costs x{loss / total:.1f} the exit side." if total > 0 else ""
    side = (f"exit side ${total:,.0f} = exit cost ${c:,.0f} (execution: {c / value:.2%}, {exit_info.get('method')}) + "
            f"carry forgone ${carry:,.0f}" if carry else
            f"exit cost ${c:,.0f} (execution only: {c / value:.2%}, {exit_info.get('method')})")
    expl = (f"{verdict}: {kind} {g.position.horizon_days}d loss if we stay ${loss:,.0f} ({loss / value:.2%} of the "
            f"${value:,.0f} position) vs {side}. {flip} Top risk drivers: {why}.")
    return Decision(verdict, loss, c, loss - total, expl, loss_type, value, g.position.horizon_days, loss / value, c / value,
                    mult, exit_info.get("method", ""), top_drivers=drivers, exit_total_usd=total,
                    carry_usd=carry if carry else None)

def decide_robust(g: DepGraph, sim: SimResult, ex: dict, prov: dict | None = None) -> Decision:
    """Point comparison (decide) + uncertainty bands + carry + freshness -> STAY / EXIT / REVIEW.
    The firm verdict requires the bands not to overlap and every decisive input to be fresh and executable."""
    from .. import freshness, uncertainty
    from ..data import http
    d = decide(g, sim, ex)
    m = g.position.meta
    lb = uncertainty.loss_band(g)
    cr = uncertainty.carry(g, m.get("reference_rates") if m.get("real") else None)
    eb = uncertainty.exit_band(ex, cr)
    fr = freshness.evaluate(g, ex, prov if prov is not None else http.provenance(), m.get("block_timestamp"))
    sig = uncertainty.robust_signal(lb, eb, cr, fr["blockers"])
    d.point_verdict_execution_only = d.verdict
    d.margin_usd_execution_only = d.margin_usd
    d.breakeven_risk_multiplier_execution_only = d.breakeven_risk_multiplier
    d.point_verdict, d.verdict = sig["point_verdict"], sig["verdict"]
    # every headline number below is on the same basis as the verdict: central loss vs exit side incl. carry
    d.exit_total_usd = eb["central_usd"]
    d.carry_usd = cr["usd"] if cr.get("status") == "estimated" else None
    d.margin_usd = lb["central_usd"] - eb["central_usd"]
    d.breakeven_risk_multiplier = sig["breakeven_risk_multiplier_incl_carry"]
    d.confidence, d.lean, d.reasons = sig["confidence"], sig["lean"], sig["reasons"]
    d.loss_band, d.exit_band, d.carry, d.freshness = lb, eb, cr, fr
    d.rule = sig["rule"]
    carry_txt = (f" Exiting also forgoes ${cr['usd']:,.0f} of excess carry (PT {cr['pt_implied_apy']:.2%} vs USDC supply "
                 f"{cr['reference_apy']:.2%}); exit side incl. carry ${eb['central_usd']:,.0f} "
                 f"[${eb['low_usd']:,.0f}-${eb['high_usd']:,.0f}]." if cr.get("status") == "estimated" else
                 " Carry not counted (unknown).")
    d.explanation = (f"{d.verdict} ({d.confidence} confidence). Staying: expected loss ${lb['central_usd']:,.0f} "
                     f"[${lb['low_usd']:,.0f}-${lb['high_usd']:,.0f}] over {g.position.horizon_days}d. Exit execution "
                     f"${ex['usd']:,.0f} ({ex.get('method')}, quote {eb['quote_status']}).{carry_txt} "
                     + (f"{d.lean}. " if d.lean else "") + ("; ".join(d.reasons) + ". " if d.reasons else "")
                     + "Point comparison incl. carry: " + d.point_verdict
                     + f" (execution cost only: {d.point_verdict_execution_only}).")
    return d
