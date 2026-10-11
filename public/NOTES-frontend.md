# Frontend notes (FAULTLINE)

Static site, no build step for the pages: vanilla HTML, CSS and ES modules served from `public/`. The only built file is
the landing hero bundle (`assets/js/landing/landing.bundle.js`, source in `tools/frontend/src/landing.js`).

## Routes
- `/` landing: cinematic hero (Three.js + GSAP, poster fallback, reduced-motion final frame), story rows, truth list.
- `/analyze.html` analysis instrument: decision first, strata X-Ray, incident lab, exit or hold, book of ten,
  stress and sensitivity, borrower and liquidation, evidence. `?snapshot=1` opens the labelled saved snapshot.
- `/vault.html` vault intelligence (Morpho V1/V2), deep link `?address=0x...&value_usd=&horizon_days=`.
- `/countermove.html` autonomous protection lab: recorded fork run (ARM, DEFEND, PROVE) and a live read-only dry run.
- `/xray.html` redirects to `/analyze.html`, keeping the query.

## Shared code
- `assets/css/tokens.css`, `assets/css/system.css`: design tokens and components (status, tag, table, alert, work, seg,
  panel, btn). Page styles: `analyze.css`, `vault.css`, `countermove.css`, `landing.css`.
- `assets/js/core/`: `api.js` (timeouts, abort, de-duplication, structured errors, session cache; never substitutes
  data), `status.js` (one status vocabulary: live, cached, mixed, stale, snapshot, demo, simulated, dryrun, unavailable,
  loading), `shell.js` (header, nav, footer), `format.js`, `work.js` (honest long-wait panel).

## Rules
- The browser never computes losses, verdicts or prices. Every financial number on screen comes from the API response.
- No silent fallback: a failed request shows Unavailable with the cause; the saved snapshot opens only on request and
  is labelled with its block and date.
- Simulated (fork) and dry-run results are labelled as such wherever they appear.

## Run locally
`python scripts/dev_server.py 8000` then open http://localhost:8000 (routes `/api/*` to `api/*.py`).
Dev-only QA tools live in `tools/frontend/` (`qa.mjs`, `a11y.mjs`, `kbd.mjs`, `shot.mjs`); see
`docs/frontend/IMPLEMENTATION_PROGRESS.md`.
