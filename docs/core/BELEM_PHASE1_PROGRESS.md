# Phase 1 — Vault Risk Analyzer: progress log

Spec: [BELEM_PHASE_1_VAULT_RISK_ANALYZER.md](BELEM_PHASE_1_VAULT_RISK_ANALYZER.md).
Validation: [BELEM_PHASE1_VALIDATION.md](BELEM_PHASE1_VALIDATION.md).
Evidence: [`audit/BELEM_PHASE1_EVIDENCE.json`](../../audit/BELEM_PHASE1_EVIDENCE.json).

- **Base SHA at start:** `ffd7df1` (Phase 0.5 GO).
- **Phase 1 commit:** `626191c`, pushed by the owner.
- **Production SHA:** `42dfa00`, from the GitHub deployments API (deployment `6983683515`, success). It is an empty trigger commit on top of `626191c`, so the tree is identical. The Phase 1 routes are live.

## 0. Start-of-phase checks (spec §7.1–7.2)

| Check | Result |
|---|---|
| `git status` / HEAD | Clean at `ffd7df1` = deployed production SHA. The Phase 0.5 report is GO. |
| Belem vault type (read-only `eth_call`) | `0xD6d4…48Ec` is a **Morpho Vault V2**: factory `0xA1D94F74…0405` `isVaultV2` is true. Asset is EURCV `0x5F78…5Ff2` (18 decimals). It has 6 Morpho Blue markets via the market adapter, a liquidity adapter on the mGLOeuro market, and `maxRedeem` = 0 by design. **Compatible.** |

## Work packages

| WP | Status | Delivered | Tests |
|---|---|---|---|
| P1-01 Input & validation | DONE | `src/defirisk/vault_input.py`: address, checksum and URL parsing (SSRF-safe: no fetch, only an address extracted from an allow-listed host); `chain_id=1` only; bounded `value_usd` / `horizon_days` / `shock` / `severity`; `VaultError` → 400/404/422/503. `api/vault.py` (Vercel function) and a `/api/vault` route in `scripts/dev_server.py`. | V01–V03, V21 |
| P1-02 Discovery & snapshot | DONE | `src/defirisk/vault_reader.py`: version detection by factory registry (V1 MetaMorpho / V2), on-chain reads pinned to a single block, and a paginated V2 adapter → market walk or V1 withdraw queue. Cross-checks against Morpho GraphQL (totalAssets, asset, APY, capacity). Prices from DefiLlama, FX from Chainlink EUR/USD. `scripts/record_vault_fixture.py` writes dated fixtures. | V04–V10, V15, V16, V24 |
| P1-03 Vault graph | DONE | `vault_model.build_graph`: depositor → vault → markets → collateral / oracle / IRM → Morpho Blue → chain. Shared dependencies are one node (`exposed_allocations`). Opt-in `path_sum` propagation in `core/propagation.py` keeps the default unchanged for Phase 0.5. | V07, V11, V22 |
| P1-04 Depositor loss model | DONE | Bad debt after on-chain liquidations, oracle drain, protocol priors, a decision-neutral deposit asset, 5 scenarios plus a custom shock, sensitivity, uncertainty bands (`uncertainty.py` path-sum support). | V12–V16 |
| P1-05 Exit & decision | DONE | Ordinary capacity (V2: idle + liquidity adapter, `maxRedeem` = 0 handled; V1: withdraw queue). Partial / zero / unknown exits. `eth_call` redeem simulation, gas, friction, fee. Carry = on-chain net APY × H, excluding rewards. Robust STAY/EXIT/REVIEW via `uncertainty.robust_signal`; EXIT → REVIEW unless the exit is fully feasible. | V17–V20, V26 |
| P1-06 UI | DONE | `public/vault.html`, `assets/js/vault.js`, `assets/js/vault/view.js` (pure view model that verifies backend identities and never recomputes), `assets/css/vault.css`. Includes form, deep links, Belem prefill, verdict card, allocations, graph, scenarios, custom shock and sensitivity. Nav links added in `shell.js` and `xray.html`. | V19, V23, Node tests |
| P1-07 Tests, docs, evidence | DONE | `tests/test_vault.py` (73), `tests/test_vault_live.py` (11 live tests), `tests/js/vault_view.test.mjs`, UI fixtures, `scripts/collect_vault_evidence.py`, and this log plus the validation doc, evidence JSON, report appendix and README. | V21–V26 |

## Commands and results (last full run)

| Suite | Command | Result |
|---|---|---|
| Offline | `$env:PYTHONPATH='src'; python -m pytest -q -p no:cacheprovider` | **135 passed, 14 skipped** (the skipped tests are live-gated) |
| Live | `$env:PYTHONPATH='src'; $env:DEFIRISK_LIVE_TESTS='1'; python -m pytest -q -p no:cacheprovider` | **149 passed, 0 skipped** (177.6 s) |
| Node (UI view models) | `node --test tests\js\vault_view.test.mjs tests\js\decision_view.test.mjs` | **17 pass, 0 fail** |
| Live evidence | `$env:PYTHONPATH='src'; python scripts\collect_vault_evidence.py` | 5/5 cases at blocks 26163199–26163202, all cross-checks ok, freshness `fresh` |
| Browser E2E | dev server `python scripts\dev_server.py 8765` + browser | See VALIDATION §V23 |

## Fixes made during validation

- **Test bug:** the scenario `vault` field is the bare address, not `vault:<addr>`. Fixed in the test, not in the model.
- **Mobile overflow:** the custom-shock select overflowed horizontally. Fixed with `min-width:0` / `minmax(0,1fr)` and re-checked.
- **V1 idle markets:** the label read "idle" with no context. It now reads "idle market (no collateral)".
- **Evidence collector:** it dropped the source fields of the price cross-check. Fixed.

## Deployment (G11 / V25) — closed on 2026-10-10

- The owner pushed `626191c` (Phase 1); Vercel deployed `42dfa00`, an empty trigger commit with the same tree, to Production.
- The SHA was checked with `gh api …/deployments` and `git diff`.
- The production smoke test passed: static pages, 5 live `/api/vault` cases, error codes, custom shock, browser E2E and Phase 0.5 regression. Details are in VALIDATION §V25 and in `production_smoke` in the evidence JSON.
- **Phase 1 verdict: GO.**
