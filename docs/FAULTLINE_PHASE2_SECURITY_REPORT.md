# FAULTLINE — Phase 2 Security Report: RescueVault and the Countermove keeper

> **NOT AUDITED.** This is a hackathon prototype tested on a local Ethereum fork. Tests and static analysis reduce risk;
> they do not prove the absence of vulnerabilities. Do not deploy with real funds.
> Companion documents: `docs/FAULTLINE_PHASE2_IMPLEMENTATION_REPORT.md`, `docs/FAULTLINE_PHASE2_DEMO_GUIDE.md`,
> `audit/FAULTLINE_PHASE2_EVIDENCE.json`, raw Slither output `audit/FAULTLINE_PHASE2_SLITHER.txt`.

## 1. Scope

| Component | Files | Holds funds? |
|---|---|---|
| RescueVault | `contracts/src/RescueVault.sol` | **Yes** (the pre-deposited reserve) |
| Keeper (Watcher, Dependency Engine, Engine, Guarded Executor, Verifier, journal, signer) | `src/defirisk/countermove/*.py` | No (its own ETH for gas only) |
| Read-only API / UI | `src/defirisk/countermove/api.py`, `public/countermove.html`, `public/assets/js/countermove/*` | No |
| Test-only simulation contracts | `contracts/src/sim/ShockFeed.sol`, `contracts/src/sim/LocalSim.sol` | No — **local chains only**, never deploy |

Trusted, out of scope: Morpho Blue v1 (`0xBBBB…EFFCb`, immutable, audited), the market's oracle (the vault reads the
same oracle Morpho liquidates with), the ERC-20 tokens of the market chosen by the owner, Foundry `cast` for signing
(including keystore decryption).

## 2. Actors and the security model

The design goal is **"the worst a compromised keeper can do is spend the reserve on the user's own Morpho position, within
the owner's limits, while the position is really at risk on-chain"**.

- The user (owner) **never** gives the vault or the keeper a Morpho authorization (`setAuthorization`) and **never**
  gives an ERC-20 allowance on their wallet. Morpho Blue `repay` and `supplyCollateral` on behalf of another address are
  permissionless, so the vault only needs its own, pre-deposited tokens.
- The protected beneficiary, the market and Morpho are `immutable`; the destination of every token the keeper can move is
  hard-coded to Morpho for `BENEFICIARY`.
- The keeper holds only its own key; user keys are never available to the keeper process (the demo strips any
  `FAULTLINE_USER*` variable from the keeper's environment and checks the users' nonces afterwards).

### Permission matrix

| Function | Owner | Keeper | Beneficiary (if ≠ owner) | Anyone else |
|---|---|---|---|---|
| `setPolicy` (bumps nonce, resets budgets) | ✅ validated | ❌ `NotOwner` | ❌ | ❌ |
| `setKeeper` | ✅ (not after revoke) | ❌ | ❌ | ❌ |
| `setPaused` | ✅ (cannot unpause after revoke) | ❌ | ❌ | ❌ |
| `revoke` (irreversible: keeper = 0, paused) | ✅ | ❌ | ❌ | ❌ |
| `deposit` (loan or collateral token only, exact delta) | ✅ | ❌ | ❌ | ❌ (a plain transfer is a donation only the owner can withdraw) |
| `withdrawReserve` (any token, **to the owner only**, any time) | ✅ | ❌ | ❌ | ❌ |
| `executeRepay` / `executeTopUp` / `executeFullRepay` | ❌ (unless set as keeper) | ✅ inside the policy | ❌ | ❌ `NotKeeper` |
| Transfer to an arbitrary address, borrow, withdraw collateral, arbitrary call, receive ETH | — | **no such code path** | — | — |

## 3. On-chain checks of a keeper call (in execution order)

1. `_preflight`: caller is the keeper and non-zero → not revoked → not paused → `expectedPolicyNonce == policyNonce`
   → `block.timestamp ≤ validUntil` (no policy ⇒ expired) → strategy bit allowed → `actionId` unused → cooldown elapsed
   → mark `actionId` used (rolled back on any revert) → `MORPHO.accrueInterest` → snapshot (debt = `toAssetsUp(borrowShares)`
   on accrued totals, market oracle price) → debt > 0 → **on-chain LTV ≥ `triggerLtv`**.
2. Per strategy: amount > 0; per-action cap; cumulative cap; partial repay `< debt`; full repay `debt ≤ keeper maxAssets`
   and `≤ maxFullRepay`. Budget counters are increased before the external calls.
3. `_pull`: reserve ≥ amount + floor; `forceApprove(MORPHO, amount)` → Morpho `repay` / `supplyCollateral` with
   `onBehalf = BENEFICIARY` and empty callback data → Morpho's returned assets (and shares for full repay) must equal the
   request → allowance reset to 0 → **exact** balance deltas on the vault and on Morpho.
4. Post-state: repay ⇒ collateral unchanged and debt strictly lower; top-up ⇒ collateral `+ amount` exactly and borrow
   shares unchanged; full repay ⇒ borrow shares 0 and collateral unchanged. Partial actions: LTV strictly lower,
   `≤ maxLtvAfter` (keeper's plan bound) and `≥ minLtvAfter` (owner floor against over-spending).
5. `lastActionAt`, `actionCount`, event `RescueExecuted(actionId, strategy, assets, debt/collateral/LTV before and after, policyNonce)`.

Policy validation in `setPolicy`: strategies non-empty and known; `0 < triggerLtv < LLTV`; `minLtvAfter < triggerLtv`;
`validUntil` in the future; per-action caps ≤ cumulative caps (full repay included in the repay budget).

## 4. Threat model

| # | Threat | On-chain mitigation | Off-chain mitigation | Evidence |
|---|---|---|---|---|
| T1 | Keeper key stolen; attacker tries to send the reserve to itself | No transfer / recipient / call function; destination fixed (Morpho, `onBehalf = BENEFICIARY` immutable); no fallback / receive | Owner can `setKeeper`, `setPaused`, `revoke`, `withdrawReserve` at any time | `test_maliciousKeeper_cannotSpendOutsidePolicy`, `test_noArbitraryCallsNoEth`, invariants `tokenConservation` + `noPrivilegeEscalation`, e2e `test_e2e_duplicate_and_malicious_keeper_transactions_fail` |
| T2 | Keeper spends the reserve without a crisis | Trigger re-checked on-chain with Morpho's accrued debt and the market oracle | Engine never executes below the trigger (scenario breach ⇒ alert only) | `test_hold_whenNotAtRisk_noTokenMoves`, fuzz `repay/topUp_respectsPolicyOrRevertsCleanly`, e2e `hold_when_healthy_and_alert_below_trigger` |
| T3 | Keeper over-spends (repays / locks more than needed) | Per-action + cumulative caps, reserve floors, owner LTV floor, strict improvement, cooldown | Engine computes the exact minimum; keeper bound `maxLtvAfter` / `maxAssets` from the plan | `test_ltvFloor_and_keeperBound`, `test_cumulativeCap_acrossActions`, `test_reserveFloor`, invariant `capsNeverExceeded` |
| T4 | Replay or repetition of an action | `actionUsed`, cooldown, trigger re-check | Journal + resolution from chain state before any new send | `test_e2e_duplicate_and_malicious_keeper_transactions_fail`, Foundry replay checks |
| T5 | Plan computed under an old policy executes after the owner changed it | `expectedPolicyNonce` must equal `policyNonce` | Policy nonce read at planning and validation | `test_policyChange_invalidatesPendingPlan_andResetsBudget` |
| T6 | Keeper borrows or withdraws the user's collateral | Code paths do not exist; the vault has no Morpho authorization; post-state checks | — | invariant `noBorrowNoCollateralWithdrawal`, Morpho position of the vault always empty |
| T7 | Wrong market / beneficiary | `immutable`; constructor checks existence and every parameter against `idToMarketParams` | Reader re-validates the vault's market against Morpho | `test_constructor_rejectsUnknownMarket` |
| T8 | Fee-on-transfer, rebasing, false-returning tokens | `SafeERC20`; exact deltas on vault and Morpho ⇒ revert (fail closed) | — | `test_feeOnTransferCollateral_isRefused`, `test_falseReturningToken_isRefused` |
| T9 | Reentrancy (token hooks, callbacks) | `nonReentrant` on every token-moving entry point; Morpho callbacks disabled (empty `data`) | — | `test_reentrancyThroughTokenHook_isBlocked`; Slither triage §6 |
| T10 | Interest / rounding drift between plan and inclusion | Debt accrued in the same tx; partial repay `< debt`; full repay pulls `toAssetsUp(shares)` bounded by `maxAssets` | Interest projected over the horizon; +2 wei repay rounding; full-repay bound debt × 1.001 | `test_interestAccrued_isIncludedOnChain`, `test_partialRepay_cannotExceedDebt_fullRepayBounds`, fuzz `ltvAgreesWithMorphoHealth`, engine minimality tests |
| T11 | Oracle manipulated downwards to open the trigger | Bounded by caps and floors; the tokens still go to the user's own position | Dependency Engine: feed freshness, mover attribution, implicit assumptions | Residual risk (§7) |
| T12 | Stale oracle feed | Not checked on-chain (Morpho does not either) | Feed older than heartbeat + 30 min ⇒ `NO_ACTION` (fail closed) | e2e `test_e2e_stale_feed_means_no_action` |
| T13 | Price moves between planning and sending | On-chain re-check of everything | Fresh re-plan at validation, same strategy required, `eth_call` of the exact calldata from the keeper | e2e `test_e2e_price_moves_during_validation_replans` |
| T14 | Owner pauses / withdraws while a keeper tx is in flight | The tx reverts (`IsPaused`, `ReserveFloor`) | Recorded as FAILED from the receipt; never re-sent blindly; the next pass refuses before sending | e2e `test_e2e_onchain_revert_is_failed_not_retried_blindly` |
| T15 | Keeper crash after broadcast; ambiguous or dropped broadcast | `actionUsed` prevents double execution | Pending action journaled **before** broadcast; resolution order receipt → `actionUsed` + logs → nonce → tx known; re-plan only once the chain proves non-execution | e2e `keeper_killed_after_broadcast_resumes_without_resending`, `ambiguous_broadcast_resolved_from_chain`, `dropped_transaction_is_failed_then_replanned` |
| T16 | Liquidator acts first | Pre-flight re-reads the position: reverts (`NoDebt`, `NotAtRisk`, `NoImprovement`) or acts on the remaining position | — | Residual risk: rescue can come too late |
| T17 | MEV / sandwich | No swap, no price-dependent output: nothing to extract from the rescue itself | — | — |
| T18 | Gas spike | — | Gas-unit cap, fee cap and keeper balance checked before signing ⇒ `NO_ACTION` with the reason | e2e `test_e2e_gas_cap_and_watch_only` |
| T19 | Accidental use against mainnet | — | `assert_local`: loopback URL **and** chain id ∈ {31337, 1337} before the keystore is even unlocked; the signer itself refuses any chain id other than 31337 before invoking `cast`; transactions are signed for chain 31337 (EIP-155 / EIP-1559 chain binding: not replayable on mainnet) | `test_chain_guard_refuses_non_local` (incl. a fork that kept chain id 1), `test_signer_keeps_the_key_off_command_lines_and_refuses_other_chains` (1, 1337, 8453 refused) |
| T20 | RPC down / inconsistent | — | RPC errors keep the position in WATCHING with `rpc_error`; pre-send failures are `NO_ACTION` | e2e `test_e2e_rpc_down_is_handled` |
| T21 | UI shows a success that did not happen | — | View-model refuses CONFIRMED without a 32-byte tx hash, `verified = true` and all checks passing; flags contradictory payloads | Node `countermove_view.test.mjs` |
| T22 | Secret leakage | — | Keeper key never on a command line nor in the keeper's environment: `cast mktx --keystore <file> --password-file <file>` decrypts an encrypted keystore inside `cast`; process arguments carry only the two paths; a plaintext `FAULTLINE_KEEPER_KEY` is refused; the demo keystore holds the **public** Anvil test account #1, is created per run in a temporary folder outside the repository (password from `secrets`, passed to `cast wallet import` through its environment) and deleted afterwards; `KeystoreSigner.__repr__` shows only the address; no key in the repository | e2e `test_signer_keeps_the_key_off_command_lines_and_refuses_other_chains`; evidence `secrets_scan` (§8) |

## 5. Off-chain guards summary

Chain guard (local only) → watch-only if no key → `eth_call` of the exact calldata from the keeper → gas estimate ≤ cap
(700,000 in the demo) → max fee ≤ cap → keeper ETH ≥ worst-case gas → sign (explicit nonce, gas, fees, chain id) →
journal `pending` with the raw transaction and hash → broadcast → receipt → Verifier (receipt status, vault event,
Morpho event for the beneficiary, re-read state at the receipt block, exact reserve movement, counters, LTV / buffer
improvement, LTV ≤ keeper bound, vault holds no Morpho position). Any failure before sending ⇒ `NO_ACTION` with the
reason; any on-chain revert ⇒ `FAILED` with the decoded custom error; backoff after `FAILED`; alerts de-duplicated.

## 6. Static analysis

### Slither 0.11.6 (102 detectors; `slither . --filter-paths "lib/|test/" --exclude-dependencies` in `contracts/`)

25 contracts analysed, **52 results, none requiring a code change**. Raw output: `audit/FAULTLINE_PHASE2_SLITHER.txt`.

| Detector | # | Where | Assessment |
|---|---|---|---|
| `reentrancy-balance` | 6 | `RescueVault._pull` | Intentional: the "stale" balances are the *before* values of the exact-delta check (the point is to compare before/after). The only external calls go to the immutable Morpho singleton and to the market's own tokens; every token-moving entry point is `nonReentrant`; Morpho callbacks are disabled (empty data). |
| `reentrancy-no-eth` | 3 | `execute*` → `_record` (`lastActionAt`) | Same reasoning; `lastActionAt` is only read inside `nonReentrant` keeper entry points. Accepted. |
| `reentrancy-benign` | 6 | budget / counter writes around `accrueInterest` and `_pull` | Benign by Slither's own classification. |
| `unused-return` | 2 | `_pull` ignores the shares of a partial repay; sim oracle | Returned assets are checked; the share effect is verified by the post-state snapshot (debt strictly lower, collateral unchanged). |
| `missing-zero-check` | 6 | keeper in constructor / `setKeeper`; sim oracle | Intentional: keeper `0` = automation off (as after `revoke`); `_preflight` rejects a zero keeper explicitly. |
| `timestamp` | 2 | expiry and cooldown | Accepted: validator timestamp drift (seconds) is irrelevant for a 30-day expiry and a 1-hour cooldown. |
| `uninitialized-state`, `constable-states`, `missing-inheritance` | 4 + 5 + 2 | `ShockFeed`, `SimFeed` (test-only) | By design: `ShockFeed` code is installed at a real feed address with `anvil_setCode` and its storage is written with `anvil_setStorageAt`, so the variables must stay in storage and start uninitialised. |
| `naming-convention` | 16 | `UPPER_CASE` immutables | Style choice (common convention for immutables). |

### `forge lint` (Foundry 1.8.5) on `src/`

30 warnings (16 on `RescueVault.sol`, 14 on test-only sim contracts): `reentrancy-no-eth` 4, `incorrect-strict-equality` 3
(lines 205, 339, 340 — the exact-delta checks, intentionally strict: any unexpected token movement reverts, and no third
party can change these balances inside the transaction without re-entering, which is blocked), `block-timestamp` 3,
`missing-events-access-control` 2 (`setPolicy` does emit `PolicySet`; `actionUsed` is covered by `RescueExecuted` in
the same transaction or rolled back), `missing-zero-check` 2 + 4 (as above), `reentrancy-events` 1 (event emitted from the
final state), `unused-return` 1 + 1, `uninitialized-state` 5 and `unsafe-typecast` 4 (sim contracts only). No change.

## 7. Residual risks (what this prototype does not solve)

1. **No audit, no formal verification.** Invariant and fuzz campaigns are bounded (512 fuzz runs, 64 × 64 invariant
   calls); they do not explore every state.
2. **Oracle trust.** The vault trusts the market oracle. A manipulated or wrong oracle can open the trigger; the damage
   is bounded by the caps, and tokens still reduce the user's own debt or add to their own collateral. Exchange-rate
   adapters (e.g. weETH/ETH) report no timestamp: they are flagged `no_timestamp` rather than stale. Heartbeats are
   configured per feed, not read from Chainlink (UNVERIFIED per feed).
3. **Within its bounds a malicious keeper still chooses the amount.** It can spend more than the engine's minimum, up to
   the per-action cap and down to the owner's LTV floor, once per cooldown, only while the on-chain LTV is above the
   trigger. The owner sets those bounds; tight caps and a high floor limit this.
4. **Liveness.** One keeper process; if it is down, out of gas or outrun by liquidators, nothing happens. The contract
   promises nothing about action, only about limits. Production would need redundant keepers, monitoring and alerting.
5. **Market conditions not reproduced by the fork.** Anvil automine: no mempool competition, no gas spikes, no MEV,
   no reorgs. A private transaction relay would be needed on mainnet.
6. **Owner errors.** A low trigger or generous caps spend the reserve earlier or larger than intended; `setPolicy`
   validation only rejects incoherent policies. An owner-key compromise can withdraw the reserve (the owner key is the
   user's own wallet key — no worse than a wallet compromise).
7. **Token coverage.** Standard ERC-20s (6 / 8 / 18 decimals), fee-on-transfer, false-returning and hook tokens are
   tested; rebasing tokens are refused by the delta checks (fail closed) rather than supported.
8. **Signer.** *Hardened:* the key no longer appears in process arguments (it used to be passed to
   `cast mktx --private-key`). The keeper signs with `cast mktx --keystore <file> --password-file <file>` from an
   encrypted Web3 Secret Storage keystore; only the two paths are visible on the command line, a plaintext key variable
   is refused, and the signer refuses any chain id other than 31337. Remaining: it is still a hot key — anyone who can
   read both files as the operator's user (or the keeper's memory / a `cast` process while it signs) can sign; the
   password file is protected only by file-system permissions. In-process signing (`eth_account`) was not chosen: it is
   absent from the environment and would add ~20 packages (pydantic, ckzg, py-ecc…) for no reduction of this residual
   risk. A real deployment needs a hardware / remote signer (cast supports Ledger, Trezor, AWS / GCP KMS) and a hardened host.
9. **Scope.** DELEVERAGE + SELL, refinancing and hedging were deliberately not built; collateral is never sold, so FULL
   REPAY removes the borrowing liquidation risk, not the price exposure.

## 8. Secrets and environment hygiene

- No private key, mnemonic other than the public Anvil test mnemonic, API key or `.env` file is stored in the repository.
  The keeper key is never stored: each demo run creates an encrypted keystore of public Anvil account #1 in a temporary
  folder outside the repository (`signer.import_test_keystore`) and deletes it at the end; the keeper process receives
  only `FAULTLINE_KEEPER_KEYSTORE` and `FAULTLINE_KEEPER_PASSWORD_FILE` (paths).
- The journal stores signed raw transactions (chain id 31337) and hashes, never keys.
- `scripts/collect_phase2_evidence.py` scans the repository (excluding `.venv`, `contracts/lib`, `contracts/out`,
  caches) for the ten Anvil test private keys and for generic `private key = 0x<64 hex>` assignments; the result is in
  `audit/FAULTLINE_PHASE2_EVIDENCE.json` → `security.secrets_scan`.
- `.gitignore` excludes Foundry dependencies and build outputs and runtime keeper journals; the recorded demo run in
  `data/countermove/demo/latest/` is committed as evidence.

## 9. What would be required before any real funds

Independent audit of `RescueVault.sol`; formal properties (caps, destination, no borrow / withdraw) proven with a
verifier; per-market oracle review and on-chain freshness bounds; hardware / remote signer; redundant keepers with
monitoring and private transaction submission; a staged deployment with small caps; legal and product review of
automated actions on users' positions.
