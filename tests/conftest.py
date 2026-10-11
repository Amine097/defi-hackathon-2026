"""Shared test setup.

* puts `src` on sys.path so any single test file runs on its own (previously only some modules did it, so
  `pytest tests/test_x.py` could fail with ModuleNotFoundError depending on which files were collected)
* FAULTLINE_REQUIRE_E2E=1 turns the silent skip of the Anvil end-to-end suites into a hard failure: CI or a release
  check must not report "all green" when 18 chain tests did not run (anvil / cast missing, or no `forge build`
  artifacts in contracts/out, which is gitignored and absent from fresh worktrees)
"""
import os
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def pytest_sessionstart(session):
    if os.getenv("FAULTLINE_REQUIRE_E2E") != "1":
        return
    from defirisk.countermove import devchain
    missing = []
    try:
        devchain.anvil_path()
    except FileNotFoundError:
        missing.append("anvil (Foundry) not found")
    try:
        from defirisk.countermove.signer import cast_path
        cast_path()
    except FileNotFoundError:
        missing.append("cast (Foundry) not found")
    for art in (devchain.OUT / "RescueVault.sol" / "RescueVault.json", devchain.OUT / "LocalSim.sol"):
        if not art.exists():
            missing.append(f"missing build artifact {art} (run `forge build` in contracts/)")
    if missing:
        raise SystemExit("FAULTLINE_REQUIRE_E2E=1 but the end-to-end suites cannot run:\n  - " + "\n  - ".join(missing))
