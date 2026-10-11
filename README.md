# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
Start with the [documentation index](docs/README.md) for the core, feature specifications and Belem brief. `PLAN.md` retains the earlier project plan.

## UI: Claude Design v2 (hosted on Vercel)
The frontend renders the approved Claude Design v2 export (`docs/design/claude-design-v2/`) on its own runtime, wired to the real backend. See [docs/frontend/README.md](docs/frontend/README.md).
- `/` (`public/index.html`): landing. Its recorded figures come from `public/data/recorded/analyze-pt.json` and the recorded fork run, checked at build time.
- `/app.html`: select a position (demonstration positions = recorded live runs, labelled RECORDED LIVE RUN; or paste a Morpho market id / vault address for a LIVE run), then Dashboard, Positions & Vaults, Dependency X-Ray (inspect, simulate attack, replay S1/S5), Countermove (policy preview validated by `/api/countermove`, live dry run for real borrowers, fork demonstration) and Activity & Evidence.
- APIs: `api/analyze.py` (`ref=auto|pendle:1:<market>|morpho:1:<market id>`, `lookup=1`), `api/vault.py` (`address=`, `lookup=1`), `api/countermove.py`.
- Build: `node tools/frontend/dc-build.mjs`; recordings: `python scripts/record_demo_payloads.py`; QA: `node tools/frontend/dc-qa.mjs`.
- Earlier pages (`/analyze.html`, `/vault.html`, `/countermove.html`) remain reachable by URL but are no longer linked; the design gaps they cover are listed in `docs/frontend/DESIGN_COVERAGE_GAPS.md`.

## Demo: Belem vault risk (Phase 1)
1. `python scripts/dev_server.py 8000`, open http://localhost:8000/vault.html
2. Click **Use the Belem vault example** (fills `0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec`), set the amount (USD, hypothetical) and horizon, click **Analyze vault** (live on-chain, ~10-20 s).
3. Read the verdict card (STAY / EXIT / REVIEW, lean, margin = expected loss − (execution + carry)), then allocations, the dependency graph, withdrawal capacity (ordinary route ≈ $405k for Belem; larger exits through the simulated `forceDeallocate` route, e.g. $1M fully withdrawable), scenarios and sensitivity.
4. Pick a dependency in **Custom shock: dependency**, set a severity and click **Run custom shock** to re-run the analysis under that failure.
5. Deep link: `/vault.html?address=0x…&value_usd=1000000&horizon_days=90`. API: `/api/vault?address=0x…&value_usd=100000&horizon_days=30[&shock=<node id>&severity=0.6]`.
6. Offline, deterministic replay of the dated vault fixtures (`data/fixtures/vault_*.json`, payloads labelled `replay`): `$env:PYTHONPATH='src'; python -m pytest tests/test_vault.py`. Live cross-checks: add `$env:DEFIRISK_LIVE_TESTS='1'`; evidence: `python scripts/collect_vault_evidence.py`.

## Demo: Autonomous Countermove (Phase 2, local fork)
A Morpho Blue borrower pre-authorizes a narrowly permissioned **RescueVault** (`contracts/`); a keeper process
(`python -m defirisk.countermove`) detects a crisis, picks the cheapest safe defense and executes it without any user
signature: AUTO-REPAY, AUTO-TOP-UP, NO ACTION or EMERGENCY FULL REPAY. The recorded run has five scenarios (S1–S5);
S5 is the Belem brief's own example: a Pendle PT (PT-reUSD) used as collateral, incident on the oracle pricing the PT.
The keeper signs from an encrypted keystore (no key on any command line). Local Anvil fork only: no mainnet transaction,
no real funds, no personal key; the contract is **not audited**.
1. `python scripts/dev_server.py 8000`, open http://localhost:8000/countermove.html (recorded fork run; LIVE button = read-only mainnet oracle reads).
2. Reproduce (Foundry 1.8.5): `contracts\install_deps.ps1`, `forge build` in `contracts/`, then `python scripts/countermove_fork_demo.py` (expects `all expected outcomes: True` for S1–S5).
3. Docs: [implementation report](docs/FAULTLINE_PHASE2_IMPLEMENTATION_REPORT.md) · [security report](docs/FAULTLINE_PHASE2_SECURITY_REPORT.md) · [demo guide](docs/FAULTLINE_PHASE2_DEMO_GUIDE.md) · [progress](docs/FAULTLINE_PHASE2_PROGRESS.md) · evidence `audit/FAULTLINE_PHASE2_EVIDENCE.json` (`python scripts/collect_phase2_evidence.py --live --fork`).

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
- `src/defirisk/countermove/`: Phase 2 keeper (watcher, dependency engine, countermove engine, guarded executor, verifier, journal); `api/countermove.py` exposes `/api/countermove`.
- `contracts/`: Foundry project — `RescueVault.sol`, test-only simulation contracts (`src/sim/`), unit / fuzz / invariant / fork tests; dependencies pinned by `install_deps.ps1`.
- `data/mock_graph.json`: offline fixture.
