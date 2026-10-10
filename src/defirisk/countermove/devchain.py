"""Local test-chain tooling for the Countermove demo and end-to-end tests: start Anvil (plain or mainnet fork), deploy
from Foundry artifacts, send SETUP transactions from Anvil's unlocked test accounts (the user's pre-crisis actions),
give test balances, install a SIMULATED feed shock. Every function refuses non-local chains (RPC.assert_local).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from .. import abi
from ..keccak import keccak256
from .chain import RPC, RPCError

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "contracts" / "out"
# Anvil's default accounts, derived from its PUBLIC test mnemonic (worthless; local chains only)
ACCOUNTS = ["0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
            "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65", "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"]
ROLE = {"deployer": ACCOUNTS[0], "keeper": ACCOUNTS[1], "user": ACCOUNTS[2], "lp": ACCOUNTS[3], "attacker": ACCOUNTS[4]}


def anvil_path() -> str:
    p = shutil.which("anvil") or shutil.which("anvil.exe")
    if p:
        return p
    cand = Path.home() / ".foundry" / "bin" / "anvil.exe"
    if cand.exists():
        return str(cand)
    cand = Path.home() / ".foundry" / "bin" / "anvil"
    if cand.exists():
        return str(cand)
    raise FileNotFoundError("Foundry `anvil` not found")


class Anvil:
    """Context manager around an Anvil process (chain id 31337 always: signatures can never replay on mainnet)."""

    def __init__(self, port: int = 8545, fork_url: str | None = None, fork_block: int | None = None,
                 extra: list[str] | None = None, log: Path | None = None):
        self.port, self.fork_url, self.fork_block, self.extra, self.log = port, fork_url, fork_block, extra or [], log
        self.url = f"http://127.0.0.1:{port}"
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 120) -> "Anvil":
        args = [anvil_path(), "--port", str(self.port), "--chain-id", "31337", "--silent"]
        if self.fork_url:
            args += ["--fork-url", self.fork_url, "--compute-units-per-second", "40", "--retries", "12",
                     "--fork-retry-backoff", "1500"]
            if self.fork_block:
                args += ["--fork-block-number", str(self.fork_block)]
        args += self.extra
        out = open(self.log, "w") if self.log else subprocess.DEVNULL  # noqa: SIM115 - closed with the process
        self.proc = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT)
        rpc = RPC(self.url, timeout=5, retries=0)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"anvil exited with code {self.proc.returncode}")
            try:
                rpc.chain_id()
                return self
            except RPCError:
                time.sleep(0.5)
        self.stop()
        raise TimeoutError("anvil did not start")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def artifact(name: str, file: str | None = None) -> dict:
    p = OUT / f"{file or name}.sol" / f"{name}.json"
    a = json.loads(p.read_text(encoding="utf-8"))
    return {"abi": a["abi"], "bytecode": a["bytecode"]["object"]}


def tx(rpc: RPC, sender: str, to: str | None, data: str, value: int = 0, gas: int = 8_000_000, check: bool = True) -> dict:
    """Setup transaction from an UNLOCKED Anvil test account (eth_sendTransaction): the user / deployer side only."""
    rpc.assert_local()
    t = {"from": sender, "data": data, "gas": hex(gas), "value": hex(value)}
    if to:
        t["to"] = to
    h = rpc.call("eth_sendTransaction", [t])
    for _ in range(200):
        rc = rpc.receipt(h)
        if rc:
            if check and int(rc["status"], 16) != 1:
                raise RuntimeError(f"setup tx reverted: {h}")
            return rc
        time.sleep(0.05)
    raise TimeoutError(f"no receipt for {h}")


def deploy(rpc: RPC, sender: str, name: str, types: list[str] | None = None, args: list | None = None,
           file: str | None = None) -> str:
    a = artifact(name, file)
    data = a["bytecode"] + (abi.encode_tuple(types, args).hex() if types else "")
    rc = tx(rpc, sender, None, data)
    return rc["contractAddress"]


def call(rpc: RPC, sender: str, to: str, signature: str, args: list | None = None, check: bool = True) -> dict:
    return tx(rpc, sender, to, abi.encode_call(signature, args or []), check=check)


def balance_slot(rpc: RPC, token: str, holder: str) -> str:
    """Storage slot of balanceOf(holder), found from eth_createAccessList + state-override probing (works for proxied
    tokens such as USDC / cbBTC / weETH where anvil_dealERC20 cannot find the slot)."""
    data = abi.encode_call("balanceOf(address)", [holder])
    al = rpc.call("eth_createAccessList", [{"to": token, "data": data}, "latest"])
    for entry in al["accessList"]:
        if entry["address"].lower() != token.lower():
            continue
        for k in entry["storageKeys"]:
            probe = 123456789123456789
            try:
                out = rpc.call("eth_call", [{"to": token, "data": data}, "latest", {token: {"stateDiff": {k: "0x" + f"{probe:064x}"}}}])
            except RPCError:
                continue
            if out and out != "0x" and int(out, 16) == probe:
                return k
    raise RuntimeError(f"balance slot of {token} not found")


def set_token_balance(rpc: RPC, token: str, holder: str, amount: int) -> None:
    """TEST FUNDS on a local fork: writes the holder's balance slot (the token's totalSupply is not adjusted)."""
    rpc.assert_local()
    slot = balance_slot(rpc, token, holder)
    rpc.call("anvil_setStorageAt", [token, slot, "0x" + f"{amount:064x}"])
    if rpc.read(token, "balanceOf(address)", [holder]) != amount:
        raise RuntimeError("balance write did not stick")


def shock_feed(rpc: RPC, feed: str, shock_bps: int, fresh_timestamp: bool | None = None) -> dict:
    """SIMULATED dependency crisis on a local fork: the feed's code becomes ShockFeed (description 'FAULTLINE SIMULATED
    SHOCK'), answering the real pre-shock answer x (1 - shock). Every oracle using this feed sees it, like a real crisis."""
    rpc.assert_local()
    rid, ans, _, upd, _ = rpc.read(feed, "latestRoundData()", [], "uint80,int256,uint256,uint256,uint80")
    dec = rpc.read(feed, "decimals()", [], "uint8")
    try:
        desc = rpc.read(feed, "description()", [], "string")
    except RPCError:
        desc = None
    if desc and "FAULTLINE SIMULATED" in desc:  # already shocked: keep the original pre-shock answer
        ans = rpc.read(feed, "baseAnswer()", [], "int256")
    code = "0x" + artifact("ShockFeed")["bytecode"][2:]
    runtime = _runtime_code(rpc, code)
    rpc.call("anvil_setCode", [feed, runtime])
    mode = 1 if (fresh_timestamp if fresh_timestamp is not None else upd != 0) else 0
    for slot, val in ((0, ans % (1 << 256)), (1, shock_bps), (2, dec), (3, rid + 1), (4, mode)):
        rpc.call("anvil_setStorageAt", [feed, "0x" + f"{slot:064x}", "0x" + f"{val:064x}"])
    rpc.call("evm_mine", [])
    return {"feed": feed, "original_description": desc, "decimals": dec, "pre_shock_answer": ans, "shock_bps": shock_bps,
            "shocked_answer": rpc.read(feed, "latestAnswer()", [], "int256"), "timestamp_mode": mode,
            "label": "SIMULATED controlled shock on a local fork (anvil_setCode); not a mainnet event"}


_RUNTIME_CACHE: dict = {}


def _runtime_code(rpc: RPC, creation: str) -> str:
    """Runtime bytecode of a contract = deploy it once on the local chain and read its code."""
    if creation in _RUNTIME_CACHE:
        return _RUNTIME_CACHE[creation]
    rc = tx(rpc, ACCOUNTS[0], None, creation)
    code = rpc.code(rc["contractAddress"])
    _RUNTIME_CACHE[creation] = code
    return code


def mine(rpc: RPC, seconds: int = 0) -> None:
    if seconds:
        rpc.call("evm_increaseTime", [seconds])
    rpc.call("evm_mine", [])


def storage_key(slot: int, key_addr: str) -> str:
    return "0x" + keccak256(abi.encode_tuple(["address", "uint256"], [key_addr, slot])).hex()
