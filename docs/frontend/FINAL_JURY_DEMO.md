# Final jury demo: 90 seconds

App: https://faultline-sandy-three.vercel.app/app.html. Every deep link below opens **DEMO · RECORDED DATA**: saved
live backend runs from block ~26,166,580, shown with the label RECORDED LIVE RUN. It needs no RPC and loads in under a
second, so it is also the fallback if the live API is slow. Production check (11 Oct): `/app.html`, both recorded JSON
files and `/api/countermove` all return 200.

Arc: **DISCOVER → QUANTIFY → DECIDE → DEFEND → PROVE.** Open the tabs below in advance, in this order.

| # | Time | Screen (deep link) | Say | Point at |
|---|---|---|---|---|
| 1 | 0–15 s | `/app.html#positions` (Belem RWA EURCV vault) | "Start from one Morpho vault address. FAULTLINE discovers what your deposit actually depends on: markets, collateral, oracles, issuers." | Vault allocations, read at a mainnet block |
| 2 | 15–30 s | `/app.html#xray` (PT-reUSD on Morpho, $1M) | "Here is the dependency graph for a Pendle PT position: Pendle contracts, reUSD, its issuer, USDC, the dollars behind it, Ethereum." | Graph nodes; click **Pendle PT/SY** to show the conditional row |
| 3 | 30–45 s | `/app.html#demo` (Dashboard) | "Probability-weighted, staying costs **$761** over 30 days (band $39–$19,664). Exiting costs **$5,448**: $1,217 execution plus carry forgone. Verdict REVIEW, lean STAY; it holds unless the risk is 7× our estimate." | Verdict card, loss band, sources |
| 4 | 45–60 s | `/app.html#simulate` | "What if the dollars behind reUSD lose 30%? The conditional loss is **$216k**: EXIT. A Pendle exploit costs **$193k**. These are *if-it-breaks* numbers, not forecasts. The $761 is their probability-weighted sum." | Simulation result; label SIMULATED |
| 5 | 60–80 s | `/app.html#replay` (S1 replay; press play) | "Defense. On a local mainnet fork the owner pre-armed a RescueVault. We simulate a 9% weETH oracle shock. LTV hits 82.4%, above the 82% trigger. The keeper repays **1,086.50 USDC** from the reserve. The user signed nothing during the crisis." | T3 DETECTED → T5 FORK CONFIRMED → T6 VERIFIED ON FORK |
| 6 | 80–90 s | `/app.html#activity` | "Every step is journaled and verified from the receipt and events. Analysis is live on mainnet, read-only. Execution is proven on a fork and on our hosted test keeper. Mainnet autonomous execution is not deployed, and we say so in the app." | Evidence rows; Autonomous tab chip **LOCAL TEST** and its "deployed on Ethereum mainnet: NO" row |

## Figures to quote, and their sources

| Figure | Meaning | Source |
|---|---|---|
| $761 | 30-day expected loss of $1M PT-reUSD, unlevered | `analyze-pt.json` `decision.expected_loss_usd` |
| $5,448 | Exit side: $1,217 execution + $4,230 carry | `decision.exit_total_usd` |
| $216,597 / $192,784 | Conditional loss if the base asset (−30%, assumed) / the Pendle contracts (−19.2%, calibrated) fail | `stress_table`; see `docs/backend/FIGURE_TRACEABILITY.md` |
| $656 vs $2,109 | Belem vault: expected loss vs exit side (forceDeallocate route, simulated) | `vault-belem.json` `decision` |
| 1,086.50 USDC, 82.4% > 82% | S1 fork rescue: repay amount, LTV that tripped the trigger | `data/countermove/demo/latest/summary.json` |

## Live keeper beat (hosted on Railway, shown in the app)

This was tested in production on 11 Oct. It went MONITORING → EXECUTING → VERIFIED in about 20 s, repaid 924.56 USDC
from the reserve, and the hash chain stayed valid.

**Before the demo**
- Open `https://faultline-sandy-three.vercel.app/app.html#autonomous`.
- Check that tab 3 shows **LOCAL TEST**, Status **MONITORING**, Reserve **3,000 USDC**, Actions executed **0**.
- If it already shows VERIFIED, ask Amine to wipe the Railway volume (Railway → volume `/data` → Settings → Wipe Volume).
  The keeper boots a fresh test chain in about 20 s.
- Do **not** run the shock beforehand: the 1-hour policy cooldown blocks a second action.

**During the demo**
1. Keep a terminal open next to the browser and run:
   `curl -X POST -H "Authorization: Bearer <admin token>" "https://defi-hackathon-2026-production.up.railway.app/admin/shock?usd=1880"`.
   This moves only the **simulated** ETH/USD feed on the test chain.
2. The tab refreshes every 5 s. Point at these changes:
   - Status goes EXECUTING → **VERIFIED**.
   - Reserve drops from 3,000 to about 2,075 USDC.
   - Actions executed goes 0 → 1.
   - The evidence log fills in: decision → validation → execution attempt → receipt → verification → finality, with the
     block and tx hash. The badge reads HASH CHAIN VALID.
3. Say: "Nobody signed anything during the crisis. The keeper detected it, picked the action, executed it and verified
   it on-chain. This is a test chain, not mainnet: the last gate says so."

If Railway is unreachable, the tab falls back to **UNAVAILABLE** (intentional and honest). Use the S1 fork replay
instead (beat 5).

## Do not say

- "Live protection on mainnet" or "it would have saved $X". There is no mainnet RescueVault and no mainnet transaction.
- "$216k expected loss". It is conditional, not expected.
- "Real-time" for DEMO screens. They are recorded runs: point at the block number.
