"""ARM PROTECTION lifecycle: one state per protected position, DERIVED from evidence, never set by hand.

Evidence, in priority order (a later layer can only refine an earlier one, never contradict it):
  1. the policy draft validation           -> DRAFT / VALIDATED
  2. the RescueVault read on-chain         -> AWAITING_AUTHORIZATION / AWAITING_RESERVES / ARMED, or PAUSED / REVOKED /
                                              EXPIRED (owner controls and expiry always win)
  3. the keeper heartbeat (health file)    -> MONITORING only while a live keeper process is watching THIS vault
  4. the keeper journal + finality record  -> TRIGGERED / EVALUATING / EXECUTING / VERIFIED / FAILED
UNAVAILABLE means the evidence needed to say anything is missing (RPC down, no deployment-side configuration):
it is never rendered as "safe" or "armed".

ARMED requires all of: contract code at the vault address, a policy signed by the owner (policy_nonce > 0), a keeper
authorized on-chain, not paused, not revoked, not expired, reserves at or above the requirement (when one is given).
VERIFIED requires a CONFIRMED journal record (receipt + verifier) AND the receipt still in the canonical chain after the
configured confirmation depth (service.Finality). A CONFIRMED record without finality stays EXECUTING.
"""
from __future__ import annotations

import time

STATES = ("DRAFT", "VALIDATED", "AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED", "MONITORING", "TRIGGERED",
          "EVALUATING", "EXECUTING", "VERIFIED", "PAUSED", "REVOKED", "EXPIRED", "FAILED", "UNAVAILABLE")
_OWNER = {"PAUSED", "REVOKED", "EXPIRED", "UNAVAILABLE"}
ALLOWED = {  # state -> states it may move to next (owner actions, expiry and loss of evidence are always possible)
    "DRAFT": {"DRAFT", "VALIDATED"},
    "VALIDATED": {"DRAFT", "VALIDATED", "AWAITING_AUTHORIZATION"},
    "AWAITING_AUTHORIZATION": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED"},
    "AWAITING_RESERVES": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED"},
    "ARMED": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED", "MONITORING"},
    "MONITORING": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED", "MONITORING", "TRIGGERED"},
    "TRIGGERED": {"ARMED", "MONITORING", "TRIGGERED", "EVALUATING"},
    "EVALUATING": {"ARMED", "MONITORING", "TRIGGERED", "EVALUATING", "EXECUTING"},
    "EXECUTING": {"ARMED", "EXECUTING", "VERIFIED", "FAILED"},
    "VERIFIED": {"AWAITING_RESERVES", "ARMED", "MONITORING", "VERIFIED", "TRIGGERED", "FAILED"},
    "FAILED": {"AWAITING_RESERVES", "ARMED", "MONITORING", "FAILED", "TRIGGERED"},
    "PAUSED": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED", "MONITORING", "PAUSED"},
    "REVOKED": {"REVOKED"},  # irreversible on-chain
    "EXPIRED": {"AWAITING_AUTHORIZATION", "AWAITING_RESERVES", "ARMED", "MONITORING", "EXPIRED"},  # owner re-signs
    "UNAVAILABLE": set(STATES),
}
for _s in STATES:
    if _s != "REVOKED":
        ALLOWED[_s] = ALLOWED[_s] | _OWNER
_JOURNAL = {"DETECTED": "TRIGGERED", "PLANNING": "EVALUATING", "VALIDATING": "EVALUATING", "EXECUTING": "EXECUTING"}
_ACTIVE = set(_JOURNAL)


def can_transition(a: str, b: str) -> bool:
    return b in ALLOWED.get(a, set())


def _gate(gates: list, name: str, ok: bool | None, detail: str) -> bool | None:
    gates.append({"gate": name, "ok": ok, "detail": detail})
    return ok


def derive(*, draft: dict | None = None, vault: dict | None = None, vault_error: str | None = None,
           requirement: dict | None = None, health: dict | None = None, journal_last: dict | None = None,
           finality: dict | None = None, now: float | None = None, chain: dict | None = None,
           last_terminal: dict | None = None) -> dict:
    """draft: policy.validate() output. vault: contracts.read_vault() output plus 'code_present' (bool).
    requirement: {'loan_raw', 'collateral_raw'} reserves needed (optional). health: service.read_health() output.
    journal_last: the latest keeper journal record for this position; last_terminal: its latest CONFIRMED / FAILED /
    NO_ACTION outcome ({'state', 'at', 'reason', 'tx_hash'}). finality: {'status': 'final'|'pending'|'reorged',
    'tx_hash', 'confirmations'} for the latest CONFIRMED tx. chain: {'chain_id', 'environment'} labels."""
    now = time.time() if now is None else now
    gates: list[dict] = []
    out = {"schema": "faultline.countermove.lifecycle/1", "chain": chain, "gates": gates, "derived_at": now}

    def done(state: str, reason: str, **extra) -> dict:
        return {**out, "state": state, "reason": reason, "armed": state in ARMED_STATES,
                "monitoring": state in MONITORED_STATES, **extra}

    if draft is not None and _gate(gates, "draft_valid", not draft["errors"],
                                   "; ".join(e["message"] for e in draft["errors"]) or "policy draft passes every rule") is False:
        if vault is None:
            return done("DRAFT", "the policy draft has errors: fix them before signing")
    if vault_error:
        _gate(gates, "vault_readable", False, vault_error)
        return done("UNAVAILABLE", f"cannot read the vault on-chain: {vault_error}")
    if vault is None:
        if draft is None:
            return done("UNAVAILABLE", "no draft and no vault: nothing to evaluate")
        return done("VALIDATED", "draft valid; no RescueVault read yet (deploy it and let the owner sign setPolicy)")
    if not _gate(gates, "vault_code", bool(vault.get("code_present", True)), f"contract code at {vault.get('address')}"):
        return done("AWAITING_AUTHORIZATION", "no contract code at the vault address")
    if _gate(gates, "not_revoked", not vault["revoked"], "owner revoked automation (irreversible)" if vault["revoked"]
             else "not revoked") is False:
        return done("REVOKED", "the owner revoked automation on-chain (irreversible)")
    pol = vault["policy"]
    if not _gate(gates, "policy_signed", vault["policy_nonce"] > 0, f"policy nonce {vault['policy_nonce']}"):
        return done("AWAITING_AUTHORIZATION", "no policy signed by the owner (policy_nonce = 0)")
    if draft is not None and draft.get("policy"):
        from .policy import matches
        diff = matches(pol, draft["policy"])
        if not _gate(gates, "policy_matches_draft", not diff, "differs: " + ", ".join(diff) if diff else "on-chain policy = draft"):
            return done("AWAITING_AUTHORIZATION", "the on-chain policy differs from the validated draft: " + ", ".join(diff))
    if _gate(gates, "not_paused", not vault["paused"], "paused by the owner" if vault["paused"] else "not paused") is False:
        return done("PAUSED", "the owner paused automation on-chain")
    head_ts = (chain or {}).get("head_timestamp") or now
    if not _gate(gates, "not_expired", pol["valid_until"] > head_ts, f"valid until {pol['valid_until']} (chain time {int(head_ts)})"):
        return done("EXPIRED", "the policy expired: the owner must sign a new one")
    if not _gate(gates, "keeper_authorized", int(vault["keeper"], 16) != 0, f"keeper {vault['keeper']}"):
        return done("AWAITING_AUTHORIZATION", "no keeper authorized on the vault")
    if health and health.get("keeper") and health["keeper"].lower() != vault["keeper"].lower():
        _gate(gates, "keeper_matches_service", False, f"service signs as {health['keeper']}, vault expects {vault['keeper']}")
        return done("AWAITING_AUTHORIZATION", "the running keeper is not the vault's authorized keeper")
    if requirement:
        short = []
        for side, have_k, floor_k in (("loan", "loan_reserve", "min_loan_reserve"), ("collateral", "collateral_reserve",
                                                                                     "min_collateral_reserve")):
            need = int(requirement.get(f"{side}_raw") or 0)
            if need:
                have, floor = int(vault[have_k]), int(pol[floor_k])
                if have < need + floor:
                    short.append(f"{side} reserve {have} < required {need} + floor {floor}")
        if not _gate(gates, "reserves_sufficient", not short, "; ".join(short) or "reserves cover the requirement"):
            return done("AWAITING_RESERVES", "reserves below the requirement: " + "; ".join(short))
    else:
        _gate(gates, "reserves_sufficient", None, "no reserve requirement supplied: not checked")
    hb = (health or {}).get("status")
    watched = bool(health) and any(str(p.get("vault", "")).lower() == vault["address"].lower() for p in health.get("positions", []))
    if not _gate(gates, "keeper_heartbeat", hb == "ok" and watched,
                 "no keeper health record" if not health else f"keeper {hb}, watching this vault: {watched}"):
        why = ("no keeper heartbeat" if not health else f"keeper status {hb}" + ("" if watched else ", not watching this vault"))
        return done("ARMED", f"armed on-chain, but NOT monitored ({why}): nothing will react to a shock")
    last = journal_last or {}
    js = last.get("state")
    ev = _slim(last) if last else None
    if js in _ACTIVE:  # a decision is in flight right now
        return done(_JOURNAL[js], last.get("reason") or last.get("note") or js.lower(), last_event=ev)
    # the watcher logs WATCHING every tick after an outcome, so the outcome comes from the last TERMINAL record
    term = last if js in ("CONFIRMED", "FAILED", "NO_ACTION") else (last_terminal or {})
    ts = term.get("state")
    if ts == "CONFIRMED":
        f = finality or {}
        if f.get("tx_hash") and term.get("tx_hash") and f["tx_hash"].lower() != str(term["tx_hash"]).lower():
            f = {}
        if f.get("status") == "final":
            return done("VERIFIED", f"last action verified on-chain and final ({f.get('confirmations')} confirmations); "
                        "the keeper keeps watching", last_event=ev, last_terminal=_slim(term), finality=f)
        if f.get("status") == "reorged":
            return done("FAILED", "the confirmed action was removed by a chain reorganisation", last_event=ev,
                        last_terminal=_slim(term), finality=f)
        return done("EXECUTING", "receipt and verification passed; waiting for the confirmation depth before VERIFIED",
                    last_event=ev, last_terminal=_slim(term), finality=f or None)
    if ts == "FAILED" and (js == "FAILED" or last.get("event") == "backoff"):
        return done("FAILED", str(term.get("reason") or "last action failed"), last_event=ev, last_terminal=_slim(term),
                    finality=finality if (finality or {}).get("status") == "reorged" else None)
    if js == "NO_ACTION" or last.get("event") == "alert_persists":
        return done("MONITORING", "keeper watching; last trigger ended with NO ACTION: " + str(last.get("reason")),
                    last_event=ev, alert=True)
    return done("MONITORING", "armed on-chain and a live keeper is watching this vault", last_event=ev,
                last_terminal=_slim(term) if term else None)


ARMED_STATES = {"ARMED", "MONITORING", "TRIGGERED", "EVALUATING", "EXECUTING", "VERIFIED", "FAILED"}
MONITORED_STATES = {"MONITORING", "TRIGGERED", "EVALUATING", "EXECUTING", "VERIFIED", "FAILED"}


def _slim(e: dict) -> dict:
    return {k: e.get(k) for k in ("ts", "at", "state", "event", "reason", "tx_hash", "block", "decision") if e.get(k) is not None}
