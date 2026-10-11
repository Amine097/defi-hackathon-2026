"""Strict validation of a Countermove protection policy (the ARM PROTECTION form) before the owner signs setPolicy.

Two layers, both deterministic and offline:
  * contract rules  - exactly the checks RescueVault.setPolicy reverts on (InvalidPolicy("strategies" | "triggerLtv" |
                      "minLtvAfter" | "validUntil" | "repayCaps" | "topUpCaps")): a draft that passes can be signed.
  * product rules   - input hygiene the contract cannot see (finite / non-negative numbers, token decimals, LLTV range,
                      strategy names and preference order, chain allowlist, address format, bounded validity and
                      cooldown, optional target health factor). They reject inputs that would otherwise be silently
                      dropped or truncated (the previous draft endpoint ignored unknown strategies and accepted NaN).
Warnings never block: they flag policies the contract accepts but that cannot protect the position as intended.
Amounts are converted with Decimal (no float rounding): 4.1 USDC is 4100000 raw units, not 4099999.
"""
from __future__ import annotations

import math
import time
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from .engine import BITS

WAD = 10 ** 18
UINT32_MAX, UINT64_MAX, UINT256_MAX = 2 ** 32 - 1, 2 ** 64 - 1, 2 ** 256 - 1
DECIMALS_BOUNDS = (0, 36)
VALID_DAYS_BOUNDS = (1 / 24, 365)     # one hour .. one year: a policy must expire, and not before it can be used
COOLDOWN_BOUNDS = (0, 30 * 86_400)    # contract accepts any uint32; more than 30 days between rescues is a mistake
MAX_TOKENS = Decimal(10) ** 15        # sanity bound on any human amount (above every real token supply in scope)
MIN_TRIGGER_GAP = 0.005               # trigger closer than 0.5 pp to LLTV leaves no time to act (warning)
# chain id -> (label, executable by the FAULTLINE keeper). Mainnet drafts are valid for the OWNER's wallet, but the
# FAULTLINE keeper only ever transacts on a loopback test chain (chain.assert_local): it is never "armed" on mainnet.
CHAINS = {1: ("Ethereum mainnet", False), 31337: ("local Anvil test chain", True), 1337: ("local test chain", True)}
AMOUNTS = {  # field -> token side
    "max_repay_per_action": "loan", "max_full_repay": "loan", "max_repay_total": "loan", "min_loan_reserve": "loan",
    "max_top_up_per_action": "collateral", "max_top_up_total": "collateral", "min_collateral_reserve": "collateral",
}
DEFAULTS = {"strategies": "REPAY,TOP_UP", "lltv": "0.86", "trigger_ltv": "0.82", "min_ltv_after": "0.4", "valid_days": "30",
            "cooldown_s": "3600", "loan_decimals": "6", "collateral_decimals": "18"}


class _Errs:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, field: str, code: str, message: str, contract_rule: str | None = None) -> None:
        self.items.append({"field": field, "code": code, "message": message, "contract_rule": contract_rule})

    def has(self, *fields: str) -> bool:
        return any(e["field"] in fields for e in self.items)


def _raw(q: dict, k: str):
    v = q.get(k)
    return DEFAULTS.get(k) if v is None or (isinstance(v, str) and not v.strip()) else v


def _number(q: dict, k: str, errs: _Errs, default=0) -> Decimal | None:
    v = _raw(q, k)
    if v is None:
        v = default
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        errs.add(k, "not_a_number", f"{k} must be a number")
        return None
    if not d.is_finite():
        errs.add(k, "not_finite", f"{k} must be a finite number")
        return None
    return d


def _int(q: dict, k: str, errs: _Errs, lo: int, hi: int) -> int | None:
    d = _number(q, k, errs)
    if d is None:
        return None
    if d != d.to_integral_value():
        errs.add(k, "not_an_integer", f"{k} must be an integer")
        return None
    if not lo <= int(d) <= hi:
        errs.add(k, "out_of_range", f"{k} must be within [{lo}, {hi}]")
        return None
    return int(d)


def _strategies(q: dict, errs: _Errs) -> list[str]:
    raw = q["strategies"] if "strategies" in q else DEFAULTS["strategies"]  # explicitly empty = none chosen
    names = [s.strip().upper() for s in str(raw if raw is not None else "").split(",") if s.strip()]
    if not names:
        errs.add("strategies", "empty", "choose at least one strategy", "strategies")
        return []
    unknown = [s for s in names if s not in BITS]
    if unknown:
        errs.add("strategies", "unknown_strategy", f"unknown strategy {', '.join(unknown)} (accepted: {', '.join(BITS)})",
                 "strategies")
    if len(set(names)) != len(names):
        errs.add("strategies", "duplicate_strategy", "each strategy can appear only once in the preference order")
    return [s for s in dict.fromkeys(names) if s in BITS]


def _address(q: dict, k: str, errs: _Errs) -> str | None:
    v = q.get(k)
    if v in (None, ""):
        return None
    from ..vault_input import parse_address
    try:
        return parse_address(v)["address"]
    except ValueError as e:
        errs.add(k, "invalid_address", f"{k}: {e}")
        return None


def _to_raw(amount: Decimal, dec: int) -> tuple[int, bool]:
    scaled = amount * (Decimal(10) ** dec)
    raw = scaled.to_integral_value(rounding=ROUND_DOWN)
    return int(raw), raw != scaled


def validate(q: dict, now: int | None = None) -> dict:
    """q: the policy-draft query (strings or numbers). Returns errors (with field + code), warnings, the exact on-chain
    policy struct (raw integers) and the derived risk mapping. Never raises on user input."""
    now = int(time.time()) if now is None else int(now)
    errs, warnings = _Errs(), []
    strategies = _strategies(q, errs)
    ld = _int(q, "loan_decimals", errs, *DECIMALS_BOUNDS)
    cd = _int(q, "collateral_decimals", errs, *DECIMALS_BOUNDS)
    lltv = _number(q, "lltv", errs)
    if lltv is not None and not 0 < lltv < 1:
        errs.add("lltv", "out_of_range", "lltv must be strictly between 0 and 1 (a Morpho Blue LLTV)")
        lltv = None
    trigger = _number(q, "trigger_ltv", errs)
    floor = _number(q, "min_ltv_after", errs)
    valid_days = _number(q, "valid_days", errs)
    cooldown = _int(q, "cooldown_s", errs, *COOLDOWN_BOUNDS)
    chain_id = None
    if q.get("chain_id") not in (None, ""):
        chain_id = _int(q, "chain_id", errs, 0, UINT64_MAX)
        if chain_id is not None and chain_id not in CHAINS:
            errs.add("chain_id", "unsupported_chain", f"chain_id {chain_id} not supported (supported: "
                     + ", ".join(f"{c} = {n}" for c, (n, _) in CHAINS.items()) + ")")
            chain_id = None
    vault = _address(q, "vault", errs)
    keeper = _address(q, "keeper", errs)

    # ---- LTV bounds (contract: triggerLtv in (0, LLTV), minLtvAfter < triggerLtv) ---------------------------------
    trig_w = floor_w = None
    if trigger is not None:
        if not 0 < trigger < 1:
            errs.add("trigger_ltv", "out_of_range", "trigger LTV must be above 0 and below the market LLTV", "triggerLtv")
        elif lltv is not None and trigger >= lltv:
            errs.add("trigger_ltv", "above_lltv", "trigger LTV must be above 0 and below the market LLTV", "triggerLtv")
        else:
            trig_w = int(trigger * WAD)
            if lltv is not None and lltv - trigger < Decimal(str(MIN_TRIGGER_GAP)):
                warnings.append(f"trigger LTV is within {MIN_TRIGGER_GAP:.1%} of the LLTV: one block of price move can "
                                "skip straight to liquidation")
    if floor is not None:
        if floor < 0:
            errs.add("min_ltv_after", "negative", "the LTV floor cannot be negative", "minLtvAfter")
        elif trigger is not None and floor >= trigger:
            errs.add("min_ltv_after", "not_below_trigger", "the LTV floor must be below the trigger", "minLtvAfter")
        else:
            floor_w = int(floor * WAD)

    # ---- validity window (contract: validUntil > block.timestamp) --------------------------------------------------
    valid_until = None
    if valid_days is not None:
        lo, hi = VALID_DAYS_BOUNDS
        if not Decimal(str(lo)) <= valid_days <= hi:
            errs.add("valid_days", "out_of_range", f"valid_days must be within [1 hour, {hi} days] (the contract requires "
                     "a future expiry)", "validUntil")
        else:
            valid_until = now + int(valid_days * 86_400)

    # ---- amounts: exact Decimal -> raw token units ------------------------------------------------------------------
    raw: dict[str, int] = {}
    for k, side in AMOUNTS.items():
        d = _number(q, k, errs)
        dec = ld if side == "loan" else cd
        if d is None or dec is None:
            continue
        if d < 0:
            errs.add(k, "negative", f"{k} cannot be negative")
            continue
        if d > MAX_TOKENS:
            errs.add(k, "too_large", f"{k} exceeds {MAX_TOKENS:,} tokens")
            continue
        raw[k], truncated = _to_raw(d, dec)
        if truncated:
            warnings.append(f"{k} has more than {dec} decimals: truncated to {raw[k]} raw units")
    have = len(raw) == len(AMOUNTS)
    if have:
        if raw["max_repay_per_action"] > raw["max_repay_total"] or raw["max_full_repay"] > raw["max_repay_total"]:
            errs.add("max_repay_total", "caps_inconsistent",
                     "per-action / full-repay caps cannot exceed the cumulative repay budget", "repayCaps")
        if raw["max_top_up_per_action"] > raw["max_top_up_total"]:
            errs.add("max_top_up_total", "caps_inconsistent",
                     "per-action top-up cap cannot exceed the cumulative top-up budget", "topUpCaps")

    # ---- optional target health factor (keeper-side; the contract enforces only the floor and the bound) ----------
    target = None
    if q.get("target_health_factor") not in (None, "") and lltv is not None:
        hf = _number(q, "target_health_factor", errs)
        if hf is not None:
            if hf <= 1:
                errs.add("target_health_factor", "out_of_range", "target health factor must be above 1")
            else:
                t_ltv = lltv / hf
                if trigger is not None and t_ltv >= trigger:
                    errs.add("target_health_factor", "not_below_trigger",
                             "the target health factor must bring the LTV below the trigger")
                elif floor is not None and t_ltv < floor:
                    errs.add("target_health_factor", "below_floor",
                             "the target health factor would push the LTV under the floor (the contract would revert)")
                else:
                    target = {"health_factor": float(hf), "ltv": float(t_ltv)}

    # ---- warnings: accepted by the contract but cannot protect as intended ------------------------------------------
    if have:
        for s, caps in (("REPAY", ("max_repay_per_action", "max_repay_total")),
                        ("TOP_UP", ("max_top_up_per_action", "max_top_up_total")),
                        ("FULL_REPAY", ("max_full_repay", "max_repay_total"))):
            if s in strategies and any(raw[c] == 0 for c in caps):
                warnings.append(f"{s} is allowed but its cap is 0: the keeper can never use it")
        if strategies and all(any(raw[c] == 0 for c in caps) for s, caps in
                              (("REPAY", ("max_repay_per_action", "max_repay_total")),
                               ("TOP_UP", ("max_top_up_per_action", "max_top_up_total")),
                               ("FULL_REPAY", ("max_full_repay", "max_repay_total"))) if s in strategies):
            warnings.append("no allowed strategy can act: this policy would never protect the position")
        for s, c in (("TOP_UP", "max_top_up_per_action"), ("FULL_REPAY", "max_full_repay")):
            if s not in strategies and raw[c] > 0:
                warnings.append(f"{c} is set but {s} is not allowed: that cap is unused")
        for side, resv_k, floor_k, cap_k in (("loan", "loan_reserve", "min_loan_reserve", "max_repay_per_action"),
                                             ("collateral", "collateral_reserve", "min_collateral_reserve", "max_top_up_per_action")):
            if q.get(resv_k) in (None, ""):
                continue
            d = _number(q, resv_k, errs)
            dec = ld if side == "loan" else cd
            if d is None or dec is None or d < 0:
                if d is not None and d < 0:
                    errs.add(resv_k, "negative", f"{resv_k} cannot be negative")
                continue
            r, _ = _to_raw(d, dec)
            if r < raw[floor_k]:
                warnings.append(f"planned {side} reserve is below its floor: no {side}-side action can execute")
            elif raw[cap_k] and r - raw[floor_k] < raw[cap_k]:
                warnings.append(f"planned {side} reserve above its floor is smaller than the per-action cap: actions are "
                                "limited by the reserve, not by the cap")
    chain = None
    if chain_id is not None:
        name, executable = CHAINS[chain_id]
        chain = {"chain_id": chain_id, "name": name, "keeper_executable": executable}
        if not executable:
            warnings.append(f"{name}: the owner can sign this policy, but the FAULTLINE keeper only transacts on local test "
                            "chains; nothing will be executed automatically on this chain")

    errors = errs.items
    pol = None
    if not errors:
        pol = {"allowed_strategies": sum(BITS[s] for s in strategies), "valid_until": valid_until, "cooldown": cooldown,
               "trigger_ltv": trig_w, "min_ltv_after": floor_w, **{k: raw[k] for k in AMOUNTS}}
    risk = None
    if lltv is not None and trigger is not None and not errs.has("trigger_ltv"):
        risk = {"lltv": float(lltv), "trigger_ltv": float(trigger), "trigger_health_factor": float(lltv / trigger),
                "floor_ltv": None if floor is None else float(floor),
                "floor_health_factor": None if not floor else float(lltv / floor), "target": target,
                "note": "health factor = LLTV / LTV (Morpho Blue); liquidation at 1.0"}
    return {"errors": errors, "warnings": warnings, "policy": pol, "preference_order": strategies, "chain": chain,
            "vault": vault, "keeper": keeper, "risk_mapping": risk,
            "decimals": {"loan": ld, "collateral": cd}}


def matches(onchain: dict, draft: dict, *, ignore_valid_until: bool = True) -> list[str]:
    """Fields where the on-chain policy differs from the validated draft (valid_until is time-of-draft dependent)."""
    return [k for k, v in draft.items() if not (ignore_valid_until and k == "valid_until") and int(onchain.get(k, -1)) != int(v)]
