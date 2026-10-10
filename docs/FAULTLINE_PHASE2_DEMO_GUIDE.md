# FAULTLINE — Phase 2 Demo Guide: Autonomous Countermove

> Everything below runs on **your machine** against a **local Anvil fork** (chain id 31337) or reads mainnet with
> `eth_call` only. Nothing is ever sent to Ethereum mainnet. The only key used to sign is the keeper's key derived from
> the **public** Anvil test mnemonic; no personal key is needed or accepted. Status labels: **LIVE** (read now on
> mainnet), **SIMULATED** (fork state or controlled shock), **CONFIRMED** (mined on the fork and verified), **FAILED**,
> **NO ACTION**.

## 0. Three-minute pitch flow (no setup beyond the dev server)

1. `python scripts/dev_server.py 8765` → open <http://localhost:8765/countermove.html> (recorded fork run).
2. **S1 · Before**: user A's weETH/USDC position (10 weETH, 20,838 USDC, LTV 75%), what the oracle depends on
   (weETH/ETH exchange rate × ETH/USD; "USDC valued at exactly 1 USD" listed as an implicit assumption), the policy the
   user signed **before** the crisis (trigger 82%, caps, floors, expiry), the funded reserve (5,000 USDC + 0.05 weETH)
   and the reserve what-if.
3. **S1 · During**: SIMULATED −9% on the weETH/ETH feed → on-chain LTV 82.42% ≥ trigger 82%. The engine compares
   REPAY 1,086.50 USDC / TOP_UP 0.5432 weETH (reserve too small) / FULL REPAY 20,838 USDC (reserve too small) and
   explains the choice; pre-send checks (local chain, `eth_call`, gas, fee, keeper funds).
4. **S1 · After**: CONFIRMED — tx hash, signer = keeper (the user's nonce did not change), debt 20,838.10 → 19,751.60,
   LTV 82.42% → 78.12%, buffer 905.76 → 1,992.26 USDC, 15/15 verification checks, limits remaining.
5. **S2** same crisis logic on cbBTC/USDC, but only 100 USDC in reserve → AUTO-TOP-UP 0.02509364 cbBTC.
   **S3** reserves too small and full repay disabled → **NO ACTION**: nothing sent, the reason is shown.
   **S4** the owner only authorized "close the debt" → EMERGENCY FULL REPAY, collateral kept.
6. **LIVE** button: the same two markets' oracle feeds read **now** on mainnet (read-only).
7. **Policy draft**: the form validates a policy with the contract's own rules and returns `setPolicy` calldata for the
   user's **own** wallet — FAULTLINE never signs for the user.

## 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Windows + PowerShell 7 | — | Commands below are PowerShell; on macOS / Linux use `/` paths and `export VAR=…` |
| Python | 3.14.6 in `.venv` (3.12+ expected to work) | `python -m venv .venv; .venv\Scripts\activate; pip install -r requirements-dev.txt` |
| Node.js | 22.19.0 | UI view-model tests only |
| Git | any | clones the pinned Solidity dependencies |
| Foundry (`forge`, `cast`, `anvil`) | **1.8.5** (commit `51a52c59`) | see §2 |
| Mainnet RPC (read-only) | public `https://eth-mainnet.public.blastapi.io` by default | only for the fork and LIVE reads; set `FORK_RPC_URL` to use your own (never commit RPC keys) |

## 2. Install Foundry 1.8.5 (Windows)

1. Download `foundry_v1.8.5_win32_amd64.zip` from the official release page
   <https://github.com/foundry-rs/foundry/releases/tag/v1.8.5>.
2. Verify it before extracting: `Get-FileHash .\foundry_v1.8.5_win32_amd64.zip -Algorithm SHA256` and compare with
   the checksum published for that release asset (the archive installed for this project hashed `21f86b56…aa45`, see
   `docs/FAULTLINE_PHASE2_PROGRESS.md`).
3. Extract `forge.exe`, `cast.exe`, `anvil.exe` (and `chisel.exe`) into `%USERPROFILE%\.foundry\bin`.
4. In every new shell: `$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"`, then `forge --version` → `1.8.5`.

(macOS / Linux: install `foundryup` from the official Foundry documentation and select version 1.8.5.)
The keeper finds `cast` on `PATH` or in `~/.foundry/bin` automatically.

## 3. Contracts: dependencies, build, tests

```powershell
$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"
powershell -ExecutionPolicy Bypass -File contracts\install_deps.ps1   # forge-std v1.17.0, OZ v5.6.1, morpho-blue v1.0.0 (commits verified)
cd contracts
forge build
forge test                                   # unit + fuzz + token behaviour + invariants; the fork test reports SKIPPED
```

Fork test against the **real** Morpho Blue cbBTC/USDC market (block 26,164,248, SIMULATED price shock via `vm.mockCall`):

```powershell
$env:FORK_RPC_URL = "https://eth-mainnet.public.blastapi.io"
forge test --match-contract Fork --fork-url $env:FORK_RPC_URL --fork-block-number 26164248 `
  --compute-units-per-second 40 --fork-retries 10 --fork-retry-backoff 1500 -vv
```

## 4. Python and UI tests

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider          # offline: Phase 0.5/1 + P0 + countermove (engine, API, e2e on a local Anvil)
$env:DEFIRISK_LIVE_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider   # + read-only mainnet cross-checks
Remove-Item Env:DEFIRISK_LIVE_TESTS
node --test tests\js\vault_view.test.mjs tests\js\decision_view.test.mjs tests\js\countermove_view.test.mjs
```

The end-to-end keeper tests (`tests/test_countermove_e2e.py`) start their own Anvil (no fork, no network) with the real
Morpho Blue v1.0.0 bytecode compiled from the pinned sources; they need Foundry on `PATH` and `forge build` done.

## 5. Re-run the full fork demonstration (S1–S4)

```powershell
$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"; $env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe scripts\countermove_fork_demo.py            # ~1.5 min + fork warm-up; add --keep-alive to keep the fork running
```

What it does, in order (every user step happens **before** the crisis):

1. Starts `anvil --fork-url $FORK_RPC_URL --fork-block-number 26164248 --chain-id 31337` on port 8547.
2. Opens four users' positions at 75% LTV on the real weETH/USDC and cbBTC/USDC markets (test balances written into
   local storage), deploys one RescueVault per user, funds the reserves and signs each policy.
3. Runs the keeper **as a separate OS process** with only the keeper key:
   `python -m defirisk.countermove --config data/countermove/demo/latest/keeper_config_<phase>.json --journal-dir data/countermove/demo/latest --interval 1 --until-terminal --max-ticks 6`.
4. Installs SIMULATED −9% shocks (weETH/ETH feed for S1/S3, BTC/USD feed for S2/S4; the replaced feed's
   `description()` returns "FAULTLINE SIMULATED SHOCK"); the keeper detects, plans, validates, executes, verifies.
5. Writes `data/countermove/demo/latest/{summary.json, journal.jsonl, state.json, keeper_config_*.json, anvil.log}` and
   prints one line per scenario. Expected: `S1 CONFIRMED`, `S2 CONFIRMED`, `S3 NO_ACTION`, `S4 CONFIRMED`,
   `all expected outcomes: True`.

The web page reads that directory, so a re-run refreshes the UI. After a re-run, refresh the UI test fixture:
`$env:FAULTLINE_EXPORT_UI_FIXTURES='1'; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests\test_countermove_api.py`.

### Running the keeper by hand (on a running fork)

```powershell
$env:FAULTLINE_KEEPER_KEY = (cast wallet private-key --mnemonic "test test test test test test test test test test test junk" --mnemonic-index 1)
python -m defirisk.countermove --config <keeper_config.json> --journal-dir data/countermove/journal --interval 3 --until-terminal
```

Without `FAULTLINE_KEEPER_KEY` the keeper is **watch-only** (plans and alerts, never signs). It refuses to sign unless
the RPC is on loopback **and** the chain id is 31337 or 1337. Config: `rpc_url`, `positions[]` (`id`, `rescue_vault`,
`engine` {`safety_margin`, `interest_horizon_s`, `ranking`, `preference`, `allow_partial`}, `scenarios[]`),
`limits` (`max_gas_units`, `max_fee_per_gas_wei`, `receipt_timeout_s`). See `keeper_config_*.json` in the demo folder.

## 5b. Dry run on a REAL mainnet borrower (LIVE + DRY-RUN, read-only)

"What would the keeper do right now?" for a real Morpho Blue borrower on Ethereum mainnet. **LIVE**: the position
(collateral, debt accrued to the block, LTV, LLTV, buffer) and the oracle's feeds with their freshness are read with
`eth_call` at one pinned block (`ETH_RPC_URL` first, then public endpoints). **DRY-RUN**: no RescueVault exists for a
real borrower, so the policy (same fields and units as the policy draft) and the reserves are hypothetical; the watcher's
state rule and the same engine decide (WATCHING / DETECTED, candidates, chosen action, reasons, reserve needed per
first hit). Nothing is signed or sent; the VALIDATING stage is skipped; the payload has no transaction field.

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m defirisk.countermove dry-run --market cbBTC/USDC --borrower auto            # largest borrower
.\.venv\Scripts\python.exe -m defirisk.countermove dry-run --market weETH/USDC --rank 2 --set trigger_ltv=0.65 --set loan_reserve=500000 --json
```

HTTP (Vercel only routes `/api/countermove` itself, hence the query-string action):
`/api/countermove?action=dry-run&market=<0x id | cbBTC/USDC | weETH/USDC>&borrower=<0x.. | auto>[&rank=1]` plus any of
`strategies`, `trigger_ltv`, `min_ltv_after`, `max_repay_per_action`, `max_top_up_per_action`, `max_full_repay`,
`max_repay_total`, `max_top_up_total`, `min_loan_reserve`, `min_collateral_reserve`, `valid_days`, `cooldown_s`,
`loan_reserve`, `collateral_reserve`, `safety_margin`, `interest_horizon_s`, `follow_on_drop`, `follow_on_dependency`
(`collateral`, a feed role such as `BASE_FEED_2`, or a feed description), `allow_partial`, `ranking`. Defaults are
scaled to the position and listed in `hypothetical.defaults_used` (reserves 10% of debt / collateral, caps = reserves,
trigger = LLTV − 4 pp, floor = min(40%, trigger − 10 pp), margin 1% of debt, follow-on −8% on the collateral price).
`borrower=auto` takes the largest borrower by borrow shares from the Morpho API, then re-reads it on-chain. Errors are
JSON `{"error": {"code", "status", "message", "field"}}`: 400 invalid input or policy (same rules as `setPolicy`), 404
unknown market / no borrower, 503 mainnet RPC or Morpho API unavailable. Tests: `tests/test_countermove_dryrun.py`
(offline, fake mainnet RPC; the live read runs with `DEFIRISK_LIVE_TESTS=1`).

## 6. Evidence

```powershell
.\.venv\Scripts\python.exe scripts\collect_phase2_evidence.py --live --fork   # runs the suites and writes audit/FAULTLINE_PHASE2_EVIDENCE.json
```

Without `--live` / `--fork` the collector runs only the offline suites (no network).

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `anvil` / `cast` not found | Foundry not on `PATH` | `$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"` |
| Fork start is slow, HTTP 429, `fork-retry` messages | public RPC rate limits (the demo throttles to 40 CU/s with retries) | wait, or set `FORK_RPC_URL` to your own endpoint |
| Keeper says feeds are **stale** → NO_ACTION | Anvil's clock = fork block time + elapsed wall time; after ~1 h of uptime the real feeds look older than their heartbeat | restart the fork (re-run the demo); this is the fail-closed rule working |
| `port 8547 already in use` | a previous fork is still running | stop that Anvil process, or `--port 8548` |
| e2e tests skipped | Foundry or the artifacts are missing | install Foundry, `forge build` in `contracts/` |
| Policy draft rejected | the draft breaks a contract rule (e.g. trigger ≥ LLTV, per-action cap > cumulative cap, expiry in the past) | adjust the fields; the error names the rule |
| LIVE panel "unavailable" | public mainnet RPCs unreachable | nothing is shown rather than stale data; retry later |
| Slither shows 52 findings | expected | triaged in `docs/FAULTLINE_PHASE2_SECURITY_REPORT.md` §6 (Slither's `forge clean` removes test artifacts: run `forge build` again afterwards) |
