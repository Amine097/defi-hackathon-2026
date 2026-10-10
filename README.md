# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
See `PLAN.md` and `docs/belem.md`.

## UI direction: Pendle X-Ray node graph (hosted on Vercel)
The main view is an interactive node graph (nodes = chain, yield source, oracle, PT market/AMM, lending, position pockets).
Click a node to simulate its failure and watch it propagate; the side panel shows STAY vs EXIT.
- `public/index.html`: the web UI (currently the prototype with mock data inline; to be wired to `/api/analyze`)
- `api/analyze.py`: Python serverless function returning the model output as JSON
- `docs/mockups/pendle-xray-node-graph.html`: untouched copy of the original prototype

## Setup
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt
    copy .env.example .env

## Run
    python -m pytest
    cd src; python -m defirisk.cli     # CLI verdict
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
- `discovery.py` real-data discovery (A) - currently mock
- `propagation.py` graph + Monte Carlo (B/C)
- `decision.py` exit cost + verdict (C)
- `portfolio.py` book of pockets, one hit, stay vs exit
- `scenarios.py` stress overrides; `http.py` cached API calls
- `api_payload.py` builds the JSON the web UI consumes
- `data/mock_graph.json` fixture so everyone can work in parallel
