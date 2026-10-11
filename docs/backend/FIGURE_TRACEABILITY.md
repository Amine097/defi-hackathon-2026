# Figure traceability: $761, $216,597, $192,784

Answers the jury question "these numbers don't agree" (Defensible impact, 30%). They don't need to agree: they measure
three different things on the same position. Every value below is read from
`public/data/recorded/analyze-pt.json`, a saved live `/api/analyze` response (labelled RECORDED LIVE RUN in the app).

## Common context

| Field | Value | JSON path |
|---|---|---|
| Position | PT-reUSD-10DEC2026 held as collateral on Morpho (USDC loan market), **no debt** | `position.label`, `position.meta.exposure_role = collateral_only` |
| Notional | $1,000,000 (hypothetical size chosen by the user, not a real holder's balance) | `position.value_usd` |
| Horizon | 30 days | `position.horizon_days` |
| Chain state | Ethereum mainnet, block 26,166,580 | `position.meta.block_number`, `_snapshot.block` |
| Recorded | 2026-10-11 03:40 UTC, backend commit `1403dac`, 133 live reads, 0 cached | `_snapshot`, `provenance` |

## The three figures

| Figure | What it is | Question it answers | Formula / source |
|---|---|---|---|
| **$761** (band $39 – $19,664) | **Expected loss**, probability-weighted, over 30 days | "What do I lose on average if I stay?" | `decision.expected_loss_usd`. Central = V × (1 − ∏(1 − pᵢ·LGFᵢ·Tᵢ)) over every dependency (independence, best-path transmission). Band: low parameters / union bound at high parameters (any correlation) → `decision.loss_band` |
| **$216,597** | **Conditional loss IF** the base asset (US dollars held as bank deposits / T-bills behind reUSD) loses 30% | "How bad is it if that one thing breaks?" | `stress_table[id=base_usd_fiat].conditional_loss_usd`. Severity 30% (**structural assumption**, not calibrated) × transmission 0.72 along `pos → pendle_core → underlying → usd_usdc → base_usd_fiat` → $216,000, + the baseline expected loss of every other dependency ($596) |
| **$192,784** | **Conditional loss IF** the Pendle PT/SY contracts (or, separately, Morpho Blue) are exploited | Same question, for a smart-contract exploit | `stress_table[label=Pendle PT / SY contracts…]` and `[label=Morpho Blue (protocol)]`. Severity 19.2% (**calibrated**: mean share of TVL lost in 23 DefiLlama exploits, 95% CI 9.4–31.5%, `data/calibration/hack_severity.json`) × transmission 1.0 → $192,2xx, + baseline of the others |

Code: `src/defirisk/api_payload.py` `_stress_table` (conditional rows: the node is forced to fail, everything else stays
at its baseline probability); `decision` from the same graph; LGF priors in `src/defirisk/data/priors.py`.

## How they fit together

The expected loss is roughly the sum of each conditional loss weighted by its probability over 30 days. Exploit base
rates are 0.020–0.044% per 30 days, so a $192k conditional loss contributes about $38 (`node_contrib_usd.pendle_core`
= $37.67, `morpho` = $37.67). The largest single contributor is the USDC depeg history: $434 of the $761
(`node_contrib_usd.usd_usdc`).

**Decision:** REVIEW, lean STAY. Staying costs $761 expected. Exiting costs $5,448: $1,217 execution (Pendle SDK
quote) plus $4,230 carry forgone. STAY holds unless the true risk is more than **×7.16** the central estimate
(`decision.lean`). All sensitivity rows (p ×0.5 / ×2 / ×5.07, LGF low / high, transmission ±25%) keep STAY
(`sensitivity`).

**Conditional verdicts:** if the base asset breaks, the verdict becomes EXIT, because $216,597 > $5,448
(`verdict_if_shocked`). This is a "what if", not a forecast.

**Over the 60 days to maturity,** the lean is HOLD TO MATURITY, with low confidence (`maturity.best_over_window`).

## The historical "$192k EXIT" bug (fixed)

An earlier X-Ray UI recomputed losses in the browser. Clicking the Pendle AMM or the Morpho market showed
**"EXIT, $192k"**, while the backend said those nodes cannot cause a principal loss for a position with no debt. The AMM
only affects the exit price, and the Morpho market only matters with debt. That client-side code was removed
(`public/assets/js/xray/model.js` header). Every dollar value is now read from the server. Debt- and exit-channel rows
carry a `channel` note in `stress_table`, and the Oracle failure and Liquidity crisis scenarios return $761 STAY.

## Model honesty (what to say if asked)

| Kind | Examples |
|---|---|
| Observed on-chain | Market, oracle, collateral, block, utilization 83.7%, supply APY 6.66%, Pendle exit quote |
| Calibrated from data | Exploit probability (DefiLlama cohort base rate), exploit severity 19.2% (23 incidents), USDC depeg history |
| Structural assumptions | Chain LGF 30%, look-through base-asset severity 30%, transmission weights (expert, ±25% band) |
| Uncertainty | Loss band $39 – $19,664; Monte Carlo mean $872; VaR95 $0 because a failure is rarer than 5% in 30 days |
| Not modelled | Correlation is bounded, not estimated; exit timing assumes you sell before the shock reaches the PT price |

The two largest stress rows, Ethereum ($300,446) and the base asset ($216,597), are driven by assumptions. They are
illustrative, not calibrated.
