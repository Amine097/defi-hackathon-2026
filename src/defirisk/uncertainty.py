"""Parameter inventory, uncertainty bands, carry and the robust STAY / EXIT / REVIEW signal (H01).

What the central expected loss is: V x (1 - prod_i (1 - p_i x LGF_i x T_i)) is the exact expectation of the loss
fraction ONLY under (a) independent node failures, (b) each failure transmitting along its single best path,
(c) failure losses compounding multiplicatively. It is labelled "central (independence)" and is bracketed by
  * dependence-free bounds at the same parameters: [V max_i p_i h_i , V min(1, sum_i p_i h_i)] - valid for ANY joint
    distribution of failures (lower: one node alone; upper: union bound, 1 - prod(1 - x_i) <= sum x_i);
  * a parameter band: low = independence with low parameters, high = union bound with high parameters.
Each p / LGF / transmission is classified observed | calibrated | protocol-derived | scenario_assumption | not_used.
"""
from __future__ import annotations

import math

from .models import DepGraph
from .propagation import best_paths

CLASSES = ("observed", "calibrated", "protocol-derived", "scenario_assumption", "not_used", "unknown")
LGF_RANGE = {"observed": (0.5, 2.0), "scenario_assumption": (0.5, 1.5)}
T_RANGE = (0.75, 1.25)  # expert edge weights: +-25%
CALIBRATED_LOW = 0.5  # cohort base rate x0.5 (better-than-average protocol)
ASSUMPTION_RANGE = (0.2, 4.0)  # e.g. chain 0.5%/y -> [0.1%, 2%]/y
CARRY_BAND = 0.5  # +-50%: implied and supply rates move over the horizon
INDICATIVE_QUOTE_BAND = 0.25  # +-25% on the swap cost when the quote could not be re-executed on-chain
GAS_BAND = 0.5


def _poisson_ci(k: int, conf: float = 0.95) -> tuple[float, float]:
    """Exact (Garwood) CI on a Poisson mean from k events, by bisection on the CDF (no scipy)."""
    a = (1 - conf) / 2

    def cdf(lam, n):
        term = s = math.exp(-lam)
        for i in range(1, n + 1):
            term *= lam / i
            s += term
        return s

    def solve(f):  # root of a monotone function on [0, 100]
        lo, hi = 0.0, 100.0
        inc = f(hi) > f(lo)
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) < 0) == inc:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    low = 0.0 if k == 0 else solve(lambda l: (1 - cdf(l, k - 1)) - a)
    high = solve(lambda l: cdf(l, k) - a)
    return low, high


def _scale_h(p: float, k: float) -> float:
    return min(max(p * k, 0.0), 1.0)


def _horizon_from_annual(annual: float, horizon_days: int) -> float:
    return 1 - (1 - min(max(annual, 0.0), 0.95)) ** (horizon_days / 365)


def classify_p(node, g: DepGraph) -> dict:
    src = node.meta.get("source", "")
    H = g.position.horizon_days
    p = node.p_fail
    if node.id == g.position.id:
        return {"class": "not_used", "low": 0.0, "central": 0.0, "high": 0.0, "why": "position itself"}
    if src.startswith("look-through only"):
        return {"class": "not_used", "low": 0.0, "central": 0.0, "high": 0.0,
                "why": "look-through node: risk carried by the parent token prior (no double counting)"}
    if src.startswith("DefiLlama stablecoin"):
        st = node.meta.get("depeg_stats")
        if st and st.get("years"):
            lo, hi = _poisson_ci(int(st["episodes"]))
            k = max(int(st["episodes"]), 0.5)
            return {"class": "observed", "central": p,
                    "low": _horizon_from_annual(lo / st["years"], H) if st["episodes"] else 0.0,
                    "high": _horizon_from_annual(hi / st["years"], H),
                    "why": f"{st['episodes']} depeg episode(s) in {st['years']:.1f}y; exact Poisson 95% CI on the rate"
                           + ("" if st["episodes"] else f" (central uses {k} episode floor)")}
        return {"class": "observed", "central": p, "low": p * 0.5, "high": _scale_h(p, 3.0),
                "why": "DefiLlama price history (episode count unavailable: x0.5 / x3 band, assumption)"}
    if src.startswith("DefiLlama hacks"):
        m = g.position.meta
        ratio = (m.get("prior_upper_annual") or 0) / (m.get("prior_central_annual") or float("inf"))
        ratio = ratio if ratio and ratio > 1 else 3.0
        return {"class": "calibrated", "central": p, "low": p * CALIBRATED_LOW, "high": _scale_h(p, ratio),
                "why": f"cohort hack base rate x modifiers; low x{CALIBRATED_LOW} (assumption), high x{ratio:.1f} "
                       "(all incidents / all protocols >= $1M, the broad DefiLlama rate)"}
    if "assumption" in src:
        return {"class": "scenario_assumption", "central": p, "low": p * ASSUMPTION_RANGE[0],
                "high": _scale_h(p, ASSUMPTION_RANGE[1]), "why": f"{src}; band x{ASSUMPTION_RANGE[0]}-x{ASSUMPTION_RANGE[1]}"}
    return {"class": "unknown", "central": p, "low": 0.0, "high": _scale_h(p, 5.0) if p else 0.0,
            "why": src or "no source recorded: wide band"}


def classify_lgf(node) -> dict:
    src = node.meta.get("lgf_source", "")
    lgf = node.loss_given_failure
    cls = "observed" if src.startswith("measured") else ("not_used" if node.p_fail == 0 else "scenario_assumption")
    lo, hi = LGF_RANGE.get(cls, (1.0, 1.0))
    return {"class": cls, "central": lgf, "low": lgf * lo, "high": min(1.0, lgf * hi), "why": src}


def inventory(g: DepGraph) -> dict:
    nodes = []
    for n in g.nodes:
        if n.id == g.position.id:
            continue
        nodes.append({"id": n.id, "label": n.label, "role": n.meta.get("role"), "mechanism": MECHANISM.get(n.meta.get("role"), "other"),
                      "p_fail_horizon": classify_p(n, g), "loss_given_failure": classify_lgf(n)})
    edges = [{"src": e.src, "dst": e.dst, "transmission": e.transmission,
              "class": "protocol-derived" if e.reason.startswith("measured") else "scenario_assumption",
              "low": e.transmission if e.reason.startswith("measured") else e.transmission * T_RANGE[0],
              "high": e.transmission if e.reason.startswith("measured") else min(1.0, e.transmission * T_RANGE[1]),
              "why": e.reason}
             for e in g.edges]
    return {"nodes": nodes, "edges": edges,
            "classes": "observed = measured on public data for this asset; calibrated = public base rate adjusted by "
                       "metadata; protocol-derived = read from contracts; scenario_assumption = expert weight with a band; "
                       "not_used = carried elsewhere (no double counting)"}


MECHANISM = {
    "underlying": "underlying depeg / impairment -> PT redeems into less value",
    "issuer": "issuer failure (operational, legal, reserves) -> underlying impaired",
    "backing": "backing asset impairment -> underlying impaired",
    "stablecoin": "stablecoin depeg (observed history)",
    "amm": "Pendle AMM / contract incident -> PT exit and price impaired",
    "oracle": "oracle failure / manipulation -> wrong collateral price -> bad liquidations / bad debt",
    "feed_provider": "feed provider failure -> oracle wrong",
    "lending": "Morpho market incident -> collateral stuck or lost",
    "morpho_blue": "Morpho Blue singleton contract exploit",
    "loan_asset": "loan asset depeg -> debt / liquidity mispriced",
    "chain": "L1 halt / rollback / consensus failure",
    "base_asset": "look-through base asset (what-if only)",
}


def _h_values(g: DepGraph, which: str) -> tuple[list[float], list[float], list[str]]:
    import networkx as nx
    from .core.propagation import path_sum, to_nx
    paths = best_paths(g)
    G = to_nx(g) if path_sum(g) else None
    tmap = {}
    for nid, (t, path) in paths.items():
        routes = list(nx.all_simple_paths(G, g.position.id, nid)) if G is not None else [path]
        total = 0.0
        for route in routes:
            tt = 1.0
            for a, b in zip(route, route[1:]):
                e = next(e for e in g.edges if e.src == a and e.dst == b)
                w = e.transmission
                if not e.reason.startswith("measured"):  # on-chain allocation weights carry no expert band
                    w = {"low": w * T_RANGE[0], "high": min(1.0, w * T_RANGE[1])}.get(which, w)
                tt *= w
            total += tt
        tmap[nid] = min(total, 1.0)
    ps, hs, ids = [], [], []
    for n in g.nodes:
        if n.id not in tmap:
            continue
        pc, lc = classify_p(n, g), classify_lgf(n)
        ps.append(pc[which])
        hs.append(lc[which] * tmap[n.id])
        ids.append(n.id)
    return ps, hs, ids


def loss_band(g: DepGraph) -> dict:
    V = g.position.value_usd
    out = {}
    for which in ("low", "central", "high"):
        p, h, _ = _h_values(g, which)
        x = [a * b for a, b in zip(p, h)]
        indep = 1 - math.prod(1 - v for v in x)
        out[which] = {"independence_usd": V * indep, "union_bound_usd": V * min(1.0, sum(x)),
                      "single_worst_usd": V * max(x, default=0.0)}
    return {
        "central_usd": out["central"]["independence_usd"],
        "low_usd": out["low"]["independence_usd"],
        "high_usd": out["high"]["union_bound_usd"],
        "dependence_bounds_at_central_usd": [out["central"]["single_worst_usd"], out["central"]["union_bound_usd"]],
        "detail": out,
        "formula": "central = V(1 - prod(1 - p_i LGF_i T_i)): exact expectation under independence + best-path "
                   "transmission; dependence-free bounds [V max p_i h_i, V min(1, sum p_i h_i)]; band low = independence at "
                   "low parameters, high = union bound at high parameters (any correlation).",
    }


def carry(g: DepGraph, rates: dict | None) -> dict:
    """Excess carry forgone by exiting over the horizon: V x (PT implied APY - USDC supply APY on the same Morpho
    market) x H/365. Counted on the EXIT side (it is what the manager gives up by selling the PT now)."""
    amm = next((n for n in g.nodes if n.meta.get("role") == "amm"), None)
    implied = (amm.meta.get("implied_apy") if amm else None)
    if implied is None or not rates or rates.get("supply_apy") is None:
        return {"status": "unknown", "usd": None, "reason": "PT implied APY or reference USDC rate unavailable: carry "
                "excluded, signal confidence downgraded"}
    H, V = g.position.horizon_days, g.position.value_usd
    excess = implied - rates["supply_apy"]
    usd = V * excess * H / 365
    return {"status": "estimated", "usd": usd, "low_usd": usd * (1 - CARRY_BAND), "high_usd": usd * (1 + CARRY_BAND),
            "pt_implied_apy": implied, "reference_apy": rates["supply_apy"], "reference": rates.get("source"),
            "excess_apy": excess,
            "formula": f"V x (PT implied APY {implied:.2%} - USDC supply APY {rates['supply_apy']:.2%}) x {H}/365",
            "note": "assumes exit proceeds are redeployed at the USDC supply rate; band +-50% for rate moves (assumption)"}


def exit_band(ex: dict, carry_info: dict) -> dict:
    swap = ex.get("slippage_and_fees_usd", 0.0)
    gas = ex.get("gas_usd", 0.0)
    status = ex.get("quote_status") or ("approximation" if ex.get("method", "").startswith("approx") else "indicative")
    k = 0.0 if status == "simulated" else INDICATIVE_QUOTE_BAND
    lo = swap * (1 - k) + gas * (1 - GAS_BAND)
    hi = swap * (1 + k) + gas * (1 + GAS_BAND)
    c = ex["usd"]
    if carry_info.get("status") == "estimated":
        cl, ch = sorted((carry_info["low_usd"], carry_info["high_usd"]))
        return {"central_usd": c + carry_info["usd"], "low_usd": lo + cl, "high_usd": hi + ch,
                "execution_usd": c, "carry_usd": carry_info["usd"], "quote_status": status}
    return {"central_usd": c, "low_usd": lo, "high_usd": hi, "execution_usd": c, "carry_usd": None, "quote_status": status}


def robust_signal(loss: dict, exb: dict, carry_info: dict, blockers: list[str]) -> dict:
    """EXIT iff even the low loss beats the high exit cost; STAY iff even the high loss is below the low exit cost;
    otherwise REVIEW with an explicitly conditional lean (the point comparison)."""
    point = "EXIT" if loss["central_usd"] > exb["central_usd"] else "STAY"
    reasons = list(blockers)
    if loss["low_usd"] > exb["high_usd"] and not blockers:
        verdict, conf = "EXIT", "high"
    elif loss["high_usd"] < exb["low_usd"] and not blockers:
        verdict, conf = "STAY", "high"
    else:
        verdict, conf = "REVIEW", "low"
        if not blockers:
            reasons.append(f"uncertainty bands overlap: staying loss ${loss['low_usd']:,.0f}-${loss['high_usd']:,.0f} vs "
                           f"exit ${exb['low_usd']:,.0f}-${exb['high_usd']:,.0f}")
    if verdict != "REVIEW" and carry_info.get("status") != "estimated":
        conf = "medium"
        reasons.append("carry excluded (unknown)")
    be = exb["central_usd"] / loss["central_usd"] if loss["central_usd"] > 0 else None
    lean = (f"lean {point} (conditional): {point} holds if the true risk is "
            + (f"at least x{be:.2f} the central estimate" if point == "EXIT" and be is not None else
               f"below x{be:.2f} the central estimate" if be is not None else "as modelled"))
    return {"verdict": verdict, "point_verdict": point, "confidence": conf, "lean": lean if verdict == "REVIEW" else None,
            "breakeven_risk_multiplier_incl_carry": be, "reasons": reasons,
            "rule": "EXIT if loss_low > exit_high; STAY if loss_high < exit_low; else REVIEW (lean = central comparison). "
                    "Stale / replayed / approximated inputs force REVIEW."}
