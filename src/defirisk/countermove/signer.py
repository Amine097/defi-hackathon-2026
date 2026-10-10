"""Keeper transaction signing from an ENCRYPTED keystore through Foundry `cast` (no custom cryptography, no key in the node).

The keeper holds ONLY its own key (never the user's), and never as plaintext on a command line or in its environment:
`cast mktx --keystore <file> --password-file <file>` decrypts the Web3 Secret Storage keystore inside the cast process.
Process arguments therefore carry only two paths (both files are readable by the operator's account only).
For the local demo and tests, the keystore is created at run time from Anvil's PUBLIC test mnemonic (well-known,
worthless, never valid on mainnet) with a random throw-away password: no key material is stored in the repository.
Defence in depth: the signer refuses any chain id other than 31337 (Anvil), on top of the executor's local-chain guard.
An operator imports a real key interactively (`cast wallet import keeper --interactive`): the key is never typed on a
command line either. A production deployment would still use a hardware / remote signer (see the security report).
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

from .chain import UnsafeChainError

ANVIL_TEST_MNEMONIC = "test test test test test test test test test test test junk"  # public Foundry/Hardhat default
SIGNABLE_CHAIN_IDS = {31337}  # Anvil only: a signature for any other chain is refused before cast is invoked
KEYSTORE_ENV, PASSWORD_FILE_ENV = "FAULTLINE_KEEPER_KEYSTORE", "FAULTLINE_KEEPER_PASSWORD_FILE"


def cast_path() -> str:
    p = shutil.which("cast") or shutil.which("cast.exe")
    if p:
        return p
    for cand in (Path.home() / ".foundry" / "bin" / "cast.exe", Path.home() / ".foundry" / "bin" / "cast"):
        if cand.exists():
            return str(cand)
    raise FileNotFoundError("Foundry `cast` not found (install Foundry: see contracts/install_deps.ps1 and docs)")


def _run(args: list[str], timeout: float = 60, env: dict | None = None) -> str:
    r = subprocess.run([cast_path(), *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **env} if env else None)
    if r.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args[:2])} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def _private_file(path: Path, text: str) -> None:
    """Create a file readable by the current user only (POSIX 0600; per-user %TEMP% / profile ACLs on Windows)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def import_test_keystore(index: int, directory: str | Path) -> tuple[Path, Path]:
    """Encrypted keystore of PUBLIC Anvil test account #index (local test chains only) + its random password file.
    The account is derived by cast from the public mnemonic; the password reaches cast through its environment
    (CAST_UNSAFE_PASSWORD), so neither the key nor the password ever appears in process arguments."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    name = f"anvil-test-{index}"
    password = secrets.token_hex(32)
    pw_file = d / f"{name}.password"
    _private_file(pw_file, password)
    _run(["wallet", "import", name, "--keystore-dir", str(d), "--mnemonic", ANVIL_TEST_MNEMONIC,
          "--mnemonic-index", str(index)], env={"CAST_UNSAFE_PASSWORD": password})
    return d / name, pw_file


class KeystoreSigner:
    def __init__(self, keystore: str | Path, password_file: str | Path):
        self._keystore, self._password_file = str(keystore), str(password_file)
        for p in (self._keystore, self._password_file):
            if not Path(p).is_file():
                raise FileNotFoundError(f"keeper keystore / password file not found: {p}")
        self.address = _run(["wallet", "address", *self._wallet()])

    @classmethod
    def from_env(cls, environ: dict | None = None) -> "KeystoreSigner | None":
        """FAULTLINE_KEEPER_KEYSTORE + FAULTLINE_KEEPER_PASSWORD_FILE -> signer; neither set -> None (watch-only)."""
        e = os.environ if environ is None else environ
        ks, pw = e.get(KEYSTORE_ENV), e.get(PASSWORD_FILE_ENV)
        if not ks and not pw:
            return None
        if not (ks and pw):
            raise ValueError(f"set both {KEYSTORE_ENV} and {PASSWORD_FILE_ENV} (or neither for a watch-only keeper)")
        return cls(ks, pw)

    def _wallet(self) -> list[str]:
        return ["--keystore", self._keystore, "--password-file", self._password_file]

    def __repr__(self) -> str:
        return f"KeystoreSigner({self.address})"

    def sign(self, tx: dict, rpc_url: str | None = None) -> str:  # noqa: ARG002 - signing is offline (every field explicit)
        """EIP-1559 transaction -> signed raw envelope (0x...). Every field is explicit: nothing is filled by a node."""
        cid = int(tx["chain_id"])
        if cid not in SIGNABLE_CHAIN_IDS:
            raise UnsafeChainError(f"refusing to sign for chain id {cid}: the keeper signs for {sorted(SIGNABLE_CHAIN_IDS)} only")
        return _run(["mktx", tx["to"], tx["data"], *self._wallet(), "--chain", str(cid),
                     "--nonce", str(tx["nonce"]), "--gas-limit", str(tx["gas"]), "--gas-price", str(tx["max_fee_per_gas"]),
                     "--priority-gas-price", str(tx["max_priority_fee_per_gas"])])
