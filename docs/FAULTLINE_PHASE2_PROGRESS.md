# FAULTLINE — Phase 2 progress log (Autonomous Countermove)

Mission: `docs/FAULTLINE_Countermove_v3_Autonomous_Crisis_Response.md` (reference) + jury request
"detect a DeFi crisis, select a pre-authorized protective action and execute it on-chain while the user is offline".
Environment: local Ethereum **fork** only (Anvil). No mainnet transaction, no real funds, no personal key.

This log is updated after every work package so the work can resume after an interruption.

## Status board

| WP | Status | Evidence |
|---|---|---|
| Baseline (before any change) | DONE | `pytest` offline 135 passed / 14 skipped; Node 17/17 (HEAD `88da12a`) |
| Tooling: Foundry v1.8.5 (forge/anvil/cast) | DONE | GitHub release zip, SHA-256 verified `21f86b56…aa45`, installed in `%USERPROFILE%\.foundry\bin` |
| P0-A vault exit routes (forceDeallocate) | DONE | `vault_reader.simulate_force_exit`, `vault_model.capacity/force_plan/reads/assess`; live Belem $1M = `full_via_force_deallocate` (block 26164187, 647,212 gas, penalty 0) |
| P0-B one economic basis for partial exits | DONE | `decision.comparison_basis`, tranche-scaled loss / carry / execution; `tests/test_vault_p0.py` |
| P0 UI (vault page) | DONE | `vault/view.js` (`EXECUTABLE`, `routeRows`, `basisText`, mixed-basis check), `vault.js` routes table |
| RescueVault contract | DONE | `contracts/src/RescueVault.sol` (solc 0.8.26, OZ v5.6.1 SafeERC20 + ReentrancyGuard, Morpho Blue v1.0.0 interfaces) |
| RescueVault tests | DONE | `forge test`: 24 unit/fuzz (3 × 512 runs) + 4 token-quirk + 4 invariants (64 × 64, all actions exercised) + 1 fork test on the real cbBTC/USDC market |
| Countermove engine (borrower) | DONE | `src/defirisk/countermove/engine.py`, `dependencies.py`; `tests/test_countermove_engine.py` 32 passed (exact + minimal to the wei vs brute force, spec example 460 / 594.32) |
| Watcher / executor / verifier | DONE | `watcher.py`, `executor.py`, `verifier.py`, `journal.py`, `reader.py`, `chain.py`, `signer.py` (Foundry cast), `devchain.py`; `tests/test_countermove_e2e.py` 16 passed x3 on a local Anvil with the real Morpho Blue bytecode |
| Fork scenarios S1–S3 (+S4) | DONE | `scripts/countermove_fork_demo.py` → `data/countermove/demo/latest/`: S1 REPAY 1,086.50 USDC (tx `0x4b9254eb…87e2`), S2 TOP_UP 0.02509364 cbBTC (`0x7ccb73cc…9050`), S3 NO_ACTION (nothing sent), S4 FULL_REPAY 18,670.41 USDC (`0xeea9ca52…aee5`); `all_expected = true`; user nonces unchanged |
| Frontend Countermove page | DONE | `public/countermove.html` + `/api/countermove`; Node `countermove_view.test.mjs` 6/6; `tests/test_countermove_api.py` 6 (+1 live); checked in the browser |
| Security review | DONE | Slither 0.11.6: 52 results, none requiring a code change (`audit/FAULTLINE_PHASE2_SLITHER.txt`); `forge lint` 30 warnings triaged; secrets scan clean (399 files) |
| Reports + evidence | DONE | `docs/FAULTLINE_PHASE2_{IMPLEMENTATION_REPORT,SECURITY_REPORT,DEMO_GUIDE}.md`, `audit/FAULTLINE_PHASE2_EVIDENCE.json` (`scripts/collect_phase2_evidence.py --live --fork`) |
| Final validation | DONE — **GO** (test environment only) | pytest offline 207 passed / 16 skipped; live subset 133 passed; Node 27/27; Foundry 29 passed + fork test (run separately) passed; fork demo 4/4 expected; 15/15 GO criteria PASS |

## Log

1. Read the five docs + challenge PDF context + Phase 0.5/1 progress. Repo inspected; baseline tests green.
2. P0-A: the ordinary route (idle + liquidity adapter) under-estimated a VaultV2 exit. Added the permissionless
   `VaultV2.multicall([forceDeallocate(adapter, abi.encode(MarketParams), assets, 0xdEaD)..., redeem])` route,
   planned by `force_plan` (cheapest penalty, deepest liquidity, ≤ 99.9% of each market) and simulated with
   `eth_call` + state override + `eth_estimateGas`. Feasibility is now `full | full_via_force_deallocate | partial |
   zero | unknown`; a route is executable only if its simulation succeeded; theoretical routes are listed as
   `unconfirmed`. Scenarios report the force capacity (confirmed vs theoretical).
3. P0-B: `assess` compares one size `w` (= simulated tranche / position): loss avoided `EL·w`, forgone carry `carry·w`,
   execution of that tranche; residual `EL·(1−w)` reported. Sensitivity break-even uses the same basis.
4. Tests: `tests/test_vault_p0.py` (18 offline), 1 new live test, 4 new Node tests, live test semantics fixed
   (`test_live_belem_large_position_partial` asserted the old under-estimate). Offline 153 passed / 15 skipped,
   Node 21/21, live vault 12/12.
5. Contracts project `contracts/` (Foundry): pinned deps cloned by `contracts/install_deps.ps1` (forge-std v1.17.0
   `f3dae6e6`, OpenZeppelin v5.6.1 `5fd1781b`, morpho-blue v1.0.0 `55d2d993`, commits verified). `RescueVault`:
   repay / supplyCollateral / full repay ONLY on behalf of the immutable beneficiary; on-chain trigger from Morpho's own
   oracle + accrued debt; per-action / cumulative caps, reserve floors, LTV floor, keeper LTV bound, expiry, cooldown,
   policy nonce, action-id replay guard, exact token-movement checks (vault AND Morpho balances), pause / irreversible
   revoke, owner-only recovery. Tests deploy the REAL Morpho Blue v1.0.0 bytecode.
6. Real markets chosen after on-chain oracle decoding: weETH/USDC (weETH/ETH rate x ETH/USD), cbBTC/USDC (BTC/USD),
   wstETH/USDC (custom wstETH/ETH x ETH/USD). Anvil fork works through blastapi with `--compute-units-per-second 40`;
   anvil's clock follows the fork block (reproducible). `anvil_dealERC20` fails on proxied tokens: balance slots are
   found with `eth_createAccessList` + state-override probing instead.
7. Python package `src/defirisk/countermove/` (borrower side, separate from the vault-depositor model): Watcher
   state machine WATCHING -> DETECTED -> PLANNING -> VALIDATING -> EXECUTING -> CONFIRMED / FAILED / NO_ACTION;
   Dependency Engine decodes MorphoChainlinkOracleV2 feeds (freshness, implicit assumptions, shock -> exact price
   factor); deterministic engine (security -> feasibility -> buffer in every scenario -> least reserve value, configurable
   preference; NO_ACTION with reasons; partial protection only if allowed); Guarded Executor (local-chain guard,
   eth_call simulation, gas / fee caps, journal-before-broadcast, chain-only ambiguity resolution); Verifier (receipt,
   vault + Morpho events, re-read position, exact reserve movement, counters, LTV / buffer improvement).
8. End-to-end tests on a local Anvil (real Morpho Blue bytecode, local test token / feed / oracle in
   `contracts/src/sim/`): auto-repay, auto-top-up, no-safe-action, full repay, hold vs alert, stale feed, RPC down,
   gas cap, watch-only, on-chain revert (race with an owner pause), keeper killed after broadcast (resumes without
   re-sending), ambiguous broadcast, dropped tx (FAILED then re-planned once), price move during validation,
   duplicate / malicious keeper transactions, chain guard, ABI bindings vs compiled artifact.
   Fixes found by these tests: journal must keep exact big integers (stringified ints broke post-restart
   verification); resolution waits for the receipt before concluding "still pending".
9. Fork demonstration `scripts/countermove_fork_demo.py` (mainnet block 26,164,248, Anvil chain id 31337): four users
   open real Morpho positions at 75% LTV, deploy / fund / configure their RescueVault before the crisis; the keeper runs
   as a separate OS process (`python -m defirisk.countermove`) with only its key; SIMULATED −9% shocks on one real
   feed per market (feed code replaced by `ShockFeed`, labelled). Results: S1 AUTO-REPAY, S2 AUTO-TOP-UP, S3 NO ACTION,
   S4 EMERGENCY FULL REPAY, all verified on the fork (15/15, 14/14, 12/12 checks), user nonces unchanged. Four runs gave
   the same decisions; S1's transaction hash is identical across runs.
10. Frontend: `public/countermove.html` (before / during / after, LIVE / SIMULATED / CONFIRMED / FAILED / NO ACTION),
   `/api/countermove` (all figures computed server-side, reserve what-if with the same engine), view-model that refuses
   an unproven CONFIRMED, LIVE mainnet dependency panel (read-only), policy draft for the user's own wallet; nav overflow
   fixed in `theme.css`. Checked in the browser.
11. Security review: Slither 0.11.6 (isolated venv) — 52 results (reentrancy reports on calls to the immutable Morpho
   singleton behind `nonReentrant`, intentional exact-delta checks, sim-only contracts, naming), none requiring a code
   change; `forge lint` 30 warnings, same triage. Hardening found during the review: the fork test now reports SKIPPED
   (`vm.skip`) instead of passing vacuously without `FORK_RPC_URL`; the demo records complete, repository-relative keeper
   commands (the previous display dropped `--journal-dir` and embedded a local absolute path) and never records a custom
   RPC URL (may embed an API key). The recorded run was regenerated with the final code and the UI fixture re-exported.
12. Flaky test found by the final validation: `test_e2e_keeper_killed_after_broadcast_resumes_without_resending` failed
   only inside the full suite. Trace: the keeper's `latest` nonce read right after the simulated crash was 0 and 1 after
   the restart, i.e. exactly ONE transaction (nothing re-sent) — Anvil's automine can answer `eth_sendRawTransaction`
   before mining. The product was correct; the test now asserts "exactly one keeper transaction and the confirmed tx is
   the journaled one", and "nothing sent" assertions read the `pending` nonce (stricter). Full suite green twice after.
13. Reports: implementation report, security report (threat model, permission matrix, static-analysis triage, residual
   risks, NOT AUDITED), demo guide; README (Phase 2 section; the Phase 1 step "partial exit above ~$405k" corrected after
   P0-A) and docs index updated.
14. Evidence: `scripts/collect_phase2_evidence.py --live --fork` runs every suite, re-assesses Belem $1M LIVE
   (block 26,164,685: `full_via_force_deallocate`, $1M withdrawable now, multicall 647,224 gas, penalty 0), runs the fork
   test on the real cbBTC/USDC market (passed, 784,085 gas), reads the recorded run, Slither and `forge lint`, scans for
   keys, and evaluates the 15 GO criteria from those results only → `audit/FAULTLINE_PHASE2_EVIDENCE.json`: **GO —
   prototype validated on a local test environment; not an authorization to manage real funds.**
15. Countermove page UX pass (after review of the deployed page): outcome-first hero per scenario (crisis → decision →
   result, reaction time, "no user signature") with an LTV gauge (before / crisis / after against trigger and LLTV);
   compact scenario tabs with human strategy names and `#S1`–`#S4` deep links; full-width sections instead of three
   squeezed columns; loan-token amounts always to the cent, durations and UTC dates in plain words; constant placeholder
   feeds hidden from the dependency list; short rejection reasons (full text on hover); check lists collapsed to
   "n/n passed"; ⚠ in the reserve table explained; light print/PDF stylesheet with every section expanded. Bug fixed:
   the policy form never sent the market's token decimals, so a cbBTC (8-decimal) policy was encoded with 18 decimals;
   the form now takes percentages, reads LLTV and decimals from the selected market, and shows units. Display only —
   no figure is computed in the browser; Node tests 27 → 33.

## Remaining limits (see the security report §7)

Not audited; local fork only (no mempool / MEV / gas spikes); one keeper process; oracle trust bounded by caps; keeper
signs with `cast --private-key` (public test key only); DELEVERAGE + SELL / refinance / hedge not built by design.
Phase 2 changes are in the working tree (not committed).
