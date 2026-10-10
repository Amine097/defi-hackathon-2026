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
4. Demo (15%): Streamlit page hosting the Pendle X-Ray node graph (see Visual direction) + verdict.

## Team (4)
- A: data/discovery (Pendle, DefiLlama, RPC)
- B: graph + propagation model
- C: Monte Carlo + exit-cost/decision logic
- D: Streamlit UI + node graph (port docs/mockups/pendle-xray-node-graph.html to real data), README, pitch deck/video

## Timeline (deadline tomorrow 11:00)
- Now-+2h: pick position, agree on JSON graph schema (nodes, edges, tvl, p_fail, loss).
- +2h-+10h: A/B/C build in parallel against mocked JSON, D builds UI.
- Sleep.
- Morning: integrate, run on real data, polish, record demo by 09:30, submit by 10:30.

## Setup
python -m venv .venv; .venv\Scripts\activate; pip install networkx numpy pandas requests streamlit web3 pyvis

## Stretch (only if core runs on real data; target: tomorrow morning)
Whale alert assistant (owner: D or A, ~2-3h):
- Poll large transfers/swaps on the Pendle market + underlying token (RPC eth_getLogs or Etherscan).
- Flag if > $500k or > 2% of pool liquidity.
- Feed into the model: bump node p_fail / shrink pool liquidity, re-run decide(), notify (Telegram/Discord webhook) with new verdict.
- Demo safety: replay a real historical whale event (block range) instead of waiting for a live one.
- Out of scope: whale labelling (Nansen/Arkham), multi-chain indexing, user accounts.

## Visual direction: "Pendle X-Ray" NODE GRAPH (DECIDED)
Main UI = interactive force-directed node graph (dark theme, nodes colored by layer L1-L5 + position pockets).
Reference prototype: docs/mockups/pendle-xray-node-graph.html (open in a browser; mock data, vanilla JS).
- Nodes: chain, yield sources/issuers, oracles, PT markets (AMM), lending venues, position pockets.
- Edges: "depends on", with a transmission factor.
- Click a node (or scenario button) = it fails; failure spreads to dependents with delay, edges pulse red.
- Side panel: loss if STAY vs cost if EXIT (11% unwind in the brief's example), per-pocket + overall verdict, hidden-concentration list (indirect deps).
Implementation: Streamlit page embeds the graph via components.html, fed with JSON from the Python model
(src/defirisk/viz.py: replace pyvis with this prototype, injecting DepGraph JSON + simulate() results).
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
