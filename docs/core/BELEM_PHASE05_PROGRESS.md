# Phase 0.5 — progress

Updated 2026-10-10. Base commit `9ec4d51`; the Phase 0.5 changes are not yet committed.

| Item | Status | Evidence |
|---|---|---|
| H03 Exit cost | DONE | Pendle SDK quote re-executed with eth_call + state override (gap 0); status/TTL/cost breakdown; R02–R04 |
| H02 Liquidations | DONE | `morpho.py`, `leverage.py`; live borrower HF 1.0544; real liquidation tx replayed (error 4.2e-11); R05–R09 |
| H01 Risk model | DONE | `uncertainty.py`, `decide_robust`; parameter classes, loss/exit bands, carry, correlated scenario; R10–R15 |
| H04 Historical replay | DONE | `scripts/replay_h04.py` → `data/fixtures/replay_h04.json` (SVB 2023, Morpho liquidation); R16 |
| H05 Freshness / provenance | DONE | `freshness.py`; TTLs, blockers, labels; API validation; R17–R18 |
| H06 Demo / preview | **BLOCKED (preview)** | Local e2e PASS (dev server + browser, dashboard and X-Ray show REVIEW, bands, carry, borrower HF). Vercel preview: `npx vercel whoami` → "Logged out" |

## Open blocker

- **G11 / R20, Vercel preview.**
  - **Needed:** a logged-in Vercel CLI, or a project token for the FAULTLINE Vercel project.
  - **Then run:** `npx vercel deploy` (preview, not `--prod`) and smoke-test `/`, `/xray.html` and `/api/analyze?borrower=auto` on the preview URL.
  - No production deployment and no on-chain transaction are part of this phase.

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
