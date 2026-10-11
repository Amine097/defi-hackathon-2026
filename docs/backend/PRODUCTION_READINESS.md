# Production readiness — FAULTLINE backend

Status of the two core actions after the final backend pass. "Ready" means implemented, tested, and truthful about its
own limits. It does not mean deployed with real funds; FAULTLINE never transacts on mainnet.

| Capability | Status | Evidence |
|---|---|---|
| SIMULATE ATTACK (`/api/analyze`, `/api/vault`): real risk calculation on live mainnet reads (cache replay when offline) | Ready | existing analysis tests; `?shock=&severity=` re-runs the model |
| ARM PROTECTION · policy validation (`policy-draft/2`) | Ready | `tests/test_countermove_policy.py` |
| ARM PROTECTION · lifecycle derived from evidence (`policy-status`) | Ready | `tests/test_countermove_lifecycle.py`, `tests/test_countermove_arm_e2e.py` |
| ARM PROTECTION · durable keeper service (lease, heartbeat, backoff, finality, reorg) | Ready for local chains / forks | `tests/test_countermove_service.py`, `tests/test_countermove_arm_e2e.py` |
| ARM PROTECTION · evidence store (append-only, hash-chained, idempotent, labelled) | Ready | `tests/test_countermove_evidence.py` |
| Keeper on Vercel | **Not possible** (stateless functions) | endpoints answer `UNAVAILABLE` with the reason |
| Mainnet execution | **Out of scope by design** | local-chain gates (see SECURITY_GATES.md) |
| UI for the new endpoints | **Pending design** (Claude Design v2 owns the UI) | `docs/frontend/DESIGN_COVERAGE_GAPS.md` G18–G21 |

## Test results (this pass, Windows, Foundry 1.x on PATH)

| Suite | Command | Result |
|---|---|---|
| Python | `$env:FAULTLINE_REQUIRE_E2E="1"; .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | **345 passed, 18 skipped** (baseline 264 / 18) |
| Solidity | `cd contracts; forge test --offline` | 29 passed, 1 skipped (unchanged) |
| JS | `node --test tests\js\*.mjs` | 54 / 54 (unchanged) |

The 18 Python skips are all opt-in live mainnet tests (`DEFIRISK_LIVE_TESTS=1`). With `FAULTLINE_REQUIRE_E2E=1`, a
missing Foundry toolchain or missing `contracts/out` artifacts **fails** the e2e tests instead of skipping them
silently.

New tests: 81 in total.

| File | Tests | Covers |
|---|---|---|
| `test_countermove_policy.py` | 19 | Contract rules, input hygiene, exact Decimal amounts |
| `test_countermove_lifecycle.py` | 27 | Every gate and terminal-outcome case |
| `test_countermove_evidence.py` | 11 | Append-only, hash chain, idempotency, labels, read-only, concurrency |
| `test_countermove_service.py` | 19 | Lease (in-process and cross-process), heartbeat, RPC outage and backoff, head regression, stale head, finality, reorg, re-inclusion, chain-id check after a late RPC, status endpoints |
| `test_countermove_arm_e2e.py` | 4 | Anvil + real Morpho Blue bytecode + RescueVault + the real keeper; see below |
| `test_http_cache.py` | +1 | Atomic cache write |

The four e2e tests cover:

* the full path `AWAITING_AUTHORIZATION → AWAITING_RESERVES → ARMED (not monitored) → MONITORING → shock → EXECUTING → VERIFIED`, with exactly one receipt row and a verified hash chain;
* a reorg that turns the action `FAILED` (never `VERIFIED`);
* pause, expiry by chain time, and revoke;
* refusal of a second keeper.

## Running the keeper locally

```powershell
$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"
# 1. local chain + contracts: see docs/FAULTLINE_PHASE2_DEMO_GUIDE.md (anvil, forge build, deploy, keeper config)
# 2. keeper service (encrypted keystore; watch-only without it)
$env:FAULTLINE_KEEPER_KEYSTORE = "<path to keystore.json>"; $env:FAULTLINE_KEEPER_PASSWORD_FILE = "<path>"
.venv\Scripts\python.exe -m defirisk.countermove.service --config <cfg.json> --state-dir .keeper --confirmations 2
# 3. API process (dev server) pointed at the same files
$env:FAULTLINE_ARM_RPC_URL = "http://127.0.0.1:8545"
$env:FAULTLINE_KEEPER_HEALTH = ".keeper\health.json"
$env:FAULTLINE_EVIDENCE_DB = ".keeper\evidence.sqlite"
```

Then `GET /api/countermove?action=policy-status&vault=0x…` reports the derived state.

## Invariants verified in this pass

* `data/countermove/demo/latest/*`: sha256 of all 10 files identical before and after; no `git status` changes under `data/`.
* Commit `690ba65` (Claude Design v2 frontend) is untouched; no file under `public/` or `docs/design/` was modified.
* No commit, push or deploy was made.

## Related documents

* [ARM_ARCHITECTURE.md](ARM_ARCHITECTURE.md): components, state machine, keeper service, evidence model.
* [API_CONTRACTS.md](API_CONTRACTS.md): endpoints, schemas, error shapes, env vars.
* [SECURITY_GATES.md](SECURITY_GATES.md): enforced gates and residual risks.
* [BACKEND_GAPS.md](BACKEND_GAPS.md): limitations, methodology notes, and what was fixed.
