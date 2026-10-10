# FAULTLINE — Belem compliance report (Phase 0 → Phase 0.5)

Date: 2026-10-10. Source of truth: [official PDF](BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf). Details: [validation](BELEM_RISK_ENGINE_VALIDATION.md), [evidence](BELEM_PHASE05_EVIDENCE.json).

## A. PDF requirements (official)

| # | Requirement (PDF) | Phase 0 | Phase 0.5 | Proof |
|---|---|---|---|---|
| P1 | Automatically identify the underlying dependencies of a DeFi position | PASS | PASS | Discovery is fully on-chain: Pendle market/SY, USDC, Morpho market (oracle, IRM, LLTV). Live tests pass. |
| P2 | Model how a failure propagates through those dependencies | PASS | PASS | Best-path propagation with dependence bounds. A shared node is counted once (R10). |
| P3 | Quantify economic impact on the position | PARTIAL: point estimate, independence presented as exact | PASS | Central value plus a low/high band, with each parameter classed observed / calibrated / assumption. Liquidation impact is computed for real borrowers (R06–R09). |
| P4 | Compare staying risk with real exit cost, including slippage | PARTIAL: indicative quote, no carry | PASS (local) | The SDK quote is re-executed on-chain (gap 0). Carry forgone is included, and since the coherence fix every displayed number uses the same exit side: execution + carry. This covers the margin, break-even, scenarios, stress table, sensitivity and book. The fix is **not yet deployed** (see B, G11). |
| P5 | Actionable, explainable signal for a PM | PARTIAL: binary STAY/EXIT presented as firm | PASS (local) | STAY / EXIT / REVIEW with a lean, bands and reasons. REVIEW is shown amber, with the lean and the cause of uncertainty. Tests cover STAY, EXIT and both REVIEW leans (`tests/test_decision_coherence.py`, `tests/js/decision_view.test.mjs`). Production still shows the contradictory "+$371 stay costs more" until redeployed. |
| P6 | Working demo on real on-chain data, no mock presented as real | PASS (labelled) | PASS | Local e2e on live block 26162781 (after the fix). Production (`a2d10c1`) tested on live block 26162693: HTTP, API, stress scenario, visual rendering. The snapshot fallback is labelled "not fresh". |

The judging weights in the PDF are 30 / 30 / 25 / 15. All four criteria are covered locally. The deployment runs the code before the coherence fix (see B).

## B. Phase 0.5 internal gates (not PDF requirements)

| Gate | Status |
|---|---|
| G01–G10 | **PASS**: code reference, executed test, observed result and block are given in the evidence JSON |
| G11 Deployment tested | **BLOCKED for the current code.** Exact deployed SHA, read from the GitHub Deployments API written by `vercel[bot]` (no Vercel login needed): the last successful Production deployment is **`a2d10c1`** (14:33:39 UTC, status `success`). The production alias serves `Last-Modified 14:34:42`. Hashes of `index.html`, `xray.html`, `api.js`, `xray.js`, `model.js`, `data.js` and `sample.json` served by production are byte-identical to `git show a2d10c1:public/...`. Every later push (`016f070`, `f070236`, `28eab7d`, and earlier `480860e`) has Vercel status **"Deployment was blocked"**: on this project only the owner's pushes deploy. The coherence fix is therefore **not in production**. R20 on `a2d10c1` (2026-10-10, 16:40–16:42) remains valid for that SHA: `/`, `/xray.html` 200; `/api/analyze?borrower=auto` 200 in 13–18 s, live, simulated, fresh, borrower_position; invalid inputs 400; stress 200; amber REVIEW. To close G11, the project owner must deploy the fix commit, then rerun R20 and check the X-Ray margin (expected: negative, amber, "lean STAY"). |
| G12 Final audit | **PASS locally, not on the deployment.** Offline: 62 passed, 3 skipped. Live (`DEFIRISK_LIVE_TESTS=1`): 65 passed. Node: 7 passed. Local e2e (dashboard + X-Ray, live block 26162781) is coherent. Cannot be closed while G11 is blocked. |

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
| ~~P1~~ fixed locally | Margin / exit figures used execution only while the verdict used execution + carry, so "+$371 stay costs more" appeared next to REVIEW / lean STAY. Same issue in scenarios, stress, sensitivity and book. | Fixed and tested (C.1). **Not deployed.** |
| **P1 open (blocking)** | Production runs `a2d10c1`, without the coherence fix. Non-owner pushes are blocked by Vercel. | The project owner deploys the fix commit; then R20 is rerun and the X-Ray margin checked. |
| Limit | The borrower deleverage decision (`liquidation.decision`) compares with execution cost only | Labelled in its `rule` ("carry not counted"). Borrower carry (PT yield − borrow rate on equity) is out of Phase 0.5 scope. |
| Limit | Wide high band, so REVIEW is frequent | Traced; better priors would narrow it (out of Phase 0.5 scope) |
| Limit | Normal PT volatility not modelled | REVIEW is forced for borrowers whose distance to liquidation is below 10 % |

## E. Verdict

**PDF requirements: 6/6 verified locally** (with tests and live e2e). On the deployment, P1–P3 and P6 are verified on `a2d10c1`. P4 and P5 are only verified locally, because production predates the coherence fix.

**Phase 0.5 internal gates: 10/12 PASS. G11 is BLOCKED (fix not deployed), and G12 is PASS locally only. Overall verdict: NO-GO (blocked on deployment).**
- No code issue remains open locally.
- To switch to GO: the project owner deploys the commit containing C.1. Then R20 is rerun on that SHA (verified via the GitHub Deployments API) and the X-Ray margin is checked: negative, amber, "lean STAY".
