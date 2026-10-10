"""JSON-RPC client used by the Countermove keeper.

One explicit endpoint per client (never the public mainnet fallback list of data/sources.py, never the disk cache:
the executor must act on live state only). Transactions can only be sent to a local test chain: `assert_local`
refuses any chain id outside LOCAL_CHAIN_IDS and any non-loopback URL, so a test key can never reach mainnet.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

from .. import abi
from ..keccak import keccak256

LOCAL_CHAIN_IDS = {31337, 1337}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class RPCError(Exception):
    """Transport or node error (timeout, connection refused, rate limit, malformed answer)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class RevertError(RPCError):
    """The call reverted: a real answer from the EVM, with the raw revert data when the node returns it."""

    def __init__(self, message: str, data: str | None = None):
        super().__init__(message, code=3)
        self.data = data


class UnsafeChainError(RuntimeError):
    pass


class RPC:
    def __init__(self, url: str, timeout: float = 20.0, retries: int = 2, backoff_s: float = 0.5):
        self.url, self.timeout, self.retries, self.backoff_s = url, timeout, retries, backoff_s
        self._id = 0
        self._chain_id: int | None = None

    # ---- transport ----------------------------------------------------------------------------------------------
    def call(self, method: str, params: list):
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            self._id += 1
            try:
                r = requests.post(self.url, json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params},
                                  timeout=self.timeout)
                if r.status_code == 429:
                    raise RPCError(f"{method}: rate limited (HTTP 429)", 429)
                r.raise_for_status()
                body = r.json()
            except (requests.RequestException, ValueError, RPCError) as e:
                last = e if isinstance(e, RPCError) else RPCError(f"{method}: {type(e).__name__}: {e}"[:300])
                time.sleep(self.backoff_s * (attempt + 1))
                continue
            err = body.get("error")
            if err:
                msg = str(err.get("message", ""))
                data = err.get("data")
                if isinstance(data, dict):
                    data = data.get("data")
                if "revert" in msg.lower() or err.get("code") == 3:
                    raise RevertError(msg[:300], data if isinstance(data, str) else None)
                raise RPCError(f"{method}: {msg}"[:300], err.get("code"))
            return body.get("result")
        raise last or RPCError(f"{method}: no answer")

    # ---- chain --------------------------------------------------------------------------------------------------
    def chain_id(self) -> int:
        if self._chain_id is None:
            self._chain_id = int(self.call("eth_chainId", []), 16)
        return self._chain_id

    def assert_local(self) -> int:
        """Refuse to sign or send anywhere but a loopback test chain (Anvil / Hardhat chain ids)."""
        host = urlparse(self.url).hostname or ""
        cid = self.chain_id()
        if host not in LOOPBACK or cid not in LOCAL_CHAIN_IDS:
            raise UnsafeChainError(f"refusing to transact: chain id {cid} at {host or self.url} is not a local test chain "
                                   f"({sorted(LOCAL_CHAIN_IDS)} on loopback)")
        return cid

    def block(self, tag: str | int = "latest") -> dict:
        b = self.call("eth_getBlockByNumber", [hex(tag) if isinstance(tag, int) else tag, False])
        if not b:
            raise RPCError(f"block {tag} not found")
        return {"number": int(b["number"], 16), "timestamp": int(b["timestamp"], 16),
                "base_fee": int(b.get("baseFeePerGas") or "0x0", 16), "hash": b.get("hash")}

    def eth_call(self, to: str, data: str, block: str | int = "latest", sender: str | None = None,
                 gas: int | None = None) -> str:
        tx = {"to": to, "data": data}
        if sender:
            tx["from"] = sender
        if gas:
            tx["gas"] = hex(gas)
        return self.call("eth_call", [tx, hex(block) if isinstance(block, int) else block])

    def read(self, to: str, signature: str, args: list | None = None, out: str = "uint256",
             block: str | int = "latest"):
        """Typed view call: read(token, 'balanceOf(address)', [user], 'uint256') -> int."""
        res = self.eth_call(to, abi.encode_call(signature, args or []), block)
        if not res or res == "0x":
            raise RevertError(f"{signature} returned no data on {to}")
        vals = abi.decode(out, res)
        return vals[0] if len(vals) == 1 else vals

    def code(self, address: str, block: str | int = "latest") -> str:
        return self.call("eth_getCode", [address, hex(block) if isinstance(block, int) else block])

    def balance(self, address: str, block: str | int = "latest") -> int:
        return int(self.call("eth_getBalance", [address, hex(block) if isinstance(block, int) else block]), 16)

    def nonce(self, address: str, tag: str = "pending") -> int:
        return int(self.call("eth_getTransactionCount", [address, tag]), 16)

    def estimate_gas(self, tx: dict) -> int:
        return int(self.call("eth_estimateGas", [tx]), 16)

    def gas_price(self) -> int:
        return int(self.call("eth_gasPrice", []), 16)

    def max_priority_fee(self) -> int:
        try:
            return int(self.call("eth_maxPriorityFeePerGas", []), 16)
        except RPCError:
            return 10 ** 9

    def send_raw(self, raw: str) -> str:
        return self.call("eth_sendRawTransaction", [raw])

    def receipt(self, tx_hash: str) -> dict | None:
        return self.call("eth_getTransactionReceipt", [tx_hash])

    def transaction(self, tx_hash: str) -> dict | None:
        return self.call("eth_getTransactionByHash", [tx_hash])

    def logs(self, address: str, topics: list, from_block: int, to_block: str | int = "latest") -> list:
        return self.call("eth_getLogs", [{"address": address, "topics": topics, "fromBlock": hex(from_block),
                                          "toBlock": hex(to_block) if isinstance(to_block, int) else to_block}])


def tx_hash_of(raw: str) -> str:
    """keccak256 of the signed transaction envelope = its hash (known BEFORE broadcasting, for the journal)."""
    return "0x" + keccak256(bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)).hex()
