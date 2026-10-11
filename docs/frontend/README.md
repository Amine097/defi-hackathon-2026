# FAULTLINE — Frontend Discovery Audit (11 Oct 2026)

This folder holds the discovery and setup audit that precedes the frontend redesign. Nothing in production code was
changed; no commit, deployment, paid generation or transaction was made.

**Audited state:** `main` @ `834a99b` (clean working tree). `origin/main` @ `5f2a859` is the same tree plus an empty
"Trigger Vercel deployment" commit. Production: https://faultline-sandy-three.vercel.app (verified identical behaviour).

## Reading order

| # | Document | Content |
|---|---|---|
| 0 | [00_EXECUTIVE_SUMMARY.md](00_EXECUTIVE_SUMMARY.md) | The findings that matter, decisions needed |
| A | [A_PROJECT_UNDERSTANDING.md](A_PROJECT_UNDERSTANDING.md) | Architecture, stack, routes, API contracts, measured behaviour, limits |
| B | [B_FEATURE_COVERAGE_MATRIX.md](B_FEATURE_COVERAGE_MATRIX.md) | Every backend capability → current UI → missing UX → target UX → proof test |
| C | [C_BACKEND_RISKS.md](C_BACKEND_RISKS.md) | Financial-model concerns, security-sensitive flows, incomplete capabilities |
| D | [D_CURRENT_FRONTEND_ASSESSMENT.md](D_CURRENT_FRONTEND_ASSESSMENT.md) | Real-browser findings per route, desktop + mobile, screenshots |
| E | [E_UX_RESEARCH_FINDINGS.md](E_UX_RESEARCH_FINDINGS.md) | Financial-product and accessibility patterns, with sources |
| F | [F_CREATIVE_DIRECTION.md](F_CREATIVE_DIRECTION.md) | Two creative directions + production-technique comparison |
| G | [G_TECHNICAL_RECOMMENDATION.md](G_TECHNICAL_RECOMMENDATION.md) | Architecture, motion stack, assets, performance, security |
| H | [H_PRODUCTION_ROADMAP.md](H_PRODUCTION_ROADMAP.md) | Phases, acceptance criteria, the 90-second demo path |
| I | [I_BLOCKERS_AND_DECISIONS.md](I_BLOCKERS_AND_DECISIONS.md) | Only the decisions that need the owner |

Screenshots of the app taken during this audit: [`audit-2026-10-11/`](audit-2026-10-11/) (WebP, own product only).
Screenshots of third-party reference sites were taken for research but are **not** stored in the repository.

## Older files in this folder (historical, not current)

`FEATURE_COVERAGE_MATRIX.md`, `MASTER_PROGRESS.md` and `UX_RESEARCH_SYNTHESIS.md` were written on the
`work/frontend-redesign` branch. They describe files that were never committed anywhere (`overview.html`, `soon.html`,
`landing.js`, `landing.css`, `wallet.js`) and statements that are false on `main` today (e.g. "RescueVault contract not
built", "Exit Runway backend endpoint not deployed" as if planned). They are left unchanged and are **superseded** by
the documents above.

## Reproduce the evidence

```powershell
cd C:\Users\badis\Hack\defi-hackathon-2026
.\.venv\Scripts\python.exe scripts\dev_server.py 8000          # http://127.0.0.1:8000/
$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"; $env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider     # 252 passed, 17 skipped (87 s)
node --test (Get-ChildItem tests\js\*.mjs).FullName              # 33 passed
cd contracts; forge test                                         # 29 passed, 1 skipped (fork test needs ETH_RPC_URL)
curl.exe -s "http://127.0.0.1:8000/api/analyze?ref=auto"         # 20-36 s, live
```
