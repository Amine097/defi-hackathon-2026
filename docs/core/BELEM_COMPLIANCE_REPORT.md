# FAULTLINE — Belem compliance report (Phase 0 → Phase 0.5)

Date: 2026-10-10. Source of truth: [official PDF](BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf). Details: [validation](BELEM_RISK_ENGINE_VALIDATION.md), [evidence](BELEM_PHASE05_EVIDENCE.json).

## A. PDF requirements (official)

| # | Requirement (PDF) | Phase 0 | Phase 0.5 | Proof |
|---|---|---|---|---|
| P1 | Automatically identify the underlying dependencies of a DeFi position | PASS | PASS | Discovery is fully on-chain: Pendle market/SY, USDC, Morpho market (oracle, IRM, LLTV). Live tests pass. |
| P2 | Model how a failure propagates through those dependencies | PASS | PASS | Best-path propagation with dependence bounds. A shared node is counted once (R10). |
| P3 | Quantify economic impact on the position | PARTIAL: point estimate, independence presented as exact | PASS | Central value plus a low/high band, with each parameter classed observed / calibrated / assumption. Liquidation impact is computed for real borrowers (R06–R09). |
| P4 | Compare staying risk with real exit cost, including slippage | PARTIAL: indicative quote, no carry | PASS | SDK quote re-executed on-chain (gap 0). Carry forgone included; every displayed number (margin, break-even, scenarios, stress table, sensitivity, book) uses the same exit side = execution + carry. Verified in production on `0e58f2c` (live block 26162848): execution $1,300 + carry $3,688 = $4,988; margin −$3,330 = loss − exit side; 0 incoherent rows across 4 scenarios, 10 stress rows, 3 sensitivity rows, 10 book pockets. |
| P5 | Actionable, explainable signal for a PM | PARTIAL: binary STAY/EXIT presented as firm | PASS | STAY / EXIT / REVIEW with lean, bands and reasons. Production X-Ray: REVIEW amber, margin −$3.3k amber (`xr-warn`), exit card 'execution $1.3k + carry $3.7k', 'lean STAY (conditional) … below x3.01'; scenario 'Underlying depeg' → EXIT, margin +$266k red. No 'stay costs more' / 'cheaper one wins' text. Tests: `tests/test_decision_coherence.py`, `tests/js/decision_view.test.mjs`. |
| P6 | Working demo on real on-chain data, no mock presented as real | PASS (labelled) | PASS | Production `0e58f2c`: source=live, 109 live fetches / 0 cached, block 26162848, quote simulated, freshness fresh, borrower HF 1.0544; badge 'Live on-chain data'. Snapshot fallback labelled 'not fresh'. |

The judging weights in the PDF are 30 / 30 / 25 / 15. All four criteria are covered, locally and on the deployment (`0e58f2c`).

## B. Phase 0.5 internal gates (not PDF requirements)

| Gate | Status |
|---|---|
| G01–G10 | **PASS**: code reference, executed test, observed result and block are given in the evidence JSON |
| G11 Deployment tested | **PASS (production alias; deviation recorded).** Exact SHA from the GitHub Deployments API (`vercel[bot]`, Production): deployment 6982681595 = **`0e58f2c`** (owner's empty commit on top of `6a61feb`, `git diff 6a61feb 0e58f2c` empty), status `success` at 2026-10-10T15:10:02Z; commit status 'Vercel: Deployment has completed'. Served `index.html`, `xray.html`, `api.js`, `xray.js`, `model.js`, `data.js`, `sample.json` are identical to the clean worktree at `0e58f2c`; backend fixes confirmed by the payload (`exit_total_usd`, `carry_usd`, `margin_usd_execution_only`, scenario `verdict_basis` 'execution + carry'). R20 (2026-10-10 ~17:15): `/` 200 0.14 s, `/xray.html` 200 0.10 s, `/api/analyze?value_usd=5` 400, `?borrower=0xbad` 400, `?borrower=auto` 200 15.3 s (live, simulated, fresh, borrower_position), `?shock=usd_usdc&severity=1` 200 11.5 s (conditional $720,343 vs exit side $4,981 → EXIT). Visual: X-Ray and dashboard checked in browser (see P4/P5). Deviation: the immutable deployment URL is behind Vercel SSO (302 to vercel.com/sso-api), so the test ran on the production alias, which serves this exact deployment. |
| G12 Final audit | **PASS.** After the last changes, at `0e58f2c`: offline 62 passed / 3 skipped (live-gated); live (`DEFIRISK_LIVE_TESTS=1`) 65 passed in 59 s; node 7 passed. Production payload coherence script: 0 errors. |

## C. Changes since Phase 0

- **Before:** firm STAY/EXIT from a point estimate, with independence presented as exact. No liquidation modelling, no carry, no freshness gating, no historical replay. The UI showed every non-EXIT verdict as green STAY.
- **After:**
  - `keccak.py`, `morpho.py`, `leverage.py`, `uncertainty.py`, `freshness.py`;
  - `decide_robust`, a correlated scenario, the API `borrower` parameter and input validation;
  - replay fixtures;
  - 25 new tests;
  - UI: REVIEW state, signal line and updated methodology.
- **Verdict change at $1M:** EXIT → REVIEW (lean STAY). The reasons are carry and overlapping bands; see the validation document, §6.

### C.1 Decision coherence fix (after R20)

- **Root cause of "+$371, stay costs more" next to REVIEW / lean STAY:** the verdict compared the loss with execution + carry, but the headline margin, the break-even, the X-Ray "Cost if EXIT" card, the scenario / stress / sensitivity / book verdicts and the dashboard "Exit cost" KPI all used **execution only**. On the live case: loss $1,657, execution $1,316, carry $3,680. Execution only gives +$342 (looks like EXIT); with carry the exit side is $4,996 and the margin is −$3,339, which matches lean STAY.
- **Backend:**
  - `decide()` accepts `carry_usd`.
  - `Decision` gains `exit_total_usd`, `carry_usd`, `margin_usd_execution_only` and `breakeven_risk_multiplier_execution_only`.
  - `decide_robust` sets `margin_usd = central loss − exit side incl. carry` and the break-even incl. carry.
  - `api_payload`: scenarios, `custom_shock`, `stress_table`, `sensitivity` and `book` (`evaluate_book(carry_rate=…)`) all use execution + carry and expose `exit_total_usd`.
  - "Certain exit cost" wording removed.
- **Frontend:**
  - `model.js`: `exitCostOf` adds carry; a new pure `decisionView` drives the margin, its colour and the hint.
  - REVIEW margin is amber, with "central values only · bands overlap or inputs not firm · lean X".
  - Exit card sub-label reads "execution $x + carry $y".
  - The guide text now describes the robust rule instead of "the cheaper one wins".
  - Dashboard "Exit cost (incl. carry)" KPI; book columns incl. carry.
  - The what-if slider is labelled as a point comparison on execution cost, with carry added.
- **Tests:** `tests/test_decision_coherence.py` (8) and `tests/js/decision_view.test.mjs` (7) cover firm STAY, firm EXIT, REVIEW lean EXIT and REVIEW lean STAY. The last case reproduces the bug: execution < loss < execution + carry. The tests also check, against the cached real replay, that every payload verdict uses the exit side incl. carry.

## D. Open findings

| Severity | Item | Required action |
|---|---|---|
| ~~P1~~ closed | Deployment not tested (G11) on `a2d10c1` | Closed on 2026-10-10 by R20 on the production URL (see B) |
| ~~P1~~ fixed | Margin / exit figures used execution only while the verdict used execution + carry ('+$371 stay costs more' next to REVIEW / lean STAY); same in scenarios, stress, sensitivity, book | Fixed and tested (C.1); verified in production on `0e58f2c` |
| ~~P1~~ closed | Production lacked the coherence fix | Deployed by the owner as `0e58f2c`; R20 rerun and coherence verified (B, G11) |
| Limit | The borrower deleverage decision (`liquidation.decision`) compares with execution cost only | Labelled in its `rule` ("carry not counted"). Borrower carry (PT yield − borrow rate on equity) is out of Phase 0.5 scope. |
| Limit | Wide high band, so REVIEW is frequent | Traced; better priors would narrow it (out of Phase 0.5 scope) |
| Limit | Normal PT volatility not modelled | REVIEW is forced for borrowers whose distance to liquidation is below 10 % |

## E. Verdict

**PDF requirements: 6/6 PASS, verified locally and on the deployment `0e58f2c`.**

**Phase 0.5 internal gates: 12/12 PASS. Verified compliance on mandatory requirements: 100 % (6/6 PDF, 12/12 gates). Verdict: GO.**
- No blocking finding open. Remaining items are documented limits (D), not compliance gaps.
- Phase 0.5 is closed; new feature work (vault analysis by address) may start.
