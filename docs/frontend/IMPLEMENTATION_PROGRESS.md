# FAULTLINE — Implementation Progress

Branch `frontend/production-redesign` (from `main` @ `834a99b`). Nothing committed, pushed or deployed.
Local preview: `.\.venv\Scripts\python.exe scripts\dev_server.py 8000` → http://127.0.0.1:8000/

## Toolchain actually used

| Tool | Status in this environment | What it contributed |
|---|---|---|
| frontend-design (Anthropic skill) | Not installed as an invocable skill; official `SKILL.md` fetched from github.com/anthropics/skills and applied | Design plan (tokens, type roles, one orchestrated motion moment), anti-default checklist: sentence case, no all-caps eyebrows, no middle-dot meta strings, no arrow CTAs, typography as an active element |
| Impeccable (pbakaus) | Not installed (its installer writes hooks into the repo); README guidance fetched and applied manually | Per-screen critique after every render: default fonts, grey on colour, tinted blacks, nested cards, bounce easing, unequal panels, truncated labels, chip overload |
| UI UX Pro Max | Not installed; not used | — |
| Three.js 0.186.1 (MIT) | Dev-only in `tools/frontend`, tree-shaken into `public/assets/js/landing/landing.bundle.js` | Landing monolith: logo extruded into stone + fault, procedural limestone shader, seismic-ledger line field shader, bloom |
| GSAP 3.15 + ScrollTrigger (no-charge licence) | Bundled into the landing bundle | Story timeline STABLE → SIGNAL → PROPAGATION → COUNTERMOVE → PROOF, headline seam choreography, scroll-linked turn |
| esbuild | Dev-only | One-file ESM bundle (708 KB minified, 194 KB gzip), legal comments in `landing.bundle.js.LEGAL.txt` |
| Playwright (playwright-core + installed Chrome 154) | Dev-only | All screenshots (`shot.mjs`), live end-to-end checks (`qa.mjs`), keyboard check (`kbd.mjs`), poster frames (`poster.mjs`), page QA scripts (`cm-shots.mjs`, `vault-shots.mjs`) |
| axe-core 4.10 | Dev-only, injected by `a11y.mjs` | WCAG 2.0/2.1/2.2 A+AA scan of every route at 1440 and 390 |
| Higgsfield | CLI signed in, free plan, 10 credits | Not used; no credits spent |
| Lighthouse | Not installed | Not run; LCP handled by the 48 KB poster frame, fonts self-hosted and preloaded |

## Milestones

### M1 — Financial truth and stability (done)
- Client-side loss engine removed (`xray/model.js` keeps only the tested `decisionView` / `exitCostOf`). Every node result
  comes from `stress_table`; incidents call `/api/analyze?shock=&severity=`.
- Silent `sample.json` fallbacks removed. Failure → Unavailable with the cause and Retry; the labelled saved snapshot
  (`public/data/snapshot-analyze.json`, block 26,165,760, recorded 11 Oct 2026 00:56 UTC) opens only on request.
- Book EXIT rows on unaffected pockets labelled "yield rebalance, not a risk exit"; backend numbers unchanged.
- One shared shell; `/xray.html` redirects to `/analyze.html`; `vercel.json` adds the redirect and security headers.

### M2 — Analysis instrument `/analyze.html` (done)
Decision first (verdict, lean, confidence, sentence from fields, stay/exit band chart, facts, reasons); strata X-Ray on
Belem's five layers (hidden nodes, channel-styled edges, server failure path, node inspector, list twin); tabs: incident
lab, exit or hold, book of ten (11% toggle), stress and sensitivity, borrower and liquidation, evidence.

### M3 — Landing (done)
The Seam × Seismic Ledger hero with poster LCP/fallback, reduced-motion final frame, Pause/Replay. The slab is placed from
the headline's measured text box, so it never collides with the type from 1024 to 1920 px; portrait and square viewports
(phones, tablets) use the stacked stage.

### M4 — Countermove and Vault (done)
- `/countermove.html`: autonomous protection lab, ARM / DEFEND / PROVE as real tabs, S5 default, keeper timeline with
  replay, LTV scale, actions compared, fork receipt with 5 pre-send and 15 on-chain checks, "Verified on the local fork"
  vs "Not verified on Ethereum mainnet", policy preview, live read-only dry run. No Etherscan links for fork transactions.
- `/vault.html`: decision first, withdrawal routes (ordinary vs forceDeallocate) in plain words, FX and peg for non-USD
  vaults, allocations, dependency map, stress with custom shock, sensitivity, assumptions; 422 shown inline. Mobile height
  4,154 px (was 11,568).

### M5 — QA and polish (done)
- Header data status stays visible on phones (second header row) instead of being hidden.
- `?snapshot=1` deep link now leaves "Re-run live" enabled.
- Borrower tab: exact liquidation threshold from `distance_to_liquidation_pct` (4.53%), grid points described as bracketing it.
- Incident sentence written from the incident fields; the backend headline kept in a fold.
- Analysis top row: panels equal height; dependency boxes sized per row (no needless truncation).

## Verification (final run)

| Gate | Result |
|---|---|
| Live end-to-end `tools/frontend/qa.mjs` (real Chrome, live backend; screen numbers = API numbers) | 45 / 45 pass (landing, analysis live + incident + 11% book, failure + snapshot, legacy redirect, Countermove, Vault + 422) |
| axe-core (`a11y.mjs`), `/`, `/analyze.html`, `/countermove.html`, `/vault.html` (empty and Belem result), 1440 + 390 | 0 violations |
| Keyboard (`kbd.mjs`): skip link first, logical order, visible focus on every stop | pass on all 4 routes |
| Node `node --test tests/js/*.mjs` | 45 / 45 |
| pytest | 252 passed, 17 skipped (same as baseline) |
| forge test | 29 passed, 1 skipped (same as baseline) |
| Viewports rendered | 1920×1080, 1440×900, 1280×800, 1024×768, 768×1024, 390×844: no horizontal overflow |

Notes: `test_offline_replay_is_reproducible` failed once while live API calls were writing the git-ignored
`data/cache/` concurrently; it passes alone and in the full run. One transient 6 s stall of `/api/countermove` was seen
once and not reproducible (8/8 cold loads in ~130 ms); the page times out at 20 s to Unavailable + Retry.

## Coverage matrix (backend capability → UI)

| Backend capability | Where |
|---|---|
| decision (verdict, lean, bands, reasons, explanation) | `/analyze.html` decision panel |
| stress_table / channel blocking / path | X-Ray node inspector, path highlight, Stress tab |
| HOLD_TO_MATURITY | Exit or hold tab |
| incident (`shock`, `severity`) | Incident lab (presets + any dependency) |
| book (`exit_cost_pct`, shared dependencies) | Book of ten tab with 11% toggle |
| sensitivity / transmission / LGF | Stress and sensitivity tab |
| liquidation price grid, countermove_suggestion | Borrower and liquidation tab |
| provenance, freshness, assumptions | Evidence tab, header status chip |
| vault analysis, routes, FX/peg, custom shock | `/vault.html` |
| recorded fork run, policy-draft, dry-run, live oracle reads | `/countermove.html` |

## Files changed
Added: `public/analyze.html`, `public/assets/css/{tokens,system,analyze,landing}.css`, `public/assets/js/core/*`,
`public/assets/js/analyze/*`, `public/assets/js/countermove/acts.js`, `public/assets/js/vault/present.js`,
`public/assets/js/landing/{landing.bundle.js,landing.bundle.js.LEGAL.txt,shell-init.js}`, `public/assets/js/redirect-xray.js`,
`public/assets/fonts/*` (Archivo, IBM Plex Mono, OFL licences), `public/assets/img/hero-poster*.webp`,
`public/data/snapshot-analyze.json`, `tests/js/analyze_view.test.mjs`, `tests/js/fixtures/analyze_{live,borrower}.json`,
`tools/frontend/*` (dev-only; `node_modules` is git-ignored).
Rewritten: `public/index.html`, `public/xray.html`, `public/countermove.html`, `public/vault.html`,
`public/assets/js/{countermove,vault}.js`, `public/assets/css/{countermove,vault}.css`, `public/NOTES-frontend.md`,
`vercel.json`. Trimmed: `public/assets/js/xray/model.js`. Banner added: `public/NOTES-xray.md`.
Deleted: `public/assets/js/{api,shell,xray}.js`, `public/assets/js/xray/{graph,data,chart,util}.js`,
`public/assets/css/{theme,xray}.css`, `public/data/sample.json`, `public/data/sample-large.json`.
No backend, contract or test-expectation changes.

## Rebuilding the landing bundle
`cd tools\frontend; npm ci; node build.mjs` (posters: `node poster.mjs`, then convert PNG → WebP).

## Credits spent
None.

## Known limitations and owner items
- C3 (book carry reference rate) and C4 (borrower notional vs $1M headline) remain backend decisions; the UI labels them
  ("yield rebalance, not a risk exit"; "Two different positions on this page") instead of altering numbers.
- Countermove execution exists only on a local fork; no RescueVault is deployed on mainnet. The site says so everywhere.
- Some backend strings stay technical (e.g. "Oracle 0x2b43…", "Signed by the keeper", US spelling "authorized").
- Chrome logs "Failed to load resource" for intended 4xx responses (vault 422); it cannot be suppressed by the page.
- The landing bundle is 194 KB gzip; the poster frame paints first, and under reduced motion the bundle renders the
  final frame without animation.
