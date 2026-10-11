"""Read-only ARM PROTECTION status endpoints (GET /api/countermove?action=evidence | keeper-status | policy-status).

Nothing here signs, sends or writes. Server-side configuration only (never a URL from the request: no SSRF):
  FAULTLINE_KEEPER_HEALTH    path of the keeper service's health.json      (unset -> keeper UNAVAILABLE)
  FAULTLINE_EVIDENCE_DB      path of the keeper's SQLite evidence store    (unset -> store UNAVAILABLE)
  FAULTLINE_ARM_RPC_URL      JSON-RPC of the chain the RescueVault lives on (unset -> vault UNAVAILABLE)
  FAULTLINE_ARM_ENVIRONMENT  label for that chain when it is local: local-test (default) | fork
On Vercel none of these exist (stateless functions, no keeper process): the answers say UNAVAILABLE, with the reason,
instead of pretending a protection is armed or monitored. The recorded fork run is always served, labelled `fork`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import contracts, lifecycle, policy
from .api import DEMO, _entries, _js
from .chain import RPC, RPCError
from .evidence import EvidenceStore, classify
from .service import read_health

_POS = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_POLICY_KEYS = ("strategies", "trigger_ltv", "min_ltv_after", "lltv", "max_repay_per_action", "max_top_up_per_action",
                "max_full_repay", "max_repay_total", "max_top_up_total", "min_loan_reserve", "min_collateral_reserve")


def _int_param(q: dict, k: str, default: int, lo: int, hi: int) -> int:
    v = q.get(k)
    if v in (None, ""):
        return default
    try:
        n = int(v)
    except ValueError:
        raise ValueError(f"{k} must be an integer") from None
    if not lo <= n <= hi:
        raise ValueError(f"{k} must be within [{lo}, {hi}]")
    return n


def _position(q: dict) -> str | None:
    p = q.get("position") or None
    if p is not None and not _POS.fullmatch(p):
        raise ValueError("invalid position id")
    return p


def _health() -> tuple[dict | None, str | None]:
    path = os.getenv("FAULTLINE_KEEPER_HEALTH")
    if not path:
        return None, ("no keeper service is configured for this deployment (FAULTLINE_KEEPER_HEALTH unset); serverless "
                      "functions cannot host the keeper: run `python -m defirisk.countermove.service` locally")
    h = read_health(path)
    return (h, None) if h else (None, "keeper health file missing or unreadable: the keeper is not running")


def keeper_status(q: dict) -> dict:
    h, why = _health()
    if h is None:
        return {"schema": "faultline.keeper.status/1", "status": "UNAVAILABLE", "reason": why, "monitoring": False}
    st = str(h.get("status")).upper()
    return _js({"schema": "faultline.keeper.status/1", "status": st, "monitoring": st == "OK",
                "reason": {"OK": "fresh heartbeat", "STALE": f"last heartbeat {h['heartbeat_age_s']:.0f}s ago",
                           "STOPPED": "keeper stopped"}.get(st, h.get("note")), "health": h})


def _recorded(position: str | None, limit: int, since: int) -> dict:
    p = DEMO / "journal.jsonl"
    if not p.exists():
        return {"status": "UNAVAILABLE", "reason": "no recorded fork run in this deployment"}
    raw = p.read_bytes()
    es = _entries(DEMO)
    summary = json.loads((DEMO / "summary.json").read_text(encoding="utf-8")) if (DEMO / "summary.json").exists() else {}
    rows = []
    for i, e in enumerate(es, 1):
        if i <= since or (position and e.get("position") != position):
            continue
        rows.append({"seq": i, "environment": "fork", "kind": classify(e), "state": e.get("state"),
                     "position": e.get("position"), "ts": e.get("ts"), "tx_hash": e.get("tx_hash"), "block": e.get("block"),
                     "event": e.get("event"), "reason": e.get("reason") or e.get("why") or e.get("note")})
        if len(rows) >= limit:
            break
    return {"status": "ok", "source": "recorded local mainnet-fork run (read-only, never rewritten)", "environment": "fork",
            "fork": (summary.get("environment") or {}).get("fork"), "generated_at": summary.get("generated_at"),
            "integrity": {"journal_sha256": hashlib.sha256(raw).hexdigest(), "records": len(es)}, "events": rows,
            "next_since": rows[-1]["seq"] if rows else since}


def _store(position: str | None, limit: int, since: int, kinds: list[str] | None) -> dict:
    path = os.getenv("FAULTLINE_EVIDENCE_DB")
    if not path:
        return {"status": "UNAVAILABLE", "reason": "no evidence store configured for this deployment (FAULTLINE_EVIDENCE_DB unset)"}
    try:
        st = EvidenceStore(path, readonly=True)
    except FileNotFoundError:
        return {"status": "UNAVAILABLE", "reason": "evidence store file not found"}
    try:
        rows = st.query(position=position, kinds=kinds, since_seq=since, limit=limit)
        integrity = st.verify()
    finally:
        st.close()
    return {"status": "ok", "source": "keeper evidence store (SQLite, append-only, hash-chained)", "integrity": integrity,
            "events": rows, "next_since": rows[-1]["seq"] if rows else since}


def evidence(q: dict) -> dict:
    position = _position(q)
    limit = _int_param(q, "limit", 200, 1, 500)
    since = _int_param(q, "since", 0, 0, 10 ** 12)
    source = q.get("source") or "all"
    if source not in ("all", "recorded", "store"):
        raise ValueError("source must be one of all, recorded, store")
    kinds = [k for k in (q.get("kinds") or "").split(",") if k] or None
    out = {"schema": "faultline.countermove.evidence/1",
           "labels": {"fork": "local Anvil fork of mainnet at a pinned block, test funds (SIMULATED)",
                      "local-test": "local Anvil chain with test contracts (SIMULATED)",
                      "mainnet-readonly": "read from Ethereum mainnet; FAULTLINE never transacts there"}}
    if source in ("all", "recorded"):
        out["recorded"] = _recorded(position, limit, since)
    if source in ("all", "store"):
        out["store"] = _store(position, limit, since, kinds)
    return _js(out)


def policy_status(q: dict) -> dict:
    from ..vault_input import parse_address
    vault = parse_address(q.get("vault"))["address"]
    draft = policy.validate(q) if any(k in q for k in _POLICY_KEYS) else None
    requirement = None
    if q.get("required_loan_raw") or q.get("required_collateral_raw"):
        requirement = {}
        for k in ("required_loan_raw", "required_collateral_raw"):
            v = q.get(k) or "0"
            if not v.isdigit() or len(v) > 78:
                raise ValueError(f"{k} must be a non-negative integer (raw token units)")
            requirement[k.replace("required_", "")] = int(v)
    health, health_why = _health()
    pos = next((p for p in (health or {}).get("positions", []) if str(p.get("vault", "")).lower() == vault.lower()), None)
    url = os.getenv("FAULTLINE_ARM_RPC_URL")
    v, verr, chain = None, None, None
    if not url:
        verr = "no RPC configured for the RescueVault chain in this deployment (FAULTLINE_ARM_RPC_URL unset)"
    else:
        try:
            rpc = RPC(url, timeout=8.0, retries=1)
            cid = rpc.chain_id()
            head = rpc.block("latest")
            env = os.getenv("FAULTLINE_ARM_ENVIRONMENT", "local-test") if cid in (31337, 1337) else (
                "mainnet-readonly" if cid == 1 else "unsupported")
            chain = {"chain_id": cid, "environment": env, "head_block": head["number"], "head_timestamp": head["timestamp"]}
            if rpc.code(vault) in ("0x", "", None):
                v = {"address": vault, "code_present": False}
            else:
                v = {**contracts.read_vault(rpc, vault), "code_present": True}
        except (RPCError, OSError, ValueError) as e:
            verr = f"vault read failed: {str(e)[:200]}"
    res = lifecycle.derive(draft=draft, vault=v, vault_error=verr, requirement=requirement, health=health,
                           journal_last=(pos or {}).get("last_event"), finality=(pos or {}).get("finality"), chain=chain,
                           last_terminal=(pos or {}).get("last_terminal"))
    res["vault_address"] = vault
    res["keeper"] = {"status": (health or {}).get("status", "UNAVAILABLE"), "reason": health_why,
                     "heartbeat_age_s": (health or {}).get("heartbeat_age_s"), "watching_this_vault": pos is not None}
    if v and v.get("code_present"):
        res["vault"] = {k: v[k] for k in ("policy_nonce", "keeper", "paused", "revoked", "loan_reserve", "collateral_reserve",
                                          "repaid_total", "topped_up_total", "last_action_at", "action_count", "owner", "lltv")}
        res["vault"]["policy"] = v["policy"]
    return _js(res)
