# Backend gaps and known limitations

Ordered by user impact. None of these is hidden by the UI copy; this list exists so that nobody claims more than the
code does.

## Deployment

1. **Vercel cannot host the keeper.** Serverless functions are stateless and short-lived, so `keeper-status` and
   `policy-status` return `UNAVAILABLE` there. Monitoring needs `python -m defirisk.countermove.service` running on a
   machine next to a local chain or fork, plus the `FAULTLINE_*` env vars of the API process pointing at its files.
2. **No mainnet execution, by design.** A mainnet policy can be drafted and signed by the owner, but the FAULTLINE keeper
   never transacts there. The draft returns `chain.keeper_executable = false` with a warning.

## Frontend (owned by Claude Design v2, not changed here)

3. The new endpoints (`evidence`, `keeper-status`, `policy-status`) and the `policy-draft/2` fields (`error_details`,
   `risk_mapping`, `lifecycle_state`) have **no UI yet**. See `docs/frontend/DESIGN_COVERAGE_GAPS.md`.
4. `fl-live.js` `qs()` drops empty parameters. An ARM form with **no strategy selected** therefore sends no
   `strategies` key, and the backend applies the default `REPAY,TOP_UP` instead of returning the `empty` error. The
   frontend should send `strategies=` explicitly or block submission.

## Methodology (documented, deliberately not changed silently)

5. **C3 — single reference APY for the book carry.** `core/book.py` computes carry as
   `V × (implied_apy − reference_apy) × H / 365` with **one** `reference_apy` for every pocket. Pockets with different
   underlying assets would each need their own reference rate. The value is shown in the payload (`reference_apy`).
6. **C4 — borrower loss fraction from the analysed notional.** `leverage.py` turns each scenario into
   `collateral_loss_fraction = conditional_loss_usd / value_usd` and applies it to the real borrower's collateral. This
   assumes the loss scales linearly with size: it ignores the extra slippage a larger borrower would pay to exit.
7. Mainnet reads fall back to public RPCs (`data/sources.RPCS`) when `ETH_RPC_URL` is unset. They are rate-limited
   and unauthenticated (read-only, but availability is not guaranteed).

## Robustness

8. The evidence store's hash chain is not anchored externally (see `SECURITY_GATES.md`).
9. Finality uses a fixed confirmation depth (`--confirmations`, default 2). That is right for Anvil; a real network would
   need a depth tied to its finality rule (for example, finalized checkpoints on Ethereum).
10. The keeper watches the positions in its config file. Adding a vault requires a restart (there is no hot reload).
11. A local Anvil `evm_revert` both removes the rescue tx and, depending on the Anvil version, may re-include it. The e2e
    test accepts either `reorged → FAILED` or re-included-and-re-verified. Both paths are implemented and unit-tested.

## Fixed in this pass

* **Float rounding** in `policy-draft`: `float("4.1") × 1e6 = 4099999`. Amounts are now exact `Decimal` with ROUND_DOWN
  and a warning on truncation.
* `policy-draft` accepted NaN, negative amounts and unknown strategy names (silently dropped). These are now errors with
  a field and a code.
* Lifecycle could never reach `VERIFIED`, because the watcher logs `WATCHING` after every outcome. The lifecycle now
  reads the last terminal outcome.
* A reorged action could be journaled after a new decision. Finality now runs before the watcher in each tick.
* A keeper started while the RPC was down skipped the local-chain check. It is now checked before the first decision.
* HTTP cache writes were not atomic (a crash left truncated JSON, which broke the offline fallback). They now use a
  temp file + `os.replace`.
* The `api/analyze.py` docstring claimed a `mock-fallback` mode that the code does not have. It now documents the
  `502 discovery_failed` behaviour.
* Test isolation: `defirisk` imports failed without `PYTHONPATH=src`. `tests/conftest.py` fixes the path.
  `FAULTLINE_REQUIRE_E2E=1` turns the silent e2e skip into a failure. The "247 passed" figure seen in worktrees was
  264 minus 17 e2e tests silently skipped for lack of Foundry artifacts.
