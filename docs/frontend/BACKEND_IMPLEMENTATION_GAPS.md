# Backend implementation gaps: designed features and their real status

Every functional element of the Claude Design v2 export, classified by what the backend actually supports today.
Classes: **Integrated** (fully implemented and connected) · **Not connected** (implemented, not wired to the UI) ·
**Local fork only** · **Read-only / dry-run only** · **Needs backend engineering** · **Needs deployment or security
authorization** · **Not implemented**. Where a feature cannot work in production, the UI keeps the approved design and
shows its truthful disabled / unavailable state; nothing below is simulated as if it worked.

| Designed feature | Screen | Class | What exists | What is missing | Notes |
|---|---|---|---|---|---|
| Market id lookup ("Morpho Blue market id · 0x + 64 hex") | Select | **Integrated** (added in this change) | `GET /api/analyze?lookup=1&ref=morpho:1:<id>` (Pendle × Morpho market lists, ≈1 s) and `ref=morpho:1:<id>` for the full analysis | — | Before this change the backend only took `auto` or `pendle:1:<Pendle market>` |
| Vault address lookup | Select | **Integrated** (added in this change) | `GET /api/vault?lookup=1&address=` (eth_getCode + factory checks + labels, ≈1 s); 404 for an EOA, 422 for a non-vault contract | — | Full analysis: `/api/vault?address=` |
| Find every position a wallet holds | Select | **Not implemented** | — | Wallet → positions discovery (Morpho / Pendle APIs) | The design itself says FAULTLINE does not scan wallets |
| Borrower on a supported market | Select | **Not connected** | `/api/analyze?borrower=0x..|auto` | A second input in the design (see design gap G7) | Available through the demonstration borrower (`borrower=auto`, recorded) |
| Loading steps and progress | Loading | **Needs backend engineering** | One request per analysis (10–40 s) | Streaming progress or job ids | Live runs show elapsed time and mark steps done together; nothing is ticked one by one |
| Network error / slow request states | Select | **Integrated** | Real timeouts, 5xx, 404/422 answers | — | The two "PROTOTYPE STATES" buttons that faked them are shown only with `?qa=1` |
| Verdict, bands, exit side, carry, margin, drivers | Dashboard | **Integrated** | `decision.*`, `node_contrib_usd`; vault `risk`, `decision`, `dependencies.nodes[].expected_loss_usd` | — | Vault drivers were "not wired" in the prototype; they are now |
| Borrower distance to liquidation, HF, P(liquidation), losses, deleverage cost | Dashboard | **Integrated** | `liquidation.*` (borrower mode) | — | Deleverage cost is an indicative quote (labelled) |
| Market facts, vault markets, withdrawal routes | Positions | **Integrated** | lending/AMM node meta, `allocations.items`, `exit.routes`, `usd_conversion` | — | KyberSwap conversion is indicative (labelled INDICATIVE) |
| Hold to maturity (route) | Positions | **Integrated** | `payload.maturity` (EXIT vs HOLD_TO_MATURITY over the same window) | — | The prototype marked it UNAVAILABLE; the backend added it |
| Hold to maturity under a shock | X-Ray › Simulate result | **Needs backend engineering** | Baseline maturity comparison only | Per-shock hold-to-maturity in `stress_table` / `scenarios` | Cell shows "n/a" and the baseline value; for the AMM it quotes `maturity.if_amm_fails` |
| Dependency graph, hidden flags, list view, inspector | X-Ray | **Integrated** (PT, borrower) | `nodes[]`, `edges[]`, `stress_table[]` (path, transmission, conditional loss, channel notes) | — | Role-aware results (no-debt oracle failure = no effect) are shown as returned |
| Vault graph | X-Ray | **Not connected** | `dependencies.nodes/edges` | A designed vault layout (design gap G3) | The designed "graph covers PT markets" state is shown |
| Single-dependency simulation | X-Ray | **Integrated** | `stress_table[]` | — | Animation only orders the propagation; figures appear after it, from the backend |
| Incident presets | X-Ray | **Integrated** | `scenarios[]` (depeg, oracle, liquidity, correlated) | — | Stressed exit for the liquidity scenario is labelled |
| Custom severity | X-Ray | **Not connected** | `?shock=&severity=` → `custom_shock`, `incident` | A designed control (design gap G1) | — |
| Borrower-specific shock losses | X-Ray | **Needs backend engineering** | Borrower mode turns the debt channel on, losses are for `value_usd` on the market; borrower liquidation scenarios are separate | Stress table at the borrower's own size | Result shows the designed borrower note |
| Replay S1 (T0–T6) | X-Ray › Replay | **Local fork only** | `/api/countermove` recorded run | — | Fork transactions are labelled chain 31337 |
| Replay S5 (Pendle PT on Morpho) | X-Ray › Replay | **Local fork only** | Recorded S5 run (REPAY 1,447.44 USDC after a −5% PT-feed shock) | — | The prototype showed "UNAVAILABLE · needs a recording"; the recording exists now |
| Replay USDC / SVB | X-Ray › Replay | **Not connected** | `data/fixtures/replay_h04.json`, `tests/test_hardening.py` | An endpoint that serves the replay | Shown as the designed historical card (recorded facts) |
| Policy preview checks | Countermove | **Read-only / dry-run only** | `?action=policy-draft` (setPolicy rules, calldata) and `?action=dry-run` (live mainnet borrower, keeper engine, nothing signed) | — | The prototype ran checks in the browser; they now come from the backend |
| Allowed actions "in priority order" (↑ / ↓) | Countermove | **Needs backend engineering** | The engine ranks fundable actions by the least reserve committed (`ranking=min_capital`), or a fixed default order; the contract stores only a bitmask | A custom preference order in the dry run and in the keeper configuration | The designed control is kept; the checks list says a custom order is not enforced |
| Fork demonstration | Countermove | **Local fork only** | Recorded run, `RescueVault.sol` on Anvil | — | Figures read from `/api/countermove` |
| Deployed autonomous protection, monitoring status, last block checked | Countermove | **Needs deployment or security authorization** | Contract and keeper code (not audited) | Mainnet RescueVault, funded reserves, keeper service, monitoring, independent audit | Designed "DESIGN TARGET · NOT AVAILABLE YET" state, all four requirements NO |
| Pause / revoke / withdraw reserve | Countermove | **Needs deployment or security authorization** | `setPaused`, `revoke`, `withdrawReserve` in the contract; calldata from `policy-draft` | A deployed vault and the owner's wallet | Buttons stay disabled as designed |
| Arm protection | Countermove | **Needs deployment or security authorization** | — | Same as above | Disabled button, designed text |
| Activity: recorded analyses, fork runs, validations | Activity | **Integrated** | Recorded payloads, `/api/countermove`, `liquidation.historical_check` | — | Each row keeps its label (RECORDED LIVE RUN, LIVE, FORK CONFIRMED, MAINNET CONFIRMED) |
| Activity: session simulations and policy previews | Activity | **Not implemented** (persistence) | In-memory, this session only | Account storage | The designed text says entries disappear when you leave |
| Activity: monitoring events | Activity | **Not implemented** | — | Keeper service + event store | Designed empty state |
| Wallet connection | Landing | **Not implemented** | — | — | Designed as a preview only; the modal has no trigger in the export |

## Backend changes made for this integration

- `src/defirisk/data/discovery.py`: `ref=morpho:1:<market id>` (validated by `_check_ref`), `lookup()`, `UnsupportedMarket`.
- `api/analyze.py`: `?lookup=1&ref=morpho:1:<id>`; `UnsupportedMarket` → 404 `unsupported_market` (was a 502).
- `src/defirisk/vault_reader.py`: `lookup()`; `api/vault.py`: `?lookup=1&address=`.
- `scripts/record_demo_payloads.py`: reproducible recordings for DEMO mode (`public/data/recorded/*.json`, refuses non-live data).
- Tests: `tests/test_design_lookup.py` (offline with stubs, live with `DEFIRISK_LIVE_TESTS=1`).

Not done here, by design: anything that signs, deploys or moves funds.
