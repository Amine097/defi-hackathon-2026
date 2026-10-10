"""Guarded Executor: turns ONE engine decision into ONE RescueVault transaction, and nothing else.

Before sending: local-chain guard, eth_call simulation from the keeper at the latest block (a revert is decoded and
reported, nothing is sent), eth_estimateGas against a gas cap, EIP-1559 fee against a fee cap, keeper ETH for gas.
Sending: the signed transaction hash, nonce and action id are journaled BEFORE broadcast. Afterwards a missing receipt
or an RPC error is AMBIGUOUS: `resolve` checks the receipt, then the vault's actionUsed(actionId) and the Morpho/vault
event logs, then the keeper nonce; an uncertain action is never re-planned or re-sent before the chain says it did not
happen. The vault itself rejects a duplicate action id, so even a double broadcast cannot spend twice.
"""
from __future__ import annotations

import time

from . import contracts
from .chain import RPCError, RevertError, tx_hash_of

DEFAULT_LIMITS = {"max_gas_units": 700_000, "max_fee_per_gas_wei": 300 * 10 ** 9, "gas_multiplier": 1.25,
                  "receipt_timeout_s": 60.0, "resolve_wait_s": 15.0, "poll_s": 0.5}


class GuardedExecutor:
    def __init__(self, rpc, signer, limits: dict | None = None):
        self.rpc, self.signer = rpc, signer
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}

    @property
    def keeper(self) -> str | None:
        return getattr(self.signer, "address", None)

    def calldata(self, chosen: dict) -> str:
        return contracts.execute_calldata(chosen["strategy"], chosen["action_id"], chosen["amount_raw"],
                                          chosen["policy_nonce"], chosen["keeper_bound"])

    def validate(self, vault: str, chosen: dict) -> dict:
        """Pre-send checks on the EXACT calldata. ok=False means nothing was sent (NO_ACTION, with the reason)."""
        out = {"ok": False, "checks": []}
        try:
            out["chain_id"] = self.rpc.assert_local()
        except Exception as e:  # noqa: BLE001
            out.update(stage="chain_guard", reason=str(e))
            return out
        out["checks"].append({"check": "local test chain", "ok": True, "chain_id": out["chain_id"]})
        if self.signer is None:
            out.update(stage="signer", reason="watch-only keeper (no signing key configured): plan reported, not executed")
            return out
        data = self.calldata(chosen)
        out["calldata"] = data
        try:
            self.rpc.eth_call(vault, data, "latest", sender=self.keeper)
        except RevertError as e:
            dec = contracts.decode_revert(e.data)
            out.update(stage="simulation", reason=f"eth_call simulation reverted: {dec['error']}{tuple(dec['args']) if dec['args'] else ''}",
                       revert=dec)
            return out
        out["checks"].append({"check": "eth_call simulation from the keeper at latest", "ok": True})
        gas = self.rpc.estimate_gas({"from": self.keeper, "to": vault, "data": data})
        out["gas_estimate"] = gas
        if gas > self.limits["max_gas_units"]:
            out.update(stage="gas", reason=f"gas estimate {gas:,} > cap {self.limits['max_gas_units']:,}")
            return out
        out["checks"].append({"check": "gas estimate under cap", "ok": True, "gas": gas, "cap": self.limits["max_gas_units"]})
        blk = self.rpc.block("latest")
        tip = min(self.rpc.max_priority_fee(), self.limits["max_fee_per_gas_wei"])
        max_fee = 2 * blk["base_fee"] + tip
        if max_fee > self.limits["max_fee_per_gas_wei"]:
            out.update(stage="fee", reason=f"max fee {max_fee / 1e9:.2f} gwei > cap {self.limits['max_fee_per_gas_wei'] / 1e9:.2f} gwei")
            return out
        gas_limit = int(gas * self.limits["gas_multiplier"])
        need = gas_limit * max_fee
        bal = self.rpc.balance(self.keeper)
        if bal < need:
            out.update(stage="keeper_funds", reason=f"keeper ETH {bal} < worst-case gas cost {need}")
            return out
        out["checks"] += [{"check": "fee under cap", "ok": True, "max_fee_per_gas": max_fee},
                          {"check": "keeper can pay gas", "ok": True, "balance_wei": bal}]
        out.update(ok=True, gas_limit=gas_limit, max_fee_per_gas=max_fee, max_priority_fee_per_gas=tip,
                   validated_block=blk["number"])
        return out

    def send(self, vault: str, chosen: dict, validation: dict, on_signed) -> dict:
        """Sign, journal (on_signed) and broadcast; then wait for the receipt. Returns status mined / ambiguous / not_sent."""
        nonce = self.rpc.nonce(self.keeper, "pending")
        tx = {"to": vault, "data": validation["calldata"], "chain_id": validation["chain_id"], "nonce": nonce,
              "gas": validation["gas_limit"], "max_fee_per_gas": validation["max_fee_per_gas"],
              "max_priority_fee_per_gas": validation["max_priority_fee_per_gas"]}
        raw = self.signer.sign(tx, self.rpc.url)
        h = tx_hash_of(raw)
        pending = {"tx_hash": h, "nonce": nonce, "action_id": chosen["action_id"], "strategy": chosen["strategy"],
                   "amount_raw": chosen["amount_raw"], "vault": vault, "raw_tx": raw, "keeper": self.keeper,
                   "signed_at": time.time()}
        on_signed(pending)
        try:
            sent = self.rpc.send_raw(raw)
            if sent and sent.lower() != h.lower():
                return {"status": "ambiguous", "tx_hash": h, "reason": f"node returned another hash {sent}", "pending": pending}
        except RPCError as e:
            msg = str(e).lower()
            if any(k in msg for k in ("already known", "nonce too low", "replacement")):
                return {"status": "ambiguous", "tx_hash": h, "reason": f"broadcast answer: {e}", "pending": pending}
            return {"status": "ambiguous", "tx_hash": h, "reason": f"broadcast error (may or may not have propagated): {e}",
                    "pending": pending}
        rc = self.wait(h)
        if rc is None:
            return {"status": "ambiguous", "tx_hash": h, "reason": "no receipt within timeout", "pending": pending}
        return {"status": "mined", "tx_hash": h, "receipt": rc, "pending": pending}

    def wait(self, tx_hash: str, timeout_s: float | None = None) -> dict | None:
        t0 = time.time()
        limit = self.limits["receipt_timeout_s"] if timeout_s is None else timeout_s
        while True:
            try:
                rc = self.rpc.receipt(tx_hash)
            except RPCError:
                rc = None
            if rc:
                return rc
            if time.time() - t0 >= limit:
                return None
            time.sleep(self.limits["poll_s"])

    def resolve(self, pending: dict, from_block: int = 0) -> dict:
        """Ground truth for an uncertain action, from the chain only. Never re-sends anything."""
        h, vault, aid = pending["tx_hash"], pending["vault"], pending["action_id"]
        rc = self.wait(h, self.limits["resolve_wait_s"]) if self.rpc.transaction(h) else self.rpc.receipt(h)
        if rc:
            return {"status": "mined", "tx_hash": h, "receipt": rc, "how": "receipt found by hash"}
        if contracts.action_used(self.rpc, vault, aid):
            logs = self.rpc.logs(vault, [contracts.RESCUE_EXECUTED_TOPIC, aid], from_block)
            if logs:
                rc2 = self.rpc.receipt(logs[-1]["transactionHash"])
                return {"status": "mined", "tx_hash": logs[-1]["transactionHash"], "receipt": rc2,
                        "how": "action id already used on-chain: executed (event found)"}
            return {"status": "executed_unverified", "how": "action id used on-chain but no event found in range"}
        latest = self.rpc.nonce(pending["keeper"], "latest")
        if latest > pending["nonce"]:
            return {"status": "not_executed_nonce_consumed", "how": f"keeper nonce {pending['nonce']} consumed by another "
                    "transaction and the action id is unused: this action did not happen"}
        if self.rpc.transaction(h):
            return {"status": "still_pending", "how": "transaction known to the node, not mined yet"}
        return {"status": "dropped", "how": "unknown to the node, action id unused, nonce unused: safe to re-plan"}
