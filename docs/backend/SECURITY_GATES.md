# Security gates

Each gate is enforced in code and pinned by a test (file in brackets).

## Transactions and keys

| Gate | Where | Test |
|---|---|---|
| The keeper only transacts on chain id 31337 / 1337 over a loopback RPC | `chain.RPC.assert_local`, `service.start` | `test_countermove_service::test_refuses_non_local_chain_and_unknown_environment` |
| If the chain id is unknown at start (RPC down), it is checked before the **first** decision; a non-local chain stops the service | `service.tick` | `test_chain_id_unknown_at_start_is_checked_before_any_decision` |
| Keystore only unlocked after the local-chain check; plaintext `FAULTLINE_KEEPER_KEY` refused | `watcher.signer_from_env` | existing signer tests |
| API endpoints never sign or send | `api/countermove.py`, `status.py` (read-only) | `test_countermove_api`, `test_countermove_service` |
| The owner signs `setPolicy` with their own wallet; FAULTLINE only returns calldata | `api.policy_draft` | `test_countermove_policy` |
| On-chain caps, cooldown, LTV floor and expiry bound every keeper action | `contracts/src/RescueVault.sol` | forge suite (29 passed) |

## Truthfulness (no fabricated states)

| Gate | Where |
|---|---|
| `ARMED` needs a signed policy, an authorized keeper, not paused, not revoked, not expired (chain time), and reserves ≥ requirement | `lifecycle.derive` |
| `MONITORING` needs a fresh `ok` heartbeat **from a service watching this vault** whose signer is the vault's keeper | `lifecycle.derive`, `service.read_health` |
| `VERIFIED` needs CONFIRMED (receipt + verifier) **and** the confirmation depth with the receipt still canonical | `service.Finality`, `lifecycle.derive` |
| A reorged action becomes `FAILED` before any new decision is taken | `service.tick` (finality first) |
| Missing configuration or a failing RPC → `UNAVAILABLE`, never "safe" or "armed" | `status.py` |
| Evidence rows carry `local-test` / `fork` / `mainnet-readonly`; transaction kinds are refused for `mainnet-readonly` | `evidence.EvidenceStore.append` |
| The recorded fork run is served read-only, with its sha256 | `status._recorded` |

These are pinned end to end on Anvil by `tests/test_countermove_arm_e2e.py`.

## Input handling

| Gate | Where |
|---|---|
| No SSRF: the vault RPC comes only from `FAULTLINE_ARM_RPC_URL`, never from the request | `status.policy_status` (test `test_policy_status_never_takes_an_rpc_from_the_request`) |
| Addresses parsed strictly; position ids match `[A-Za-z0-9_.:-]{1,64}`; `limit` ≤ 500; raw amounts are digits only, ≤ 78 chars | `status.py`, `vault_input.parse_address` |
| Policy numbers must be finite and in bounds; strategy names are allowlisted; amounts use exact Decimal | `policy.validate` |
| The evidence DB is opened read-only by the API (`mode=ro`) | `EvidenceStore(readonly=True)` |
| 500 responses carry a generic message; details go to stderr only | `api/countermove.py` |

## Integrity and concurrency

| Gate | Where |
|---|---|
| Single keeper per state directory (OS file lock; released when the holder dies) | `service.Lease` |
| Evidence is append-only (SQL triggers), hash-chained (`verify()`), idempotent (UNIQUE key) | `evidence.py` |
| Journal appends are `fsync`ed; health, finality and HTTP cache files are written atomically (temp + `os.replace`) | `journal.py`, `service._atomic_json`, `data/http._atomic_write` |

## Residual risks (accepted for the hackathon scope)

* The evidence hash chain detects tampering only if the attacker cannot rewrite the whole file. It is not anchored
  externally (no signature, no on-chain commitment).
* The health file is trusted by the API process. Anyone with write access to that path can claim `ok`. Run the keeper
  and the API under the same, restricted user.
* `reorg_suspected` is sticky for the lifetime of the process (cleared on restart). That is deliberate: it is a flag
  for the operator.
* The public mainnet RPC fallbacks (`sources.RPCS`) are used for **reads only**. Set `ETH_RPC_URL` to a trusted endpoint
  for anything beyond a demo.
