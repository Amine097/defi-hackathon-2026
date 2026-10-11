# Hosted keeper on Railway

`Dockerfile.keeper` + `railway.json` + `scripts/railway_keeper.py` run the ARM PROTECTION keeper as a hosted service.
This fixes the Railpack error "No start command detected": Railway now builds the Dockerfile instead of guessing.

## What it is (and is not)

ONE container contains:
- a local **Anvil test chain** (chain id 31337, test USDC/WETH, a **simulated** ETH/USD feed)
- Morpho Blue v1.0.0 and the `RescueVault`, deployed on first start
- one armed test position: 5 WETH collateral, 8,000 USDC debt, trigger LTV 82%
- the persistent keeper service, signing with an encrypted keystore of the **public Anvil test account #1**
- a read-only JSON status API

It **never** touches Ethereum mainnet and holds no real key or funds. The keeper refuses any chain id other than
31337/1337 (`KeeperService.start`). It shows that the keeper runs 24/7 without a laptop. It does not protect a real
position.

## Railway setup

1. **Service source:** repo `Amine097/defi-hackathon-2026`, branch `main`. The error mentioned commit `82198b4a`, which
   exists neither locally nor on GitHub `main`. Check in *Settings → Source* that the service points at this repo/branch.
2. **Volume:** *Settings → Volumes → New volume*, mount path **`/data`**. Without it, every deploy starts a new chain and
   the evidence history is lost. Volumes cannot be declared in `railway.json`.
3. **Variables** (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | injected by Railway | status API port |
| `FAULTLINE_DATA_DIR` | `/data` | persistent state (chain, journal, evidence, keystore) |
| `FAULTLINE_KEEPER_INTERVAL` | `3` | keeper tick (s) |
| `FAULTLINE_BLOCK_TIME` | `6` | Anvil block time (s); confirmations need new blocks |
| `FAULTLINE_ADMIN_TOKEN` | unset | enables `POST /admin/shock` (demo); unset = 404 |

4. **Networking:** *Settings → Networking → Generate domain*.
5. Deploy. `railway.json` sets the Dockerfile builder, the start command, healthcheck `/healthz`, restart ON_FAILURE,
   and 1 replica (the keeper also holds a single-writer lease lock).

Expected first-start logs:

```
[railway-keeper] bootstrapping the local test world (Morpho Blue v1.0.0 + RescueVault, test tokens)
[railway-keeper] armed test position: vault 0x… (owner 0x3C44…93BC, keeper 0x7099…79C8)
[railway-keeper] keeper service started (pid …)
[railway-keeper] status API on 0.0.0.0:<PORT> (local-test: …)
```

Later starts log `chain state reloaded: vault 0x… present at block N`, and the keeper resumes from its journal.

## Routes

| Route | Result |
|---|---|
| `GET /healthz` | 200 when the keeper heartbeat is fresh and OK, else 503 (stale after max(3 × interval, 15) s) |
| `GET /` | service description, environment label, test vault |
| `GET /api/countermove?action=keeper-status` | same schema as the Vercel endpoint |
| `GET /api/countermove?action=policy-status[&vault=]` | lifecycle state and gates (defaults to the test vault) |
| `GET /api/countermove?action=evidence[&source=store\|recorded\|all]` | hash-chained evidence store |
| `POST /admin/shock?usd=1880` + `Authorization: Bearer <token>` | **simulated** feed move on the local chain |

Limits: JSON only, CORS `*`, 120 requests/min per IP (10/min for admin), generic 500s (details stay in the logs).

Demo (about 15 s): `curl -X POST -H "Authorization: Bearer $TOKEN" https://<domain>/admin/shock?usd=1880`, then poll
`policy-status`: MONITORING → EXECUTING → VERIFIED (2 confirmations).

## Verified locally (Docker Desktop, 11 Oct 2026)

- `docker build -f Dockerfile.keeper` succeeds: Foundry 1.8.5, pinned deps, full `forge build`. Image is about 1 GB.
- First boot on an empty volume: healthy in about 7 s.
- Status routes behave as described: 400 for an invalid action, 404 for an unknown route, 401 for an admin call without
  the token.
- Shock to 1,880 → MONITORING → EXECUTING → VERIFIED in about 15 s. The evidence hash chain is valid.
- `docker restart`: graceful SIGTERM shutdown, the chain reloads from `/data`, the state stays VERIFIED, the evidence
  chain stays valid.

## Showing it in the app (Vercel)

The browser cannot call the Railway domain (CSP `connect-src 'self'`). Instead, `/api/countermove` on Vercel reads it
server-side (`src/defirisk/countermove/remote.py`) for `keeper-status`, `policy-status` and `evidence`:

1. In Railway, generate a public domain for the service.
2. In Vercel → Project → Settings → Environment Variables (Production), set
   `FAULTLINE_KEEPER_URL=https://<railway-domain>` (https only; no path or query). Then redeploy.
3. Open `/app.html#autonomous`. Tab 3 "Autonomous protection" shows **LOCAL TEST** and polls every 5 s:
   - the lifecycle state and gate checklist (G18)
   - keeper health with heartbeat age (G19)
   - the latest evidence rows with the hash-chain integrity badge (G20)
   - a permanent row "RescueVault deployed on Ethereum mainnet: NO"

Without the variable, or if Railway does not answer, the tab falls back to **UNAVAILABLE** and shows the original design
target. The payload carries `hosted.status = UNREACHABLE` and never reports a fabricated OK. The proxy is read-only:
admin routes are never proxied.

## Limits and recovery

- **Not mainnet.** Even when the tab shows LOCAL TEST, it is a test chain inside the container with a simulated feed.
  No real position is protected.
- If `/data/anvil-state.json` is lost or corrupted, the service archives the old `/data/keeper` to
  `keeper-archived-<ts>` and bootstraps a fresh test world. It never mixes a journal with a different chain.
- If Anvil or the keeper exits, the process exits with code 1 and Railway restarts it.
- Deploying requires a push to `main`, which also redeploys Vercel.
