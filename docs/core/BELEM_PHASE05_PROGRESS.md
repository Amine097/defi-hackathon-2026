# Phase 0.5 — progress

Updated 2026-10-10 16:45. The Phase 0.5 changes are in commit `480860e`, pushed to `origin/main`.

| Item | Status | Evidence |
|---|---|---|
| H03 Exit cost | DONE | Pendle SDK quote re-executed with eth_call + state override (gap 0); status/TTL/cost breakdown; R02–R04 |
| H02 Liquidations | DONE | `morpho.py`, `leverage.py`; live borrower HF 1.0544; real liquidation tx replayed (error 4.2e-11); R05–R09 |
| H01 Risk model | DONE | `uncertainty.py`, `decide_robust`; parameter classes, loss/exit bands, carry, correlated scenario; R10–R15 |
| H04 Historical replay | DONE | `scripts/replay_h04.py` → `data/fixtures/replay_h04.json` (SVB 2023, Morpho liquidation); R16 |
| H05 Freshness / provenance | DONE | `freshness.py`; TTLs, blockers, labels; API validation; R17–R18 |
| H06 Demo / deployment | BLOCKED | Local e2e passes (live block 26162781, after the coherence fix). Production runs **`a2d10c1`**: the SHA comes from the GitHub Deployments API (`vercel[bot]`) and was confirmed by hashing the served files. R20 passed on that SHA. Later pushes are "Deployment was blocked" by Vercel (non-owner). The coherence fix needs a deployment by the project owner, then R20 must be rerun. |
| Coherence fix (margin / exit side incl. carry) | DONE locally | See compliance report §C.1; `tests/test_decision_coherence.py`, `tests/js/decision_view.test.mjs` |

## Open items

- **P1 (blocking):** deploy the coherence fix (project owner), then rerun R20 on the new SHA. Expected X-Ray result: margin ≈ −$3.3k, amber, "lean STAY"; exit card "execution $1.3k + carry $3.7k".

## Log

1. Baseline: 31 passed, 1 skipped.
2. H03: quote simulation, cost statuses.
3. H02: Morpho maths and live borrower, wired into the API (`borrower` param).
4. H01 + H05: bands, carry, robust verdict, freshness.
   - **Bug fixed:** `point_verdict` ignored carry.
5. H04: replays.
6. UI:
   - REVIEW badge (amber);
   - signal line (bands, carry, quote status, freshness, liquidation);
   - methodology text updated;
   - query string forwarded to the API;
   - snapshot fallback labelled "not fresh";
   - `public/data/sample.json` regenerated from a live run (block 26162571).
7. Tests: offline 54 passed / 3 skipped; live (`DEFIRISK_LIVE_TESTS=1`) 57 passed.
8. Coherence fix:
   - margin, break-even, exit KPI, and the scenario / stress / sensitivity / book verdicts now use execution + carry, the same basis as the verdict;
   - `decisionView` in `model.js` drives the UI (REVIEW shown amber, with its lean).
   - Tests: offline 62 passed / 3 skipped; live 65 passed; node 7 passed.
   - Local live check on block 26162781 gives a margin of −$3,339. With execution only, the margin was +$342: this was the bug.
   - Not deployed yet: production is `a2d10c1`.
