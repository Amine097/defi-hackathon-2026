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
| 6 | 80–90 s | `/app.html#activity` | "Every step is journaled and verified from the receipt and events. Analysis is live on mainnet, read-only. Execution is proven on a fork. Mainnet autonomous execution is not deployed, and we say so in the app." | Evidence rows; Arm tab chip **UNAVAILABLE** |

## Figures to quote, and their sources

| Figure | Meaning | Source |
|---|---|---|
| $761 | 30-day expected loss of $1M PT-reUSD, unlevered | `analyze-pt.json` `decision.expected_loss_usd` |
| $5,448 | Exit side: $1,217 execution + $4,230 carry | `decision.exit_total_usd` |
| $216,597 / $192,784 | Conditional loss if the base asset (−30%, assumed) / the Pendle contracts (−19.2%, calibrated) fail | `stress_table`; see `docs/backend/FIGURE_TRACEABILITY.md` |
| $656 vs $2,109 | Belem vault: expected loss vs exit side (forceDeallocate route, simulated) | `vault-belem.json` `decision` |
| 1,086.50 USDC, 82.4% > 82% | S1 fork rescue: repay amount, LTV that tripped the trigger | `data/countermove/demo/latest/summary.json` |

## Optional live-keeper beat (only if asked "is the keeper real?")

- **Railway** (if deployed per `docs/backend/RAILWAY_KEEPER_DEPLOYMENT.md`): `GET https://<domain>/healthz` → 200 OK.
  `POST /admin/shock?usd=1880` with the admin token, then poll `?action=policy-status`:
  MONITORING → EXECUTING → VERIFIED in about 15 s. This runs on a test chain inside the container, with a simulated feed.
- **Laptop:** the same flow with Anvil and the keeper locally (tested 11 Oct: AWAITING_AUTHORIZATION → ARMED →
  MONITORING → EXECUTING → VERIFIED, 43 hash-chained evidence rows).
- **In the app** (only if `FAULTLINE_KEEPER_URL` is set on Vercel and Railway answers): open `/app.html#autonomous`.
  Tab 3 shows **LOCAL TEST**, the gate checklist, keeper heartbeat, reserve and the evidence log. It refreshes every
  5 s, so after the shock you can watch it go to VERIFIED with the tx rows. Say: "This is a test chain, not mainnet:
  the last gate says so." If the keeper is not reachable, the tab stays UNAVAILABLE. That is intentional and honest.

## Do not say

- "Live protection on mainnet" or "it would have saved $X". There is no mainnet RescueVault and no mainnet transaction.
- "$216k expected loss". It is conditional, not expected.
- "Real-time" for DEMO screens. They are recorded runs: point at the block number.
