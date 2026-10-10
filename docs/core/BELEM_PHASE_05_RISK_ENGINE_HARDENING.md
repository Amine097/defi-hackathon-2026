# FAULTLINE — Phase 0.5: Risk Engine Hardening

**Status: execution and validation protocol intended for Claude Code.**
**Objective: close the six known reservations, consolidate the STAY/EXIT decision engine and prohibit the addition of secondary functionalities until final validation is effective.**
**Scope: existing FAULTLINE, primarily Ethereum / Pendle PT / Morpho Blue.**
**Language of reports: English. Code and identifiers: follow repository conventions.**

> **Upper guidance: execute this plan from start to finish without stopping to request intermediate validations. Only ask the user a question if information, access, risky permission or a product decision is strictly necessary and no safe and honest solution exists. If a point is blocked, advance to all other independent points before requesting the missing information.**
>
> “100%” here means **100% of the validation criteria below proven by tests and artifacts**; it never means that a financial model predicts the markets perfectly. No PASS without proof, no model figures presented as observed truth.

---

## 0. References, ground truth and objective limits

Before any modification, read in full:

1. `docs/core/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf` (official source).
2. `docs/core/BELEM_SPEC_COMPLIANCE_AUDIT.md` (Phase 0 audit protocol).
3. `docs/core/BELEM_COMPLIANCE_REPORT.md` (initial report and completed fixes, if present).
4. `docs/core/BELEM_EVIDENCE.json` (declared evidence; check that it is reproducible).
5. Existing technical documents and configurations, then the sources and tests concerned.

If the path has changed, search by name **in the repository**, without inventing a missing document. The above documents serve as a starting point and **do not prove** that the current code is identical or that live calls still succeed.

### A. Official obligations — do not misrepresent them

The PDF imposes an **operational prototype on real data**, automatically discovering the dependencies of a position and estimating their economic impact in order to help choose **STAY or EXIT** considering the exit cost. The jury weighs: discovery **30%**, impact estimate **30%**, usefulness of the decision **25%**, demo on real data **15%**. The PDF **does not** explicitly require liquidation modeling, backtesting, Vercel, or perfect statistical calibration; These elements are **additional quality objectives adopted for FAULTLINE**, in order to make its demo more credible. Never declare them “obligatory according to Belem”.

### B. Findings from the previous report to revalidate

| Ref. | Open reserve in the parts provided | Target of this phase |
|---|---|---|
| H01 | LGF / propagation coefficients mostly hypothetical | Explicit mechanisms, provenance, calibration or bounds, validation of correlations and uncertainty |
| H02 | No debt or actual liquidation on the hypothetical exposure | Two distinct modes: debt-free exposure and on-chain borrowing position, threshold and liquidation stress |
| H03 | Inclusion of Pendle costs in the quote not demonstrated | Reconstruction, simulation when available, accounting without double counting, dated estimate |
| H04 | No historical backtesting | At least one real and measurable historical replay, without temporal leakage |
| H05 | Cache without blocking expiration threshold | Freshness policy by data and secure decisions in degraded mode |
| H06 | Unverified Vercel deployment | Build / real preview / smoke test, without taking risks in production |

Other points identified by the report, **to be included in cross-functional controls**: independence of failures not justified; carrying/yield of a PT omitted; verdict at $1M close to threshold; conditional scenarios sometimes compared to immediate costs; fictitious position size; consistency of “executable” output; potential evolution of live sources.

**Historical reference figures, not permanent truths:** for a theoretical position of $1M without debt, expected loss ~$1,653.55, exit ~$978.46, EXIT; for $5M, loss ~$8,267.75, exit ~$15,336.41, STAY. Never freeze these numbers in live tests: prices, blocks and routes change. Use time-stamped fixtures and invariants, and report explainable discrepancies.

**Checking an ambiguity:** the report cites a parameterized `oracle` shock (severity 0.6, $5M, conditional loss ~$2.4M) and a predefined scenario “oracle_failure” ($1M, ~$321k). Determine if their definitions differ. If they are supposed to be equivalent, correct the discrepancy; otherwise make the parameters and the two names explicit. Do not conclude that there is necessarily a bug before examining the code.

---

## 1. Autonomy and safety protocol — mandatory

1. **Start immediately** with `git status`, inventory of project commands and reproduction of the 20 declared tests. Do not overwrite uncommitted changes from the previous audit. If necessary, work on a consolidation branch without losing the current state.
2. **Plan then implement.** At each step: read the code → establish a test that fails or highlights uncertainty → correct with the smallest appropriate architecture → test → document → move on.
3. **Don't stop after a report, suggestion or plan.** Actually modify sources, API, UI and tests when necessary; check runtime behavior; continue automatically until all validation doors are closed.
4. **Do not request approval** for inspection, public reading of data, code, testing, minimal refactorings, documentation, installations of normal project dependencies, local server launch, public read-only HTTP/RPC calls, fixture generation and local validation. Never expose a key or token.
5. **Do not perform any real transactions or operations with funds**, any signing, wallet approval, publication of secrets, data destruction, force-push, destructive rebase, destructive migration or deployment to production without explicit consent. Read-only `eth_call` calls/mocks are allowed.
6. Deploy in **preview / non-production environment** if access and authorizations are already available and if this does not modify the production environment; otherwise test the same configuration locally and log what is missing. If only identifiers, a login or the authorization of an external action allow you to complete H06, ask **a single targeted question after having completed the rest**.
7. If an API/RPC fails: try with bounded backoff, another public RPC or provider already configured, replay fixture and unit validation. **A mock test is never a live proof.** Do not loop indefinitely on an unavailable service.
8. When two rules contradict each other, prioritize: security / truth of results → official PDF → economic invariants → tests and conventions of the code → this document. Document the arbitration.
9. Retain old API/UI contracts where reasonable; if change necessary, migrate consumers and tests. No Whale Tracking features, advanced Breaking Point, new protocol or UI redesign during this phase.
10. Update `docs/core/BELEM_PHASE05_PROGRESS.md` after each major batch, with `DONE / IN PROGRESS / BLOCKED`, commands, latest result and next tasks. If interrupted, **resume from this file without requesting the plan again**.
11. Avoid artificial human validation (“do you want me to continue?”). **Question authorized only** if irreducible need for a decision on an economic agreement, external access, secrecy, authorization of risky action or blockage preventing an essential criterion. Expose the choices and propose a safe default, but do not transform an `UNVERIFIED` into a `PASS`.
12. **End criterion:** never announce “DONE / 100% / GO” before all doors `G01–G12`. In the absence of a safe and testable solution to a blocked point, `BLOCKED / NO-GO` state and precise question; continue with the other points first. An unavailable deposit, compulsory paid access or deployment requiring login cannot be circumvented by invented proofs.

---

## 2. H03 — Actual Exit Cost and Pendle Fee (Immediate Priority)

**Why first:** the earlier report already found an approximation multiplying the exit cost by ~40 and reversing the verdict. An error here invalidates the STAY/EXIT core.

### Work

- Trace `position/exposure -> exact quantity of PT -> quote Pendle -> aggregator route -> quantity of token received -> output USD price -> gas -> net cost -> verdict -> UI`. Indicate each unit, decimal place, source, block/time, destination token and string.
- Determine, from the **SDK response and/or contract, the documentation actually used and a read-only transaction simulation if available**, whether swap/Pendle/aggregator fees are included in `outputs[0].amount`. Provide machine proof, not intuition. No double counting of fees.
- Compare homogeneous quantities: actually liquidable USD value of the quantity of PT vs net USD revenue, with the same price/time stamp basis and the same exposure definition. Do not call the simple mark-to-market spread, fees or depeg “slippage”; detail the positions or group them explicitly when not separable.
- Distinguish **indicative quote**, **built route**, **simulated and potentially executable route**. Do not claim that a swap is executable if its calldata or simulation is absent. No transaction sent.
- Estimate gas costs in a traceable manner (network, estimated gas or justified range, gas price, ETH price, any applicable additional costs); avoid false precision, record limits.
- Make the quote perishable (`quote_timestamp`, validity/TTL, source, chain_id, market, destination, quantity and if possible block/block tag). If expired or route impossible, do not render a firm verdict based on an invented cost.
- Test several sizes (small, $1M, $5M depending on market liquidity), stablecoin price not exactly $1, sub-liquidity, decimals, variable gas, missing route, fees included/excluded, channel change.

### Deliverables and evidence

An output module/cost with typing/provenance and testing of invariants; timestamped fixture of the response quote (sanitized); demonstration calculated line by line; API and UI indicating "estimated", "simulated", "outdated" or "unavailable" as applicable.

### H03 acceptance criteria

- [ ] Verified quotation costs or, if they are not technically decomposable, **economic inclusion of the net revenue** verified and impossibility of double counting demonstrated; explicitly visible residual uncertainty.
- [ ] No hardcoded cost taken for real execution; no expired `quote` treated as fresh.
- [ ] Traceable real quote or proven read-only simulation; price tests, units and quotes without writing on-chain.
- [ ] STAY/EXIT changes correctly when the exit cost changes, without using historical figures in live assertions.

---

## 3. H02 — Real borrowing positions and Morpho liquidations

### Business model: separate cases

**Mode A — `unlevered_exposure`:** PT holding, hypothetical exposure or collateral without debt attached to an identified borrower. `borrow_assets = 0` or `unknown`, depending on the source; **never** consider the existence of a market LLTV as evidence of position indebtedness. If no actual debt is provided, loan-related liquidation **NOT_APPLICABLE** or **UNKNOWN**, not a made-up number.

**Mode B — `borrower_position`:** real account address and market ID, with proof of borrower state at the observed block. Collect amounts in native units: collateral, borrow shares, total borrow assets/shares (with relevant cumulative interest), loan token, collateral token, oracle address/price, LLTV, precision and rounding, liquidity. Check if there is an active open position at the chosen block; otherwise discover **another publicly verifiable position** on the same market or a comparable Morpho/Pendle market, without inventing a wallet or debt.

### Calculations and mechanics

- Read Morpho Blue values ​​in a coherent block; use integer/`Decimal` arithmetic and **per-protocol rounding convention** for borrow shares → assets conversion and solvency. Check the precise version of the contracts, the management of virtual shares/assets, the accumulation of interests, the price scale of the oracle and the decimals of the two assets before coding the equations. Do not naively apply generic lending formulas.
- Display at least: `collateral_amount`, `collateral_value_loan_units` (or equivalent), `debt_assets`, `debt_value_usd`, `LLTV`, `max_borrow`, `LTV`, `health_ratio` / `liquidation_buffer`, price of the collateral at the threshold, distance % to the threshold, source of each value, `as_of_block`.
- Treat separately the **crossing the liquidation threshold**, the **economic loss of the borrower after liquidation** (incentive/bonus, slippage/market conditions, debt repaid, collateral seized, bad debt if applicable) and the **risk of the lender**. Do not equate “triggered liquidation” with “100% loss”; do not equate drop in collateral with loss of the lender.
- Model direct and indirect stresses: PT depeg/underlying, obsolete or incorrect oracle, increase in borrow assets, AMM concentration/liquidity, LLTV variation according to market conventions. Define the **economic** price and the **oracle price used for liquidation eligibility**: they may diverge.
- Define safe behaviors if oracle invalid/stale, if position closed between two blocks, if illiquid market, if no real borrowing position detectable. Keep the demo function unlevered and explain the limit instead of manufacturing a result.
- Verify the arithmetic of shocks and liquidations with at least one independent reference: fixed-block contract data, reconstructed `Liquidate` historical event, or official protocol implementation. Use dated on-chain state fixtures.

### Testing and acceptance H02

- [ ] `borrower_position` real, referenced and verified at the block, **with non-zero debt**, and separated from the market itself.
- [ ] Collateral/debt/oracle/LLTV match with the channel for this position; Verifiable calculations, correct decimals and roundings.
- [ ] Healthy case, exact limit, liquidation and extreme shock tested; monotony of the risk margin in the relevant scenarios.
- [ ] Non-negative/bounded net liquidation losses according to an explicit agreement, without double counting or borrower/lender confusion.
- [ ] A debt-free position displays **no** false liquidation probability; unknown data ≠ zero.
- [ ] UI and API allow you to understand which **economic entity** is analyzed and if real mode is active.

---

## 4. H01 — LGF, transmission, probabilities and signal quality

### Mandatory economic diagnosis

1. Inventory all values ​​(LGF, transmission, probabilities, frequency of events, severity, correlation, horizon), their impact function and exact origin. Class: `observed`, `calibrated`, `protocol-derived`, `scenario_assumption`, `unknown`. Remove silent hardcoded digits, including UI side.
2. Construct a **mechanistic typology**: protocol fault/incident, underlay depeg, oracle failure/manipulation, AMM dysfunction, liquidation on borrowing position, chain failure, issuer risk. **The same coefficient must not be applied mechanically to all paths.** The mechanism and direction of transmission must be explained.
3. Justify priors/probabilities by **consistent cohort, period, exposure, denominator, quality and reporting limits**. Do not make an overall hack rate the observed probability of default of each oracle, stablecoin or chain; use bounds/assumptions if no representative history exists.
4. Reexamine the previous formula `1 − ∏(1 − p_i · LGF_i · T_i)`: explain exactly what it represents and under what hypotheses it is valid. Check independence, overlaps/common causes, multiple paths, simultaneous losses. **Do not qualify it as “exact loss expectation” outside of these hypotheses.** Correct if the multiplication of LGF and probabilities does not correspond to a rigorous economic expectation; use mutually exclusive scenarios, documented joint distribution, Monte Carlo or conservative bounds when necessary.
5. Avoid double counting (issuer/underlying/shared stablecoin, chain/come, feed/oracle, price shock/liquidation). For each loss, define an economic owner and a P&L item.
6. Correlate the propagation with the **observable mechanisms of the protocol**; when LGF/transmission are impossible to calibrate, display plausible interval, pessimistic/central/optimistic scenario, origin and justification of these limits.
7. Add a **decision uncertainty model**: compare the ranges of expected losses and exit costs (fees, illiquidity), display break-even threshold. If the intervals overlap, indicate `REVIEW / INDETERMINATE` or equivalent, with a **STAY/EXIT bias only if it is explicitly conditional**; do not give a firm recommendation inconsistent with sensitivity. Preserve Belem's explicit STAY/EXIT objective, including an intelligible explanation when information is missing.
8. Define the common horizon: the exit cost is immediate, the expected loss is over N days. Include, estimate or **explain as an excluded P&L element** the PT carry/yield, financing costs, opportunity and re-entry costs; if exclusion potentially changes the signal, downgrade one's confidence rather than mask the factor.
9. Separate `expected` losses, `conditional_on_shock`, liquidation P&L, extreme scenario, VaR/quantile. Avoid any comparison of non-comparable values ​​without explaining the probability/hypothesis.
10. Test the extreme scenarios of decorrelation/strong correlation, depeg + oracle + liquidity, issuer default, borrower close to LLTV, expired quote, zero risk, zero horizon, zero or invalid value.

### H01 acceptance criteria

- [ ] **Each** LGF/transmission/probability used in the final result is explicit, justified by proof or bounded as a hypothesis, and attached to the mechanism and node concerned.
- [ ] Cohorts and units verified; the absence of statistical data is never transformed into a certain empirical frequency.
- [ ] Tests showing absence of double counting, consistency of expectation, relevant monotonies, loss bounds, correlated stress and stability of conclusions when justified.
- [ ] Decision signal with degree of uncertainty; case $1M unstable **no** presented as incontestable EXIT if its hypotheses do not support it.
- [ ] Clear output format: expected amount, interval/sensitivity, exit cost, possible liquidation cost, drivers, assumptions, source, block, verdict/action and justification.

---

## 5. H04 — Historical replay and empirical validation (without overpromises)

- Select **at least one real documentable historical event** relevant to the scope (observed depeg, Pendle dislocation/liquidity, oracle episode, Morpho liquidation), with date/block, public source and variables known **before** the event.
- Freeze a pre-event state and **replay the model on the inputs that it would have actually known at that moment**; do not inject the realization of the shock a posteriori into the forecast probabilities.
- Compare prediction of loss / stress / decision with a posteriori observation if this observation is available, without claiming general statistical validation on a single case. Give errors, bounds, limits and possible missing data.
- Also test invariants on historical fixtures independent of the flagship case: stability of units, liquidation mode, recalculation of a quote, impact linked to the market / oracle. If historical data is insufficient, produce a **limited factual replay** (without artificial observations), and classify any impossible conclusions `UNVERIFIED`, not `PASS`.
- Ensure that the history and fixtures are dated, traceable, reproducible, ideally frozen without secrets. Never call synthetic data “real backtest”.

### H04 acceptance criteria

- [ ] At least one truly verifiable historical event record with block/date, source data, replay logic, results and limits.
- [ ] No temporal leak; assertions independent of current live market values; reproducible tests.
- [ ] If the data does not allow the risk of the event to be assessed, do not derive an “accuracy” or an imaginary empirical validation from it.

---

## 6. H05 — Freshness, cache, provenance, decision security

- Add validity rules **by data type**, configurable and documented: execution quote (short), price/oracle and solvency parameters (blocks/time), market metadata, histories/prioris (longer). Define the TTLs with reasoning and test them (do not impose the same arbitrary TTL on everything).
- Record `observed_at`, `source`, `as_of_block` when applicable, `cached_at`, `age_seconds`, `max_age_seconds`, `stale`, possible `last_live_error`, origin of each critical variable; distinguish snapshot same block vs data read at different heights.
- Do not serve a stale value as live. Choose explicit behavior: new collection, displayed degradation or **refusal of firm verdict** if quote, debt, oracle or critical price is out of date; an offline fixture is just an offline demo.
- Test time expiration with injected clock (no real waits), RPC errors, fallback and persistent cache, bad chain, reorg/finality when relevant, block inconsistency, polluted cache, API unavailable.
- Add input limits (`value_usd`, `severity`, `node`, addresses) and stable error handling, without displaying browser-sensitive keys or traces.

### H05 acceptance criteria

- [ ] TTL/freshness policy documented and applied to **all decisive data**.
- [ ] An expired oracle/quote/debt does not produce a firm “LIVE EXIT”; the browser indicates the degradation.
- [ ] Automatic test covering live/cache/mixed/mock/mock-fallback/offline, timestamp, API errors, inconsistent block and crash recovery.

---

## 7. H06 — Build, preview and end-to-end demo

- Inspect configurations (including `vercel.json`, max duration, dependencies, routes, environment variables, function limits), local launch options and existing tests.
- Reproduce the demo locally: frontend and `/api/analyze` on **real data**; direct/indirect shock; debt-free position; borrowing position with debt; liquidation simulation; quote and verdict; provenance.
- If the Vercel CLI and access are available and compatible with an **isolated preview**, perform preview build and deployment (never `--prod` by default), then smoke HTTP/API/UI tests on real URL. Hide secrets in logs. Test for errors, cache expiration, latency, mobile if useful, absence of console errors.
- If Vercel access is absent, finish everything **except** the action requiring a login; test `vercel build` offline when possible, or an equivalent local build, and provide the **exact command** + an access question. Do not indicate “deployed”.
- Provide a backup demonstration mode **clearly labeled** if the APIs are unavailable; never present it as proof of the real mode.

### H06 acceptance criteria

- [ ] Build + local server + functional API/UI tests without misleading data.
- [ ] Preview Vercel actually tested on non-productive URL, OR `BLOCKED` identified as such if user access is essential. Local compilation alone does not validate Vercel.
- [ ] At least one trackable live demo run, plus a distinct and clearly signposted deterministic replay.

---

## 8. Minimum test battery to produce/execute

The names are indicative: keep the conventions of the repository. The old 20 tests are still necessary and should not be removed to achieve an artificial success rate.

| ID | Test / invariant | Nature of proof |
|---|---|---|
| R01 | Existing Phase 0 tests go before and after hardening | Local CI |
| R02 | Quote fees included and no double account | Fixture SDK + contract/doc/simulation |
| R03 | Quote recalculated correctly at different sizes, non-standard decimals | Unit + integration |
| R04 | Quote absent, expired, incorrect network, degraded gas => no false EXIT/STAY closes | Unit + API |
| R05 | Debt-free position => liquidation N/A, unknown ≠ zero | Unit + API/UI |
| R06 | Live borrowing position with debt, RPC/market state evidence and block snapshot | Live integration |
| R07 | Conversion borrow shares, rounding, oracle scale, LLTV at threshold | Unit + independent reference |
| R08 | Collateral stress/underlying/oracle/interests => threshold + plausible liquidation | Stress/replay |
| R09 | Borrower P&L vs lender risk: no double counting | Unit |
| R10 | Common/shared node graph: no double LGF counted | Unit |
| R11 | Expectation calculation and controlled dependence/correlation assumptions | Unit / scenarios |
| R12 | Consistent priors by category, horizon, unit, cohort | Unit + documentation |
| R13 | Direct/indirect shock scenarios, monotony, terminals | Property-based or fixtures |
| R14 | Robust verdict; fragile scenario => REVIEW/indeterminate explicit | Unit + API/UI |
| R15 | Carrying/omitted risks documented and degraded signal if material | Unit + API contract |
| R16 | Backtest/replay on a **real historical** event without look-ahead | Historical fixture + test |
| R17 | Differentiated TTL, snapshot block consistency, live/cache/mock modes | Injected clock + API |
| R18 | API errors input/sources, no secrets exposed | Unit + HTTP |
| R19 | Local e2e: true graph → shock → possible liquidation → loss → exit → decision | Integration |
| R20 | Real preview: HTTP, JS, API, performance, provenance, stress scenario | Smoke test URL preview |

**Specific regression:** reproduce, under fixed fixtures, the old case $1M/$5M and the decision near the break-even; compare the old and new models by explicitly showing *why* a verdict has changed. Never hardcode that it **must** remain EXIT/STAY after correction.

---

## 9. Required deliverables in the repository

1. **Fixed code**, actually plugged into the existing pipeline: sources, discovery, business model, liquidation, propagation, decision, API, UI (if needed).
2. **Automated tests** newly added, old tests retained, historical fixtures or anonymized and dated snapshots.
3. `docs/core/BELEM_PHASE05_PROGRESS.md` — current actions and blockers, updated as work proceeds.
4. `docs/core/BELEM_RISK_ENGINE_VALIDATION.md` — readable summary: architecture, risk model, assumptions/bounds, horizon, formulas, liquidation, costs, provenance, limitations, reproduction commands, observed cases.
5. `docs/core/BELEM_PHASE05_EVIDENCE.json` — **structured** evidence: timestamps, commit/diff, commands, exit codes, live and historical cases, source/block, errors, detailed G01–G12 statuses. Never record secrets or unnecessary personal data.
6. `docs/core/BELEM_COMPLIANCE_REPORT.md` **updated or created** with before/after differences; retain the audit trail and distinguish “PDF requirements” from “Phase 0.5 internal thresholds”.
7. If Vercel preview possible: preview URL + dated tests + necessary configuration; otherwise question of precise access and reproducible order.
8. Concise final report to user: affected files, H01–H06 fixes, tests actually executed, failed/unverified validations, STAY/EXIT summary and **GO/NO-GO verdict**.

### Quality of evidence

A `PASS` entry must include at least: **code reference, test executed, result observed, timestamp, data origin** if external. `FAIL`, `BLOCKED`, `UNVERIFIED`, `NOT_APPLICABLE` remain distinct. JSON output written without execution does not constitute proof. Live sources are moving: note the exact blocks and the age of the data, not just `live=43`.

---

## 10. Final gate — G01 to G12: everything must be checked

| Gate | Condition to demonstrate | Validation mode |
|---|---|---|
| **G01** | Project compiles/starts, old functions and tests preserved | Tests + runs |
| **G02** | The exit quote and the inclusion of costs are defensible, without double counting | H03 + R02–R04 |
| **G03** | Properly identified debt-free exposure | H02 + R05 |
| **G04** | Real borrowing position with independently verified debt, liquidation/LLTV and calculations | H02 + R06–R09 |
| **G05** | LGF/transmissions/probabilities justified or honestly bounded | H01 + R10–R13 |
| **G06** | P&L savings and comparable scenarios, correlations and double counting processed | H01 + R10–R15 |
| **G07** | Robust STAY/EXIT or explicit and intelligible indeterminacy | H01 + R14–R15 |
| **G08** | At least one real historical replay without temporal leak | H04 + R16 |
| **G09** | Freshness/TTL/labeling and refusal of false live verdict | H05 + R17–R18 |
| **G10** | Complete real case: dependence → shock → liquidation if applicable → impact → cost → decision | R19 + provenance |
| **G11** | Real preview deployment tested (not just a build), without action on funds | H06 + R20 |
| **G12** | Up-to-date documentation and evidence; Phase 0 + Phase 0.5 tests pass; zero P0/P1 and zero reservation H01–H06 unresolved | Final audit |

**To announce GO:** each gate `PASS` and all reserves H01–H06 `CLOSED`, without `BLOCKED`/`UNVERIFIED` on the required criteria. Irreducible financial limitations can remain **only if they are honestly limited, do not invalidate a firm verdict and are traced**; we do not promise the disappearance of market uncertainties. If a preview requires a login, gate G11 remains `BLOCKED` and **no global GO** is allowed until it is tested.

If a point is intrinsically impossible (e.g. no relevant historical data accessible), do not create fictitious data: provide the explanation and **minimal decision question** to obtain an alternative source or explicitly review the gate. Without user agreement, **NO-GO** verdict on Phase 0.5.

---

## 11. Work order and last message format

Run automatically in this order:

1. **Baseline**: reading, inventory, tests, state saving and initial G01–G12 checklist.
2. **Quote / fees (H03)**: trace, correct and test.
3. **Debt / liquidation (H02)**: real source, calculations and scenarios.
4. **Economic risk (H01)**: mechanisms, LGF/transmission, probability, uncertainty and decisions.
5. **History (H04)**: time-stamped public event, replay and limits.
6. **Freshness/cache (H05)**: TTL per data, display, API and degraded cases.
7. **Build/demo/preview (H06):** end-to-end tests, evidence and a Vercel preview if available.
8. **Final audit**: rerun all orders, complete G01–G12 and docs, compare with the initial state. Correct any regression then **retest**.

At the end, give exactly the following information (no victory proclaimed without proof):

```text
FAULTLINE — PHASE 0.5 / FINAL REPORT
H01 Risk model: PASS | BLOCKED | FAIL
H02 Actual liquidations: PASS | BLOCKED | FAIL
H03 Exit cost: PASS | BLOCKED | FAIL
H04 Historical replay: PASS | BLOCKED | FAIL
H05 Cache / provenance: PASS | BLOCKED | FAIL
H06 Preview / demo: PASS | BLOCKED | FAIL
Gates validated: X / 12
Tests: N passed, M failed, K skipped (+ commands)
Open P0 / P1 findings: X / Y
Live data: timestamp, chain, block, position, verdict and justification
Changes: files + key points
Evidence: docs/core/BELEM_RISK_ENGINE_VALIDATION.md; docs/core/BELEM_PHASE05_EVIDENCE.json
VERDICT: GO / NO-GO / BLOCKED
USER QUESTION: none, or ONE essential and targeted question
```

**DON'T STOP** at the first green test: the objective is an engine that is financially defensible, observable, tested and deployed in preview. **DO NOT STOP** because a reservation is “documented”: either the improvement is made and verified, or its impossibility is proven and the point remains blocked. **DO NOT INVENT** data, tests, deployments or certainties.
