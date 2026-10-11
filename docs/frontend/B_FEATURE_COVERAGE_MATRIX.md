# B. Backend-to-Frontend Feature Coverage Matrix

Legend — **Backend class:** ✅ implemented & working (verified live) · 🟡 implemented but constrained · 🔵 implemented,
not independently verified here · 🧪 demo / fork-only · ⛔ specification only / not implemented.
**UI status:** Integrated · Partial · **Contradicted** (the UI shows numbers the backend does not produce) · Missing.

## B1. Summary

| # | Capability | Backend | UI status | Priority for redesign |
|---|---|---|---|---|
| 1 | Dependency discovery (5 Belem layers + hidden nodes) | ✅ 🟡 | Integrated (X-Ray graph) | P0 hero of the app |
| 2 | Token look-through, coverage, peg | ✅ | Partial (X-Ray card + tooltips) | P1 |
| 3 | Oracle feeds & feed quality | ✅ | Partial (node drawer) | P1 (Belem "layer 3 incident") |
| 4 | **Role-aware loss channels** (principal / debt / exit) | ✅ | **Contradicted** (client ignores `channel`) | **P0 fix** |
| 5 | Expected loss, bands, VaR95 | ✅ | Partial (numbers, no band visual) | P0 |
| 6 | Robust verdict STAY/EXIT/REVIEW, lean, break-even, reasons | ✅ | Partial (700-char text blob) | P0 |
| 7 | Executable exit quote + carry + decomposition | ✅ | Partial (KPI + tooltip) | P0 |
| 8 | Predefined scenarios (4, conditional) | ✅ | Integrated (channel notes missing) | P0 |
| 9 | **Incident path** `shock=&severity=` (position + book) | ✅ | **Missing** (X-Ray recomputes client-side) | **P0** |
| 10 | Stress table (each dependency alone) | ✅ | Missing | P1 |
| 11 | Sensitivity (p, LGF, transmission) | ✅ | Missing on analyze (vault has its own) | P1 |
| 12 | **Hold to maturity** | ✅ | **Missing** | **P0** (jury: "is there better than exiting?") |
| 13 | Real book: pockets, shared dependencies, 11 % exit cost, book shock | ✅ 🟡 | Partial (table only; negative exit costs shown as EXIT) | P0 |
| 14 | Borrower mode: HF, liquidation grid, expected borrower loss, drift | ✅ 🟡 | Partial (one text line) | P1 (Breaking Point view) |
| 15 | Countermove policy suggestion (signal → action) | ✅ | Missing | P1 |
| 16 | Assumptions & parameter inventory | ✅ | Partial (static methodology text) | P1 (evidence layer) |
| 17 | Provenance & freshness | ✅ | Partial (badge; ages and blockers not shown) | P0 (status system) |
| 18 | Vault analyzer (Morpho V1/V2) | ✅ 🟡 | Integrated (form-first, jargon) | P1 |
| 19 | Countermove recorded fork run S1–S5 | 🧪 | Integrated | P0 (PROVE) |
| 20 | Countermove LIVE dependency reads | ✅ | Integrated (button) | P2 |
| 21 | Policy draft (setPolicy calldata) | 🟡 | Integrated, **misleading copy** | P1 (ARM preview) |
| 22 | Countermove mainnet dry run | ✅ | Missing | P0 (real data for DEFEND) |
| 23 | Keeper process + RescueVault contract | 🧪 | Partial (keeper runs table) | P2 (evidence) |
| 24 | Evidence bundles (tests, Slither, GO criteria) | ✅ | Missing | P2 |
| 25 | Mock graph `ref=mock` | ✅ | Not used (static sample files instead) | Replace fallbacks |
| 26 | Breaking Point engine, Exit Runway endpoint, Whale Impact, Reaction Window, Chain of Blame, Leverage Hunter, Cascade Radar, Telegram, Portfolio Dependency (wallet) | ⛔ | Not on main (historical "Coming soon") | Do not show as features |

## B2. Per-capability detail

Each entry: **Purpose · Backend · Contract · In → Out · Network/auth · Limits · Current UI · Status · Missing interactions ·
Target UX · Proof test.**

### 1. Dependency discovery
- **Purpose:** show everything a position silently depends on (Belem: 30 %).
- **Backend:** `data/discovery.py::discover_real`, `data/sources.py`.
- **Contract:** `GET /api/analyze?ref=auto|pendle:1:<market>` → `nodes[]` (`id, layer, label, p_fail, loss_given_failure,
  meta{role, hidden, depth, source, lgf_source, expiry, implied_apy, feeds…}`), `edges[]` (`src, dst, transmission,
  reason, channel`).
- **Network:** public APIs + RPC; no auth. **Limits:** Ethereum; PT-on-Morpho positions only; 20–36 s.
- **Current UI:** `xray.html` canvas force/layer graph; dashboard 5-layer static explainer. **Status:** Integrated.
- **Missing:** layer-strata layout as default, list/table twin of the graph, search, keyboard traversal, "why is this a
  dependency" sentence per edge, hidden-node reveal moment.
- **Target UX:** the graph is the analytical hero — five horizontal strata (chain → lending), the position on top,
  hidden nodes revealed with their path; a synchronized table (Arkham-style list view).
- **Proof:** Playwright: live load shows 12 nodes / 19 edges and the five layer labels; table rows = graph nodes.

### 2. Look-through, coverage, peg
- **Backend:** `data/lineage.py`, `exposure.py`, `peg.py` → `position.meta.lookthrough|coverage|shared_exposure`,
  node `meta.lineage|peg|lookthrough_pct`.
- **Current UI:** X-Ray "What you really hold" card, node tooltip, peg block. **Status:** Partial.
- **Missing:** unknown-share visualisation (the honest `UNKNOWN` remainder), data date. **Target:** a stacked bar
  "what $1 of this PT is made of", unknown shown as hatched, peg sparkline. **Proof:** shares sum to 100 % incl. unknown.

### 3. Oracle feeds & feed quality
- **Backend:** `discovery._feed_quality` (every feed read on-chain: description, provider, answer, age; single feed,
  computed-on-read, unreadable, deviation vs Pendle → multipliers).
- **Current UI:** node drawer fields (`single_feed`, sources). **Status:** Partial.
- **Target:** an oracle "instrument card" (feeds, providers, age, staleness guard, deviation) — this is Belem's
  layer-3 incident. **Proof:** card lists every feed address returned by the payload.

### 4. Role-aware loss channels — **P0 correctness**
- **Backend:** `core/models.py` (`CHANNELS`, `edge_weight`), `propagation.blocked_channels`; payload `edges[].channel`,
  `stress_table[].channel`, `scenarios[].channel_notes`, `custom_shock.channel`, `uncertainty.edges[].reaches_position`.
- **Current UI:** `xray/data.js:79` keeps `e.transmission` and drops `channel`; `xray/model.js::positionLosses`
  recomputes conditional losses client-side. **Status: Contradicted** — failing the oracle shows EXIT $154k, the AMM or
  the Morpho market EXIT $192k, while the backend returns $761 / STAY with "no effect without debt" (screens 05–07).
- **Target UX:** dollar figures only from the server (`stress_table` rows, `shock=` calls); the client animates hop
  order only; blocked edges drawn dashed with a "only matters with debt / only affects exit cost" label.
- **Proof:** for every node, the UI loss equals `stress_table[id].conditional_loss_usd` (±$1); oracle shows "no effect
  without debt".

### 5–7. Expected loss, verdict, exit cost
- **Backend:** `propagation.simulate`, `uncertainty.loss_band|exit_band|carry|robust_signal`, `decision.decide_robust`,
  `quote_exit`, `freshness.evaluate` → `decision.{verdict, point_verdict, confidence, lean, reasons,
  breakeven_risk_multiplier, loss_band, exit_band, carry, freshness, exit_total_usd, margin_usd}`, `exit.decomposition`.
- **Current UI:** dashboard verdict + 488–700-char `explanation` paragraph; X-Ray decision card (good structure).
  **Status:** Partial.
- **Missing:** one-sentence headline; band visual (stay band vs exit band overlap = why REVIEW); exit decomposition
  (fee / price impact / off-peg / gas); quote age ticking; "what would flip it" (×6.81).
- **Target UX:** a verdict block that reads in 3 seconds: "REVIEW — lean STAY. Staying risks $761 (≤ $19.7k); exiting
  costs $5.2k now. Exit only pays if risk is ×6.8 higher." Two horizontal bands on one scale; details behind disclosure.
- **Proof:** rendered numbers equal payload fields; REVIEW is never coloured as STAY/EXIT; band overlap drawn.

### 8. Predefined scenarios
- **Backend:** `core/scenarios.py` (underlying depeg 30 %, oracle failure, liquidity crisis with liquidity ×0.5,
  correlated) → `scenarios[]` incl. `channel_notes`, stressed `exit`. **Status:** Integrated (dashboard table, X-Ray
  buttons). **Missing:** channel explanations, "hypothesis" badge on severities, link to the graph cascade.
- **Proof:** "Oracle failure" row shows $761 + "only matters with debt".

### 9. Incident path (custom shock) — **P0**
- **Backend:** `scenarios.shock`, `api_payload._incident`; `GET /api/analyze?shock=<node>&severity=<0-1>` →
  `custom_shock` + `incident{headline, position, book{pockets_hit, pockets_to_exit, book_loss…}, hold_to_maturity}`.
- **Current UI:** none (X-Ray severity is fixed to node LGF and computed client-side). **Status:** Missing.
- **Target UX:** select a dependency → severity slider (debounced) → server recompute (~20 s; show staged progress) →
  one headline for position and book. Cache results per (node, severity).
- **Proof:** issuer at 50 % shows "$360k vs $5.5k → EXIT; 2 pockets hit, exit 2".

### 10–11. Stress table, sensitivity
- **Backend:** `_stress_table` (each dependency failing alone, path, hops, channel), `_sensitivity` (p ×0.5/×2/×upper,
  LGF low/high, transmission ×0.75/×1.25). **Status:** Missing on analyze.
- **Target UX:** "Which single failure hurts most" ranked bars with assumption badges (Ethereum and US-dollar base asset
  rows are assumption-driven); a tornado showing the verdict is stable across parameter families.
- **Proof:** every sensitivity row verdict rendered; assumption badges present on chain/base-asset rows.

### 12. Hold to maturity — **P0**
- **Backend:** `core/maturity.py` → `maturity{status, days_to_maturity, best_over_window, confidence, options[EXIT,
  HOLD_TO_MATURITY, STAY], rule}`; `not_applicable` for borrowers or non-PTs.
- **Current UI:** none. **Status:** Missing.
- **Target UX:** a three-way decision strip over the same window ("now → 10 Dec, 60 days"): EXIT $9.2k · HOLD $1.5k ·
  (STAY 30 d shown separately). Answers the jury's "is there better than exiting?".
- **Proof:** three options with bands; HOLD flagged "low confidence"; hidden for borrower mode with the backend reason.

### 13. Real book
- **Backend:** `core/book.py` → `book{mode: real_book, pockets[10], shared_dependencies[], shock, exit_cost_override_pct,
  total_stay_loss_usd, total_optimal_usd, pct_of_book}`; params `exit_cost_pct, book_shock, book_severity, weights`.
- **Current UI:** pockets table on dashboard and X-Ray. **Status:** Partial; **negative exit costs (−$584…−$1,095) are
  displayed with EXIT badges for pockets the shock does not touch** (`index.html:196`), see C3.
- **Missing:** the brief's 11 % toggle, shared-dependency table ("Ethereum and Morpho Blue: 10/10 pockets"), book shock
  selector, weights.
- **Target UX:** "Belem book example" panel: 10 pockets × 10 %, choose the hit dependency, toggle "11 % exit cost (brief)"
  vs "quoted"; hit pockets highlighted; rebalancing effects (negative carry) shown separately from risk exits.
- **Proof:** `exit_cost_pct=0.11` → 2 EXIT, 8 STAY, 2.52 % of book.

### 14–15. Borrower mode and Countermove suggestion
- **Backend:** `leverage.analyze`, `morpho.borrower_state`, `liquidation_outcome`, `countermove_suggestion` →
  `liquidation{health_factor, ltv, lltv, distance_to_liquidation_pct, liquidation_oracle_price, price_grid[],
  scenarios[], expected, drift, decision, countermove_suggestion{policy_draft_url, reserve_to_deposit,
  reserve_per_first_hit}, historical_check}`.
- **Current UI:** one line in the dashboard signal ("Borrower 0x… HF 1.054"). **Status:** Partial.
- **Target UX:** "Breaking Point" instrument: HF curve vs oracle drop from `price_grid` (no client maths), first
  liquidation at −4.5 %, then "Arm a defense" CTA pre-filled from `countermove_suggestion`.
- **Proof:** curve points equal `price_grid`; CTA opens policy draft with the suggested query unchanged.

### 16–17. Assumptions, uncertainty inventory, provenance, freshness
- **Backend:** `assumptions[]`, `uncertainty{nodes[p_fail_horizon, loss_given_failure classes], edges[]}`,
  `provenance{live, cached, mode}`, `data_as_of`, `decision.freshness{items[], blockers[], label}`.
- **Current UI:** source badge; methodology `<details>`; freshness label in a text line. **Status:** Partial.
- **Target UX:** a persistent evidence bar: status chip (LIVE / CACHED / MIXED / SAVED SNAPSHOT / DEMO / SIMULATED /
  UNAVAILABLE), block, "as of 42 s ago" ticking, quote TTL countdown (60 s) → "re-run before acting"; every number has a
  provenance popover (observed / calibrated / assumption).
- **Proof:** chip text (not colour only) in an `aria-live` region; turns STALE after 60 s without re-fetch.

### 18. Vault analyzer
- **Backend:** `vault_*` → `/api/vault` (see A5). ✅ live; 🟡 Ethereum, Morpho V1/V2 only, severity priors, oracle nodes
  labelled by address, storage-override simulations may be `unavailable` on unsupported layouts.
- **Current UI:** `vault.html` — most complete integration; deep links; custom shock; sensitivity; crash curve.
- **Missing:** result-first layout (form collapses after run), plain-language exit routes ("$411k now through ordinary
  withdrawal; full $1M only via forceDeallocate, shared liquidity"), allocation treemap, FX vs peg explanation, oracle
  names, Dune/Belem example list (sponsor's table), mobile length (11,568 px).
- **Proof:** Belem example renders verdict + exit routes; error 422 shows inline with suggestion.

### 19–23. Countermove
- **Recorded run (🧪):** `/api/countermove` → S1–S5 with before/shock/timeline/decision/validation/execution/
  protections. UI integrated and honest (SIMULATED). Missing: ARM → DEFEND → PROVE narrative, S5 first (Belem's PT
  example), replayable timeline, tx receipts linked to verification checks.
- **LIVE reads (✅):** `?live=1` — integrated as a button.
- **Policy draft (🟡):** validated `setPolicy` calldata. UI copy "Sign this setPolicy call, sent to your RescueVault"
  implies an actionable signature although no vault exists outside a local fork. Target: "Policy preview — calldata
  for a RescueVault (local fork demo; no mainnet deployment)".
- **Dry run (✅, Missing in UI):** real borrower, LIVE + DRY-RUN; the strongest real-data proof for DEFEND.
  Target: "What would the keeper do right now?" panel with market selector and rank.
- **Keeper + contract (🧪):** chain-31337 signer, 29 forge tests, Slither report, not audited.
- **Proof:** S5 tab default shows 1,447.44 USDC repay, 15/15 checks, "no user signature"; dry run shows LIVE block and
  no transaction field.

### 24–25. Evidence bundles, mock
- `audit/BELEM_PHASE1_EVIDENCE.json`, `audit/FAULTLINE_PHASE2_EVIDENCE.json` (16/16 GO), `audit/*SLITHER.txt` — not
  surfaced. Target: a compact "Proof" drawer (tests, GO criteria, last run, links).
- `ref=mock` exists but the UI uses static `public/data/sample*.json` (pre-role-aware) instead — replace (see C2).

### 26. Specification-only modules (⛔)
`docs/features/*`: Breaking Point (dedicated engine), Exit Feasibility / Exit Runway (`/exit-cost/{id}` does not exist),
Whale Impact, Reaction Window, Chain of Blame (jury: "remove"), Leverage Hunter, Cascade Radar, Telegram Ping (C5 not
done), Portfolio Dependency (wallet → positions). `git grep` finds no implementation. Do not render them as features;
if mentioned at all, one "Roadmap" line.
