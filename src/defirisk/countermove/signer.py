"""Keeper transaction signing through Foundry `cast mktx` (no custom cryptography, no key in the node).

The keeper holds ONLY its own key (never the user's). For the local demo the key is derived at run time from Anvil's
PUBLIC test mnemonic (well-known, worthless, never valid on mainnet), so no key material is stored in the repository.
The key is passed to `cast` as a process argument: acceptable for this public test key on a local machine only; a real
deployment would use a hardware / remote signer (cast supports keystores and remote signers).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ANVIL_TEST_MNEMONIC = "test test test test test test test test test test test junk"  # public Foundry/Hardhat default


def cast_path() -> str:
    p = shutil.which("cast") or shutil.which("cast.exe")
    if p:
        return p
    for cand in (Path.home() / ".foundry" / "bin" / "cast.exe", Path.home() / ".foundry" / "bin" / "cast"):
        if cand.exists():
            return str(cand)
    raise FileNotFoundError("Foundry `cast` not found (install Foundry: see contracts/install_deps.ps1 and docs)")


def _run(args: list[str], timeout: float = 60) -> str:
    r = subprocess.run([cast_path(), *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().replace(os.environ.get("FAULTLINE_KEEPER_KEY", "\0"), "<key>")
        raise RuntimeError(f"cast {args[0]} failed: {msg[:300]}")
    return r.stdout.strip()


def anvil_test_key(index: int) -> str:
    """Private key #index of the PUBLIC Anvil test mnemonic (local test chains only)."""
    return _run(["wallet", "private-key", "--mnemonic", ANVIL_TEST_MNEMONIC, "--mnemonic-index", str(index)])


class CastSigner:
    def __init__(self, private_key: str):
        self._key = private_key
        self.address = _run(["wallet", "address", "--private-key", private_key])

    def __repr__(self) -> str:  # never print the key
        return f"CastSigner({self.address})"

    def sign(self, tx: dict, rpc_url: str) -> str:
        """EIP-1559 transaction -> signed raw envelope (0x...). Every field is explicit: nothing is filled by the node."""
        return _run(["mktx", tx["to"], tx["data"], "--private-key", self._key, "--chain", str(tx["chain_id"]),
                     "--nonce", str(tx["nonce"]), "--gas-limit", str(tx["gas"]), "--gas-price", str(tx["max_fee_per_gas"]),
                     "--priority-gas-price", str(tx["max_priority_fee_per_gas"]), "--rpc-url", rpc_url])
