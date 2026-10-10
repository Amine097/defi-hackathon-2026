# FAULTLINE — Backend-to-Frontend Feature Coverage Matrix

Generated: 2026-10-11
Branch: work/frontend-redesign

## Backend API Surface

| # | Capability | API Route | Backend Source | Frontend Page | Status | Gap |
|---|-----------|-----------|---------------|--------------|--------|-----|
| 1 | Dependency X-Ray (live/cache/mock) | `GET /api/analyze?ref=&shock=&severity=&value_usd=&borrower=` | `api/analyze.py` → `src/defirisk/api_payload.py` | `xray.html` + `xray.js` | **Working** | Needs design parity with landing |
| 2 | Vault Risk Analyzer (on-chain) | `GET /api/vault?address=&value_usd=&chain_id=&horizon_days=&shock=&severity=` | `api/vault.py` → `src/defirisk/vault_model.py` | `vault.html` + `vault.js` | **Working** | Needs design parity, mobile polish |
| 3 | Countermove recorded demo | `GET /api/countermove[?live=1]` | `api/countermove.py` → `src/defirisk/countermove/api.py` | `countermove.html` + `countermove/app.js` | **Working** | Core product; needs polish |
| 4 | Policy draft encoder | `GET /api/countermove/policy-draft?...` | `api/countermove.py` → `cm.policy_draft()` | `countermove/app.js` (ARM phase) | **Working** | Calldata generated but no wallet signing UI yet |
| 5 | Risk overview dashboard | N/A (uses /api/analyze) | `src/defirisk/api_payload.py` | `overview.html` + `shell.js` | **Working** | Needs unified navigation, design polish |
| 6 | Breaking Point scenarios | Part of /api/analyze payload | `src/defirisk/core/scenarios.py` | `breaking-point.js` (overview) | **Working** | Embedded in overview, not standalone |
| 7 | Exit Runway / cost analysis | Part of /api/analyze payload | `src/defirisk/exposure.py` | `exit-runway.js` (overview) | **Working** | Embedded in overview |
| 8 | STAY / EXIT decision engine | Part of /api/analyze payload | `src/defirisk/core/decision.py` | `overview.html` verdict section | **Working** | Clear visual, needs context explanation |
| 9 | Live dependency reads (mainnet) | `GET /api/countermove?live=1` | `cm.live_dependencies()` | Toggle in countermove.html | **Working** | Needs clearer live vs simulated badge |
| 10 | Wallet connection | N/A (client-side) | — | `wallet.js` (EIP-6963) | **Working** | Read-only; no signing flows yet |

## Backend Services (not directly API-exposed)

| # | Capability | Source | Purpose | Frontend Needs |
|---|-----------|--------|---------|---------------|
| 11 | Countermove engine (planning/execution) | `src/defirisk/countermove/engine.py` | Min-repay/top-up calculation, strategy ranking | Shown via /api/countermove payload |
| 12 | Countermove executor | `src/defirisk/countermove/executor.py` | On-chain execution via keeper | Status shown in DEFEND/PROOF phases |
| 13 | Countermove verifier | `src/defirisk/countermove/verifier.py` | Post-execution verification | Verification checks shown in PROOF |
| 14 | Countermove watcher | `src/defirisk/countermove/watcher.py` | Price/oracle monitoring | Detection event shown in timeline |
| 15 | Countermove journal | `src/defirisk/countermove/journal.py` | Event log (JSONL) | Timeline view in countermove app |
| 16 | RescueVault contract | `contracts/src/RescueVault.sol` | On-chain policy + execution | Policy draft UI exists; signing missing |
| 17 | ShockFeed simulator | `contracts/src/sim/ShockFeed.sol` | Fork-test price shocks | Demo mode only; not user-facing |
| 18 | Fork demo script | `scripts/countermove_fork_demo.py` | Generates demo run data | Not user-facing |
| 19 | Dependency resolution | `src/defirisk/countermove/dependencies.py` | Oracle chain discovery | Shown in X-Ray and countermove |
| 20 | Morpho on-chain reader | `src/defirisk/morpho.py` + `vault_reader.py` | Market/position reads | Powers vault analyzer |

## Frontend Pages Inventory

| Page | File | Purpose | Backend Connection | Design Quality |
|------|------|---------|-------------------|---------------|
| Landing | `index.html` | Hero + ARM/DEFEND/PROVE narrative + demo | Graph from `/data/sample.json` | **Good** — needs hero film, typography refinement |
| Risk Overview | `overview.html` | Full position analysis dashboard | `/api/analyze` | **Functional** — needs design system parity |
| Dependency X-Ray | `xray.html` | Interactive 3D dependency graph | `/api/analyze` | **Good** — sophisticated 3D, needs polish |
| Vault Analyzer | `vault.html` | On-chain vault risk analysis | `/api/vault` | **Functional** — basic form + results |
| Countermove | `countermove.html` | ARM/DEFEND/PROOF demo flow | `/api/countermove` | **Good** — core product screen |
| Coming Soon | `soon.html` | Placeholder | None | Minimal |

## Data Sources and Environment Labels

The backend carefully labels every data source:
- **LIVE**: Real-time Ethereum mainnet reads (read-only eth_call)
- **SIMULATED**: Local Anvil fork with controlled shocks
- **cache**: Replayed from saved on-chain snapshots
- **mock**: Demo graph (requested explicitly or fallback)
- **mock-fallback**: Live discovery failed; demo shown with error

The frontend must surface these labels clearly and never misrepresent simulated data as live.

## Critical Gaps Requiring Implementation

1. **Navigation shell consistency**: overview.html uses `shell.js`; other pages have different nav patterns
2. **Design system tokens**: Landing uses `landing.css`; product pages use `theme.css` — need unified system
3. **Wallet connection flow**: Works for read-only; no signing/policy-authorization UI
4. **Mobile experience**: Landing is responsive; product pages need mobile work
5. **Loading/error states**: Inconsistent across pages
6. **Demo vs live toggle**: Exists in countermove; needs to be clearer product-wide
7. **Hero film slot**: Infrastructure ready (`HERO_FILM = null`); video blocked by Higgsfield trial
8. **Cross-page navigation**: No unified way to move between overview ↔ x-ray ↔ vault ↔ countermove
