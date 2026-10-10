"""Countermove DRY-RUN on a REAL Ethereum-mainnet Morpho Blue borrower: what would the keeper do right now?

  LIVE     the borrower's position (collateral, debt accrued to the block, LTV, LLTV, buffer), its market and the
           oracle's real dependencies (feeds + freshness) are read now with eth_call, all pinned to ONE block.
  DRY-RUN  no RescueVault exists for a real borrower: the policy (same fields and units as policy_draft) and the
           reserves are HYPOTHETICAL inputs, with defaults scaled to the position. The watcher's state rule and the
           same deterministic engine plan exactly as the keeper would. Nothing is signed and nothing is sent: the
           VALIDATING stage (eth_call of the vault action, gas / fee caps) is skipped because there is no vault, and
           the payload carries no transaction field at all.

    GET /api/countermove?action=dry-run&market=<id|alias>&borrower=<0x..|auto>[&rank=1][&trigger_ltv=0.8]...
    python -m defirisk.countermove dry-run --market cbBTC/USDC --borrower auto [--set trigger_ltv=0.7] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from .. import morpho
from ..keccak import keccak256
from . import contracts, dependencies, engine
from .api import FIRST_HITS, LIVE_RPCS, _cand_view, _h, _js, policy_draft
from .chain import RPC, RPCError, RevertError
from .reader import token_meta

SCHEMA = "faultline.countermove.dryrun/1"
MARKETS = {"cbBTC/USDC": "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64",
           "weETH/USDC": "0x85252bb8485c99bba46fe149c7dd2aad83672640f53c630890673cf1848ba16e"}
DEFAULT_MARKET = "cbBTC/USDC"
ZERO = "0x" + "0" * 40
MAX_LEN = 200
MAX_AMOUNT = Decimal(10) ** 18  # human token units: far above any real position, keeps every integer bounded
AMOUNT_KEYS = ("loan_reserve", "collateral_reserve", "safety_margin", "max_repay_per_action", "max_top_up_per_action",
               "max_full_repay", "max_repay_total", "max_top_up_total", "min_loan_reserve", "min_collateral_reserve")
KNOWN = {"action", "market", "borrower", "rank", "strategies", "trigger_ltv", "min_ltv_after", "valid_days", "cooldown_s",
         "interest_horizon_s", "follow_on_drop", "follow_on_dependency", "allow_partial", "ranking", *AMOUNT_KEYS}
LABELS = {"LIVE": "read now from Ethereum mainnet with eth_call at one pinned block (read-only)",
          "DRY-RUN": "hypothetical policy and reserves (no RescueVault exists for this borrower): the keeper's engine "
                     "plans, nothing is signed, nothing is sent"}
DEFAULT_RULES = {"loan_reserve": "10% of the current debt", "collateral_reserve": "10% of the current collateral",
                 "caps": "per-action and cumulative caps = the reserves (full repay cap = loan reserve if FULL_REPAY)",
                 "trigger_ltv": "market LLTV - 4 pp", "min_ltv_after": "min(40%, trigger - 10 pp)",
                 "safety_margin": "1% of the current debt", "strategies": "REPAY,TOP_UP (as policy_draft)",
                 "follow_on": "collateral oracle price -8% after any action", "interest_horizon_s": "86,400 (1 day)"}
_HEX32 = re.compile(r"0x[0-9a-fA-F]{64}")
_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
_DEP = re.compile(r"[A-Za-z0-9_ ./:()-]{1,64}")


class DryRunError(Exception):
    """Structured error: code (machine), status (HTTP), message (human, no secrets)."""

    def __init__(self, code: str, status: int, message: str, **detail):
        super().__init__(message)
        self.code, self.status, self.message, self.detail = code, status, message, detail

    def to_dict(self) -> dict:
        return _js({"error": {"code": self.code, "status": self.status, "message": self.message, **self.detail}})


def _bad(field: str, msg: str) -> DryRunError:
    return DryRunError("invalid_input", 400, f"{field}: {msg}", field=field)


# ---- input -----------------------------------------------------------------------------------------------------------
def checksum(address: str) -> str:
    a = address.lower().removeprefix("0x")
    h = keccak256(a.encode()).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c for i, c in enumerate(a))


def _dec(q: dict, key: str, lo: Decimal | int, hi: Decimal | int, lo_open: bool = False, integer: bool = False):
    v = q.get(key)
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise _bad(key, f"not a number: {s[:40]!r}") from None
    if not d.is_finite():
        raise _bad(key, "must be a finite number")
    if d < lo or (lo_open and d == lo) or d > hi:
        raise _bad(key, f"must be in {'(' if lo_open else '['}{lo}, {hi}]")
    if integer and d != d.to_integral_value():
        raise _bad(key, "must be an integer")
    return int(d) if integer else d


def _market(q: dict) -> tuple[str, str | None, bool]:
    raw = str(q.get("market") or "").strip()
    if not raw:
        return MARKETS[DEFAULT_MARKET], DEFAULT_MARKET, True
    alias = {k.lower(): k for k in MARKETS}.get(raw.lower().replace(" ", ""))
    if alias:
        return MARKETS[alias], alias, False
    if not _HEX32.fullmatch(raw):
        raise _bad("market", "must be a Morpho Blue market id (0x + 64 hexadecimal characters) or one of "
                   + ", ".join(MARKETS))
    if int(raw, 16) == 0:
        raise _bad("market", "zero market id")
    return raw.lower(), None, False


def _borrower(q: dict) -> str | None:
    raw = str(q.get("borrower") or "").strip()
    if raw.lower() in ("", "auto", "largest", "top"):
        return None
    if not _ADDR.fullmatch(raw):
        raise _bad("borrower", "must be 0x followed by 40 hexadecimal characters, or 'auto'")
    body, cs = raw[2:], checksum(raw)
    if body != body.lower() and body != body.upper() and raw != cs:
        raise _bad("borrower", "address checksum (EIP-55) is invalid")
    if int(body, 16) == 0:
        raise _bad("borrower", "zero address")
    return cs


def parse_request(q: dict) -> dict:
    """Every local check (no network): bad input -> DryRunError 400 before any mainnet read."""
    for k, v in q.items():
        if len(str(k)) > 64 or len(str(v)) > MAX_LEN:
            raise _bad(str(k)[:64], "value too long")
    mid, alias, mdefault = _market(q)
    r = {"market_id": mid, "market_alias": alias, "borrower": _borrower(q), "defaults_used": ["market"] if mdefault else [],
         "ignored": sorted(k for k in q if k not in KNOWN)}
    r["rank"] = _dec(q, "rank", 1, 20, integer=True) or 1
    raw_s = q.get("strategies")
    if raw_s is None or not str(raw_s).strip():
        r["strategies"] = None
    else:
        st = [s.strip().upper() for s in str(raw_s).split(",") if s.strip()]
        unknown = [s for s in st if s not in engine.BITS]
        if unknown or not st:
            raise _bad("strategies", f"choose among {', '.join(engine.BITS)} (got {', '.join(unknown) or 'nothing'})")
        r["strategies"] = list(dict.fromkeys(st))
    r["trigger_ltv"] = _dec(q, "trigger_ltv", 0, 1, lo_open=True)
    r["min_ltv_after"] = _dec(q, "min_ltv_after", 0, Decimal("0.9999"))
    r["valid_days"] = _dec(q, "valid_days", 0, 3650, lo_open=True)
    r["cooldown_s"] = _dec(q, "cooldown_s", 0, 365 * 86_400, integer=True)
    r["interest_horizon_s"] = _dec(q, "interest_horizon_s", 0, 30 * 86_400, integer=True)
    r["follow_on_drop"] = _dec(q, "follow_on_drop", 0, Decimal("0.95"))
    dep = str(q.get("follow_on_dependency") or "").strip()
    if dep and not _DEP.fullmatch(dep):
        raise _bad("follow_on_dependency", "use 'collateral', a feed role (e.g. BASE_FEED_1) or a feed description")
    r["follow_on_dependency"] = dep or None
    r["amounts"] = {k: _dec(q, k, 0, MAX_AMOUNT) for k in AMOUNT_KEYS}
    ap = str(q.get("allow_partial") or "").strip().lower()
    if ap not in ("", "0", "1", "true", "false", "yes", "no"):
        raise _bad("allow_partial", "must be 0/1 or true/false")
    r["allow_partial"] = ap in ("1", "true", "yes")
    rk = str(q.get("ranking") or "min_capital").strip()
    if rk not in ("min_capital", "preference"):
        raise _bad("ranking", "must be min_capital or preference")
    r["ranking"] = rk
    return r


# ---- borrower discovery (Morpho API) + live reads -------------------------------------------------------------------
def pick_borrower(market_id: str, rank: int, top=None) -> dict:
    """The rank-th largest borrower of the market (Morpho API, by borrow shares); its position is re-read on-chain."""
    from ..data import http
    default = top is None
    try:
        items = (top or morpho.top_borrowers)(market_id, first=rank + 4)
    except Exception as e:  # noqa: BLE001 - indexer down: say so, never guess an address
        raise DryRunError("morpho_api_unavailable", 503, "could not list this market's borrowers from the Morpho API: "
                          "pass borrower=0x.. instead", detail=f"{type(e).__name__}: {e}"[:200]) from None
    if len(items) < rank:
        raise DryRunError("no_borrower", 404, f"the Morpho API lists {len(items)} borrower(s) with debt on this market "
                          f"(rank {rank} asked)", field="borrower")
    it = items[rank - 1]
    out = {"address": checksum(it["address"]), "source": "auto", "rank": rank,
           "how": f"#{rank} borrower by borrow shares in the Morpho API (indexer); the position below is re-read on-chain",
           "api_borrow_assets_raw": it.get("borrow_assets_api"), "api_health_factor": it.get("health_factor_api")}
    if default:
        out.update(api_from_cache=bool(http.LAST.get("cached")), api_fetched_at=http.LAST.get("fetched_at"))
    return out


def endpoints() -> list:
    urls = list(dict.fromkeys(u for u in (os.getenv("ETH_RPC_URL"), *LIVE_RPCS) if u))
    return [RPC(u, timeout=12, retries=0) for u in urls]


def _host(url: str) -> str:
    return urlparse(url).hostname or "rpc"  # never echo the full URL: ETH_RPC_URL may embed an API key


def read_live(rpc, market_id: str, user: str) -> dict:
    """Market, position (debt accrued to the block) and oracle dependencies at ONE block. eth_call only."""
    cid = rpc.chain_id()
    if cid != 1:
        raise RPCError(f"endpoint is on chain {cid}, not Ethereum mainnet")
    b = rpc.block("latest")
    blk, ts = b["number"], b["timestamp"]
    mo = contracts.MORPHO_BLUE
    params = contracts.market_params(rpc, mo, market_id, blk)
    if int(params["loan_token"], 16) == 0:
        raise DryRunError("market_not_found", 404, f"no Morpho Blue market {market_id} on Ethereum mainnet", field="market")
    if int(params["collateral_token"], 16) == 0 or int(params["oracle"], 16) == 0:
        raise DryRunError("idle_market", 422, "idle market (no collateral / no oracle): there is no borrower to protect",
                          field="market")
    st = contracts.market_state(rpc, mo, market_id, blk)
    rate = contracts.borrow_rate(rpc, params, st, blk)
    acc = morpho.accrue(st, rate, ts)
    p = contracts.position(rpc, mo, market_id, user, blk)
    debt = morpho.to_assets_up(p["borrow_shares"], acc["total_borrow_assets"], acc["total_borrow_shares"])
    price = contracts.oracle_price(rpc, params["oracle"], blk)
    loan, coll = token_meta(rpc, params["loan_token"]), token_meta(rpc, params["collateral_token"])
    pos = {"block": blk, "timestamp": ts, "block_hash": b.get("hash"), "market_id": market_id, "morpho": mo,
           "beneficiary": user, "collateral": p["collateral"], "borrow_shares": p["borrow_shares"], "debt": debt,
           "price": price, "lltv": params["lltv_raw"], "rate_per_s": rate, "oracle": params["oracle"], "irm": params["irm"],
           "loan_token": params["loan_token"], "collateral_token": params["collateral_token"],
           "loan_symbol": loan["symbol"], "loan_decimals": loan["decimals"],
           "collateral_symbol": coll["symbol"], "collateral_decimals": coll["decimals"],
           "interest_accrued_seconds": acc["accrued_seconds"],
           "market_totals": {k: acc[k] for k in ("total_supply_assets", "total_borrow_assets", "total_borrow_shares")}}
    deps = dependencies.resolve(rpc, params["oracle"], blk, ts,
                                {"address": params["loan_token"], "symbol": loan["symbol"], "decimals": loan["decimals"]},
                                {"address": params["collateral_token"], "symbol": coll["symbol"], "decimals": coll["decimals"]})
    return {"pos": pos, "deps": deps, "rpc_host": _host(getattr(rpc, "url", "")), "block_hash": b.get("hash")}


# ---- hypothetical policy / reserves ---------------------------------------------------------------------------------
def _raw(d: Decimal, dec: int) -> int:
    return int(d.scaleb(dec))


def _hs(raw: int, dec: int) -> str:
    return format(Decimal(raw).scaleb(-dec), "f")


def hypothetical(req: dict, pos: dict) -> dict:
    """Policy (RescueVault.Policy fields, raw integers), reserves and engine settings; defaults scaled to the position.
    The policy is checked by policy_draft (the same rules as RescueVault.setPolicy)."""
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    lltv = Decimal(pos["lltv"]).scaleb(-18)
    used, am = [], req["amounts"]

    def amt(key, default_raw, dec):
        if am.get(key) is None:
            used.append(key)
            return default_raw
        return _raw(am[key], dec)

    strategies = req["strategies"]
    if strategies is None:
        used.append("strategies")
        strategies = ["REPAY", "TOP_UP"]
    loan_res = amt("loan_reserve", pos["debt"] // 10, ld)
    coll_res = amt("collateral_reserve", pos["collateral"] // 10, cd)
    trig = req["trigger_ltv"]
    if trig is None:
        used.append("trigger_ltv")
        trig = (lltv - Decimal("0.04")).quantize(Decimal("0.0001"))
        if trig <= 0:
            raise DryRunError("invalid_policy", 400, "market LLTV too low for the default trigger: pass trigger_ltv",
                              field="trigger_ltv")
    mla = req["min_ltv_after"]
    if mla is None:
        used.append("min_ltv_after")
        mla = max(min(Decimal("0.40"), trig - Decimal("0.10")), Decimal(0)).quantize(Decimal("0.0001"))
    per_repay = amt("max_repay_per_action", loan_res, ld)
    per_top = amt("max_top_up_per_action", coll_res, cd)
    full = amt("max_full_repay", loan_res if "FULL_REPAY" in strategies else 0, ld)
    rep_total = amt("max_repay_total", max(per_repay, full), ld)
    top_total = amt("max_top_up_total", per_top, cd)
    min_lr, min_cr = amt("min_loan_reserve", 0, ld), amt("min_collateral_reserve", 0, cd)
    margin = amt("safety_margin", pos["debt"] // 100, ld)
    valid_days = req["valid_days"] if req["valid_days"] is not None else Decimal(30)
    cooldown = req["cooldown_s"] if req["cooldown_s"] is not None else 3_600
    horizon = req["interest_horizon_s"] if req["interest_horizon_s"] is not None else 86_400
    for k, v in (("valid_days", req["valid_days"]), ("cooldown_s", req["cooldown_s"]),
                 ("interest_horizon_s", req["interest_horizon_s"])):
        if v is None:
            used.append(k)
    pol = {"allowed_strategies": sum(engine.BITS[s] for s in strategies),
           "valid_until": pos["timestamp"] + int(valid_days * 86_400), "cooldown": cooldown,
           "trigger_ltv": int(trig.scaleb(18)), "min_ltv_after": int(mla.scaleb(18)),
           "max_repay_per_action": per_repay, "max_top_up_per_action": per_top, "max_full_repay": full,
           "max_repay_total": rep_total, "max_top_up_total": top_total, "min_loan_reserve": min_lr,
           "min_collateral_reserve": min_cr}
    draft = policy_draft({"loan_decimals": ld, "collateral_decimals": cd, "lltv": str(lltv), "strategies": ",".join(strategies),
                          "valid_days": str(valid_days), "cooldown_s": str(cooldown), "trigger_ltv": str(trig),
                          "min_ltv_after": str(mla), **{k: _hs(pol[k], cd if "top_up" in k or "collateral" in k else ld)
                                                        for k in contracts.POLICY_FIELDS[5:]}})
    if draft["errors"]:
        raise DryRunError("invalid_policy", 400, "hypothetical policy rejected by the RescueVault.setPolicy rules: "
                          + "; ".join(draft["errors"]), errors=draft["errors"])
    vault = {"address": ZERO, "policy": pol, "policy_nonce": 1, "keeper": ZERO, "paused": False, "revoked": False,
             "repaid_total": 0, "topped_up_total": 0, "last_action_at": 0, "loan_reserve": loan_res,
             "collateral_reserve": coll_res}
    ecfg = engine.EngineConfig(safety_margin_raw=margin, interest_horizon_s=horizon, allow_partial=req["allow_partial"],
                               ranking=req["ranking"])
    return {"vault": vault, "ecfg": ecfg, "strategies": strategies, "defaults_used": used, "warnings": draft["warnings"]}


def _scenarios(req: dict, deps: dict, pos: dict) -> list:
    drop = req["follow_on_drop"] if req["follow_on_drop"] is not None else Decimal("0.08")
    dep = req["follow_on_dependency"] or "collateral"
    if drop == 0:
        return dependencies.build_scenarios(deps, [])
    try:
        _, applied = dependencies.price_factor(deps, [{"dependency": dep, "drop": float(drop)}])
    except ValueError:
        avail = ["collateral"] + [f["role"] for f in deps["feeds"]] + [f["description"] for f in deps["feeds"] if f.get("description")]
        raise DryRunError("invalid_input", 400, f"follow_on_dependency: '{dep}' is not a dependency of this market's oracle",
                          field="follow_on_dependency", available=avail) from None
    label = (f"{pos['collateral_symbol']} oracle price" if dep.lower() == "collateral" else applied[0]["label"])
    return dependencies.build_scenarios(deps, [{"id": "follow_on", "label": f"{label} -{float(drop):.0%} follow-on",
                                                "shocks": [{"dependency": dep, "drop": float(drop)}]}])


# ---- views -----------------------------------------------------------------------------------------------------------
def _px(raw: int | None, pos: dict) -> float | None:
    """Oracle price (1e36 scale, loan raw per collateral raw) -> loan tokens per collateral token."""
    return None if raw is None else raw / 1e36 * 10 ** (pos["collateral_decimals"] - pos["loan_decimals"])


def _w(x: int | None) -> float | None:
    return None if x is None else int(x) / 1e18


def position_view(pos: dict) -> dict:
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    C, D, P, L = pos["collateral"], pos["debt"], pos["price"], pos["lltv"]
    mb = engine.max_borrow(C, P, L)
    ev = engine.evaluate(pos, [engine.Scenario("now", "now", engine.WAD)], engine.EngineConfig(0, 0))
    rate = pos["rate_per_s"]
    return {"label": "LIVE", "borrower": pos["beneficiary"], "has_debt": pos["borrow_shares"] > 0,
            "collateral": _h(C, cd), "collateral_symbol": pos["collateral_symbol"],
            "collateral_value": _h(engine.collateral_value(C, P), ld), "debt": _h(D, ld), "debt_symbol": pos["loan_symbol"],
            "ltv": _w(engine.ltv_wad(D, C, P)), "lltv": _w(L), "max_borrow": _h(mb, ld), "buffer": _h(mb - D, ld),
            "healthy": mb >= D, "health_factor": (mb / D) if D else None, "oracle_price": _px(P, pos),
            "liquidation_price": _px(ev["liquidation_price"], pos), "drop_to_liquidation": _w(ev["drop_to_liquidation_wad"]),
            "borrow_apr_onchain": None if rate is None else rate * 365 * 86_400 / 1e18,
            "interest_accrued_seconds": pos["interest_accrued_seconds"],
            "raw": {"collateral": C, "debt": D, "borrow_shares": pos["borrow_shares"], "price": P, "lltv": L,
                    "rate_per_s": rate},
            "source": f"Morpho Blue {pos['morpho']} position / market / idToMarketParams + IRM borrowRateView + oracle "
                      f"price() @ block {pos['block']} (interest accrued to the block timestamp)"}


def market_view(pos: dict, alias: str | None, deps: dict) -> dict:
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    t = pos["market_totals"]
    return {"label": "LIVE", "id": pos["market_id"], "name": alias or f"{pos['collateral_symbol']}/{pos['loan_symbol']}",
            "loan": {"symbol": pos["loan_symbol"], "decimals": ld, "address": pos["loan_token"]},
            "collateral": {"symbol": pos["collateral_symbol"], "decimals": cd, "address": pos["collateral_token"]},
            "oracle": pos["oracle"], "oracle_type": deps["oracle"].get("type"), "irm": pos["irm"], "lltv": _w(pos["lltv"]),
            "total_borrow": _h(t["total_borrow_assets"], ld), "total_supply": _h(t["total_supply_assets"], ld),
            "url": f"https://app.morpho.org/ethereum/market/{pos['market_id']}"}


def dependencies_view(deps: dict) -> dict:
    fr = {}
    for f in deps["feeds"]:
        fr.setdefault(f.get("freshness") or "unknown", []).append(f.get("description") or f["role"])
    return {"label": "LIVE", "oracle": deps["oracle"], "feeds": deps["feeds"], "vaults": deps["vaults"],
            "assumptions": deps["assumptions"], "stale": deps["stale"], "simulated": deps["simulated"],
            "freshness": fr, "graph": deps["graph"], "block": deps["block"]}


def hypothetical_view(h: dict, pos: dict, scen: list, req: dict) -> dict:
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    p, v, e = h["vault"]["policy"], h["vault"], h["ecfg"]
    warnings = list(h["warnings"])
    if req["ignored"]:
        warnings.append(f"ignored unknown parameter(s): {', '.join(req['ignored'])}")
    return {"label": "DRY-RUN", "note": "no RescueVault exists for this borrower: this policy and these reserves are "
                                        "hypothetical; the real owner would sign setPolicy with their own wallet",
            "policy": {"strategies": h["strategies"], "trigger_ltv": _w(p["trigger_ltv"]), "min_ltv_after": _w(p["min_ltv_after"]),
                       "valid_until": p["valid_until"], "cooldown_s": p["cooldown"],
                       "max_repay_per_action": _h(p["max_repay_per_action"], ld),
                       "max_top_up_per_action": _h(p["max_top_up_per_action"], cd),
                       "max_full_repay": _h(p["max_full_repay"], ld), "max_repay_total": _h(p["max_repay_total"], ld),
                       "max_top_up_total": _h(p["max_top_up_total"], cd), "min_loan_reserve": _h(p["min_loan_reserve"], ld),
                       "min_collateral_reserve": _h(p["min_collateral_reserve"], cd)},
            "reserves": {"loan": _h(v["loan_reserve"], ld), "loan_symbol": pos["loan_symbol"],
                         "collateral": _h(v["collateral_reserve"], cd), "collateral_symbol": pos["collateral_symbol"]},
            "engine": {"safety_margin": _h(e.safety_margin_raw, ld), "interest_horizon_s": e.interest_horizon_s,
                       "ranking": e.ranking, "preference": list(e.preference), "allow_partial": e.allow_partial},
            "scenarios": [{"id": s.id, "label": s.label, "price_factor": s.factor_wad / 1e18, "shocks": s.shocks} for s in scen],
            "defaults_used": req["defaults_used"] + h["defaults_used"], "default_rules": DEFAULT_RULES, "warnings": warnings}


def watcher_view(pl: dict | None, deps: dict, pos: dict) -> dict:
    """Same state rule as Watcher.cycle: HOLD inside the target -> WATCHING, anything else -> DETECTED -> PLANNING ->
    NO_ACTION (stale feeds / engine NO_ACTION) or the action the keeper would validate and send (here: nothing)."""
    ld = pos["loan_decimals"]
    if pl is None:
        return {"label": "DRY-RUN", "state": "WATCHING", "path": ["WATCHING"], "outcome": "NOTHING_TO_PROTECT",
                "reason": "the borrower has no debt on this market at this block: nothing to protect"}
    trig = {"ltv": _w(pl["ltv_now"]), "trigger_ltv": _w(pl["trigger_ltv"]), "trigger_met": pl["trigger_met"],
            "scenario_breaches": [{"label": r["label"], "buffer": _h(r["buffer"], ld)}
                                  for r in pl["hold"]["scenarios"] if not r["meets_margin"]]}
    if pl["decision"] == "HOLD":
        return {"label": "DRY-RUN", "state": "WATCHING", "path": ["WATCHING"], "outcome": "HOLD", "reason": pl["why"],
                "trigger": trig}
    path = ["WATCHING", "DETECTED", "PLANNING"]
    if deps["stale"]:
        outcome, reason = "NO_ACTION", (f"stale or unreadable oracle feed(s) {deps['stale']}: the keeper refuses to act on a "
                                        "price that may be wrong")
    elif pl["decision"] != "EXECUTE":
        outcome, reason = "NO_ACTION", pl["why"]
    else:
        outcome, reason = "WOULD_EXECUTE", pl["why"]
        path.append("VALIDATING (skipped in dry-run: no RescueVault to simulate against)")
    path.append(outcome)
    return {"label": "DRY-RUN", "state": "DETECTED", "path": path, "outcome": outcome, "reason": reason, "trigger": trig,
            "signed": False, "broadcast": False}


def _chosen_view(ch: dict | None, pos: dict) -> dict | None:
    if not ch:
        return None
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    a, m = ch.get("after") or {}, ch.get("metrics") or {}
    return {"strategy": ch["strategy"], "amount": _h(ch["amount_raw"], cd if ch["strategy"] == "TOP_UP" else ld),
            "token": (ch.get("token") or {}).get("symbol"), "ltv_after": _w(a.get("ltv_now")),
            "worst_buffer_after": _h(a.get("min_buffer"), ld), "meets_target": a.get("meets_target"),
            "capital_committed": _h(m.get("capital_committed_raw"), ld)}


def decision_view(pl: dict | None, pos: dict) -> dict | None:
    if pl is None:
        return None
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    hold = pl["hold"]
    return {"label": "DRY-RUN", "decision": pl["decision"], "why": pl["why"], "alert": pl.get("alert", False),
            "partial_protection": pl.get("partial_protection", False), "rule": pl["rule"], "ranking": pl["ranking"],
            "preference": pl["preference"], "safety_margin": _h(pl["safety_margin_raw"], ld),
            "interest_horizon_s": pl["interest_horizon_s"],
            "scenarios": [{"id": s["id"], "label": s["label"], "price_factor": s["factor_wad"] / 1e18, "shocks": s["shocks"]}
                          for s in pl["scenarios"]],
            "hold": {"worst_buffer": _h(hold["min_buffer"], ld),
                     "hypothetical_penalty": _h(hold["hypothetical_liquidation_penalty_raw"], ld),
                     "scenarios": [{"label": r["label"], "buffer": _h(r["buffer"], ld), "liquidatable": r["liquidatable"],
                                    "ltv": _w(r["ltv"])} for r in hold["scenarios"]]},
            "candidates": [_cand_view(c, ld, cd) for c in pl["candidates"]], "chosen": _chosen_view(pl.get("chosen"), pos)}


def reserve_needs(pos: dict, scen: list, ecfg, vault: dict) -> list[dict]:
    """After a first hit h on the collateral oracle price: LTV, the minimal repay / top-up that keeps the follow-on
    scenarios inside the margin (same exact engine), whether the hypothetical reserves cover it, and what the keeper
    would decide under the hypothetical policy."""
    ld, cd = pos["loan_decimals"], pos["collateral_decimals"]
    out = []
    for hit in FIRST_HITS:
        ph = {**pos, "price": pos["price"] * (10_000 - int(round(hit * 10_000))) // 10_000}
        r, q = engine.min_repay(ph, scen, ecfg), engine.min_top_up(ph, scen, ecfg)
        ltv = engine.ltv_wad(ph["debt"], ph["collateral"], ph["price"])
        pl = engine.plan(ph, vault, scen, ecfg)
        ch = _chosen_view(pl.get("chosen"), pos)
        out.append({"first_hit": hit, "ltv_after_hit": _w(ltv),
                    "trigger_met_after_hit": ltv is None or ltv >= vault["policy"]["trigger_ltv"],
                    "liquidatable_after_hit": engine.max_borrow(ph["collateral"], ph["price"], ph["lltv"]) < ph["debt"],
                    "min_repay": _h(r, ld), "repay_possible": r is not None, "min_top_up": _h(q, cd),
                    "min_top_up_value": _h(engine.collateral_value(q, ph["price"]) if q else 0, ld),
                    "full_repay": _h(ph["debt"], ld),
                    "hypothetical_reserves_cover": {"repay": r is not None and r <= vault["loan_reserve"],
                                                    "top_up": q is not None and q <= vault["collateral_reserve"]},
                    "keeper_would": {"decision": pl["decision"], "strategy": (ch or {}).get("strategy"),
                                     "amount": (ch or {}).get("amount"), "token": (ch or {}).get("token"), "why": pl["why"]}})
    return out


# ---- entry points ----------------------------------------------------------------------------------------------------
def build(live: dict, req: dict, borrower: dict) -> dict:
    pos, deps = live["pos"], live["deps"]
    h = hypothetical(req, pos)
    scen = _scenarios(req, deps, pos)
    has_debt = pos["borrow_shares"] > 0
    pl = engine.plan(pos, h["vault"], scen, h["ecfg"], keeper=None) if has_debt else None
    return {"schema": SCHEMA, "status": "ok", "mode": "DRY-RUN", "labels": LABELS,
            "environment": {"label": "LIVE", "chain_id": 1, "network": "Ethereum mainnet", "block": pos["block"],
                            "block_timestamp": pos["timestamp"], "block_hash": live.get("block_hash"),
                            "rpc_host": live["rpc_host"], "read_only": True, "signed": False, "broadcast": False,
                            "methods": ["eth_chainId", "eth_getBlockByNumber", "eth_call"]},
            "market": market_view(pos, req["market_alias"], deps), "borrower": borrower,
            "position": position_view(pos), "dependencies": dependencies_view(deps),
            "hypothetical": hypothetical_view(h, pos, scen, req), "watcher": watcher_view(pl, deps, pos),
            "decision": decision_view(pl, pos),
            "reserve_requirements": reserve_needs(pos, scen, h["ecfg"], h["vault"]) if has_debt else [],
            "not_done": ["no RescueVault exists for this borrower: policy and reserves are hypothetical",
                         "VALIDATING skipped: no vault action to simulate with eth_call, no gas / fee check",
                         "nothing signed, nothing sent: this endpoint holds no key"],
            "served_at": time.time()}


def run(q: dict, rpcs: list | None = None, top=None) -> dict:
    """Validate -> pick the borrower (input or Morpho API) -> read mainnet on the first answering endpoint -> plan."""
    t0 = time.time()
    req = parse_request(q)
    if req["borrower"]:
        borrower = {"address": req["borrower"], "source": "input"}
    else:
        borrower = pick_borrower(req["market_id"], req["rank"], top)
        req["defaults_used"].append("borrower")
    attempts = []
    for rpc in (rpcs if rpcs is not None else endpoints()):
        try:
            live = read_live(rpc, req["market_id"], borrower["address"])
        except RevertError as e:  # a real EVM answer: another endpoint would return the same
            raise DryRunError("onchain_read_failed", 502, f"a mainnet read reverted: {e}"[:300]) from None
        except RPCError as e:
            attempts.append(f"{_host(getattr(rpc, 'url', ''))}: {e}"[:200])
            continue
        out = build(live, req, borrower)
        out["elapsed_s"] = round(time.time() - t0, 3)
        return _js(out)
    raise DryRunError("mainnet_unavailable", 503, "no Ethereum mainnet RPC answered: nothing is shown rather than stale "
                      "data", attempts=attempts)


def summary_text(o: dict) -> str:
    m, p, w, b, e = o["market"], o["position"], o["watcher"], o["borrower"], o["environment"]
    ls, cs = p["debt_symbol"], p["collateral_symbol"]

    def pct(x):
        return "n/a" if x is None else f"{x:.2%}"

    lines = [f"DRY-RUN (nothing signed or sent) | LIVE Ethereum mainnet block {e['block']:,} via {e['rpc_host']}",
             f"market    {m['name']} {m['id']} LLTV {pct(m['lltv'])} oracle {m['oracle_type']}",
             f"borrower  {b['address']} ({b.get('how') or 'given'})",
             f"position  {p['collateral']:,.6f} {cs} (value {p['collateral_value']:,.2f} {ls}) | debt {p['debt']:,.2f} {ls} | "
             f"LTV {pct(p['ltv'])} | buffer {p['buffer']:,.2f} {ls} | liquidation after {pct(p['drop_to_liquidation'])} drop"]
    for f in o["dependencies"]["feeds"]:
        lines.append(f"feed      {f.get('description') or f['role']}: {f.get('freshness')}"
                     + (f" (age {f['age_s']} s)" if f.get("age_s") is not None else ""))
    for a in o["dependencies"]["assumptions"]:
        lines.append(f"assumes   {a}")
    hp = o["hypothetical"]
    lines.append(f"policy    (hypothetical) trigger {pct(hp['policy']['trigger_ltv'])}, floor {pct(hp['policy']['min_ltv_after'])}, "
                 f"{','.join(hp['policy']['strategies'])}; reserves {hp['reserves']['loan']:,.2f} {ls} + "
                 f"{hp['reserves']['collateral']:,.6f} {cs}; margin {hp['engine']['safety_margin']:,.2f} {ls}")
    lines.append(f"watcher   {' -> '.join(w['path'])}: {w['reason']}")
    d = o.get("decision")
    if d and d.get("chosen"):
        c = d["chosen"]
        lines.append(f"decision  {d['decision']} {c['strategy']} {c['amount']:,.6f} {c['token']} -> LTV {pct(c['ltv_after'])}")
    for r in o["reserve_requirements"]:
        k = r["keeper_would"]
        rep = "n/a" if r["min_repay"] is None else f"{r['min_repay']:,.2f}"
        top = "n/a" if r["min_top_up"] is None else f"{r['min_top_up']:,.6f}"
        act = f" {k['strategy']} {k['amount']:,.4f} {k['token']}" if k["strategy"] else ""
        lines.append(f"hit -{r['first_hit']:.0%}   LTV {pct(r['ltv_after_hit'])} | min repay {rep} {ls} | "
                     f"min top-up {top} {cs} | keeper: {k['decision']}{act}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m defirisk.countermove dry-run",
                                 description="Countermove DRY-RUN on a real Ethereum-mainnet Morpho Blue borrower "
                                             "(read-only: nothing is signed or sent)")
    ap.add_argument("--market", help=f"market id (0x + 64 hex) or alias: {', '.join(MARKETS)} (default {DEFAULT_MARKET})")
    ap.add_argument("--borrower", default="auto", help="0x address, or 'auto' = largest borrower (Morpho API)")
    ap.add_argument("--rank", help="with --borrower auto: 1 = largest borrower, 2 = second largest, ...")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="any API parameter, e.g. --set trigger_ltv=0.7 --set loan_reserve=50000 --set strategies=REPAY")
    ap.add_argument("--json", action="store_true", help="print the full JSON payload")
    a = ap.parse_args(argv)
    q = {k: v for k, v in (("market", a.market), ("borrower", a.borrower), ("rank", a.rank)) if v is not None}
    for kv in a.set:
        k, sep, v = kv.partition("=")
        if not sep:
            ap.error(f"--set expects KEY=VALUE, got {kv!r}")
        q[k.strip()] = v.strip()
    try:
        out = run(q)
    except DryRunError as e:
        print(json.dumps(e.to_dict(), indent=1), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, allow_nan=False) if a.json else summary_text(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
