# Design fidelity report: Claude Design v2 → production

**Reference:** the Claude Design v2 export, byte-identical to `claude_design/Faultline Landing prototype` and to the zip
of the same name, committed in [`docs/design/claude-design-v2/`](../design/claude-design-v2/). Landing:
`Faultline Landing v2.dc.html`. App: `Faultline App.dc.html` (the file Landing v2 links to; `Faultline App v1.dc.html`
and `Faultline Landing.dc.html` are earlier versions, kept for reference only).

## How the implementation stays faithful

- **Same templates.** `tools/frontend/dc-build.mjs` copies the export's `<x-dc>` templates into `public/index.html` and
  `public/app.html` and applies a short, explicit list of edits. Each edit must match exactly, or the build fails. Styles,
  layout, typography, spacing, colours, components, hover / focus styles and responsive rules are the export's own inline
  styles: nothing was re-implemented.
- **Same runtime.** The pages run on the design's runtime, `support.js`, copied verbatim. React 18.3.1 UMD is self-hosted;
  both files match the SRI hashes pinned in `support.js`, so they are byte-identical to what the design loads from unpkg.
  three.js 0.160.0 is the same build, self-hosted.
- **Same fonts.** The exact Google Fonts files and unicode ranges the export requests (Archivo `wdth 62..125`,
  `wght 100..900`; IBM Plex Mono 400 / 500) are self-hosted under `public/assets/fonts/gf/`.
- **Same logic.** The landing class is generated from the export, changing only the three.js URL and links. The app class
  (`public/assets/dc/app.js`) keeps the export's state machine, timings (420 ms loading steps, 800 ms propagation steps,
  2.6 s replay steps), animations and render-value shapes. Its data comes from the backend through
  `public/assets/dc/fl-live.js` instead of `faultline-data.js`.
- **CSP unchanged** (`script-src 'self'`): the export's `<script data-dc-script>` body is shipped as a same-origin file
  and attached to the runtime by `public/assets/dc/register.js`. There is no `eval` and no third-party origin.

## Verification

`tools/frontend/dc-qa.mjs` drives the export (served with its own mock data) and the implementation (served with the
backend) through the same states at **1440×900, 1024×900 and 390×844**. It saves paired captures in
[`fidelity/<viewport>/<state>.{design,app}.webp`](fidelity/). States: landing hero, layers, ARM, DEFEND, PROVE, ENTER;
app select, candidate review, loading, dashboard, technical details, positions, X-Ray (inspect, revealed, node selected,
list), simulate (single dependency and incident type, result), replay (S1 at T5, S5), Countermove (fork preview,
validated, fork tab, deployed tab) and activity. **168 captures; 164 completed on both sides.** The 4 failures are
identical on the design and the implementation: at 390 px the landing header nav overflows the viewport, so PROVE and
ENTER cannot be clicked (a property of the approved design, reported below, not changed).

Review of the pairs: the layout, hierarchy, spacing, type scale, colour, component shapes, hover styles, responsive
reflow (sidebar ↔ bottom nav at 900 px, wrapping grids) and animation timing match. The differences are the data
(backend values instead of the prototype's copies) and the deviations listed below.

Additional checks: hover and focus styles come from the export's `style-hover` / `style-focus` attributes, compiled by
the same runtime. Keyboard: native buttons and inputs, as in the export. `prefers-reduced-motion`: the export's
`reduced()` paths are kept (instant loading, propagation and replay; no dive animation).
Automated: `node --test "tests/js/*.test.mjs"` (54 tests, including `design_app.test.mjs`); `python -m pytest` (247 passed).

## Remaining deviations and reasons

| # | Where | Deviation | Reason | Approval |
|---|---|---|---|---|
| D1 | Everywhere | Figures differ from the prototype | The prototype copied an older run (block 26,162,781, before the role-aware model). Production shows the backend: recorded live runs (labelled, blocks 26,166,578–26,166,582) or live runs | Required by the brief |
| D2 | Landing "Five layers deep" | `$761 ($39 to $19,664) vs exit side $5,448`, block 26,166,580, "84% utilized" instead of `$1,657 / $4,996`, 88 % | Filled at build time from `public/data/recorded/analyze-pt.json`; the old artifact (`public/data/sample.json`) no longer exists | Required (truthfulness) |
| D3 | Landing DEFEND | "HOLD 89.6 % · liquidatable" kept as designed | Recorded crisis LTV ÷ the −8 % follow-on price factor; correct, but derived by the designer, not a stored backend field | Kept: please confirm |
| D4 | App loading (live runs) | Steps are not ticked one by one; the note shows elapsed seconds and states that steps are marked done together | The backend returns one response after 10–40 s and reports no progress. Ticking steps on a timer would invent progress. Recorded runs keep the designed ticking, with the designed "recorded run, so it is quick" note | Needs approval (or a backend progress stream) |
| D5 | Select › PROTOTYPE STATES | NETWORK ERROR and SLOW REQUEST buttons appear only with `?qa=1` | They fabricated states. The real states are reached by real failures and slow reads, with the designed visuals | Needs approval |
| D6 | Select › lookup messages | "Still working (block pinned, 4 of 113 reads done)" became "Still working. Public RPC endpoints can be slow…"; market-id lookups say "Matching the market id against Pendle and Morpho market lists…" | No read counter exists; market ids are matched against API lists, not factory registries | Truthfulness |
| D7 | App sidebar mode box | Shows "LIVE · ETHEREUM MAINNET · READ-ONLY" (cyan) for live runs; "DEMO · RECORDED DATA" otherwise | The design only knew recorded data; LIVE reuses the export's chip colour | Data-dependent |
| D8 | X-Ray graph | 11 backend nodes (PT / SY contracts and the AMM are separate, Morpho Blue custody edge), coordinates of the design for known ids, free slots for new ids | Role-aware backend graph | Data-dependent |
| D9 | X-Ray "How to read it" | "Your wallet shows 4 dependencies: Pendle PT / SY, Pendle AMM, Morpho market and Morpho Blue. FAULTLINE traced 7 more" | Sentence generated from the graph instead of fixed text | Data-dependent |
| D10 | X-Ray for a vault | Designed "graph covers…" state, text no longer says "in this prototype" | A vault layout is not designed (design gap G3) | Gap reported |
| D11 | Simulate result | DECISION colour follows the verdict (cyan STAY when a shock does not reach a no-debt position); chip "SIMULATED · RECORDED / LIVE BACKEND VALUES"; hold-to-maturity cell shows the baseline value or the AMM note; uncertainty band uses the run's band | Role-aware backend results; maturity exists now but not per shock | Data-dependent |
| D12 | Replay S5 | Rendered with the S1 replay component instead of the "UNAVAILABLE · needs a recording" card | The S5 recording exists now; the card remains for a missing recording | Uses an approved component |
| D13 | Countermove › Policy preview | Defaults come from the backend (recorded fork policy; for a borrower, `countermove_suggestion`); checks come from `/api/countermove` (`policy-draft`, live `dry-run`); the footnote says so | The export's checks ran in the browser and said "In the product, … come from /api/countermove" | Required |
| D14 | Countermove › Fork tab | Same grid and copy, values read from the recorded run | Backend-derived | Data-dependent |
| D15 | Activity | Legend adds a LIVE chip; rows come from recordings, the recorded fork run and this session | Live runs exist | Data-dependent |
| D16 | Positions › routes | "Hold to maturity" shows a value (MODELLED) instead of UNAVAILABLE | `payload.maturity` exists now | Data-dependent |
| D17 | `<head>` | Page titles and descriptions added; favicon reuses `/assets/brand/logo.svg` | Not visual | — |
| D18 | Console | "attribute x1: Expected length, "{{ c.x }}"" and similar during page parse | The browser parses the raw `<x-dc>` template before the runtime replaces it; the export logs the same messages | Harmless, documented |
| D19 | Captures | Sticky sidebar and header appear more than once in full-page screenshots | Capture artifact of fixed or sticky elements; the export shows the same | — |
| D20 | Countermove › Reserves | Notes under the reserve fields read "Policy floor kept after an action: 100" instead of "Minimum 100" | The 100 USDC / 0.01 weETH values are the policy's reserve floors (`min_loan_reserve`, `min_collateral_reserve`), not a minimum deposit | Truthfulness |
| D22 | X-Ray graph and replay | Round logo badges on the nodes that have a known logo (Morpho, Pendle, Ethereum, USDC, ether.fi…), from `public/assets/logos` | Requested by the owner on top of the export; drawn over the designed circles, faded while a node is hit | Owner request |
| D21 | Countermove › Policy preview | A "Priority order" check is added to the checks list | The backend does not take a custom order (the engine ranks by least reserve committed); the designed ↑ / ↓ control stays | Needs approval (or backend support) |

## Issues found in the approved design (reported, not changed)

1. At 390 px the landing header nav (5 links + LAUNCH APP) is wider than the viewport: PROVE and ENTER are off screen
   (`fidelity/390/landing-prove.*`).
2. The landing "Connection preview" modal has no trigger in the export (design gap G17).
3. X-Ray column labels "02 YIELD / ISSUER" and "01 CHAIN" overlap at every width (columns 800 and 915 in a
   1010-wide viewBox).
