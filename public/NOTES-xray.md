# FaultLine X-Ray page: notes (historical)

> **Superseded (production redesign, Oct 2026).** `/xray.html` now redirects to `/analyze.html`. The files listed
> below were removed, including the client-side loss model (it ignored role-aware channels). The analysis page draws only
> backend numbers; see `public/NOTES-frontend.md` and `docs/frontend/IMPLEMENTATION_PROGRESS.md`. Kept for the payload
> requests referenced from `PLAN.md`.

Page: `/xray.html`. Vanilla HTML/CSS/ES modules, no build, no CDN.

## Files (owned by the X-Ray dev)
- `xray.html`: layout and element IDs
- `assets/css/xray.css`: styles (`xr-` prefix; theme.css variables re-declared as fallbacks)
- `assets/js/xray.js`: controller (boot, panels, simulation, verdict)
- `assets/js/xray/data.js`: loader and payload normalisation
- `assets/js/xray/model.js`: reachability, cascade, per-position losses, concentration, break-even
- `assets/js/xray/graph.js`: canvas renderer (own force simulation, layers layout, camera, cascade animation)
- `assets/js/xray/chart.js`: SVG break-even chart
- `assets/js/xray/util.js`: helpers
- `data/sample-large.json`: synthetic 10-pocket book (44 nodes / 77 edges) proving the page is data-driven

## Run
```
python -m http.server 8000 -d public
```
- `http://localhost:8000/xray.html`: tries `GET /api/analyze` and falls back to `/data/sample.json` (the "Demo data" badge appears).
- `?data=large`: the synthetic 10-pocket book.
- `?data=sample`: forces the mock data.
- The header dropdown switches between sources.

## Features
- **Graph:** DPR-aware canvas force graph with drag, pan, wheel/pinch zoom, Fit, and double-click to unpin. It has hover tooltips for nodes and edges (an edge shows its `reason` and transmission). Colours are per layer; node size reflects expected-loss contribution and degree. High-risk nodes get halos, and position nodes are hexagons. **Force / Layers** toggle: Layers mode puts L5 lending at the top and L1 chain at the bottom, with rows ordered by barycentre.
- **Failure simulation:** click a node (or use the picker; Shift-click or "+ Add" fails several). The failure propagates dst→src, damped by `transmission`, at 650 ms per hop. Red pulsing edges carry particles, nodes ripple, and the hop timeline shows T+0..T+n. Positions show "−x% value" chips.
  - Client loss = value × loss_given_failure × best-path transmission, combined as `1-Π(1-h)`, the same as the backend.
  - Payload scenarios (keys 1–9) show the **server** `expected_loss_usd`/`verdict` as authoritative, with the client propagation as a check.
- **Decision panel:**
  - Animated STAY/EXIT badge, plus loss if STAY vs cost if EXIT vs margin, with bars.
  - A plain-English "why" built from the numbers, including the top risk driver's share.
  - The model `explanation`.
- **Break-even card:**
  - Chart of EL(p) = base + p·L against the exit side (execution + carry forgone, of the exposed positions), with a marker. It states "Exit if P > X%".
  - A P(incident) slider and an exit-cost (% slippage) slider; the exit slider overrides the cost client-side.
- **Book:** `book.pockets` table with stay / best-per-pocket / exit-all totals. Clicking a row focuses that pocket if it is a graph node.
- **Hidden concentration:** for each node, the number of positions that transitively depend on it and the % of book, with an "indirect" tag. Insights read like "P2 never touches Chainlink directly but depends on it via Aave (2 hops)". Clicking an item focuses the node and its dependents.
- **Node drawer:** p_fail, loss_given_failure, expected loss, max transmission, positions exposed, upstream/downstream lists, and all `meta`. It adds oracle quality chips (TWAP, single feed, deviation, heartbeat), address copy buttons and links.
- **Shortcuts:** R reset · Esc deselect · F fit · L toggle layout · 1–9 scenarios.
- **Other:** responsive (on mobile the graph is on top and the panel becomes a bottom sheet), honours `prefers-reduced-motion`, and has loading and error states.

## Payload change requests (backend, optional, all rendered if present)
1. `book.scenario`: name and failed node id of the stress used for the book (currently the page assumes `scenarios[0]`).
2. **Multi-pocket books as graph nodes:** one node per pocket with `meta.kind="position"`, `meta.value_usd`, `meta.exit_cost_usd`, plus edges from each pocket to its own dependencies. This lights up the concentration panel (see `data/sample-large.json`).
3. **Oracle meta:** `twap_window` / `twap_minutes`, `single_feed` (bool), `sources` (int), `deviation_threshold` (fraction), `heartbeat` (seconds), `provider`.
4. **Node meta:** `tvl_usd`, `address` / `addresses`, `url`, `chain`.
5. **Edge meta (optional):** `lag_hours` (or `delay_hours`), for a real "how fast" timeline instead of uniform hops.

## Known gaps
- In the client simulation, failure is assumed certain (a conditional loss). Probabilistic expected loss comes from the server (baseline and scenarios).
- Base expected loss in the break-even chart, when several pockets are involved, is pro-rated by exposed value (an approximation).
- Graphs with more than about 100 nodes have not been profiled (the O(n²) repulsion is fine up to roughly 150).

## Look-through / lineage (added 10 Oct evening)
- **Panel "What you really hold"** (reads `position.meta.lookthrough`, `.coverage` and `.shared_exposure`) shows:
  - the coverage bar (traced vs unknown) with the reasons;
  - the base assets;
  - the chain of tokens (PT → SY → underlying → …);
  - the tokens shared across the top Morpho PT markets.
  Clicking a name selects the node through `meta.token_id`. When the data is missing, it shows an empty-state sentence (mock / `?data=large`).
- **Inspector:**
  - a "Hidden dependency" tag and explanation (`meta.hidden`, `meta.depth`);
  - the share of the position (`meta.lookthrough_pct` and its routes);
  - "Why it is in the graph" (`meta.lineage[]`: parent, weight or "share unknown", via, confidence chip, source link, as_of);
  - a peg check (`meta.peg`: worst/today deviation, or "not enough data" with the reason).
- **Graph:** lineage/base-asset nodes get a dotted purple outer ring.
- **Data:** `data/sample.json` is now a saved run of the real pipeline (`source: "live"`), so the badge reads "Real data snapshot · date" instead of MOCK. `api.js` (dashboard, other owner) still labels the fallback as MOCK.
