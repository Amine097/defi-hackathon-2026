"""Dependency Engine for a Morpho Blue borrower: what actually prices this position's collateral?

The market oracle (MorphoChainlinkOracleV2) computes
    price = SCALE_FACTOR x baseVault conversion x BASE_FEED_1 x BASE_FEED_2 / (quoteVault conversion x QUOTE_FEED_1 x QUOTE_FEED_2)
from immutable feed addresses. We read those addresses on-chain, then each feed (description, decimals, answer,
updatedAt), classify freshness against the block time, list the implicit assumptions (what the oracle does NOT see),
and map a shock on any dependency to an exact oracle price factor (WAD) for the Countermove scenarios: a fall of a
base feed lowers the price, a fall of a quote feed raises it. A dependency we cannot identify is a config error, never
silently ignored.
"""
from __future__ import annotations

from .engine import WAD, Scenario

FEED_ROLES = ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2")
VAULT_ROLES = ("BASE_VAULT", "QUOTE_VAULT")
DEFAULT_MAX_AGE_S = 3600 + 1800  # Chainlink 1 h heartbeat + 30 min grace
ZERO = "0x" + "0" * 40


def _feed(rpc, addr: str, role: str, block, block_ts: int, max_age: int) -> dict:
    f = {"id": f"feed:{addr.lower()}", "role": role, "side": "base" if role.startswith("BASE") else "quote", "address": addr}
    try:
        f["description"] = rpc.read(addr, "description()", [], "string", block)
    except Exception:  # noqa: BLE001 - optional metadata
        f["description"] = None
    try:
        f["decimals"] = rpc.read(addr, "decimals()", [], "uint8", block)
        rid, ans, _, upd, _ = rpc.read(addr, "latestRoundData()", [], "uint80,int256,uint256,uint256,uint80", block)
        f.update(answer=ans, round_id=rid, updated_at=upd)
    except Exception as e:  # noqa: BLE001 - an unreadable feed is a finding, not a crash
        f.update(answer=None, updated_at=None, freshness="unreadable", error=f"{type(e).__name__}: {e}"[:160])
        return f
    desc = (f["description"] or "").upper()
    f["simulated"] = "FAULTLINE SIMULATED" in desc
    if upd == 0:
        f.update(age_s=None, freshness="no_timestamp",
                 freshness_note="computed at call time (exchange-rate adapter): no update time to check")
    else:
        f["age_s"] = max(block_ts - upd, 0)
        f["max_age_s"] = max_age
        f["freshness"] = "stale" if f["age_s"] > max_age else "fresh"
    f["value"] = ans / 10 ** f["decimals"] if f.get("decimals") is not None else None
    return f


def resolve(rpc, oracle: str, block: int, block_ts: int, loan: dict, collateral: dict,
            max_age_s: dict | None = None) -> dict:
    """Dependency map of one market oracle at a pinned block. loan / collateral: {'address','symbol','decimals'}."""
    max_age_s = max_age_s or {}
    deps = {"oracle": {"id": f"oracle:{oracle.lower()}", "address": oracle, "type": "opaque"}, "feeds": [], "vaults": [],
            "assumptions": [], "block": block, "block_timestamp": block_ts}
    try:
        deps["oracle"]["price"] = rpc.read(oracle, "price()", [], "uint256", block)
    except Exception as e:  # noqa: BLE001
        deps["oracle"].update(price=None, error=f"{type(e).__name__}: {e}"[:160])
    try:
        deps["oracle"]["scale_factor"] = rpc.read(oracle, "SCALE_FACTOR()", [], "uint256", block)
        deps["oracle"]["type"] = "MorphoChainlinkOracleV2"
    except Exception:  # noqa: BLE001 - not a MorphoChainlinkOracleV2: kept as one opaque dependency
        deps["assumptions"].append("oracle type not recognised: treated as ONE opaque dependency (no feed breakdown)")
    if deps["oracle"]["type"] == "MorphoChainlinkOracleV2":
        for role in FEED_ROLES:
            a = rpc.read(oracle, f"{role}()", [], "address", block)
            if int(a, 16):
                deps["feeds"].append(_feed(rpc, a, role, block, block_ts, max_age_s.get(a.lower(), DEFAULT_MAX_AGE_S)))
        for role in VAULT_ROLES:
            a = rpc.read(oracle, f"{role}()", [], "address", block)
            if int(a, 16):
                deps["vaults"].append({"id": f"vault:{a.lower()}", "role": role, "address": a,
                                       "note": "ERC4626 conversion rate read at call time (wrapper exchange rate)"})
        quote = [f for f in deps["feeds"] if f["side"] == "quote" and "DUMMY" not in (f.get("description") or "").upper()]
        if not quote and not any(v["role"] == "QUOTE_VAULT" for v in deps["vaults"]):
            deps["assumptions"].append(
                f"{loan.get('symbol')} (loan token) is valued as exactly 1 unit of the base feeds' quote currency: "
                f"a {loan.get('symbol')} depeg is NOT seen by this oracle")
        base_desc = [f.get("description") or "" for f in deps["feeds"] if f["side"] == "base"]
        csym = (collateral.get("symbol") or "").upper()
        if base_desc and not any(csym and csym in d.upper().replace(" ", "") for d in base_desc):
            deps["assumptions"].append(
                f"{collateral.get('symbol')} (collateral) is priced through {', '.join(base_desc)}: a "
                f"{collateral.get('symbol')} discount to that reference is NOT seen by this oracle")
        if any("EXCHANGE RATE" in d.upper() for d in base_desc) or deps["vaults"]:
            deps["assumptions"].append(
                f"{collateral.get('symbol')} is valued at its protocol exchange rate, not at a market price: a secondary-"
                "market discount is NOT seen by this oracle (no liquidation trigger, but a real loss if sold)")
    deps["stale"] = [f["id"] for f in deps["feeds"] if f.get("freshness") in ("stale", "unreadable")]
    deps["simulated"] = [f["id"] for f in deps["feeds"] if f.get("simulated")]
    deps["graph"] = _graph(deps, loan, collateral)
    return deps


def _graph(deps: dict, loan: dict, coll: dict) -> dict:
    oid = deps["oracle"]["id"]
    nodes = [{"id": "position", "label": "Borrower position", "kind": "position"},
             {"id": f"token:{coll.get('address', '').lower()}", "label": f"{coll.get('symbol')} (collateral)", "kind": "collateral"},
             {"id": f"token:{loan.get('address', '').lower()}", "label": f"{loan.get('symbol')} (debt)", "kind": "loan"},
             {"id": oid, "label": f"Market oracle ({deps['oracle']['type']})", "kind": "oracle"},
             {"id": "morpho_blue", "label": "Morpho Blue (liquidation engine)", "kind": "protocol"}]
    edges = [{"src": "position", "dst": nodes[1]["id"], "why": "collateral"},
             {"src": "position", "dst": nodes[2]["id"], "why": "debt"},
             {"src": nodes[1]["id"], "dst": oid, "why": "valued by (drives liquidation)"},
             {"src": "position", "dst": "morpho_blue", "why": "liquidation when debt > LLTV x collateral value"}]
    for f in deps["feeds"]:
        nodes.append({"id": f["id"], "label": f.get("description") or f["address"], "kind": "feed", "side": f["side"],
                      "freshness": f.get("freshness"), "simulated": f.get("simulated", False)})
        edges.append({"src": oid, "dst": f["id"], "why": "multiplies the price" if f["side"] == "base" else "divides the price"})
    for v in deps["vaults"]:
        nodes.append({"id": v["id"], "label": f"{v['role']} conversion", "kind": "vault"})
        edges.append({"src": oid, "dst": v["id"], "why": "exchange rate"})
    return {"nodes": nodes, "edges": edges}


def _match(deps: dict, key: str) -> dict | None:
    k = key.lower()
    for f in deps["feeds"]:
        if k in (f["role"].lower(), f["address"].lower(), f["id"]) or (f.get("description") and k in f["description"].lower()):
            return f
    return None


def price_factor(deps: dict, shocks: list[dict]) -> tuple[int, list[dict]]:
    """Exact oracle price multiplier (WAD) for a set of dependency shocks {'dependency': role|address|description|
    'collateral'|'oracle', 'drop': 0.10}. Base feed / collateral / oracle falls lower the price; quote feed falls raise it."""
    factor, applied = WAD, []
    for sh in shocks:
        d = int(round(float(sh["drop"]) * WAD))
        if not 0 <= d < WAD:
            raise ValueError(f"drop must be in [0, 1): {sh}")
        key = str(sh["dependency"])
        if key.lower() in ("collateral", "oracle"):
            factor = factor * (WAD - d) // WAD
            applied.append({"dependency": key.lower(), "label": f"{key} price", "side": "base", "drop": sh["drop"]})
            continue
        f = _match(deps, key)
        if f is None:
            raise ValueError(f"dependency '{key}' is not part of this oracle ({[x['role'] for x in deps['feeds']]})")
        if f["side"] == "base":
            factor = factor * (WAD - d) // WAD
        else:
            factor = factor * WAD // (WAD - d)
        applied.append({"dependency": f["id"], "label": f.get("description") or f["role"], "role": f["role"],
                        "side": f["side"], "drop": sh["drop"]})
    return factor, applied


def build_scenarios(deps: dict, configured: list[dict]) -> list[Scenario]:
    """The current price is always a scenario (the target must hold now), then every configured dependency shock."""
    out = [Scenario("now", "current oracle price", WAD, [], "current")]
    for c in configured:
        f, applied = price_factor(deps, c["shocks"])
        out.append(Scenario(c["id"], c.get("label") or c["id"], f, applied, "dependency_shock"))
    return out


def attribute_move(now: dict, ref: dict | None, threshold: float = 0.001) -> dict:
    """Which dependency moved since the reference snapshot (e.g. the last healthy observation)?"""
    if not ref:
        return {"oracle_change": None, "movers": [], "note": "no reference snapshot yet"}
    po, pr = now["oracle"].get("price"), ref["oracle"].get("price")
    movers = []
    by_id = {f["id"]: f for f in ref["feeds"]}
    for f in now["feeds"]:
        r = by_id.get(f["id"])
        if not r or not f.get("answer") or not r.get("answer"):
            continue
        ch = f["answer"] / r["answer"] - 1
        if abs(ch) >= threshold:
            label = r.get("description") or f.get("description") or f["role"]
            if f.get("simulated") and "SIMULATED" not in (label or "").upper():
                label = f"{label} (SIMULATED SHOCK)"
            movers.append({"dependency": f["id"], "label": label, "role": f["role"],
                           "side": f["side"], "change": ch, "simulated": f.get("simulated", False),
                           "effect_on_collateral_price": ch if f["side"] == "base" else -ch})
    movers.sort(key=lambda m: -abs(m["change"]))
    return {"oracle_change": (po / pr - 1) if po and pr else None, "movers": movers,
            "reference_block": ref.get("block"), "block": now.get("block")}
