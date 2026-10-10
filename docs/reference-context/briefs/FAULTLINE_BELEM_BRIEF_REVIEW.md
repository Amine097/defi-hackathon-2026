# FaultLine vs the Belem brief: backend review

Date: 11 Oct 2026. Scope: the backend (X-Ray engine, data/discovery layer, Vault analyzer, Countermove), checked
against *BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf*. The frontend is being reworked by a
teammate; section 8 lists what the UI should show, not how.

**Bottom line:** the brief is covered end to end and runs on real data. The weak spot is how defensible the impact
numbers are (30% of the score): several losses come from mechanisms that cannot reach the analysed position. Fixing
that, and adding a "hold to maturity" option, are the highest-value next steps.

---

## 1. What the brief asks

| Item | Brief |
|---|---|
| Build | Automatically identify the dependencies of a position and estimate the economic impact on it when one of them is affected. |
| Question to answer | Stay in the position, or is the expected loss high enough to justify exiting despite execution costs? |
| Worked example | Pendle PT position, 5 layers: settlement chain, underlying yield source and issuer, oracle pricing the asset (incident), PT market and its AMM curve, lending market holding it as collateral. |
| Book example | 10 pockets × 10%, one affected, unwinding costs 11% slippage. Exit = expensive and certain; stay = cheap and uncertain. Make the trade-off explicit. |
| Scope (free choice) | Any ecosystem (Solana, EVM, Canton, Tempo); oracle dependency and feed quality; vaults deploying into an external venue (e.g. perp exchange); protocols concentrating a large share of TVL; any risk method. |
| Expected output | A working prototype on real data producing a signal a manager could act on. Not slides. |
| Judging | Dependency discovery 30% · Impact estimation 30% · Decision usefulness 25% · Working demo on real data 15%. |

## 2. How this review was done

- Read the core engine: `src/defirisk/core/{decision,propagation,scenarios,portfolio,models}.py`, `api_payload.py`, `api/analyze.py`.
- Two parallel code reviews: (a) the Vault analyzer (`vault_model.py`, `vault_reader.py`, `uncertainty.py`, `leverage.py`, `morpho.py`, `freshness.py`, `api/vault.py`); (b) the data layer (`src/defirisk/data/*`).
- **Ran the X-Ray engine live** (`build_payload("auto", live)`), then the same run offline to inspect edges and loss parameters.
- Checked which `docs/features/*` specs have code behind them.

## 3. Live run (11 Oct 2026, source `live`, 21 s)

**Position picked by `auto`:** $1,000,000 of PT-reUSD-10DEC2026 posted as collateral on Morpho (USDC market),
Ethereum, 30-day horizon. No borrower given, so mode `unlevered_exposure` (liquidation NOT_APPLICABLE).

**Dependencies discovered (11 nodes, 15 edges):**

| Layer | Node | p_fail (30 d) | Loss if it fails | p source |
|---|---|---|---|---|
| chain | Ethereum | 0.00041 | 0.30 | assumption: 0.5%/y serious L1 incident |
| yield_source | re.xyz (issuer) | 0.00041 | 0.60 | DefiLlama hacks (25 incidents ≥ $1M in 3 y, cohort) |
| yield_source | reUSD (yield source) | 0.00041 | 0.50 | DefiLlama hacks |
| yield_source | USDC (stablecoin) | 0.01549 | 0.04 | DefiLlama stablecoin prices, 5.8 y daily |
| amm | Pendle market PT-reUSD-10DEC2026 | 0.00039 | 0.60 | DefiLlama hacks |
| oracle | Morpho oracle (ChainlinkOracleV2) | 0.00044 | 0.40 | DefiLlama hacks |
| oracle | Ojo (feed provider) | 0.00044 | 0.40 | DefiLlama hacks |
| lending | Morpho market PT-reUSD/USDC | 0.00020 | 0.70 | DefiLlama hacks |
| protocol | Morpho Blue | 0.00020 | 0.70 | DefiLlama hacks |
| yield_source | US dollars (bank/T-bills) | 0 | 0.30 | look-through only (token lineage) |

**Edges (transmission T):**

| From | To | T | Reason |
|---|---|---|---|
| Position | Pendle market | 1.00 | holds the PT; exits through the Pendle AMM |
| Position | Morpho market | 1.00 | PT posted as collateral on Morpho |
| Pendle market | reUSD | 0.90 | SY wraps reUSD |
| reUSD | re.xyz | 0.80 | issued/managed by re.xyz |
| reUSD | USDC | 0.80 | accounted in / redeemable for USDC |
| Morpho market | Morpho oracle | 0.80 | liquidations and borrow limits use this oracle |
| Morpho oracle | Pendle market | 0.70 | feed reads the Pendle market |
| Morpho oracle | Ojo | 0.90 | price comes from the Ojo feed |
| Ojo | Ethereum | 0.50 | feed publishes on Ethereum |
| Morpho market | Morpho Blue | 0.70 | singleton market |
| Morpho market | USDC | 0.30 | liquidity denominated in USDC |
| Pendle market / Morpho market | Ethereum | 1.00 | settle on Ethereum |
| reUSD | US dollars (bank/T-bills) | 0.50 | reinsurance collateral (off-chain) |
| USDC | US dollars (bank/T-bills) | 1.00 | Circle reserves |

**Decision:** `REVIEW` (low confidence), lean STAY.

- Staying: expected loss **$1,657** [$171 – $27,517] over 30 d.
- Exit execution: **$1,068** (0.107%), Pendle SDK quote, re-executed with `eth_call` (`simulated`).
- Carry forgone by exiting: **$3,649** (PT 11.81% vs USDC supply 7.37%); exit side incl. carry $4,717 [$2,892 – $6,542].
- Point comparison incl. carry: STAY. Execution cost only: EXIT. STAY holds unless true risk is above ×2.85 the central estimate.
- No freshness blockers.

**Scenarios (loss conditional on the shock):**

| Scenario | Loss | Exit side | Verdict |
|---|---|---|---|
| Underlying depeg (−30%) | $271,075 | $4,717 | EXIT |
| Oracle failure | $321,031 | $4,717 | EXIT |
| Liquidity crisis (AMM impaired 50%, liquidity ×0.5) | $500,711 | $5,784 | EXIT |
| Correlated depeg + oracle + liquidity | $752,072 | $5,784 | EXIT |

**Stress table (single dependency shocked, top 6):** Morpho market $700,456 · Pendle market $600,569 · Morpho Blue
$490,796 · reUSD $450,810 · re.xyz $432,840 · Morpho oracle $321,031 — all EXIT.

**Book (10 × $1M, P0 hit by "Underlying depeg"):** stay-everywhere loss $285,992; optimal $19,634 (0.196% of book);
hit-pocket exit cost 0.107% of the pocket (real quote, not the brief's 11%).

## 4. Assessment per judging criterion

| Criterion | What is there | Gaps | Rating |
|---|---|---|---|
| **Dependency discovery (30%)** | Live graph from Pendle API, Morpho GraphQL, DefiLlama, Ethereum RPC. All 5 Pendle layers covered. Recursive token lineage (ERC-4626 `asset()` + curated `data/registry.json`, depth ≤ 8, unknown shares kept as `UNKNOWN`). Feed reads (`latestRoundData`, `description`, `decimals`). Concentration of our dependencies across the Morpho PT lending book. | Input is only `auto` or `pendle:1:<market>`: no arbitrary position, wallet or other protocol. Ethereum only. Oracle quality uses only the first feed address (`discovery.py:67-86`). Perp-venue vaults and non-EVM not covered (scope items, optional). | Strong |
| **Impact estimation (30%)** | Loss = V(1 − ∏(1 − pᵢ·LGFᵢ·Tᵢ)), exact under independence; dependence-free bounds; Monte Carlo VaR95 (20k draws); parameter band; correlated joint scenario; executable exit quote re-executed on-chain; carry with ±50% band; stressed exit (slippage / liquidity factor). | Loss-if-it-fails (LGF) values are fixed structural assumptions (`priors.py:12-24`). **Role-blind losses** (section 5). Sensitivity varies only p, not LGF or T. Edge transmissions are expert weights. Chain prior is an assumption. All protocol p values are near-identical (same cohort rate, small modifiers). | Main risk |
| **Decision usefulness (25%)** | STAY / EXIT / REVIEW with explicit rule; same exit basis (execution + carry) everywhere; break-even risk multiple; scenarios, custom shock (`?shock=<node>&severity=`), stress table, 10-pocket book. Optional borrower mode with real debt, health factor and liquidation. | Live headline is REVIEW (wide band), weaker as "one number". No HOLD-TO-MATURITY option for a PT. Book is 10 copies of one position; no user-set exit cost (11% example); no shared dependency across different pockets. Explanation is one long string. | Good |
| **Demo on real data (15%)** | Live sources, `eth_call` swap simulation, provenance (`live` / `cache` / `mixed`), freshness gates (quote > 60 s, state > 120 s → REVIEW). | `api/analyze.py:21-28` falls back to the mock graph on discovery failure (labelled `mock-fallback`, but a plausible demo is still shown). | Strong |

## 5. Model correctness issues (priority order)

1. **Oracle and lending losses charged to a position without debt.** The payload itself says
   `unlevered_exposure`, liquidation NOT_APPLICABLE, yet:
   - oracle failure → $321k (Position → Morpho market T 1.0 → oracle T 0.8, LGF 0.4);
   - Morpho market failure → $700k (LGF 0.7), the top row of the stress table.

   On Morpho Blue, collateral is isolated and not lent out; with no debt nothing can be liquidated, and bad debt
   falls on lenders, not on collateral providers. Only a Morpho Blue contract exploit can reach this position.
   Fix: losses that depend on the position's role (collateral only / borrower / lender). With a borrower, route
   oracle and price shocks through the existing liquidation analysis (`leverage.py`).
2. **Pendle AMM failure treated as principal loss.** "Liquidity crisis" = $500k (AMM LGF 0.5). A PT redeems at par
   at maturity whatever the AMM does. AMM impairment raises the exit cost or forces holding to maturity; only the
   Pendle contracts (PT/SY/YT) put principal at risk. Fix: split `Pendle core contracts` (principal) from
   `Pendle AMM` (exit cost / time to exit).
3. **Unsourced LGF constants** (chain 0.30, issuer 0.60, oracle 0.40, AMM 0.60, lending 0.70; `priors.py:12-26`) and
   protocol modifiers (no audit ×1.5, TVL ≥ $1B ×0.5; `priors.py:105-133`). Fix: calibrate from DefiLlama hack amount
   vs TVL at the time, cite recoveries, and add LGF rows to the sensitivity table.
4. **No hold-to-maturity branch.** For a PT, the natural third answer is HOLD TO MATURITY (par at maturity vs exit
   now vs expected loss over the remaining term).
5. **Independence assumption** for the central number. Bounds and the correlated scenario exist; the headline should
   make clear which one drives the verdict.
6. **Book is not a book.** `api_payload.py` builds 10 deep copies of the same graph. No heterogeneous pockets, no
   shared dependencies, no user-set exit cost.

## 6. Vault analyzer (Phase 1) — findings

**What it does:** live detection of Morpho vaults (V1 MetaMorpho / V2) via factory checks; one pinned block for all
reads (assets, supply, share price, idle, fees, gates, adapters, market positions); look-through vault → adapters →
Morpho markets → collateral → oracle → borrowers (Morpho GraphQL) → liquidity. Bad debt per borrower via
`morpho.liquidation_outcome()`; oracle drain `L · max(0, 1 − (1−d)/lltv) / total_supply`; exit by redeem or
`forceDeallocate` + redeem simulated in a multicall (P0-A fix); carry = net APY × H/365; robust STAY/EXIT/REVIEW with
bands and freshness gates.

| Severity | Issue | Where |
|---|---|---|
| High | V1 reconciliation sums every market against every adapter, hiding per-adapter gaps | `vault_reader.py:300-321` |
| High | Unindexed debt assumed to sit exactly at LLTV → worst case, can overstate bad debt when API coverage is partial | `vault_model.py:233-261` |
| High | Oracle failure = instant overpricing, no liquidation lag; underpricing excluded from depositor loss | `vault_model.py:262-276` |
| Medium | Morpho-vault specific: no Pendle AMM or issuer look-through beyond priors; not a perp-venue vault | `vault_model.py:278-420` |
| Medium | Severity constants are priors (50% collateral crash, 40% oracle overpricing, 10% depeg, bands, TTLs) | `vault_model.py:29-40`, `uncertainty.py:8-18` |
| Medium | Redeem / force-exit simulation relies on storage-slot overrides; unsupported layouts → "unavailable" | `vault_reader.py:419-505` |
| Low | Deposit-asset depeg shown but decision-neutral | `vault_model.py:321-334, 942-946` |

## 7. Data / discovery layer — findings

**Sources:** Pendle API v2 (`/markets/active`, `/markets/{addr}`, `/markets/{addr}/data`, SDK `/convert`);
Morpho Blue GraphQL; DefiLlama (`/protocols`, `/hacks`, coins prices and charts, stablecoin prices); Ethereum RPC
(`ETH_RPC_URL`, then drpc, then blastapi). Every call is cached to `data/cache/`; live first, cache on failure;
provenance tells which. Bundled: `data/mock_graph.json` (demo), `data/fixtures/*` (replays), `data/registry.json`
(curated issuer reserves).

**Priors:** protocol exploit rate from DefiLlama hacks over 3 years (non-CEX, ≥ $1M, cohort TVL ≥ $10M) with an
upper bound from all incidents; stablecoin depeg from daily price history (< $0.98). LGF and chain rate are
structural assumptions; stablecoin fallback 10%/y.

**Peg / lineage / exposure:** peg and ERC-4626 basis vs fair value from DefiLlama charts (missing data flagged,
never filled); lineage with provenance, confidence, cycle detection; exposure multiplies weights along paths, sums
across paths, caps at 100%, unexplained share → `UNKNOWN`.

| Severity | Issue | Where |
|---|---|---|
| High | Mainnet only; input limited to `auto` or one Pendle market | `discovery.py:31-56, 245-253` |
| High | LGF and chain risk hardcoded | `priors.py:12-26, 105-139` |
| High | Mock fallback on discovery failure | `api/analyze.py:21-28` |
| Medium | Oracle quality reads only the first feed | `discovery.py:67-86` |
| Medium | Registry-based reserve splits can be incomplete (correctly → `UNKNOWN`) | `lineage.py:129-184` |
| Medium | No Solana / non-EVM / perp venue | `sources.py`, `discovery.py` |
| Low | Cache replay can be stale but accepted; freshness depends on cache content | `http.py:28-90` |

## 8. Extras (beyond the brief)

| Item | Relevance | Advice |
|---|---|---|
| **Countermove** (Phase 2): RescueVault contract + keeper, local fork demo S1–S4, verification, Slither | Not judged. Answers "and then what?" after the signal. | Show it last, 1 minute: "the signal can also act within limits the owner signed". |
| **Vault analyzer** (Phase 1) | Partly in scope ("vaults deploying into an external venue") but Morpho vaults, not perp venues | Keep as the second product; fix the High items in section 6 if time allows. |
| **7 specs in `docs/features/`** (breaking-point, chain-of-blame, exit-feasibility, telegram-ping, whale-impact, portfolio-dependency, reaction-window) | No code for breaking-point, chain-of-blame, exit-feasibility, telegram, whale, portfolio-dependency | Label them "roadmap" so the jury does not expect them in the demo. |

Countermove scenarios, for reference (same −9% shock on one real feed, LTV 75% → 82.4%, trigger 82%, LLTV 86%):

| | Reserve | Outcome | Why |
|---|---|---|---|
| S1 weETH/USDC | 5,000 USDC + 0.05 weETH | Auto-repay 1,086.50 USDC, LTV → 78.1% | cheapest sufficient action that fits the reserve |
| S2 cbBTC/USDC | 100 USDC + 0.2 cbBTC | Auto top-up 0.0251 cbBTC, LTV → 78.5% | USDC reserve too small → switches asset |
| S3 weETH/USDC | 150 USDC + 0.01 weETH | No action, nothing sent | every option blocked; reasons shown |
| S4 cbBTC/USDC | 21,000 USDC | Emergency full repay 18,670.41 USDC, debt → 0 | only strategy the owner authorized |

## 9. Plan (backend)

| # | Step | Criterion | Effort | Done when |
|---|---|---|---|---|
| 1 | **Role-aware losses.** Collateral-only: oracle and lending-market loss = 0, only Morpho Blue core exploit counts. Borrower: oracle/price shocks go through `leverage.py`. Split Pendle into core contracts (principal) vs AMM (exit cost only). | Impact | ½ day | Live stress table no longer puts "Morpho market" / "oracle" at $300–700k for a no-debt position; tests assert it. |
| 2 | **HOLD-TO-MATURITY** as a third answer for PTs (par at maturity vs exit now vs expected loss to maturity). | Decision | ½ day | Payload `decision.options` with three costed options. |
| 3 | **Calibrate LGF** (DefiLlama hack amount / TVL, cited recoveries); add LGF and transmission rows to the sensitivity table. | Impact | ½ day | Every LGF has a `lgf_source` that is not "structural assumption", or a band. |
| 4 | **Real book input:** heterogeneous pockets, user-set exit cost (reproduce the 11% example), shared dependencies aggregated across pockets (a USDC depeg hits every USDC pocket). | Decision | 1 day | `/api/analyze?book=...` reproduces the brief example; shared-dependency table in the payload. |
| 5 | **"Incident now" path:** pick a dependency + severity → impact on the position and the book, with time-to-impact where known. Custom shock exists; make it the main endpoint. | Decision | ¼ day | One call answers "X is hit at Y%: stay or exit, per pocket". |
| 6 | **Wider discovery:** any Pendle market on any chain the Pendle API serves; wallet address → positions (Morpho / Pendle APIs); reuse `countermove/dependencies.py` to decode all oracle feeds. | Discovery | 1 day | Arbitrum/Base markets analyse; multi-feed oracles fully listed. |
| 7 | **No silent mock:** on discovery failure return an error with the cause (or keep the fallback only behind an explicit flag). | Demo | ¼ day | `mock-fallback` never reached in normal use. |
| 8 | **Vault analyzer High items:** per-adapter V1 reconciliation; band instead of "all unindexed debt at LLTV"; liquidation lag in oracle drain. | Impact | 1 day | Tests per item. |
| 9 | **Regression tests + evidence** on the new rules, then rerun the evidence script. | All | ¼ day | Suites green, evidence regenerated. |

Order: 1 → 2 → 5 → 3 → 4 → 7 → 6 → 8, with 9 after each step.

## 10. Notes for the UI rework (teammate)

What the backend already provides and the page should surface:

- **One sentence first:** "Exit costs $X, staying risks $Y over 30 days → VERDICT". The current `decision.explanation`
  is ~700 characters in one string; the backend should also return structured fields (headline, lean, reasons,
  what-would-flip-it). Keep the long text behind a toggle.
- **REVIEW must be actionable:** show the break-even multiple ("STAY holds unless risk is ×2.85 higher") and which
  input is uncertain.
- **Graph by Belem's 5 layers** (chain, yield source/issuer, oracle, PT market/AMM, lending), with "click a
  dependency to shock it" as the main interaction (`?shock=<node>&severity=`).
- **Book next to the brief's example** (10 × 10%, 11% exit cost), once step 4 exists.
- **Data status impossible to miss:** `live` / `cache` / `mixed` / `mock-fallback`, with `data_as_of`.
- **Plain words:** "room before liquidation" instead of "buffer", strategy names instead of enums, amounts to the
  cent for stablecoins, dates and durations in words (as done on the Countermove page).

## 11. Verification status at the time of review

- Live X-Ray run: OK (21 s, source `live`, no freshness blockers).
- Countermove: API tests 6 passed / 1 skipped; Node 33/33; policy draft now reachable on Vercel
  (`/api/countermove?action=policy-draft`).
- Earlier full suites (Phase 2 close): pytest offline 207 passed / 16 skipped; live 133 passed; forge 29 + fork test;
  15/15 GO criteria.
