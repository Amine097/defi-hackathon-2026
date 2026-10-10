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
4. Demo (15%): Streamlit page (graph, scenario sliders, verdict).

## Team (4)
- A: data/discovery (Pendle, DefiLlama, RPC)
- B: graph + propagation model
- C: Monte Carlo + exit-cost/decision logic
- D: Streamlit UI, README, pitch deck/video

## Timeline (deadline tomorrow 11:00)
- Now-+2h: pick position, agree on JSON graph schema (nodes, edges, tvl, p_fail, loss).
- +2h-+10h: A/B/C build in parallel against mocked JSON, D builds UI.
- Sleep.
- Morning: integrate, run on real data, polish, record demo by 09:30, submit by 10:30.

## Setup
python -m venv .venv; .venv\Scripts\activate; pip install networkx numpy pandas requests streamlit web3 pyvis
