# Backend API contracts

All endpoints are `GET` and return JSON, never HTML or tracebacks. They are Vercel Python functions under `api/`, also
served by the local dev server. `allow_nan=False` is enforced on output.

## Error shapes (two, documented rather than unified to avoid breaking the frontend)

| Endpoint family | Shape |
|---|---|
| `/api/analyze` | `{"error": "<message>", "code": "invalid_input" \| "unsupported_market" \| "discovery_failed", "hint"?}` with 400 / 404 / 502 |
| `/api/countermove`, `/api/vault` | `{"error": {"code", "status", "message", "field"?}}` with 400 / 404 / 500 / 503 |

`/api/analyze` has **no silent demo fallback**: a failed live discovery returns 502 `discovery_failed`. The demo graph
is only served when it is asked for explicitly with `ref=mock`. The old docstring that mentioned `mock-fallback` was
stale and has been corrected.

## `/api/countermove`

| `action` | Schema | Notes |
|---|---|---|
| *(none)* `[live=1]` | `faultline.countermove/1` | Recorded local mainnet-fork run (SIMULATED), plus live mainnet dependency reads when `live=1`. |
| `policy-draft` | `faultline.countermove.policy-draft/2` | See below. Never signs. |
| `dry-run` | `faultline.countermove.dryrun/1` | A real mainnet borrower read and what the keeper *would* do. No tx. |
| `evidence` | `faultline.countermove.evidence/1` | Recorded fork journal plus the keeper evidence store. |
| `keeper-status` | `faultline.keeper.status/1` | Keeper heartbeat. |
| `policy-status` | `faultline.countermove.lifecycle/1` | Derived ARM state for one vault. |

An unknown `action` returns 400 `invalid_input`, `field: "action"`.

### `policy-draft`

**Query.** All fields are optional; defaults are in brackets:

| Field | Default / format |
|---|---|
| `strategies` | `REPAY,TOP_UP` — ordered preference; an explicitly empty value is an error |
| `lltv` | `0.86` |
| `trigger_ltv` | `0.82` |
| `min_ltv_after` | `0.4` |
| `valid_days` | `30` — between 1 hour and 365 days |
| `cooldown_s` | `3600` — between 0 and 30 days |
| `loan_decimals` | `6` |
| `collateral_decimals` | `18` |
| `max_repay_per_action`, `max_top_up_per_action`, `max_full_repay`, `max_repay_total`, `max_top_up_total`, `min_loan_reserve`, `min_collateral_reserve` | Human token amounts |
| `loan_reserve`, `collateral_reserve` | Planned reserves; produce warnings only |
| `chain_id` | 1, 31337 or 1337 |
| `vault`, `keeper` | Addresses |
| `target_health_factor` | Optional |

**Response:**

| Field | Contents |
|---|---|
| `valid` | Boolean |
| `errors` | List of messages (v1 compatibility) |
| `error_details` | `[{field, code, message, contract_rule}]` |
| `warnings` | Non-blocking |
| `policy` | Exact on-chain struct in raw integers, or null |
| `calldata` | `setPolicy(...)` calldata, or null when invalid |
| `preference_order`, `risk_mapping`, `chain` | Health factor = LLTV / LTV |
| `lifecycle_state` | `VALIDATED` or `DRAFT` |
| `pause_calldata`, `resume_calldata`, `revoke_calldata` | Owner controls |
| `note`, `signer` | Text |

Error `code`s:

| Code | Meaning |
|---|---|
| `not_a_number`, `not_finite`, `not_an_integer`, `out_of_range`, `negative`, `too_large` | Number checks |
| `empty`, `unknown_strategy`, `duplicate_strategy` | Strategy checks |
| `above_lltv`, `not_below_trigger`, `below_floor` | LTV bounds |
| `caps_inconsistent` | Per-action / full-repay cap above the cumulative budget |
| `unsupported_chain` | Chain not in the allowlist |
| `invalid_address` | Malformed address |

`contract_rule` names the `InvalidPolicy(...)` reason that `RescueVault.setPolicy` would revert with.

### `evidence`

**Query:**

| Parameter | Format |
|---|---|
| `position` | `[A-Za-z0-9_.:-]{1,64}` |
| `since` | Sequence cursor |
| `limit` | 1–500, default 200 |
| `source` | `all` \| `recorded` \| `store` |
| `kinds` | Comma-separated; store only |

**Response:**

* `labels`
* `recorded`: `{status, environment: "fork", integrity: {journal_sha256, records}, events[], next_since}`
* `store`: `{status, integrity: verify(), events[], next_since}`, or `{status: "UNAVAILABLE", reason}` when
  `FAULTLINE_EVIDENCE_DB` is unset or the file is missing. The store is opened **read-only**.

### `keeper-status`

**Response:** `{status: OK | STALE | DEGRADED | UNAVAILABLE | STOPPED | STARTING, monitoring: status == OK, reason,
health}`. Returns `UNAVAILABLE` with a reason when `FAULTLINE_KEEPER_HEALTH` is unset or the file is missing.

### `policy-status`

**Query:**

| Parameter | Format |
|---|---|
| `vault` | Required address |
| Policy-draft fields | Optional; supply the **complete** policy, because amount fields default to 0 |
| `required_loan_raw`, `required_collateral_raw` | Raw integer token units; optional |

**Response:**

| Field | Contents |
|---|---|
| `state` | One of `lifecycle.STATES` |
| `reason` | Text |
| `armed`, `monitoring` | Booleans |
| `gates` | `[{gate, ok, detail}]` |
| `chain` | `{chain_id, environment, head_block, head_timestamp}` |
| `vault_address` | The queried address |
| `keeper` | `{status, reason, heartbeat_age_s, watching_this_vault}` |
| `vault` | On-chain summary: policy, nonce, reserves, totals, paused, revoked … |
| `last_event`, `last_terminal`, `finality`, `alert` | Present when relevant |

The RPC comes **only** from the server env var `FAULTLINE_ARM_RPC_URL`. A URL in the request is ignored (no SSRF).

## Server-side configuration

| Env var | Used by | Unset → |
|---|---|---|
| `FAULTLINE_ARM_RPC_URL` | `policy-status` | `UNAVAILABLE` ("no RPC configured") |
| `FAULTLINE_ARM_ENVIRONMENT` | label for chain 31337/1337: `local-test` (default) or `fork` | `local-test` |
| `FAULTLINE_KEEPER_HEALTH` | `keeper-status`, `policy-status` | keeper `UNAVAILABLE` → state at most `ARMED` |
| `FAULTLINE_EVIDENCE_DB` | `evidence` (`store`) | store `UNAVAILABLE` |
| `FAULTLINE_KEEPER_KEYSTORE`, `FAULTLINE_KEEPER_PASSWORD_FILE` | keeper process only | watch-only keeper |
| `ETH_RPC_URL` | mainnet reads (analysis, dry-run) | public RPC list |

On Vercel none of the FAULTLINE_* variables point to a running keeper, so `keeper-status` and `policy-status` honestly
report `UNAVAILABLE`.

## Compatibility

* `policy-draft` moved from schema `/1` to `/2`. Existing fields are kept (`valid`, `errors` as strings, `policy`,
  `calldata`, the pause / resume / revoke calldata); the other fields are new.
* **Behaviour change:** malformed inputs that the old float parser silently accepted (NaN, unknown strategy names,
  negative amounts) are now errors. Amounts that float mis-rounded are now exact. For example, 4.1 USDC is now
  4 100 000 raw units; the float parser produced 4 099 999.
