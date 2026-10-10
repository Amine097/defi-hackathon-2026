# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
See `PLAN.md` and `docs/belem.md`.

## UI direction: Pendle X-Ray node graph (hosted on Vercel)
The main view is an interactive node graph (nodes = chain, yield source, oracle, PT market/AMM, lending, position pockets).
Click a node to simulate its failure and watch it propagate; the side panel shows STAY vs EXIT.
- `public/index.html` (dashboard) and `public/xray.html` (node graph): fed by `/api/analyze`; a badge shows whether numbers are live, replayed from cache, or MOCK
- `api/analyze.py`: Python serverless function returning the model output as JSON
- `docs/mockups/pendle-xray-node-graph.html`: untouched copy of the original prototype

## Setup
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt
    copy .env.example .env

## Run
    python -m pytest
    $env:PYTHONPATH='src'; python -m defirisk.cli auto 1000000   # live discovery + verdict for a $1M position
    python -m defirisk.cli mock                                  # offline MOCK graph (not real data)
    python scripts/dev_server.py 8000  # web UI + API locally without the Vercel CLI
    $env:DEFIRISK_LIVE_TESTS='1'; python -m pytest   # adds on-chain cross-checks against the real APIs
    vercel dev                         # web UI + API locally (npm i -g vercel)
    vercel                             # deploy

## Deploying on Vercel (from the git repo)
1. Import the GitHub repo in Vercel; no framework preset, no build command, leave root directory as `/`.
2. `public/` is served as the site; `api/analyze.py` becomes `/api/analyze` (deps from `requirements.txt`).
3. Env vars go in Project Settings (`.env` is gitignored): `ETH_RPC_URL`, `ETHERSCAN_API_KEY`, `DEFIRISK_OFFLINE=1` for the demo.
4. Commit `data/cache/` (pre-warmed responses) so the deployed API works without live calls.
5. Vercel's filesystem is read-only: the cache is read there, never written.

## Layout
- `src/defirisk/models.py` shared schema (Position, Node, Edge, DepGraph)
- `discovery.py` real-data discovery: Pendle API, Morpho GraphQL, DefiLlama, Ethereum RPC (`mock` ref = demo fixture)
- `propagation.py` graph + Monte Carlo (B/C)
- `decision.py` exit cost (executable Pendle SDK quote + gas; flagged x*y=k fallback) + verdict
- `portfolio.py` book of pockets, one hit, stay vs exit
- `scenarios.py` stress overrides; `http.py` cached API calls
- `api_payload.py` builds the JSON the web UI consumes (`/api/analyze?ref=auto&value_usd=1000000&shock=<node>&severity=0.3`)
- `data/mock_graph.json` fixture so everyone can work in parallel
