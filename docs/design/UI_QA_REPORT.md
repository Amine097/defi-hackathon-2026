# FaultLine — UI QA report (frontend v2)

_10 Oct 2026 · static app in `public/` · served with `python -m http.server -d public` (no `/api`, so the app runs on its saved real snapshot, as it would if the API were down)._

## What was run
- Chrome 143 headless, driven over the DevTools protocol (the Playwright MCP is not installed here). Viewports 1440×900, 1280×800, 390×844. Screenshots in `docs/design/qa/`, raw results in `docs/design/qa/results.json`.
- **Skill actually run:** `frontend-design` (installed by the user, then invoked once). It changed: sentence-case card titles instead of tracked all-caps labels, no `→` in buttons, fewer `·`-joined strings, the four identical KPI cards replaced by one strip whose breaking-point cell carries the red fault line, IBM Plex Sans/Mono self-hosted in `assets/fonts/` (OFL, 5 woff2, ~90 KB). The palette and layout were left as the spec defines them.
- **Installed but not usable in the session that did this work:** Playwright MCP (`claude mcp list` shows it connected, its tools were not exposed to the running session, so the DevTools driver was kept).
- **Not run:** Impeccable (not installed), 21st.dev, Higgsfield (not installed; nothing paid). There is no lint/typecheck/build for this static project; JS was syntax-checked with `node --check`. The live API (`/api/analyze` with network access, `?borrower=`) was not exercised.

## Results
| Check | Result |
|---|---|
| No horizontal overflow, Overview + X-Ray, 1440 / 1280 / 390 | PASS |
| Console exceptions / `console.error` | PASS (none) |
| Failed requests | Only `/api/analyze` 404 (expected offline, falls back to the snapshot) and `/exit-cost/pos` 404 (expected: Exit Runway shows `not connected`). Logo 404s fixed with `assets/logos/manifest.json`. |
| Same provenance label on both pages for the same file | PASS ("Real data snapshot · 2026-10-10 · as of … UTC") |
| Journey: Overview → click a driver → X-Ray with that node failed ("If it happens") → click a Breaking Point scenario marker → scenario replayed (STAY $271.1k vs EXIT $4,996) → `R` resets | PASS |
| Overview scenario row → `xray.html?scenario=1` replays that scenario | PASS |
| Guide closed by default, opens from "? Guide", `Esc` closes | PASS |
| Exit Runway: `not_connected` by default; `?runway=demo` renders the labelled fixture (DEMO chip + banner, 7 rows, method / as-of / assumptions) | PASS |
| Breaking Point from `liquidation.price_grid` (−5.2 %, HF 1.054, 4 scenarios) on both pages | PASS |
| "N/A · no debt" path of the Breaking Point | Not rendered in a browser (the bundled snapshot has a borrower); covered by code only |
| `aria-pressed` on segmented controls, canvas `aria-label`, `alt` on images | PASS |

## Known limitations
1. **Exit Runway has no backend.** No `/exit-cost/*` endpoint exists in the repo, so the card says `not connected`. Field names in `exit-runway.js` follow §20.4 and must be agreed with the backend owner.
2. **Breaking Point depends on the borrower analysis** (`?borrower=0x…|auto`); otherwise it says N/A. The reference borrower is the largest on the Morpho market, not the user's $1M position (stated in "Position, method and data").
3. **Local run is not live:** behaviour with the real `/api/analyze` (~15 s discovery, `live` badge) was not tested.
4. **Graph density:** on the 44-node demo book, labels that would overlap are hidden (hover/select shows them); Layers mode is still busy.
5. **X-Ray still recomputes a client-side point verdict** when the exit-cost slider moves (labelled "point comparison", not the engine's REVIEW).
6. No keyboard path to individual graph nodes beyond the "Fail a node…" select and the concentration list.
7. Fonts are self-hosted (no external host); the canvas graph picks Plex up once the font has loaded.
