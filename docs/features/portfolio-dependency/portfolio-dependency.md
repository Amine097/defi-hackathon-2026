# What You Really Hold — Token Dependency Map (Complete Specification v2)

**Project:** Belem Capital EPFL Hackathon 2026 · FAULTLINE / Pendle X-Ray
**Audience:** a coding LLM working in the existing repository
**This document replaces** "Implementation Spec — Crypto Dependency Map" (v1) and "Crypto Dependency Map — Phase 2". It contains everything: what the feature is, what is already built, and what to build next.

**How to read it:** every section has a status tag:
- **[DONE — VERIFY]** reported as built by the previous session; check it works, fix if not, do not rebuild.
- **[PARTIAL]** started; complete it.
- **[TODO]** not started; build it.
- **[OPTIONAL]** only if everything else is done.

The work order is in §17.

---

## 0. Context

We compete in the **Belem Capital track** of the BSA EPFL hackathon (Lausanne, 10–11 Oct 2026, submission deadline **Sunday 11:00 CEST**).

**Belem Capital** (from their challenge brief): Luxembourg-based on-chain asset manager (~$400M AUM, track record since Oct 2020), market-neutral yield strategies across stablecoin, ETH, BTC and SOL mandates. Capital is deployed only on protocols that clear their pre-selection scorecard; every position is monitored in real time. They report zero security incidents, counterparty defaults or liquidations. **Never present any incident as Belem's.**

**The challenge:** identify the dependencies of a position, estimate the economic impact when one is affected, and answer **stay or exit, despite execution costs?** Their worked example is a Pendle PT position, five layers deep, including the underlying yield source and its issuer.

**Judging:** dependency discovery (depth, correctness) 30% · impact estimation (is the number defensible) 30% · decision usefulness (stay/exit and why) 25% · working demo on real data 15%.

### What this feature is
A PT position looks like one token, but it is a **stack of tokens**: `PT-sUSDe → sUSDe → USDe → reserves`. The Crypto Dependency Map shows:
1. **what the position really holds**, token by token, down to base assets;
2. **how those tokens move together**, especially in crashes;
3. **where the token-level risk comes from**;
4. **what exiting a position would change**.

**Pitch:** *"Every position is a stack of tokens. We show what you really hold, how those tokens behave in a crash, and where your token-level risk comes from."*

### Where it sits in the app

| Part | Role |
|---|---|
| Pendle X-Ray (existing) | dependency graph, shock simulation, main UI |
| **Crypto Dependency Map (this feature)** | token stacks, exposure %, price behaviour, risk contribution, exit effect — shown inside X-Ray |
| ExitSense (existing) | stay/exit decision; **source of exit cost** for this feature (read-only) |
| Chain of Blame (existing or in progress) | historical incident investigation; do not modify |

---

## 1. Status board

| § | Component | Status | Files (reported) |
|---|---|---|---|
| 5 | Token lineage down to base assets, sourced edges, cycles | DONE — VERIFY | `lineage.py`, `data/registry.json` |
| 6 | Look-through exposure, traced vs unknown, shared exposure across top Morpho PT markets | DONE — VERIFY (+ wording fix) | `exposure.py` |
| 7 | Unknown share, explicit when reserves unpublished | DONE — VERIFY | `exposure.py` |
| 8 | Price dependency | PARTIAL — only peg/basis deviation | `peg.py` |
| 9 | Structure-vs-price flags + base-asset shock | TODO | — |
| 10 | Risk contribution per token | TODO | — |
| 11 | Exit effect (with ExitSense exit cost) | TODO | — |
| 12 | Clusters, stress exposure, drift, limits, events, offline mode | OPTIONAL | — |
| 13 | UI: "What you really hold" panel, "Hidden dependency" tag, inspector "why this node" | DONE — VERIFY | UI files, `sample.json` |
| 13 | Data-source label shows MOCK for fallback | TODO (fix) | `api.js` |
| 13 | Demo positions (PT-sUSDe primary, PT-reUSD opacity case) | TODO | config |

Reported tests: 31 passed, 1 skipped (live-only) — **not independently re-run; verify.**

Reported live results:
- **PT-reUSD:** coverage RED, 0% traced — the reUSD reserve split is not published; the panel says so.
- **Shared exposure:** "2 of 12 markets hold reUSD (59% of supply)"; "7 of 12 reach USD fiat through 4 different PTs" — denominator must be made explicit (§6.3).

---

## 2. Rules (apply to everything)

- **Tokens only** as nodes. Protocols, vaults, markets, oracles, issuers, chains appear only as edge annotations (`via`, `issuer`, `custodian`).
- **Never invent** addresses, weights, reserve compositions, prices, API routes, schema fields or test results. Fetch, introspect, or leave explicit `null` / placeholders.
- **Every number traceable:** `source`, `as_of`, `confidence` (high = on-chain/API fresh; medium = derived; low = manual/stale), `method`, `assumptions`.
- **Never hide** unknown shares, cycles, derived prices or small samples.
- **Reuse** existing pipelines (prices from `peg.py`, graph from X-Ray). No duplicate pipelines.
- **Do not break** X-Ray, ExitSense or Chain of Blame.
- Inspect the repository before coding; report changed files and **actual** test output after.

---

## 3. Inputs

### 3.1 Positions as token holdings
Each position = list of token holdings (token id `{chain_id}:{address}`, USD value) plus debt tokens for borrowers. Source: X-Ray's existing position/graph data; fallback `config.yaml`. Never guess addresses.

Token types: `base | stablecoin_fiat | stablecoin_synthetic | staked | wrapper_4626 | pendle_pt | pendle_yt | lp | vault_share | bridged | other`.

### 3.2 Base assets
`base:ETH`, `base:BTC`, `base:SOL`, `base:USD_FIAT` (fiat/T-bill reserves), `base:HEDGED_DELTA_NEUTRAL` (synthetic dollars backed by spot + short perps), `base:UNKNOWN`.

### 3.3 Registry (`data/registry.json`) — manual, sourced
Reserve splits of issued tokens (stablecoins, synthetic dollars, wrapped BTC). Every entry: `weight` (or `null`), `source_url`, `as_of`. `null` → flows to `base:UNKNOWN`. Only fill from the issuer's published data.

---

## 4. Demo positions [TODO]

- **Primary:** a PT-sUSDe market (sUSDe → USDe → reserves). Add `demo.preferred_markets` in config; "auto" selects it when available. Fill the USDe reserve split in the registry from the issuer's transparency data, with `source_url` and `as_of`; if unavailable, `null` and say so.
- **Secondary (opacity case):** PT-reUSD — "0% traced: reserve split not published; opacity is itself a risk signal."
- Keep the 12 tracked Morpho PT markets for the portfolio/shared-exposure view.

---

## 5. Token lineage [DONE — VERIFY]

Decomposition rules (weight = share of value):

| Token type | Children | Source |
|---|---|---|
| `wrapper_4626` (sUSDe…) | underlying via `asset()`, weight 1.0; record `convertToAssets` rate | on-chain |
| staked / wrapped staking (wstETH → stETH → ETH) | underlying, 1.0; record exchange rate | on-chain (verify ABI) |
| `pendle_pt` / `pendle_yt` | SY → underlying, 1.0 | Pendle API or `readTokens()` (verify) |
| `lp` | pool tokens by value share | on-chain balances × prices |
| `vault_share` | collapsed to the vault's token mix: allocation × (utilization → collateral token; idle → loan token) | Morpho API |
| lender in a lending market | idle share → loan token; lent share → collateral tokens (weight = utilization) | Morpho API |
| issued tokens | reserve components / base asset | registry |

Each edge: `weight`, `weight_low`, `weight_high`, `source`, `as_of`, `confidence`, `via`.
Cycles: detect, break for sums, report loop and `amplification = 1/(1 − g)` (g = product of weights; g ≥ 1 → "unstable loop").

**Verify:** conservation (child weights + UNKNOWN = 1.0 ± 1%), cycles test, every edge sourced.

---

## 6. Look-through exposure & hidden concentrations [DONE — VERIFY + fix]

### 6.1 Per position
`exposure(P, T)` = share of P's value resting on token T: multiply along paths, add across paths, cap 1.0, propagate bounds. Base-asset row sums to 100% incl. UNKNOWN.

### 6.2 Portfolio and hidden concentrations
`portfolio_exposure(T) = Σ_P value(P) × exposure(P, T) / Σ_P value(P)`, with all routes by which the portfolio reaches T.

### 6.3 Fix: unambiguous shared-exposure sentences [TODO]
Every shared-exposure figure states its **denominator, market set, unit and timestamp**, e.g.:
*"2 of the 12 tracked Morpho PT markets hold reUSD; together they represent 59% of the combined USD supply of those 12 markets (as of <timestamp>)."*
Render sentences from structured fields, not hand-written strings.

---

## 7. Unknown share [DONE — VERIFY]

`null` weights, unpublished reserves, unverified wrappers, missing prices → `base:UNKNOWN`.
Sentence: *"X% traced to base assets; Y% unknown: <reason>."* Severity: ≥ 20% ORANGE, ≥ 40% RED (configurable).

---

## 8. Price dependency [PARTIAL — complete it]

Already built: 90-day peg/basis deviation from DefiLlama prices (`peg.py`), explicit when data is missing.

### 8.1 Data (reuse `peg.py`'s fetching and caching)
- 90-day history for each token in the demo stacks and base-asset proxies (ETH, BTC; USD = 1). Verify DefiLlama routes; CoinGecko fallback only with a key.
- PT tokens without clean series: derive from underlying + implied yield (Pendle) → `method: "derived_price"`, or `insufficient_data`.
- Wrappers/staked: divide by the on-chain conversion rate so yield accrual is not deviation.

### 8.2 Metrics per pair (A, B) [TODO]
| Metric | Definition |
|---|---|
| Correlation | Pearson on log returns (full + rolling 30d) |
| Beta | slope of A on B |
| Stress beta | A's average move on B's worst 5% days ÷ B's average move those days |
| Basis / peg deviation | existing; add its value on B's stress days |
| Data quality | points, gaps, staleness, confidence interval |

Pairs: each token vs its structural parent, and vs ETH and BTC. Stablecoins: peg deviation, not correlation.

---

## 9. Structure-vs-price flags & base-asset shock [TODO]

### 9.1 Flags
| Structure | Price | Flag |
|---|---|---|
| A built on B | tracks B, small basis | `CONSISTENT` |
| A built on B | basis widens on B's stress days beyond normal range | `BASIS_RISK` |
| no structural link | high stress beta / stress correlation | `HIDDEN_MARKET_LINK` |
| USD-backed | drops on ETH/BTC stress days | `PEG_SENSITIVITY` |
| weight unknown | — | `UNTRACED` |

Thresholds in one config place; each flag carries the numbers that triggered it.

### 9.2 Shock
`POST /shock {base_asset, move_pct}` (or the app's equivalent):
```
structural_move(T) = Σ paths T→X (product of weights) × d
market_move(T)     = stress_beta(T, X) × d  (+ historical basis behaviour)
conservative(T)    = larger loss of the two (flagged)
position impact    = Σ exposure(P, T) × move(T)
portfolio impact   = value-weighted sum, with a range
```

### 9.3 UI
- Token inspector: correlation, stress beta, basis stats, flag + one-line explanation.
- "If ETH drops X%" control: position impact (structural / observed / conservative).

---

## 10. Risk contribution per token [TODO]

- Scenarios:
  - depeg/basis: empirical frequency of deviations ≥ 1%, 3%, 10% from §8 history; tails under-sampled → risk engine tail probabilities if available, else documented fallback base rates (`method: "fallback_base_rates"`, labelled in UI);
  - base-asset moves: empirical distribution of 1-day/7-day ETH and BTC moves.
- `EL(P, T) = Σ_s p_s × exposure(P, T) × loss_s`; `contribution = EL(P, T) / Σ_T EL(P, T)` (sums to 100%).
- Output: exposure, risk contribution, ratio (> 1 = riskier than its weight). Note the independence approximation.
- UI: per token, two bars — **share of exposure vs share of risk**. Headline: *"<Token> is <a>% of exposure but <b>% of token-level risk."*

---

## 11. Exit effect [TODO]

- For each position and `f ∈ {0.25, 0.5, 1.0}`: recompute portfolio token/base-asset exposures and token-level expected loss with the position reduced (exited value → cash).
- **Exit cost from ExitSense** via its existing interface, read-only. If unavailable: `exit cost: not available`. Never estimate it here.
- Rank positions by risk reduction per dollar of exit cost (only when exit cost exists).
- Sentence: *"Exiting <position> cuts exposure to <token> from <x>% to <y>% and token-level expected loss by <z>%, for an exit cost of <c>."* A recommendation input, never an automatic action.

---

## 12. Optional [OPTIONAL]

- **Clusters:** tokens with the same backing or high stress correlation; combined exposure and risk.
- **Stress exposure:** lender exposure to collateral rising with utilization `borrowed / (supplied − withdrawn)`; curator caps `cap / total_assets`.
- **Drift:** snapshots every 10 min; alert when exposure changes ≥ 10 points or ≥ 50% in 24h; name the cause.
- **Limits** (placeholders, replace with Belem's if shared): per token 25/35%, per cluster 35/50%, unknown 20/40%, risk contribution 40/60%.
- **Events** to the alert layer (Telegram) if it exists: `PEG_DEVIATION`, `BASIS_WIDENING`, `HIDDEN_MARKET_LINK`, `RISK_CONCENTRATION`, `CONCENTRATION_LIMIT_BREACH`, `EXPOSURE_DRIFT`, `UNKNOWN_SHARE_HIGH`, `STRESS_EXPOSURE_HIGH`, `DEPENDENCY_CYCLE`.
- **Offline demo mode:** serve recorded real data for the two demo cases, labelled `RECORDED`.

---

## 13. UI and data-source labelling

### 13.1 Existing [DONE — VERIFY]
"What you really hold" panel, "Hidden dependency" tag, inspector "why this node is here". `sample.json` regenerated from the real pipeline.

### 13.2 Fix the MOCK label [TODO]
In `api.js` (or wherever set), label data precisely:
- `LIVE` — fetched in this session;
- `RECORDED · <timestamp>` — recorded snapshot of real data;
- `MOCK` — only for truly synthetic data.
Real recorded data must never show `MOCK`.

### 13.3 New UI elements [TODO]
Token inspector price metrics and flag (§9.3), shock control (§9.3), exposure-vs-risk bars (§10), exit-effect line (§11).

---

## 14. API (use the app's existing style)

| Endpoint | Returns | Status |
|---|---|---|
| `GET /tokens/{id}/lineage` | stack to base assets with sources | DONE — VERIFY |
| `GET /positions/{id}/tokens` | look-through exposure, base-asset row, coverage | DONE — VERIFY |
| `GET /portfolio/tokens` | portfolio exposures, routes, shared exposure | DONE — VERIFY |
| `GET /price-deps?tokens=&window=90d` | correlation, beta, stress beta, basis | TODO |
| `GET /flags` | structure-vs-price flags | TODO |
| `POST /shock` | token/position/portfolio impact | TODO |
| `GET /risk-contribution/{id}` and `/portfolio` | §10 | TODO |
| `GET /exit-effect/{id}?fraction=` and `/ranking` | §11 | TODO |

Every response: `as_of`, `data_sources`, `confidence`, `method`, `assumptions`, ranges where relevant, `freshness_seconds`, `approximations`, `missing`.

---

## 15. Validation (defensibility)

- Conservation checks (§5) listed in a health/status output.
- Cross-checks: vault token mix vs vault total assets; wrapper rates vs on-chain; PT underlying vs Pendle API.
- Price sanity: USDC peg deviation near zero as a control; derived PT prices vs any market quote.
- Spot-check 3–5 numbers against public UIs for the demo positions; record honestly in the README.
- Ranges widen when confidence is low, data stale or samples small.

---

## 16. Tests

Existing (verify they pass): lineage, exposure, unknown share, peg.
Add:
- Data-source labels: real recorded data never `MOCK`.
- Demo auto-selection prefers configured PT-sUSDe market; clean fallback.
- Shared-exposure sentence includes denominator, market set, unit, timestamp.
- Correlation/beta/stress beta on synthetic series with known values; stablecoins via peg deviation; conversion rates remove yield accrual.
- One synthetic case per flag.
- Shock: structural vs market vs conservative; ranges ordered.
- Risk contribution sums to 100%; low-exposure fragile token can dominate; fallbacks flagged.
- Exit effect: full exit removes contributions; missing exit cost handled.
- X-Ray, ExitSense, Chain of Blame unaffected.

---

## 17. Work order

| Step | What | Time | Sections |
|---|---|---|---|
| **1** | **Verify** reported state: run all tests (paste actual output), run pipeline for PT-reUSD and one other market, open the UI, check conservation. Write "Verified state" in README. Fix anything broken. | ≤ 30 min | 1, 5–7, 13.1 |
| **2** | **Demo readiness:** fix MOCK label, PT-sUSDe primary demo (+ registry from published data), keep PT-reUSD opacity case, explicit shared-exposure sentences. | ≤ 1 h | 4, 6.3, 13.2 |
| **3** | **Price dependency + flags + shock**, with inspector UI and shock control. | ≤ 3 h | 8–9, 13.3 |
| **4** | **Risk contribution**, with exposure-vs-risk bars. | ≤ 1.5 h | 10 |
| **5** | **Exit effect** with ExitSense exit cost. | ≤ 1.5 h | 11 |
| 6 | Optional items. | if time | 12 |

If time runs short, steps 1–3 already give a solid demo; steps 4–5 make it strong on the "decision" criterion.

---

## 18. Definition of done

- [ ] Tests pass (actual output in README); UI renders; conservation checks pass or violations listed.
- [ ] No `MOCK` label on real data.
- [ ] PT-sUSDe stack shown to base assets with sources; PT-reUSD shows the opacity case.
- [ ] Shared-exposure sentences state denominator, market set, unit, timestamp.
- [ ] Correlation, beta, stress beta, basis computed on real history for the demo stack; flags shown with explanations.
- [ ] Shock control returns structural / observed / conservative impact with a range.
- [ ] Risk contribution sums to 100%; exposure-vs-risk bars shown; fallbacks labelled.
- [ ] Exit effect computed; exit cost from ExitSense or explicitly unavailable.
- [ ] X-Ray, ExitSense, Chain of Blame still work.

---

## 19. Demo script

Use only real pipeline values; replace every `<placeholder>`.

1. **PT-sUSDe:** "This line is really PT-sUSDe → sUSDe → USDe → published reserves. Here is what you really hold, with sources."
2. **Hidden concentration:** "<n> of the 12 tracked Morpho PT markets reach USD fiat through <k> different PTs — <precise denominator>."
3. **Structure vs price:** show the flag the data actually supports, e.g. "sUSDe is built on USDe, but on ETH's worst days its basis widens: basis risk."
4. **Shock:** "If ETH drops 20%, this position moves by <structural> / <observed>; conservative <x>."
5. **Risk contribution:** "<Token> is <a>% of exposure but <b>% of token-level risk."
6. **Exit effect:** "Exiting this position cuts <token> exposure from <x>% to <y>% for an exit cost of <z>."
7. **PT-reUSD:** "Here 0% can be traced: the reserve split is not published. We say so instead of guessing — opacity is itself a risk."

---

## 20. End-of-session report

- Verified state with actual test output.
- Changed files.
- Delivered / partial per step; data-coverage limitations.
- Demo path: markets, panels, numbers.
- Open issues.