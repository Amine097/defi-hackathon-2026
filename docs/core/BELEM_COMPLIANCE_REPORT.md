# FAULTLINE — Belem compliance report (Phase 0 → Phase 0.5)

Date: 2026-10-10. Source of truth: [official PDF](BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf). Details: [validation](BELEM_RISK_ENGINE_VALIDATION.md), [evidence](BELEM_PHASE05_EVIDENCE.json).

## A. PDF requirements (official)

| # | Requirement (PDF) | Phase 0 | Phase 0.5 | Proof |
|---|---|---|---|---|
| P1 | Automatically identify the underlying dependencies of a DeFi position | PASS | PASS | Discovery is fully on-chain: Pendle market/SY, USDC, Morpho market (oracle, IRM, LLTV). Live tests pass. |
| P2 | Model how a failure propagates through those dependencies | PASS | PASS | Best-path propagation with dependence bounds. A shared node is counted once (R10). |
| P3 | Quantify economic impact on the position | PARTIAL: point estimate, independence presented as exact | PASS | Central value plus a low/high band, with each parameter classed observed / calibrated / assumption. Liquidation impact is computed for real borrowers (R06–R09). |
| P4 | Compare staying risk with real exit cost, including slippage | PARTIAL: indicative quote, no carry | PASS | The SDK quote is re-executed on-chain (gap 0). Carry forgone is included. |
| P5 | Actionable, explainable signal for a PM | PARTIAL: binary STAY/EXIT presented as firm | PASS | STAY / EXIT / REVIEW with a lean, bands and reasons, shown in the dashboard and in X-Ray. |
| P6 | Working demo on real on-chain data, no mock presented as real | PASS (labelled) | PASS | The local e2e ran on live block 26162571. The deployed app at https://faultline-sandy-three.vercel.app was also tested on live block 26162693: HTTP, API, stress scenario and visual rendering. The snapshot fallback is labelled "not fresh". |

The judging weights in the PDF are 30 / 30 / 25 / 15. All four criteria are covered, both locally and on the deployment.

## B. Phase 0.5 internal gates (not PDF requirements)

| Gate | Status |
|---|---|
| G01–G10 | **PASS**: code reference, executed test, observed result and block are given in the evidence JSON |
| G11 Deployment tested | **PASS, with a recorded deviation.** R20 was run on the existing **production** deployment `https://faultline-sandy-three.vercel.app`, not on a separate preview. Only read-only GET requests were sent; no funds were touched. The teammate ran the tests at 16:40 and the agent rerun them independently at 16:42.<br>• `/` and `/xray.html`: 200<br>• `/api/analyze?borrower=auto`: 200 in 13–18 s (under 60 s); `source=live`, `quote_status=simulated`, `freshness=fresh`, `liquidation.mode=borrower_position`, HF 1.0544<br>• invalid inputs: 400, no secret in the body<br>• stress shock `usd_usdc`: 200<br>• in the browser, the REVIEW badge is amber and the "live on-chain data" badge is shown on both pages<br>The deployed SHA was inferred from the served code (Phase 0.5 JS and API fields), not read from Vercel. |
| G12 Final audit | **PASS**. Offline tests: 54 passed, 3 skipped. Live tests: 57 passed. Docs and evidence are up to date. No open P0 or P1 finding. |

## C. Changes since Phase 0

- **Before:** firm STAY/EXIT from a point estimate, with independence presented as exact. No liquidation modelling, no carry, no freshness gating, no historical replay. The UI showed every non-EXIT verdict as green STAY.
- **After:**
  - `keccak.py`, `morpho.py`, `leverage.py`, `uncertainty.py`, `freshness.py`;
  - `decide_robust`, a correlated scenario, the API `borrower` parameter and input validation;
  - replay fixtures;
  - 25 new tests;
  - UI: REVIEW state, signal line and updated methodology.
- **Verdict change at $1M:** EXIT → REVIEW (lean STAY). The reasons are carry and overlapping bands; see the validation document, §6.

## D. Open findings

| Severity | Item | Required action |
|---|---|---|
| ~~P1~~ closed | Deployment not tested (G11) | Closed on 2026-10-10 by R20 on the production URL (see B) |
| P2 | In X-Ray, the "margin" card shows "+$371, stay costs more" in red, and the guide says "the cheaper one wins". Both use the execution-only comparison, without carry, so they can read as contradicting REVIEW / lean STAY. | Show the margin including carry, or label it "execution cost only"; update the guide text. |
| Limit | Wide high band, so REVIEW is frequent | Traced; better priors would narrow it (out of Phase 0.5 scope) |
| Limit | Normal PT volatility not modelled | REVIEW is forced for borrowers whose distance to liquidation is below 10 % |

## E. Verdict

**PDF requirements: 6/6 verified, locally and on the deployment.**

**Phase 0.5 internal gates: 12/12 PASS. Overall verdict: GO.**
- G11 was validated on the production URL instead of a separate preview; this deviation is recorded above.
- One P2 explainability fix remains in the X-Ray UI.
