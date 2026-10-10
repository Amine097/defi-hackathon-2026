# FAULTLINE risk engine — Phase 0.5 validation

Scope: hardening items H01–H06 from [BELEM_PHASE_05_RISK_ENGINE_HARDENING.md](BELEM_PHASE_05_RISK_ENGINE_HARDENING.md). Structured evidence: [BELEM_PHASE05_EVIDENCE.json](BELEM_PHASE05_EVIDENCE.json). Status: [BELEM_PHASE05_PROGRESS.md](BELEM_PHASE05_PROGRESS.md).

## 1. Architecture (data path)

```
position (Pendle PT-USDC, Ethereum)                    src/defirisk/discovery.py
  └─ dependency graph: PT → Pendle market/SY → USDC → Circle; Morpho Blue market (oracle, IRM, LLTV)
       ├─ priors per node (DefiLlama stablecoins / hacks, labelled assumptions)   priors.py, discovery.py, uncertainty.py
       ├─ propagation + expected loss + Monte Carlo                                propagation.py
       ├─ liquidation (Morpho Blue formula, on-chain state)                        morpho.py, leverage.py
       ├─ exit cost: Pendle SDK quote → eth_call re-execution at a pinned block    sources.py, decision.py (quote_exit)
       ├─ carry forgone: PT implied APY vs USDC supply APY on the same market      morpho.market_rates, uncertainty.carry
       ├─ uncertainty bands + robust verdict                                       uncertainty.py, decision.decide_robust
       └─ freshness / provenance labels                                            freshness.py
API: api/analyze.py → api_payload.build_payload      UI: public/index.html, public/xray.html
```

## 2. Risk model (H01)

- **Mechanisms.** Each node has a failure probability `p` over the horizon `H`, a loss-given-failure `LGF` and per-edge transmission `T`. The loss reaching the position is `p × LGF × path T`.
- **Central estimate.** `1 − ∏(1 − p·LGF·T)` over nodes, using the best (maximum-transmission) path. This value is exact only under independence; it is not presented as a bound.
- **Dependence bounds** at central parameters: comonotone `max_i` (lower) to union bound `min(1, Σ_i)` (upper). In the diamond test (R10), a shared node is counted once.
- **Parameter classes** (`uncertainty.inventory`, exposed in the payload as `uncertainty`):

  | Class | Parameters | Low | High |
  |---|---|---|---|
  | observed | DefiLlama stablecoin depeg frequency | exact Garwood Poisson CI on the episode count, converted to horizon `H` | same |
  | calibrated | DefiLlama hacks base rate | ×0.5 | × prior_upper / prior_central |
  | assumption | everything else | ×0.2 | ×4 |
  | not_used | look-through (wrapper) nodes | — | — |

  LGF and T have class-specific ranges.
- **Loss band.** low = independence at low parameters; central = independence at central parameters; high = union bound at high parameters.
- **Scenarios.** Losses are conditional on the shock (p = 1). A fourth, correlated scenario (depeg 0.3 + oracle + AMM 0.5 + exit factor 0.5) dominates each of its components (R13).

## 3. Liquidation (H02)

- **Morpho Blue maths** (`morpho.py`): borrow shares → assets with virtual shares and assets, rounded up. `LIF = min(1.15, 1/(0.3·LLTV + 0.7))`, which gives 1.026167 at LLTV 0.915. Seized collateral = repaid × LIF / oracle price.
- **Independent check.** `verify_liquidation` replays the real liquidation tx `0x906a5315…e0d` (block 25829913), reading state at block N−1:
  - HF was 0.99770, so the position was liquidable;
  - repaid amount = full debt;
  - seized collateral matches the formula with a relative error of 4.2e-11.
- **Modes.**
  - Default: `unlevered_exposure`. Liquidation is NOT_APPLICABLE, which is different from "zero risk" (R05).
  - `?borrower=0x…` or `?borrower=auto` (largest borrower): reads debt, collateral, HF, liquidation price and distance on-chain. It then stresses the position over a price grid and the Monte Carlo samples.
  - The borrower P&L counts only equity lost plus penalty. Bad debt goes to lenders and is not added to the borrower (R09).
  - The borrower decision compares this P&L with the cost of deleveraging (indicative quote on the collateral + repay gas). It returns REVIEW if the distance to liquidation is below 10 %, because normal PT price volatility is not modelled.

## 4. Exit cost (H03)

- **Execution cost.** The Pendle SDK swap is built for the full size, then re-executed with `eth_call` at a pinned block. A state override funds and approves the PT (balance slot 0, allowance slot 1).
- **Quote status.**
  - `simulated`: the on-chain output equals the SDK output (gap 0 at the pinned block).
  - `indicative`: no simulation.
  - `replayed_cache`, `approximation`: constant-product fallback, labelled as such.
- **Cost breakdown.** fees + price impact + gas. Each item is counted once (R02).
- **Carry.** `V × (PT implied APY − USDC supply APY) × H/365`, with a ±50 % band. If the carry is unknown, it is excluded and confidence is downgraded to medium (R15).
- **Exit band.** A simulated quote gets a ±0 band; any other status gets ±25 %. Gas gets ±50 %. The carry is then added.

## 5. Decision rule (H01 + H05)

- **EXIT** if `loss_band.low > exit_band.high`.
- **STAY** if `loss_band.high < exit_band.low`.
- **REVIEW** in every other case.
  - REVIEW comes with a conditional `lean` and the break-even risk multiplier.
  - Any freshness blocker forces REVIEW: stale decisive data, cache replay, mock, approximation, or simulation mismatch.
- **TTLs:**

  | Data | TTL | Decisive |
  |---|---|---|
  | exit quote | 60 s | yes |
  | on-chain state | 120 s | yes |
  | market data | 900 s | no |
  | priors | 7 days | no |

- **Point verdicts** are kept for transparency:
  - `point_verdict` compares central loss with exit cost **including carry**;
  - `point_verdict_execution_only` reproduces the Phase 0 rule.

## 6. Observed live cases (Ethereum mainnet, 2026-10-10)

| Case | Block / source | Verdict | Central loss [band] | Exit execution | Exit incl. carry [band] |
|---|---|---|---|---|---|
| $1M PT, unlevered | 26162571, live, fresh | **REVIEW**, lean STAY | $1,657 [$171–$27,532] | $1,212–1,216, quote simulated | $4,897 [$3,052–$6,738] |
| $5M PT, unlevered | live | **REVIEW** | $8,287 [$853–$137,659] | $16,240 | [$25.4k–$43.8k] |
| $1M + `borrower=auto` | live | **REVIEW** | — | — | — |

- **$1M, unlevered.** Carry is $3,681 (PT 11.79 % vs USDC supply 7.31 %). The point comparison including carry gives STAY; on execution cost alone it gives EXIT.
- **$5M, unlevered.** Carry is $18.4k.
- **$1M + `borrower=auto`.** The borrower `0xAa34d20b…5Dd5` has HF 1.0544, 5.16 % from liquidation.
  - p(liquidation) is 0.34 %; the expected borrower loss is $11.5k and the expected lender bad debt is $12.7k.
  - Deleveraging costs $76.7k, on $12.17M of collateral.
  - The verdict is REVIEW because the distance to liquidation is below 10 %.
- **Latency.** 25–36 s; the borrower mode adds about 9 s. This is under Vercel's `maxDuration` of 60 s.

### Regression vs Phase 0 ($1M / $5M)

- **Phase 0** at $1M said **EXIT**: expected loss ≈ $1,654 > execution cost ≈ $1,212.
- **Phase 0.5** at $1M returns **REVIEW**, for two reasons:
  1. **Carry.** Exiting into USDC gives up a $3.7k excess yield over 30 days, so the point comparison flips to STAY.
  2. **Overlapping bands.** The defensible loss band ($171–$27.5k) overlaps the exit band ($3.0k–$6.7k), so neither firm verdict can be defended.
- The lean is "STAY holds if the true risk is below ×2.95 the central estimate".
- **$5M:** same mechanism. The exit side grows with price impact and carry; the loss band still overlaps it.
- **Reproducible replay.** `DEFIRISK_OFFLINE=1`, clock frozen. At $1M: REVIEW, point STAY, execution-only EXIT. At $5M, the cache holds no SDK quote, so the labelled `approximation` is used and REVIEW is forced. No verdict is hardcoded; tests only assert REVIEW for cache and mock modes.

## 7. Historical replay (H04)

`python scripts/replay_h04.py` produces [data/fixtures/replay_h04.json](../../data/fixtures/replay_h04.json). Tests: `tests/test_hardening.py::test_r16_*`.

- **USDC / SVB, March 2023.** Cut-off is 2023-03-11, and only data before the cut-off is used.
  - There were 0 depeg episodes in the 2.19 years before the cut-off, so the prior falls back to a non-zero floor.
  - The realised daily close on 2023-03-12 was $0.961.
  - The intraday low is not in the dataset (documented limit).
- **Morpho liquidation `0x906a5315…`.** State at block N−1 gives HF 0.99770 (liquidable), full repayment, and a formula error of about 1e-12.

## 8. Freshness and provenance (H05)

- The payload `decision.freshness` carries:
  - `label`: fresh / stale / replay / mock;
  - `blockers`;
  - per-item age vs TTL, with a block timestamp read from the chain.
- The UI shows the label. A saved snapshot fallback is shown as "saved snapshot, not fresh".
- API inputs are validated (`value_usd` finite and in [1e3, 1e8], severity in [0, 1], ids by regex, borrower address). Errors return 400 and never echo `ETH_RPC_URL` (R18).

## 9. Limitations (traced, not hidden)

- **Wide high band.** The union bound at high parameters is about 16× the central loss. The robust verdict is therefore often REVIEW. This is intended: assumption-class priors cannot support a firm call.
- **Unmodelled volatility.** Normal PT price volatility (outside failure events) is not modelled. For borrowers this is mitigated by REVIEW when the distance is below 10 %.
- **SVB replay.** It uses daily data only.
- **Breakeven multiplier.** `breakeven_risk_multiplier` excludes carry; the lean includes it.
- **Deployment** was tested on the production URL (https://faultline-sandy-three.vercel.app, block 26162693), not on a separate preview. On that deployment, the API latency was 13–18 s.

## 10. Reproduction

```powershell
$env:PYTHONPATH="src"; python -m pytest -q                              # offline: 54 passed, 3 skipped
$env:DEFIRISK_LIVE_TESTS="1"; python -m pytest -q                       # live:    57 passed
python scripts/replay_h04.py                                            # historical replays
python scripts/dev_server.py 8765                                       # http://127.0.0.1:8765/?borrower=auto , /xray.html
```

`ETH_RPC_URL` must point to an archive node that supports state overrides; drpc was used.
