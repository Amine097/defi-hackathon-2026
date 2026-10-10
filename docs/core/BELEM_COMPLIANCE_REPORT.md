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
| P6 | Working demo on real on-chain data, no mock presented as real | PASS (labelled) | PASS locally; **preview BLOCKED** | The local e2e runs on live block 26162571. The snapshot fallback is labelled "not fresh". The Vercel preview is untested. |

The judging weights in the PDF are 30 / 30 / 25 / 15. All four criteria are covered locally. The working-demo criterion (15 %) is verified locally only.

## B. Phase 0.5 internal gates (not PDF requirements)

| Gate | Status |
|---|---|
| G01–G10 | **PASS**: code reference, executed test, observed result and block are given in the evidence JSON |
| G11 Vercel preview | **BLOCKED**: `npx vercel whoami` returns "Logged out" |
| G12 Final audit | **BLOCKED**: depends on G11 |

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
| P1 | Vercel preview not tested (G11) | Log in to Vercel CLI, run `npx vercel deploy` (preview), smoke-test `/`, `/xray.html`, `/api/analyze?borrower=auto` |
| Limit | Wide high band, so REVIEW is frequent | Traced; better priors would narrow it (out of Phase 0.5 scope) |
| Limit | Normal PT volatility not modelled | REVIEW is forced for borrowers whose distance to liquidation is below 10 % |

## E. Verdict

**Compliance to the PDF requirements is verified locally: 6/6 requirements, with P6 limited to the local demo.**

**Phase 0.5 internal gates: 10/12 PASS, 2 BLOCKED. Overall verdict: BLOCKED.** No GO until the preview is deployed and tested.
