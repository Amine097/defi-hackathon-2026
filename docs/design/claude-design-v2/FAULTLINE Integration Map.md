# FAULTLINE prototype: integration map

Prototype files: `Faultline Landing v2.dc.html` (landing) and `Faultline App.dc.html` (application). All figures come from `faultline-data.js`, which copies recorded backend artifacts. Nothing in the prototype recomputes a financial value.

Status key: **EXISTS** = the backend already returns it · **PARTIAL** = it exists, but the prototype or the frontend still needs wiring · **MISSING** = needs backend work.

## Screens

| Screen / state | Backend source | Status |
|---|---|---|
| Landing: hero, 3D scene, scroll story | Static. ARM/DEFEND/PROVE figures from `data/countermove/demo/latest/summary.json` (S1) | EXISTS |
| Landing: "Five layers deep" | `public/data/sample.json` (live `/api/analyze` run, block 26,162,781) | EXISTS |
| Position select: market id lookup | `/api/analyze?ref=<market>` (Pendle PT / Morpho markets only) | EXISTS |
| Position select: vault lookup | `/api/vault?address=` (V1/V2 factory detection, 404/422 errors) | EXISTS |
| Position select: borrower | `/api/analyze?borrower=0x…\|auto` | EXISTS |
| Position select: find every position a wallet holds | — | MISSING. The UI says so explicitly |
| Loading, long request, network error, retry | HTTP 400/404/422/503 codes from both endpoints; about 35 s per live run | PARTIAL: progress steps are cosmetic, since there is no streaming progress |
| Dashboard: verdict, bands, exit side, carry, margin, drivers | `decision.*`, `node_contrib_usd`, `exit_band`, `carry` | EXISTS |
| Dashboard: vault driver breakdown | Vault payload | PARTIAL: not wired in the prototype |
| Positions & Vaults: market facts, vault markets, withdrawal routes | `lending.meta`, `snap.markets`, `route_gas`, `conversion` | EXISTS |
| X-Ray: graph, hidden flags, transmissions, list view | `nodes[]` (`meta.hidden`, `depth`), `edges[]` | EXISTS |
| X-Ray: vault graph | Vault payload graph | PARTIAL: the prototype renders only the PT graph |
| Simulate: single dependency | `stress_table[]` (conditional loss, path, transmission) | EXISTS |
| Simulate: incident presets | `scenarios[]` (depeg, oracle, liquidity, correlated) | EXISTS |
| Simulate: custom severity | `?shock=&severity=` → `custom_shock` | EXISTS in the backend; the prototype slider is read-only |
| Simulate: HOLD TO MATURITY | — | MISSING: no redemption-value model |
| Simulate: borrower-specific shock losses | — | MISSING: stress table is computed for unlevered value |
| Replay S1 (T0–T6) | `summary.json` S1: states, plan, validation, execution, verification | EXISTS (local fork) |
| Replay S5, Pendle PT | — | MISSING: no S5 recording in `data/countermove` |
| Replay, historical USDC/SVB | `data/fixtures/replay_h04.json` | EXISTS (model check only) |
| Countermove 1: policy preview + dry run | `api/countermove.py` | EXISTS. The prototype's checks are client-side placeholders |
| Countermove 2: fork demonstration | `summary.json`, `keeper_config_*.json`, `RescueVault.sol` on Anvil | EXISTS (simulated) |
| Countermove 3: deployed autonomous protection | — | MISSING: no mainnet RescueVault, keeper service or authorization flow |
| Pause / revoke / withdraw | `RescueVault.setPaused`, `revoke`, `withdrawReserve` | Contract EXISTS; mainnet deployment MISSING |
| Activity: recorded analyses, fork runs, validations | Artifacts listed above | EXISTS (files, not an API) |
| Activity: session simulations and policy dry runs | — | Session only: no persistence or account service |
| Activity: monitoring events | — | MISSING: honest empty state shown |
| Wallet connection | — | Not used. Connecting grants no permission in any design state |

## Rules the UI enforces

- A status reads as protected only when all four are verified: RescueVault deployed and verified on mainnet, reserves funded, keeper running, owner policy and keeper confirmed on-chain. Today it never does.
- Every number shows where it came from: RECORDED LIVE RUN, SIMULATED, DRY RUN, FORK CONFIRMED, MAINNET CONFIRMED, HISTORICAL DATA, PENDING, UNAVAILABLE.
- Animation only shows the order of propagation. Losses and verdicts appear after it finishes and come from backend fields.
- Fork transactions are labelled with chain 31337. The only mainnet transaction shown is a third-party liquidation used for validation.

## Suggested backend additions, in priority order

1. Record a Countermove S5 run on the PT-reUSD / USDC market (`scripts/countermove_fork_demo.py`).
2. Hold-to-maturity comparison for PT positions.
3. Streaming progress or job ids for 35-second analyses.
4. Borrower-aware stress table (`borrower=` combined with `shock=`).
5. Persistence for analyses, simulations and policy previews.
6. Mainnet RescueVault deployment, keeper service and monitoring events. This is what would make design state 3 real.

## Frontend integration notes

- Each screen reads one position context. Map `POS` to the `/api/analyze` or `/api/vault` response, plus the `ref` / `address` that produced it.
- `NODES`/`EDGES` map 1:1 to `nodes[]`/`edges[]`. Graph x positions come from `layer`; y positions are laid out per column.
- `SCEN` maps to `scenarios[]`, and the single-dependency results map to `stress_table[]`.
- `REPLAY` steps are derived from one `summary.json` scenario: `before_shock`, `simulated_shock`, `detected`, `plan`, `validation`, `execution`, `verification`.
- Styling is inline in the prototype. The tokens are #05070b background, #e9edf2 ink, #8a94a3 muted, #2bb8ff defense, #ff6a3d threat, #ffb547 simulated or preview. Fonts are Archivo (variable width) and IBM Plex Mono.
