# Phase 1 — Vault Risk Analyzer: validation

Live figures below come from `audit/BELEM_PHASE1_EVIDENCE.json` (blocks 26163199–26163202, $100k / 30 days unless stated). They move with the chain. The tests assert invariants, not these USD values.

## 1. Architecture (actual code)

```
public/vault.html ─ assets/js/vault.js ─ assets/js/vault/view.js (pure; checks backend identities, never recomputes)
        │  GET /api/vault?address=…&value_usd=…&horizon_days=…[&shock=<node id>&severity=…]
api/vault.py (Vercel)  /  scripts/dev_server.py (local)  →  vault_model.analyze(parse_request(q))
  vault_input.py   validation → VaultError(code, status)
  vault_reader.py  detection (factory registry), block-pinned eth_call snapshot, V2 adapters / V1 withdraw queue,
                   Morpho GraphQL cross-checks, DefiLlama prices, Chainlink EUR/USD, borrower positions
  vault_model.py   graph → depositor loss → exit / carry → decision → scenarios / sensitivity → payload faultline.vault/1
  Phase 0.5 engine reused: core.propagation (opt-in path_sum), uncertainty (bands, robust_signal), freshness, priors, morpho
```

There is no parallel engine and no silent mock. Every payload has `mode` = `live` or `replay` (fixture, labelled), and the UI shows it as a badge.

## 2. Support scope

- **Supported:** Ethereum mainnet (`chain_id=1`) only.
  - Morpho Vault **V2**: factory `0xA1D94F746dEfa1928926b84fB2596c06926C0405`, with Morpho Blue market adapters.
  - Morpho Vault **V1** (MetaMorpho): factory-registered, withdraw-queue markets.
- **Rejected cleanly:**
  - other chains → 400;
  - EOA or non-contract → 404 `not_found`;
  - a contract that is not a factory-registered Morpho vault → 422 `unsupported`;
  - a source down → 503 `source_unavailable`. A mock graph is never returned.
- **Partially attributable V2 adapters** (for example a vault holding another vault): the share is reported as `unattributed_share`. Coverage below 95 % forces REVIEW.

## 3. Calculations and P&L convention

The P&L belongs to the **depositor** of vault shares. `value_usd` is a **hypothetical** notional, converted to shares at the pinned share price. Losses are fractions of the vault's assets, so 0 ≤ loss ≤ value.

### Transmission to the depositor

| Shock | Depositor loss |
|---|---|
| Collateral failure (50 % jump drop) | **Only the bad debt** left after on-chain liquidations (Morpho Blue liquidation math, LIF from LLTV) on every indexed borrower. Debt the indexer does not list (it returns the largest positions) gets a **band**: low = no bad debt; central = the indexed borrowers' bad-debt rate per unit of debt shrunk toward the at-LLTV rate by the unindexed share `1 − c` (`r = c·r_indexed + (1 − c)·r_LLTV`; no list → at the LLTV); high = all of it at the LLTV (the former single assumption). The band is carried by the edge into `uncertainty.loss_band` (×0.75 / ×1.25 expert range on top). A borrower liquidation without shortfall costs the depositor **0**. |
| Oracle failure (40 % mis-pricing, direction unknown) | Over-pricing: the free liquidity `L` is drained at once (one block, flash-loanable); after correction the drained positions are liquidated and the liquidator keeps the incentive, so suppliers lose `L × max(0, 1 − (1 − d)/(LLTV × LIF))` (low end: full recovery, `L × max(0, 1 − (1 − d)/LLTV)`). Under-pricing: Morpho liquidates at the false price; while reported collateral × LIF covers the debt only borrowers lose, beyond that all collateral is seized and the rest is socialised to suppliers, as after a real drop of `d` (`bad_debt_fraction(d)` and its band). Central = mean of the two directions; band = milder direction at its low end … worse direction at its high end. |
| Morpho Blue / vault / curator / chain | Phase 0.5 protocol priors (shared Morpho prior ×0.5 each, chain 0.5 %/y). |
| Deposit asset depeg, EUR/USD | **Decision-neutral**: the asset is held after redeeming too. Shown as context and as a what-if scenario. |

### Aggregation

- Shared nodes are counted once (`path_sum` over distinct paths, capped at 1).
- Expected loss: EL = Σ p(node, H) × loss. The band is P10–P90 from `uncertainty`.

### Exit side

- Execution = gas (from the `eth_call` estimate) + friction (assets requested − assets out of the simulated `redeem`) + fee (0 on Morpho vaults; read on-chain).
- Carry = V × on-chain net APY (supply APY × share, net of the performance fee, **excluding rewards**) × H/365, with a ±50 % band. Its reference is 0 %, the yield given up by exiting to cash.
- Exit side = execution + carry. The **margin** is EL − exit side.

### Verdict (`uncertainty.robust_signal`)

| Verdict | Condition |
|---|---|
| **STAY** | The whole loss band is below the exit-side band. |
| **EXIT** | The whole band is above it, **and** the exit is fully feasible. A partial, zero or unknown exit turns EXIT into REVIEW (V26). |
| **REVIEW** | The bands overlap, or the coverage, freshness, cross-check or simulation is degraded. |

- REVIEW always reports the point lean and `breakeven_risk_multiplier` (the factor by which risk must be wrong to flip the verdict).
- Colours: STAY green, EXIT red, REVIEW amber with confidence low.

### Withdrawal capacity

| Vault | How capacity is computed |
|---|---|
| V2 | `maxRedeem`/`maxWithdraw` = 0 is a V2 design choice, not "no liquidity". Capacity = idle + liquidity adapter's market free liquidity, subject to the gates. It is cross-checked against Morpho GraphQL `liquidity`. Force-deallocate is shown as a non-standard path and is not counted. |
| V1 | Σ min(vault supply, market free liquidity) over the withdraw queue. A token balance held by a MetaMorpho vault is outside `totalAssets()` and is not used by withdrawals, so it is not counted. |

## 4. Sources

| Data | Primary | Cross-check |
|---|---|---|
| Version, asset, totalAssets, shares, adapters, allocations, caps, gates, fees | `eth_call` on public Ethereum RPC, pinned block | Morpho GraphQL `vaultV2ByAddress` / `vaultByAddress` (totalAssets rel. 2 %, APY 50 bp) |
| Market state, LLTV, oracle, IRM | Morpho Blue `market()` / `idToMarketParams()` at the block | Morpho GraphQL markets |
| Borrower positions | Morpho GraphQL `marketPositions` (paginated) | Unindexed remainder: band (none / indexed rate shrunk toward LLTV / at LLTV) |
| Asset USD price | DefiLlama coins (max age 1 h) | Morpho GraphQL `asset.price.usd` (1 %) |
| EUR/USD | Chainlink EUR/USD feed (max age 26 h) | n/a (decision-neutral) |
| Event probabilities | Phase 0.5 priors (DefiLlama hacks base rates) | n/a (assumption, labelled) |

## 5. Limitations (stated in the UI and payload `assumptions`)

- Probabilities are horizon-scaled annual base rates, not forecasts. **This is not investment advice and not a regulatory audit.**
- Ordinary capacity is shared with all depositors and can change every block.
- Supply-cap and gate changes by the curator are not modelled.
- Shock severities (50 % / 40 %) are assumptions. The sensitivity table shows how the verdict moves when they change.
- All five live cases were REVIEW (lean STAY) at collection time. Firm STAY and EXIT appear on recorded real snapshots with controlled shocks (V19).

## 6. Tests V01–V26

Commands:
- Offline: `$env:PYTHONPATH='src'; python -m pytest -q -p no:cacheprovider` → 135 passed, 14 skipped.
- Live: add `$env:DEFIRISK_LIVE_TESTS='1'` → 149 passed.
- Node: `node --test tests\js\vault_view.test.mjs tests\js\decision_view.test.mjs` → 17 pass.

| ID | Status | Evidence |
|---|---|---|
| V01 | PASS | `test_v01_invalid_addresses_rejected`, `_checksum_roundtrip`, `_eoa_and_non_vault_contract`, `_url_input_no_ssrf`. Live: `test_live_http_errors` (EOA → 404). E2E: `0x123` → client error. |
| V02 | PASS | `test_v02_chain_must_be_ethereum` (any chain ≠ 1 → 400, no discovery). |
| V03 | PASS | `test_v03_value_bounds` (0, −5, NaN, ±inf, 1e400, 1e12, 999 below the minimum, "abc", "1,000", "0x10"), `test_v03_other_parameters` (horizon, severity, shock). |
| V04 | PASS | `test_v04_detection_by_factory`, `test_v04_fixture_versions`. Live: Belem / Confidential / USDC Yield = v2, Steakhouse = v1. |
| V05 | PASS | `test_live_belem_onchain_identity`: v2, EURCV, 18 decimals, factory. Evidence block 26163199: 6 markets, coverage 1.0, totalAssets rel. diff 1.1e-7 vs API. |
| V06 | PASS | `test_live_two_other_v2_vaults` (Confidential `0xc207…Da36`, USDC Yield `0xE018…1965`), `test_live_v1_metamorpho` (Steakhouse `0xBEEF…64CB`). Coverage 1.0 on all. |
| V07 | PASS | `test_v07_graph_changes_with_address`. Live graphs: 24 / 16 / 23 / 33 nodes. No address-specific code. |
| V08 | PASS | `test_v08_v1_withdraw_queue`. Live Steakhouse: 12 queue markets, capacity = Σ min(supply, liquidity). |
| V09 | PASS | `test_v09_v2_max_redeem_zero_is_not_zero_liquidity`, `test_v09_closed_gate_blocks_ordinary_exit`. Live Belem: `maxRedeem` = 0, capacity ≈ $404.9k, API cross-check ok. |
| V10 | PASS | `test_v10_reconciliation`: Σ allocations + idle + unattributed = totalAssets, shares sum to 1, pagination. Per adapter (strict holder match, each adapter credited at most what it reports): `test_v10_per_adapter_gaps_not_masked`, `test_v10_v1_reconciliation_is_not_a_tautology` (V1 checked against `MetaMorpho.totalAssets()`, idle outside it), `test_v10_adapter_gap_warning_and_unattributed_node`. |
| V11 | PASS | `test_v11_shared_dependency_one_node_no_double_count`. E2E Steakhouse: Morpho Blue is one node behind 12 allocations. |
| V12 | PASS | `test_v12_liquidation_without_shortfall_costs_depositor_nothing`, `test_v12_unindexed_debt_without_list_is_valued_at_lltv`, `test_v12_partial_coverage_band`, `test_v12_coverage_band_reaches_the_uncertainty_band`, `test_v12_oracle_failure_both_directions`, `test_v12_mild_underpricing_costs_suppliers_nothing`, `test_v12_oracle_edge_band_in_graph`. |
| V13 | PASS | `test_v13_scenarios` (collateral crash, oracle, market failure, liquidity crisis, correlated, deposit-asset what-if), each with paths. Also `test_v13_custom_shock_targets_this_vault`. |
| V14 | PASS | `test_v14_bounds_and_monotonicity` (0 ≤ loss ≤ V, monotone in severity), `test_v14_linear_in_exposure`, decimals 6 and 18. |
| V15 | PASS | `test_v15_eurcv_price_fx_and_peg` (EURCV USD vs Chainlink EUR/USD; depeg = price / FX − 1), `test_v15_missing_fx_no_firm_usd`. |
| V16 | PASS | `test_v16_share_valuation`. The payload labels `value_usd` as HYPOTHETICAL. |
| V17 | PASS | `test_v17_partial_zero_unknown`. Live Belem $1M: withdrawable $404.9k, blocked $595.1k, `simulated_partial`. |
| V18 | PASS | `test_v18_cost_breakdown`, `_rewards_not_counted_in_carry`, `_horizon_scaling`. Live: `test_live_carry_from_onchain_apy` (on-chain 2.613 % vs API 2.624 %). |
| V19 | PASS | `test_v19_three_verdicts_coherent` (STAY / EXIT / REVIEW), `_live_fixtures_coherent`, `_ui_fixtures_in_sync`. The Node `vault_view.test.mjs` checks margin, colour, lean and bands for all three verdicts. E2E consistency badge: OK. |
| V20 | PASS | `test_v20_stale_price`, `_indexer_disagrees`, `_api_down_is_a_warning_not_a_mock`, `_low_coverage`, `_stale_simulation` → REVIEW with a reason, never a firm live verdict. |
| V21 | PASS | `test_v21_http_status_and_no_leak` (400/404/422/503/500; no RPC URL or key in the body), `_payload_contract`, `_invalid_scenario`. Live: `test_live_http_ok_and_url_input`. Big integers are serialized as strings. |
| V22 | PASS | `test_v22_engine_default_unchanged` and the full Phase 0.5 suites (`ref=auto`, `borrower=auto`, Pendle quote, carry coherence) all pass. E2E dashboard and X-Ray still run live. |
| V23 | PASS | Browser on the local dev server (live sources), detailed below, and on the production URL (§V25). |
| V24 | PASS | `test_v24_offline_replay_deterministic_and_labelled` (4 dated fixtures, blocks 26163088–92, `mode=replay`), plus live runs. |
| V25 | PASS | Production deployment `42dfa00` (an empty trigger commit on top of `626191c` = Phase 1; identical tree), deployment `6983683515`, state success. Smoke test on https://faultline-sandy-three.vercel.app on 2026-10-10: static pages 200; 5 live `/api/vault` cases (blocks 26163255–57) with the margin identity verified; error codes 400/404/422/400 (`invalid_scenario`); custom shock; browser E2E (Belem block 26163265, deep link $1M partial block 26163266); Phase 0.5 `/api/analyze` regression. See §V25 below. |
| V26 | PASS | `test_v26_partial_exit_never_executable_exit`. A partial or zero exit can never yield an executable EXIT; the immediately withdrawable amount is shown. |

**Totals: 26 PASS, 0 FAIL, 0 BLOCKED, 0 N/A.**

### V23 browser observations

| Case | Observation |
|---|---|
| `0x123` | Client-side error, no request sent. |
| `0x…dEaD` (EOA) | Structured 404 shown, no graph. |
| Belem prefill button, then Analyze (block 26163170, 18.6 s) | REVIEW, amber, lean STAY ×3.40, confidence low. EL $63 [$11–$323], exit $215 (gas $0.07 + carry $215), margin −$152, consistency OK. 6 allocations, 25 nodes, 29 edges, 6 scenarios, 24 shock options, 6 sensitivity rows. |
| Deep link $1M / 90 d plus custom shock on mGLOeuro collateral at 0.6 | Partial: $404.9k withdrawable, $595.1k blocked, warning shown. Shock loss $365.3k. REVIEW lean STAY. |
| Steakhouse V1 | 12 markets, 34 nodes, shared nodes deduplicated. EL $53, exit $356, REVIEW. |
| Mobile width | Overflow found and fixed. |
| Phase 0.5 pages | Dashboard and X-Ray still live. Nav links present. |

### V25 production smoke test (2026-10-10, https://faultline-sandy-three.vercel.app)

**Deployment check.**
- `gh api …/deployments`: latest Production deployment is SHA `42dfa00` (created 16:32:40Z, state success).
- `git diff 626191c 42dfa00` is empty, and `git diff 42dfa00` with `git status` shows a clean local tree.
- So the deployed code is exactly the validated Phase 1 code.

**Static pages and assets.** `/`, `/xray.html`, `/vault.html`, `vault.js`, `vault/view.js` and `vault.css` all return 200.

**Error codes.**

| Request | Response |
|---|---|
| `0x123` | 400 `invalid_input` |
| EOA `0x…dEaD` | 404 `not_found` |
| `chain_id=10` | 400 `invalid_input` |
| `value_usd=0` | 400 `invalid_input` |
| USDT contract (not a vault) | 422 `unsupported_contract` |
| `shock=nope:x` | 400 `invalid_scenario` (lists the valid ids) |

**Live `/api/vault` runs** (`mode=live`, freshness `fresh`, coverage 1.0, cross-checks ok, margin = EL − (execution + carry) checked on every run):

| Case | Block | Version | Verdict | EL | Exit side | Margin | Withdrawal |
|---|---|---|---|---|---|---|---|
| Belem $100k / 30 d | 26163255 | v2 | REVIEW lean STAY | $63.2 | $214.8 | −$151.7 | full |
| Belem $1M / 90 d | 26163255 | v2 | REVIEW lean STAY | $1,893 | $6,443 | −$4,550 | **partial**: $404.9k now, $595.1k blocked |
| Confidential USDC | 26163256 | v2 | REVIEW lean STAY | $71.1 | $544.0 | −$472.9 | full |
| USDC Yield | 26163256 | v2 | REVIEW lean STAY | $70.6 | $523.5 | −$452.9 | full |
| Steakhouse USDC | 26163257 | v1 | REVIEW lean STAY | $52.9 | $356.1 | −$303.2 | full |

**Custom shock.** mGLOeuro collateral at severity 0.6 (Belem, $1M): 200, loss $365.3k, REVIEW.

**Browser on the production URL.**
- Belem pre-fill, then Analyze vault (5.1 s, block 26163265): live, fresh, coverage 100 %, quote simulated.
  - REVIEW lean STAY ×3.40; EL $63 [$11–$323]; exit $215; margin −$152.
  - Badge "figures consistent". Allocations, graph, scenarios, custom shock, sensitivity and withdrawal capacity are all rendered (capacity cross-check ok).
- Deep link at $1M / 90 d (block 26163266): withdrawal partial ($404.9k / $595.1k), REVIEW lean STAY, margin −$4,550, consistent.
- The first browser attempt failed only because the pre-fill and submit clicks were sent concurrently. The pre-fill was checked separately and works, and the sequential retry passed.

**Phase 0.5 regression in production.**

| Request | Result |
|---|---|
| `/api/analyze?borrower=auto` | 200, live, REVIEW, quote simulated, fresh, `borrower_position` |
| `?ref=auto` | 200, live, `unlevered_exposure` |
| `?value_usd=5` | 400 |

### Smoke test commands (rerunnable)

```powershell
gh api repos/Amine097/defi-hackathon-2026/deployments --jq '.[0] | {sha, environment, created_at}'   # must equal the pushed SHA
curl.exe -s -o NUL -w "%{http_code}\n" https://faultline-sandy-three.vercel.app/vault.html          # 200
curl.exe -s "https://faultline-sandy-three.vercel.app/api/vault?address=0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec&value_usd=100000&horizon_days=30" | python -c "import json,sys;d=json.load(sys.stdin);print(d['mode'],d['vault']['version'],d['allocations']['coverage'],d['decision']['verdict'],d['decision']['margin_usd'])"
curl.exe -s -o NUL -w "%{http_code}\n" "https://faultline-sandy-three.vercel.app/api/vault?address=0x123"   # 400
```

## 7. Gates G01–G12

| Gate | Status | Evidence |
|---|---|---|
| G01 | PASS | Address and amount form → live `/api/vault`, locally and in production (V23, V25). The Belem button only pre-fills the address; nothing is precomputed. |
| G02 | PASS | Detection through the factory registry (V04). Scope in §2. Clean 400/404/422 errors (V01, V21). |
| G03 | PASS | Belem verified live as V2 / EURCV and analyzed end to end (V05, V23, evidence `belem`). |
| G04 | PASS | Confidential USDC (V2), USDC Yield (V2) and Steakhouse USDC (V1) analyzed live. No address-specific discovery (V06, V07). |
| G05 | PASS | Reconciliation (V10). Coverage 1.0. Price, totalAssets, APY and capacity cross-checks ok. Freshness `fresh`, block-pinned (V20 covers degradation). |
| G06 | PASS | Vault-specific graph with deduplicated nodes and justified transmission per edge (V07, V11). |
| G07 | PASS | Depositor-only loss: bad debt and drain, never the raw borrower loss (V12). Scenarios, assumptions and bands shown (V13, V14). |
| G08 | PASS | Fees, gas, friction, capacity, partial exit, USD conversion and carry separated. V1 and V2 capacity rules differ (V08, V09, V17, V18). |
| G09 | PASS | Backend, Node and UI agree on all three verdicts. Borderline cases → REVIEW with the lean and the reason (V19, V26). |
| G10 | PASS | Offline 135 passed, live 149/149, Node 17/17. No open P0 or P1 issue. |
| G11 | PASS | Production deployment `42dfa00` (tree identical to `626191c`, Phase 1). The SHA was checked with the GitHub deployments API and git. The production smoke test covered the API, error codes, custom shock, browser E2E and Phase 0.5 regression (V25). |
| G12 | PASS | This document, the progress log, evidence JSON (secret-free) and README instructions. Offline replay and live checks are reproducible. |

## 8. Redacted payload example (Belem, block 26163199)

```json
{"schema": "faultline.vault/1", "mode": "live", "as_of_block": 26163199,
 "vault": {"address": "0xD6d4…48Ec", "name": "Belem RWA EURCV", "version": "v2", "asset": {"symbol": "EURCV", "decimals": 18, "currency": "EUR"}},
 "allocations": {"coverage": 1.0, "idle_share": 7.3e-10, "unattributed_share": 0.0, "items": ["mGLOeuro 85.8 %", "WBTC 9.7 %", "cbBTC 2.5 %", "wstETH 2.1 %", "…"]},
 "risk": {"expected_loss_usd": 63.16, "band_usd": [11.31, 323.31]},
 "exit": {"withdrawal_feasibility": "full", "immediately_withdrawable_usd": 100000, "quote_status": "simulated",
          "gas_usd": 0.07, "withdrawal_friction_usd": 0, "exit_fee_usd": 0, "carry": {"usd": 214.76, "net_apy_onchain": 0.02613}},
 "decision": {"verdict": "REVIEW", "colour": "amber", "point_verdict": "STAY", "confidence": "low",
              "exit_side_usd": 214.83, "margin_usd": -151.67, "breakeven_risk_multiplier": 3.40,
              "reasons": ["uncertainty bands overlap: staying loss $11-$323 vs exit $107-$322"]}}
```
