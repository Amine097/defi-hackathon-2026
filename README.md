# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
Start with the [documentation index](docs/README.md) for the core, feature specifications and Belem brief. `PLAN.md` retains the earlier project plan.

## UI direction: Pendle X-Ray node graph (hosted on Vercel)
The main view is an interactive node graph (nodes = chain, yield source, oracle, PT market/AMM, lending, position pockets).
Click a node to simulate its failure and watch it propagate; the side panel shows STAY vs EXIT.
- `public/index.html` (dashboard) and `public/xray.html` (node graph): fed by `/api/analyze`; a badge shows whether numbers are live, replayed from cache, or MOCK
- `api/analyze.py`: Python serverless function returning the model output as JSON
- `public/vault.html` (Vault analyzer): enter any Ethereum Morpho vault address (V1/V2) and an amount; fed by `/api/vault` (`api/vault.py`)
- `docs/core/dependency-graph/mockup.html`: untouched copy of the original prototype

## Demo: Belem vault risk (Phase 1)
1. `python scripts/dev_server.py 8000`, open http://localhost:8000/vault.html
2. Click **Use the Belem vault example** (fills `0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec`), set the amount (USD, hypothetical) and horizon, click **Analyze vault** (live on-chain, ~10-20 s).
3. Read the verdict card (STAY / EXIT / REVIEW, lean, margin = expected loss − (execution + carry)), then allocations, the dependency graph, withdrawal capacity (partial exit above ~$405k), scenarios and sensitivity.
4. Pick a dependency in **Custom shock: dependency**, set a severity and click **Run custom shock** to re-run the analysis under that failure.
5. Deep link: `/vault.html?address=0x…&value_usd=1000000&horizon_days=90`. API: `/api/vault?address=0x…&value_usd=100000&horizon_days=30[&shock=<node id>&severity=0.6]`.
6. Offline, deterministic replay of the dated vault fixtures (`data/fixtures/vault_*.json`, payloads labelled `replay`): `$env:PYTHONPATH='src'; python -m pytest tests/test_vault.py`. Live cross-checks: add `$env:DEFIRISK_LIVE_TESTS='1'`; evidence: `python scripts/collect_vault_evidence.py`.

## Local UI test
Never open `public/index.html` with `file://` (root-relative `/assets/...` and `/api/analyze`). Use
`python scripts/dev_server.py 8000` (UI + API) or `python -m http.server 8000 -d public` (UI only, falls back to the saved real snapshot).
Useful URLs: `/` (Overview), `/xray.html`, `/xray.html?data=large` (synthetic book), `/?runway=demo` (labelled Exit Runway rehearsal fixture), `/?borrower=auto` (live Breaking Point).

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
- `src/defirisk/core/`: shared graph models, failure propagation, scenarios, exit decisions, and portfolio evaluation.
- `src/defirisk/data/`: live discovery, token lineage and exposure, failure priors, price checks, HTTP clients, and cache.
- `src/defirisk/cli.py`: command-line entry point; `api_payload.py` builds JSON for the web UI.
- `src/defirisk/*.py`: compatibility imports for existing callers; new code should import from `core` or `data`.
- `api/analyze.py`: Vercel function exposing `/api/analyze`.
- `data/mock_graph.json`: offline fixture.
