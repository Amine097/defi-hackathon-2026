# D. Current Frontend Assessment (real browser)

Method: local `scripts/dev_server.py` (live APIs) inspected in Chrome 154 via Playwright (1440×900 desktop, 390×844
mobile, DPR 2) and in the app's browser panel (420 px). API failures were simulated by intercepting `/api/analyze`
with a 502. Screens are in [`audit-2026-10-11/`](audit-2026-10-11/).

## D1. The "Loading…" baseline screenshot — diagnosis

`docs/reference-context/baseline/FAULTLINE_BEFORE.png` shows the **`work/frontend-redesign` branch** (sidebar shell,
"Coming soon" items), not `main`. Its `public/` was extracted with `git archive` and served with API calls forwarded to
the current backend (screens 12–13):

- At t = 3 s the page looks exactly like the baseline (all cards "Loading…").
- After **31 s** `/api/analyze` returned 200 and every card rendered (REVIEW, $761, $5,472, N/A breaking point).
- The only card that never resolves to data is **Exit runway**: it fetches `/exit-cost/pos`, an endpoint that does not
  exist in any backend (404 → "not connected").

**Conclusion:** a slow first load (live discovery + executable quote, 20–36 s), not a backend failure and not a CSS
problem — plus one card wired to a non-existent endpoint. The same latency exists on `main` today: the dashboard
renders after 26.5 s (desktop) / 28.8 s (mobile), X-Ray after 31–35 s, with no progress indication.

## D2. Route findings

### `/` Dashboard (screens 01–03)
- **Works:** live verdict, KPIs with count-up (respects reduced motion), drivers, scenarios, book, methodology; badge
  "live on-chain data".
- **Problems:**
  1. For 26–29 s the page shows "loading…", "—" and empty cards (no staged progress, no skeleton, no time estimate).
  2. The verdict card is a 500-character paragraph (`index.html:166`), duplicated by a second dense line; the
     decision is not readable in 3 seconds.
  3. Book table prints **negative exit costs with EXIT badges** for unaffected pockets (`index.html:196`; C3).
  4. HOLD TO MATURITY, incident path, stress table, sensitivity, shared dependencies, 11 % example: absent.
  5. API failure → silent stale snapshot labelled "MOCK (API offline)" with superseded numbers (screen 03; C2).
  6. Brand: gradient blue→purple wordmark on a Tailwind-like palette; the logo's bone/red identity is unused. The
     "hero" is a heading and two buttons — there is no landing experience on `main`.
  7. Mobile: header links overflow — **"Countermove" is clipped off-screen**; 6,080 px tall page.

### `/xray.html` (screens 04–07)
- **Works:** canvas graph (force + layered modes), node tooltips, look-through card, peg checks, hidden-concentration
  insights, keyboard shortcuts (R, F, L, 1–9, Esc), picker as keyboard alternative, `aria-label` on the canvas, data
  source select, live badge, reduced-motion handling in CSS/JS.
- **Problems:**
  1. **P0: client-side financial recomputation contradicts the backend** (C1): oracle → EXIT $154k, AMM → EXIT $192k,
     Morpho market → EXIT $192k, while the scenario chips next to it say "$761 · STAY".
  2. First visit opens a modal guide that hides the entire graph (desktop and mobile) after a 35 s wait.
  3. Break-even sliders invent "P(incident)" and "exit cost %" what-ifs on the client — acceptable only if visibly
     labelled as a what-if calculator, not as model output.
  4. No `?shock=` server path; no severity control; no HTM; book shows negative exit costs.
  5. Header crowded: nav lacks Countermove; on mobile the "X-Ray" link wraps; source select + badge + chips overflow.
  6. 404s for `/assets/logos/us.svg`, `rexyz.svg`, `reusd.svg` (fallback works, console errors remain).
  7. 60 s client timeout then silent sample fallback (C2).

### `/vault.html` (screens 08–09)
- **Works:** best end-to-end integration: input validation, Belem example button, deep links, live analysis
  (15–25 s), verdict + reasons, KPI, breakdown, allocations table, SVG graph, risk, scenarios, custom shock,
  sensitivity, crash curve, withdrawal routes, assumptions, provenance; errors are inline and specific
  ("unsupported_contract (422): contract is not a Morpho vault…").
- **Problems:** form-first layout (result starts below the fold; on mobile the form fills the first screen); the
  REVIEW badge text overflows its frame; chips expose enums (`withdrawal full_via_force_deallocate`); oracle nodes
  shown as `Oracle 0x2b43e079…`; status line "Analysis done in 22.9 s" is the only progress feedback; mobile page is
  **11,568 px** long; no list of sponsor vaults (Dune table) to pick from.

### `/countermove.html` (screens 10–11)
- **Works:** clearest page. SIMULATED banner with fork block and caveats, S1–S5 tabs with outcome badges, three-step
  story (crisis → decision → result), LTV gauge (trigger / liquidation / before / crisis / after), reserve table,
  actions compared, pre-send checks, on-chain verification, protections, keeper runs, LIVE reads button, policy draft.
- **Problems:** it is a long document, not an ARM → DEFEND → PROVE experience; S1 (weETH) is the default while S5 is
  Belem's own PT example; the policy draft says "Sign this setPolicy call, sent to your RescueVault" although no vault
  exists to sign for (C8); the mainnet dry run is not exposed; no link from the X-Ray borrower verdict.

## D3. Cross-cutting issues

| Area | Finding |
|---|---|
| Information architecture | Four parallel pages with different headers (X-Ray has its own, missing Countermove). No journey from "what is my risk" → "what should I do" → "protect it" |
| Status honesty | Badges exist, but the fallback path mislabels a stale real snapshot as MOCK and the X-Ray contradicts the server |
| Latency UX | 15–36 s waits with spinners only (NN/g: > 10 s needs a progress indicator and an estimate) |
| Typography & colour | System fonts, generic blue/green/red/amber; REVIEW amber vs EXIT red vs warn tones are not differentiated by shape/text in every place |
| Mobile | Nav overflow, modal over the graph, very long pages, dense tables without priority columns |
| Accessibility | Good base (focus-visible, reduced motion, aria-live on dashboard/vault/countermove), but canvas graph lacks a table alternative; colour carries verdict meaning in tables |
| Performance | Pages are light (no frameworks); the cost is entirely API latency |
| Engineering | Clean modular JS with tested view models (`tests/js`); escaping is consistent; no build needed |

## D4. Keep or migrate the architecture?

**Keep the static HTML/CSS/ES-module architecture; do not migrate to React/Next.js now.**
- The difficulty is not state management but trustworthy rendering of server payloads, latency handling and visual
  craft; a framework adds a build, a runtime and a migration risk with a deadline of hours.
- Vercel already serves `public/` statically next to the Python functions with zero configuration; the view models are
  pure functions tested with `node --test`, which ports to any future framework if needed.
- What should change: one shared shell (nav, status bar, footer), one design-token file, a small `core/` module set
  (API client with timeouts/abort/retry, formatters, status model, evidence popovers), and **removal of all client-side
  financial computation** except clearly labelled what-if calculators.
- The landing page may load Three.js + GSAP as **self-hosted ES modules** (import map, no CDN), lazily, after first
  paint. A bundler (Vite) is optional later, only if the landing's WebGL code grows beyond a few modules.
