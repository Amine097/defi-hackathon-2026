"""FAULTLINE Autonomous Countermove (Phase 2): bounded, pre-authorized crisis response for Morpho Blue BORROWERS.

DETECT -> UNDERSTAND -> SIMULATE -> CHOOSE -> EXECUTE -> VERIFY, as five separate parts:
  watcher.py       Watcher: polls protected positions, state machine, journal, restart recovery
  dependencies.py  Dependency Engine: decodes the market oracle into its real price feeds and maps shocks
  engine.py        Countermove Engine: exact minimal repay / top-up / full repay, scenario buffers, comparator
  executor.py      Guarded Executor: re-validates, simulates, signs (Foundry cast) and sends ONLY RescueVault calls
  verifier.py      Verifier: receipt, events and the re-read Morpho position must match the plan

This is separate from the Morpho VAULT DEPOSITOR analysis (vault_model.py): a depositor cannot repay or add
collateral; those are borrower actions. Transactions are only ever sent to a local test chain (chain-id guard).
"""
