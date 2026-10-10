# FAULTLINE — Belem Capital challenge compliance audit (Phase 0)

> **Instruction for Claude Code or any agent capable of reading and testing the repository.**
> **Exclusive mission: verify that the prototype meets all the explicit requirements of the official PDF before launching other features.**
> **Source of truth:** `BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf` (EPFL Hackathon 2026, *DeFi Risk Dependency Challenge*, **page 1**, single page).
> **Audited project:** FAULTLINE repository, from its root.

---

## 0. Role and mandatory rules

You are an **independent technical auditor**, specialized in DeFi, on-chain integration, risk modeling and software validation. Your mission is **not** to improve the aesthetics or build future features of FAULTLINE. It is to **prove, with verifiable elements**, that the base requested by Belem Capital works.

1. Read **the entire PDF** (text, Pendle diagram, numerical example, evaluation table) before the audit. If it is not in the repository, look for it in the accessible files or ask for the path. **Do not invent its contents.** The matrix below serves as an operational transcription, but the PDF takes precedence in the event of a discrepancy.
2. Explore **the code actually present**, the data schema, the contracts/API, the frontend if present, the tests and the README. Never rely on a written promise without proof of execution.
3. Work **read-only on the product**: inspect files, run non-destructive build/test commands, read public data, and generate audit reports. Do not deploy, migrate, send on-chain transactions, write to a wallet, install large dependencies, or modify application code without agreement. Never reveal secrets contained in `.env`.
4. For each requirement, provide: **status, evidence, command/test, observed result, gap and minimal fix**. Cite file paths, symbols and line numbers when available.
5. **Clearly distinguishes:** (A) explicit requirements of the challenge, (B) qualitative criteria of the jury, (C) examples from the sheet, (D) freedom of design, (E) engineering recommendations proposed by you. **Does not elevate an example or recommendation to the rank of obligation.**
6. Do not consider a mock, a fixture, a hard copy API response, a hand-written graph or fictitious metrics as sufficient proof of operation on **real data**.
7. Tests are means of verification offered here, **not technical requirements imposed by the PDF**. Respect any choice of ecosystem, framework and risk model consistent with the challenge.
8. When a point is impossible to test (network, key, RPC, API, dataset, position), mark **NOT VERIFIABLE**, detail the blockage and propose a validation procedure. **Never declare “100% compliant” without effective verification.**
9. **No new functionality** (whale tracking, new scenarios, accessory dashboards, graphic polish, etc.) before the end of this audit and the correction of the identified blockages.

---

## 1. What Belem Capital really asks for

### 1.1. Obligations of the core of the challenge — to prove

| ID | Requirement based on PDF | Minimum evidence sought | Where in PDF |
|---|---|---|---|
| **M01** | An **executable prototype**, not just a diagram or presentation. | The project starts; end-to-end execution produces an actionable response. | “What we expect” |
| **M02** | **Automatically identify dependencies of a position** DeFi. | On a selected real position, the software derives its dependencies from verifiable data/relationships, without manually entering the entire graph. | “The challenge / Build the system” |
| **M03** | Represent the **relevant underlying dependencies**, including their sequence, sufficiently faithfully to explain the transmission of risk. | Graph or equivalent structure showing relationships, their origin and their effect on position; validation of important links. | “The problem”, “Dependency discovery” criterion |
| **M04** | Estimate **the potential economic impact on the position** when one of its dependencies is affected. | A shock defined on a selected dependency changes a numerical loss/exposure/cost estimate in an explainable way. | “The challenge / Build the system” |
| **M05** | Provide a **risk signal that can be used by a manager**, in practice a **stay or exit** decision and its justification. | The output links position, shock, losses and costs to an intelligible and reasoned recommendation. | Hook, “Answer the question a risk manager actually asks”, “What we expect” |
| **M06** | Show **the trade-off between potential loss from staying and execution costs of exiting**. | Both sides of the decision are explained using consistent units and time horizons, with assumptions and limits visible. | “Answer the question a risk manager actually asks” |
| **M07** | Run the prototype on **real on-chain data** (direct or taken from documented sources using on-chain data). | At least one real traceable case: chain, contract/position or pool, source, timestamp or block, values ​​actually used by the calculation and result. | “What we expect”, “Working demo on real data” criterion |
| **M08** | Produce a **concrete usable result** and show the chain *dependence → incident/shock → impact → decision*. | A repeatable demo connecting outputs together, rather than four unrelated screens or numbers. | “The challenge”, “What we expect” |

**Careful interpretation:** M03, M06 and M08 make the brief's goals testable; they prescribe **no particular mathematical model, score, interface or fixed graph depth**. The document does not require a public API, trading automation, or exhaustive coverage of all protocols.

### 1.2. Judgment criteria — qualitative dimensions, not numerical thresholds

| ID | Official criteria | Official weight | What to evaluate |
|---|---|---:|---|
| **J01** | Dependency discovery: depth and correctness | **30%** | Justified depth, correctness of nodes and links, coverage of important dependencies of the chosen case. |
| **J02** | Impact estimation: is the number defensible | **30%** | Traceable calculation, exposed assumptions, consistent propagation, sensitivity and absence of arbitrary numbers. |
| **J03** | Decision usefulness: stay or exit, and why | **25%** | Intelligible recommendation, comparison of scenarios and costs, explanation adapted to a manager. |
| **J04** | Working demo on real data | **15%** | Functional application and demonstration actually using the data of the chosen case. |

**Please note:** these percentages are **judging weights**, not compliance thresholds or a guaranteed score. The PDF sets **no numerical passing threshold**. Do not invent an “official” grade.

### 1.3. Examples and freedoms — **DO NOT make them obligatory**

- **Ecosystems:** Solana, EVM, Canton and Tempo are possibilities. **A single ecosystem may be enough** for a credible prototype; the PDF does not require support for all.
- **Pendle PT:** the illustrative diagram presents **five layers**: (1) settlement chain; (2) underlying yield source and issuer; (3) oracle pricing the asset; (4) PT market and AMM curve; (5) lending market holding it as collateral. **Do not impose Pendle or exactly five layers** at other positions. If FAULTLINE chooses *this* Pendle position as the flagship case, audit the layers applicable to the exact position, reporting those that do not exist in this case.
- **Other illustrative cases:** a vault allocating funds to a perps platform, TVL concentration, and dependence on an oracle/feed. These are examples, **not required modules**.
- **Risk methods:** graph analysis, simulation, statistics and agents are allowed; **none are imposed**.
- **Decision example:** a portfolio with ten 10% allocations, one affected allocation, and **11% slippage** to unwind it. This is an illustrative case, **not a slippage value to hard-code**. Exiting an allocation worth 10% of the portfolio at 11% slippage costs **1.1% of the total portfolio value**; show the correct denominator.
- **Belem Information:** AUM, history, number of protocols/chains followed and internal practices describe the organizer. **These are not implementation requirements for FAULTLINE.**

---

## 2. Audit protocol (order to be respected)

### Step A — Inventory and traceability

1. Identify language, frameworks, entry points, packages, execution scripts, external services, RPCs/indexers, configuration files, frontend/backend, models and tests.
2. Identify **the actual entity analyzed**: wallet address, token, vault, market, LP, PT, loan position or other. Record the chain, contract address(es), identifiers and units.
3. For M01 to M08, associate the functions/modules, endpoints, UI components and tests concerned; if no implementation is found, note **ABSENT**.
4. Classify the origin of **each important variable**: chain/RPC, indexer, external on-chain data API, config, estimate, hypothetical scenario, mock/fixture, or hardcode.
5. Describe in one sentence the current **end-to-end path**: `entry position → discovery → graph → shock → calculation → exit cost → decision → display`.
6. Identify the additional functionalities already present, but **do not audit them instead of the Belem core**.

### Step B — Static Logic Verification

Control, by precisely documenting the results:

- **Discovery M02/M03:** origin of dependencies; proof of automatic discovery; direction of edges; indirect risks; node identifiers; absence of cycles or planned treatment; duplication of risks; explicitly partial coverage when necessary; consistency of the position with the network.
- **Propagation M04:** which shock hits which node; causal relationship up to position; equations, parameters, limits, conversion to monetary value; direct/indirect risk distinction; no risk counted twice without justification.
- **Decision M05/M06:** definition of “stay”, “exit”, exit costs and risk of staying; horizon and probabilities **if used**; costs correctly expressed in %/bps/currency; distinction between conditional loss, expected loss and heuristic score; recommendation and explanation consistent with the figures.
- **M07 Authenticity:** data analysis, precision of decimal places of tokens, prices, timestamps, chain IDs, API calls and exceptions; the **final calculation** must use the real data, not just display it as decoration.
- **Demo M01/M08:** backend and frontend status, local execution, errors, loading, empty states, visible provenance and reproducibility. **No UI sophistication requirement** not provided for by the PDF.

### Step C — End-to-end execution and testing

**Runs existing tests**, then adapts the controls below to the existing architecture. Announces “PASS” only for **observed** exits. When the test requires absent access, **NOT VERIFIABLE**, without inventing a result.

| Test | Verification scenario | Expected observation |
|---|---|---|
| **T01** | Install/initialize according to the doc **if authorized**, then launch the project. | The prototype starts without blocking errors and presents its results. |
| **T02** | Analyze **an actually existing position** in the supported ecosystem. | Dependencies generated by product logic; the position is not a simple fixture. |
| **T03** | Inspect T02 dependencies and verify **at least some critical relationships** via contract, protocol docs, RPC or indexer. | Plausible, validated and sourced relationships; recognized shortcomings. |
| **T04** | Select a direct dependency and apply a defined shock to it. | A quantified economic impact on the position is calculated and explained. |
| **T05** | Select an **indirect** dependency, when one exists in the chosen case. | The shock propagates via the relevant relationship; otherwise **NOT APPLICABLE** with justification. |
| **T06** | Compare zero / weak / significant shock, for a parameter whose expected effect is monotonic. | Consistent and verifiable results; no guarantee of monotonicity for non-monotonic mechanisms. |
| **T07** | Test consistency of units with a controllable position value. | $/token/%/bps, decimals and reference value correctly converted. |
| **T08** | Examine the exit cost of the **real case**: source and assumptions of slippage, fees, liquidity and other components actually modeled. | Explicit and justified cost; limits reported; no arbitrary value presented as real. |
| **T09** | Propose a case where the risk of staying is clearly lower than the cost of exit and the opposite, **if the decision logic allows it**. | Signal and justification compatible with the defined decision rule; otherwise default or explicit limit. |
| **T10** | Repeat the same case with the same fixed data and parameters. | Reproducible result, or explained variability if probabilistic model. |
| **T11** | Trace a displayed number from the source data to the formula and the interface. | Evidence of actual use of the data and sufficient provenance for verification. |
| **T12** | Disable/simulate the unavailability of a source **without destructive action**, if feasible. | Error or clear degraded mode; no invented number or silent fallback presented as live. |
| **T13** | Check outdated, malformed or unavailable data, with clearly identified test mock if necessary. | Explicit behavior; freshness/unmasked boundaries. |
| **T14** | Walk through the case from position entry to the final signal screen or API. | Complete understandable journey: **dependence → shock → impact → decision**. |
| **T15** | Reread the outputs and compare the assertions (“real time”, “expected loss”, “exact”, “live”, etc.) to their implementation. | No unproven claims; clearly distinct estimation and observation. |

**Note:** T06–T13 are **proposed robustness and credibility tests**, not as many distinct features required by Belem. An absence on these points may harm the defensibility of the result, but does not artificially create an obligation on the PDF.

### Step D — Financial Decision Test

Require for the **main demonstration case** a summary of this type, with values ​​actually calculated:

```text
Position analyzed       : [protocol / position / chain / verifiable identifier]
Exposure                : [amount + currency + date / block]
Affected dependency     : [identified node, source of the link]
Scenario                : [shock, magnitude, horizon if relevant, assumptions]
Estimated loss if held  : [amount / % + definition of the measure]
Estimated exit cost     : [amount / % + method / assumptions]
Decision                : [STAY / EXIT / INDETERMINATE]
Reason                  : [explicit comparison and caveats]
Data provenance         : [chain, contracts, sources, timestamp / block]
```

Specifically check that:

- A **risk score without economic translation** does not by itself replace the requested impact estimate.
- A **loss conditional on a shock** is not called an “expected loss” without probability estimation. If the model instead uses a threshold, a stress test, a range or a heuristic rule, it announces this honestly and explains how the decision is produced.
- An “exit” recommendation **is not automatic** as soon as a risk is high: it must take into account the cost of exit within the chosen framework.
- Exit costs calculated on a sub-position are **not confused** with losses reported for the entire portfolio.
- Arbitrary or uncertain hypotheses are **visible and testable**, not disguised as observed market data.
- If the information does not allow a defensible decision, **INDETERMINATE / insufficient data** is preferable to false certainty; explain what this prevents from satisfying in the tested case.

---

## 3. How to note the findings

### Proof statuses (for each M and each test)

- **VERIFIED**: code located **and** demonstration/test observed conclusive.
- **PARTIAL**: functional part but absence of an essential element or justification.
- **FAIL**: absent, incorrect, or contrary to the requirement.
- **NOT VERIFIABLE**: no data, environment or possibility of execution to establish the result.
- **NOT APPLICABLE**: only for a conditional test or a free example, **never** for fundamental requirements M01–M08.

### Severities and work priority

| Level | Definition | Example |
|---|---|---|
| **P0 — Compliance Blocker** | Prevents fulfillment of an explicit obligation or invalidates the result. | No real on-chain data; fully hardcoded graph; no economic estimates; stay/exit signal without cost comparison. |
| **P1 — Major jury risk** | Existing basis but insufficient credibility, accuracy or defensibility. | Incorrect decimals, omitted critical dependency, hidden major assumption, non-reproducible results. |
| **P2 — Reinforcement** | Useful improvement for demo or quality, not essential for basic compliance. | Better node coverage, additional tests, better exposed provenance. |
| **P3 — Out of phase** | Additional or cosmetic feature. | Advanced whale analyzer, complete design reorganization, multi-chain without need for demo. |

**Prioritization rule:** fix **P0** issues first, then **P1** issues affecting J01–J04. P2/P3 work must not hide a P0 issue. Do not confuse engineering priorities with official jury rules.

---

## 4. Reports to write in the repository

Creates the files **in `audit/`**, without modifying the product code:

### A. `audit/BELEM_REQUIREMENTS_AUDIT.md`

Required structure:

1. **Overall verdict**: `CONFORMITY DEMONSTRATED` or `CONFORMITY NOT DEMONSTRATED` (if an M is partial, failed or not verifiable).
2. **Scope and environment**: commit/branch, date, commands used, necessary services, access limits.
3. **Matrix M01 to M08**: status, implementation (path + lines), test executed, result observed, link to proof, priority if deviation.
4. **Tests T01 to T15**: status, commands/parameters, observed results, limits.
5. **Real case route**: input, sources, verified dependencies, shock, impact formula, exit cost, decision.
6. **Analysis by jury criterion** J01–J04: strengths, risks, evidence, **official weights**; no official note invented.
7. **Bugs, uncertainties and orderly deviations** P0 → P3; for each deviation: why it is important, reproduction steps, minimal correction, non-regression test.
8. **Strictly minimal action plan** to achieve demonstrable compliance; distinguish necessary / recommended / optional.
9. **Final validation checklist** with boxes checked only if actually verified.

### B. `audit/BELEM_EVIDENCE.json`

Creates valid, machine-readable JSON, for example:

```json
{
  "source": "BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf",
  "source_page": 1,
  "project": "FAULTLINE",
  "commit": "<git-sha-or-unknown>",
  "verdict": "COMPLIANCE NOT DEMONSTRATED",
  "requirements": [
    {
      "id": "M01",
      "status": "NOT VERIFIABLE",
      "evidence": [],
      "tests": [],
      "blockers": ["<specific reason>"],
      "priority": "P0"
    }
  ],
  "tests": [],
  "real_data_case": null,
  "blocking_findings": [],
  "audited_at": "<ISO-8601>"
}
```

Include **the eight entries M01–M08**, even if not verifiable. Keep relevant raw results (no secrets, no unnecessary personal data) and mention missing evidence.

### C. Final Terminal Summary

At the end of the audit, conclude with:

```text
AUDIT BELEM — FAULTLINE
M01 [status] Executable prototype
M02 [status] Automatic discovery
M03 [status] Dependencies correctly linked
M04 [status] Quantified economic impact
M05 [status] Explainable stay / exit signal
M06 [status] Risk/exit cost arbitration
M07 [status] Real on-chain data
M08 [status] End-to-end demo usable

Critical P0: [count]
Major P1   : [count]
VERDICT: [COMPLIANCE DEMONSTRATED / COMPLIANCE NOT DEMONSTRATED]
NEXT ACTION: [smallest correction needed / authorization to move on to features]
```

---

## 5. Phase lock: when can we move on to other features?

The transition from **Phase 0 (compliance with specifications)** to **Phase 1 (additional FAULTLINE features)** is authorized **only if**:

- [ ] The PDF has been read and the requirements have been correctly separated from the examples.
- [ ] **M01, M02, M03, M04, M05, M06, M07 and M08 = VERIFIED.**
- [ ] A **real** case was executed from start to finish with inspectable evidence.
- [ ] The key figures (impact, exit cost and decision) are linked to the data and hypotheses that produce them.
- [ ] None **P0** unresolved; no inconsistency **P1** making the demonstration misleading.
- [ ] Known limits are documented; fictitious data are not presented as real.
- [ ] Audit reports exist and reflect the observations actually made.

**Otherwise:** respond **“COMPLIANCE NOT DEMONSTRATED — DO NOT PROGRESS TO NEW FEATURES”**, with minimum fixes prioritized. **Do not silently correct the product: deliver the diagnosis and wait for the team's agreement to modify the code.**

**If everything passes:** answer **“CONFORMITY DEMONSTRATED ON THE TESTED PERIMETER — PHASE 1 AUTHORIZED”**. This formulation guarantees the traceability of the explicit requirements of the PDF, **not** a perfect score from the jury nor the absolute absence of bugs.

---

## 6. Startup instruction for agent

**Start now.** Read the reference PDF and the FAULTLINE repository. Only asks a question if lack of access actually prevents control. Otherwise, audit the existing one, perform the possible non-destructive validations, write the two reports, then give the verdict. **Absolute priority: prove the heart of the Belem challenge before any other feature.**
