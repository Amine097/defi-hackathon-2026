# Plan: Belem Capital track (DeFi Risk Dependency)

## Why Belem (not Swissquote)
- Pure software; real data from free public APIs (DefiLlama, Pendle API, RPC) - no wallet infra, bundler, passkeys, legal docs.
- Splits cleanly across 4 people; every piece demoable on its own.
- Swissquote needs create+sign+recover+testnet tx+legal+business case; many moving parts for a first hack.

## Demo target
One position: Pendle PT (e.g. PT-sUSDe) used as collateral on Morpho/Aave.
Output: dependency graph -> failure scenarios -> expected loss vs exit cost -> STAY/EXIT.

## Pipeline
1. Discovery (30%): Pendle API (market -> SY -> underlying yield source), oracle (Chainlink/Pendle oracle) via on-chain reads, lending market (Morpho/Aave), chain. Build with networkx.
2. Impact (30%): per-node failure probability x loss-given-failure (depeg, oracle failure, exploit, liquidity crunch); propagate along edges; Monte Carlo (numpy).
3. Decision (25%): exit cost = AMM slippage + gas; EXIT if expected loss (horizon) > exit cost. Show assumptions + sensitivity.
4. Demo (15%): Vercel-hosted web app: static `public/index.html` (X-Ray node graph) + Python serverless API `api/analyze.py` (reuses src/defirisk). Streamlit dropped.

## Status (updated 10 Oct ~14:00; deadline Sun 11 Oct 11:00)

### Done
- Python core `src/defirisk/`: models, propagation (Monte Carlo), decision (stay/exit), scenarios, portfolio (10 pockets), http cache.
- Backend API `api/analyze.py` + `api_payload.py` (payload contract), Vercel config, tests (4 passing).
- Frontend (pushed): FaultLine dashboard (`public/index.html`) + X-Ray node graph (`public/xray.html`): cascade animation,
  decision panel, break-even sliders, hidden concentration, large-graph mode. Falls back to `public/data/sample*.json`.
- Name FaultLine, brand logo, README/Vercel deploy steps, Belem brief insights.

### Remaining (priority order, graded by Belem criteria)
1. **Real discovery (30%)** - `discovery.py` real mode raises NotImplementedError. For ONE real PT position: Pendle API (market -> SY -> underlying),
   oracle address/type, Morpho/Aave market, chain. Owner: A. BLOCKER for the real-data demo (15%).
2. **Defensible numbers (30%)** - replace placeholder p_fail / loss_given_failure in `data/mock_graph.json` with sourced values
   (past incidents, audits, TVL); show source in UI. Owner: B/C.
3. **Real exit cost (25%)** - quote from Pendle AMM/swap instead of the constant-product approximation; stressed exit cost. Owner: C.
4. Wire UI to live `/api/analyze`; pre-warm and commit `data/cache/`; set `DEFIRISK_OFFLINE=1` on Vercel for the demo. Owner: D.
5. Backend payload extras requested by the UI (public/NOTES-xray.md): per-pocket nodes, oracle meta (twap, single feed, heartbeat), edge `lag_hours`, node tvl/address.
6. Oracle feed-quality analysis and "how fast" timeline using real delays.
7. Book mentor office hours (contact@belemcapital.com) to challenge assumptions.
8. Submission: README update, 2-min demo video by 09:30, submit by 10:30.

### Optional (only if 1-4 are done): exit-cost / liquidity-stress module
Spec reviewed (whale-watcher-spec.md); build a trimmed version: market snapshot + exit curve, exit-queue scenario, forced sellers under a shock
-> `exit_cost_stressed` feeding `decide()`; then validation on a few real past swaps. Skip live watcher, Telegram, replay, exit plan.
## Team (4)
- A: data/discovery (Pendle, DefiLlama, RPC)
- B: graph + propagation model
- C: Monte Carlo + exit-cost/decision logic
- D: Web UI on Vercel (public/index.html: port the node graph to fetch /api/analyze), README, pitch deck/video

## Timeline (deadline tomorrow 11:00)
- Now-+2h: pick position, agree on JSON graph schema (nodes, edges, tvl, p_fail, loss).
- +2h-+10h: A/B/C build in parallel against mocked JSON, D builds UI.
- Sleep.
- Morning: integrate, run on real data, polish, record demo by 09:30, submit by 10:30.

## Setup
python -m venv .venv; .venv\Scripts\activate; pip install -r requirements-dev.txt

Deploy: `npm i -g vercel; vercel` (static `public/` + Python function `api/analyze.py`). Local: `vercel dev`.

## Stretch (superseded by the optional module above; only if core runs on real data; target: tomorrow morning)
Whale alert assistant (owner: D or A, ~2-3h):
- Poll large transfers/swaps on the Pendle market + underlying token (RPC eth_getLogs or Etherscan).
- Flag if > $500k or > 2% of pool liquidity.
- Feed into the model: bump node p_fail / shrink pool liquidity, re-run decide(), notify (Telegram/Discord webhook) with new verdict.
- Demo safety: replay a real historical whale event (block range) instead of waiting for a live one.
- Out of scope: whale labelling (Nansen/Arkham), multi-chain indexing, user accounts.

## Visual direction: "Pendle X-Ray" NODE GRAPH (DECIDED)
Main UI = interactive force-directed node graph (dark theme, nodes colored by layer L1-L5 + position pockets).
Implemented in public/xray.html. Original prototype kept in docs/core/dependency-graph/mockup.html.
- Nodes: chain, yield sources/issuers, oracles, PT markets (AMM), lending venues, position pockets.
- Edges: "depends on", with a transmission factor.
- Click a node (or scenario button) = it fails; failure spreads to dependents with delay, edges pulse red.
- Side panel: loss if STAY vs cost if EXIT (11% unwind in the brief's example), per-pocket + overall verdict, hidden-concentration list (indirect deps).
Implementation: Vercel. `public/index.html` is the prototype (mock data inline); next step is to replace its hardcoded N/E/POS
arrays with the JSON from `GET /api/analyze` (src/defirisk/api_payload.py). May later migrate to Next.js if desired.
Secondary (only if time): break-even chart (loss vs P(incident)), cascade timeline.
Dropped: stack/tower diagram and Sankey.

## Demo safety
All API/RPC calls go through src/defirisk/http.py (get_json/post_json): disk cache in data/cache + automatic fallback if the API is down. Before the demo: run the app once online, COMMIT data/cache, and set DEFIRISK_OFFLINE=1 to guarantee no live calls on stage.

## Brief insights (from official PDF)
- Layers are fixed: 1 chain, 2 yield source + ISSUER, 3 oracle, 4 PT market + AMM CURVE, 5 lending collateral. Keep our 5 layers aligned.
- Their decision example: book of 10 pockets x 10%, one hit, unwind costs 11% slippage -> exit = expensive+certain, stay = cheap+uncertain. Show this trade-off explicitly (portfolio-level, not only one position).
- "How fast" matters -> cascade timeline.
- Extras they value: oracle feed-quality analysis, vaults routing to perp venues, TVL concentration.
- Belem offers mentor office hours to challenge assumptions: USE THEM. contact@belemcapital.com
