# C. Backend Risks — model correctness, security-sensitive flows, incomplete capabilities

No backend code was changed. Items marked **[BE]** are for the backend owner; **[FE]** are frontend obligations that
must not be solved by silently altering financial outputs in the browser.

## C0. Status of the historical Belem-review concerns (independently re-checked on live data)

| Concern (review §5) | Current status | Evidence (11 Oct, live) |
|---|---|---|
| Role-aware losses (collateral-only vs borrower) | **Fixed in backend** | Edges carry `channel`; with `exposure_role=collateral_only`, debt-channel edges weigh 0. Borrower mode switches them on |
| Can an oracle failure harm a position with no debt? | **No (backend)** — but the **X-Ray UI still says yes** (C1) | Oracle / feed / Morpho market rows: +$0, "no effect without debt"; scenario "Oracle failure" → STAY $761 |
| Pendle AMM impairment vs PT principal | **Fixed** | Split `pendle_core` (principal) vs `amm` (exit channel). Liquidity crisis: loss unchanged, exit side $5,179 → $6,309 |
| Structural LGF assumptions | **Mostly fixed**; residual | Exploit-type LGF calibrated (23 DefiLlama incidents, mean 19.2 %, 95 % CI 9.4–31.5 %). Chain LGF 30 % and look-through what-if 30 % remain assumptions (C6) |
| Transmission weights & sensitivity | **Addressed** | Expert weights with ±25 % band; sensitivity rows for p, LGF and T all keep STAY |
| Hold to maturity | **Implemented** | 60 days: HOLD $1,515 vs EXIT $9,228 → HOLD_TO_MATURITY (low confidence) |
| Book heterogeneity | **Partly** | 10 real Morpho PT markets with shared dependency keys, but only 6 distinct PTs and a carry artefact (C3) |
| Silent mock on failure | **Fixed in backend** (502) — **re-introduced by the UI** (C2) | `api.js:25`, `xray/data.js:37` fall back to `sample.json` |

## C1. [FE, P0] X-Ray recomputes losses client-side and contradicts the model
`public/assets/js/xray/data.js:79` copies `transmission` and drops `channel`; `xray/model.js:136 positionLosses()`
multiplies value × LGF × best-path transmission. Observed in Chrome (screens 05–07):

| Action | Backend | X-Ray shows |
|---|---|---|
| Scenario "Oracle failure" | $761, STAY | same card adds "Client propagation check: $154k lost" (`xray.js:431`) |
| Click "Morpho oracle" | $761, STAY, "no effect without debt" | **EXIT, loss $154k, margin +$148k**, "exiting only pays if odds exceed 3.0 %" (`xray.js:410,416`) |
| Click "Pendle AMM pool" | exit channel only | **EXIT, $192k** |
| Click "Morpho market" | no effect without debt | **EXIT, $192k** |

This is the most visible interaction of the product and it presents unsupported financial numbers — the exact
opposite of the backend's fix. Rule for the redesign: **every dollar value comes from the server** (`stress_table`,
`scenarios`, `?shock=&severity=`); the client may only animate the order of hops.

## C2. [FE, P0] Silent fallback to a superseded snapshot
On any `/api/analyze` failure or timeout (60 s), `api.js:25` and `xray/data.js:37` load `public/data/sample.json`
(committed 10 Oct 17:06, **before** role-aware losses). With a simulated 502 the dashboard shows REVIEW, "MOCK (API
offline)", oracle failure **$321k EXIT**, liquidity crisis **$501k EXIT**, and a borrower line (HF 1.054) that does not
belong to the unlevered headline (screen 03). The data are real but stale, so "MOCK" is also mislabelled.
Required: an UNAVAILABLE state with cause and retry; a snapshot only if regenerated from the current backend and
labelled SAVED SNAPSHOT with block and date.

## C3. [BE, High] Book: one reinvestment rate for every pocket → yield-driven EXIT verdicts
`core/book.py:94`: `carry = V × (pocket implied APY − reference_apy) × H/365`, where `reference_apy` is the analysed
market's loan-asset supply APY (~6.5–7.4 %, a high-yield PT-collateral market). Pockets whose PT yields less than that
get a **negative exit side** (−$584 to −$1,095) and an **EXIT** verdict although the scenario does not touch them
(4/10 pockets in the default run). `total_optimal_usd` sums `min(stay, exit_total)`, so these yield gains also
**reduce the reported book loss** (0.086 % of book). This conflates "rebalance for yield" with "exit for risk".
Options for the owner: per-pocket reference rates (each pocket's own Morpho supply APY); floor the exit side at the
execution cost for the risk verdict; report rebalancing gains in a separate column.
Until fixed, the UI must label such rows "yield rebalance (not a risk signal)" — not re-compute them.

## C4. [BE, Medium] Borrower mode mixes two position sizes
With `borrower=auto`, `decision` (headline) is computed on the hypothetical `value_usd` ($1M), while `liquidation`
analyses the real borrower ($12.66M collateral, $11.06M debt). `leverage.py:81-82` turns scenario losses computed on
$1M into loss fractions applied to the borrower. Outcomes are internally consistent per section, but two verdicts with
different notionals appear side by side (REVIEW on $1M vs borrower REVIEW with $11,276 expected loss vs $206,891
deleverage cost). Owner options: set V to the borrower's collateral value in borrower mode, or mark the headline
"hypothetical exposure" and make the borrower decision primary. UI must never merge the two.

## C5. [BE, Medium] Exit timing is implicit
Scenario and incident comparisons put the **conditional** loss of staying against the cost of exiting at today's quote,
i.e. they assume the position can be sold **before** the shock is priced in. After an observed depeg the PT price, and
therefore exit proceeds, would already be impaired. The brief asks "what it does to your book, **and how fast**";
Reaction Window is spec-only. UI copy must state "assumes you exit before the shock reaches the PT price"; the
backend could add a post-shock exit variant.

## C6. [BE, Medium] Top of the stress table is assumption-driven
Ethereum ($300,446; chain LGF 30 %, 0.5 %/y — `priors.py:24,28`) and "US dollars (bank/T-bills)" look-through
($216,597, what-if 30 %) head the single-failure ranking above calibrated dependencies. The review lists this as an
open point. UI: badge these rows "assumption"; owner: calibrate or band them.

## C7. [BE, Low] Other modelling notes to disclose, not to "fix" in the UI
- Exploit priors are near-identical cohort base rates (0.020–0.044 % per 30 d); the largest expected-loss driver is the
  USDC depeg history ($434 of $761) — counter-intuitive for a reUSD PT; explain it.
- HOLD_TO_MATURITY bands overlap widely (HOLD $77–$35.6k vs EXIT $5.2k–$13.3k): present as a lean; when the incident is
  on the issuer/underlying, holding to maturity does not avoid the principal loss (the incident payload already omits
  the HTM note except for AMM shocks).
- The book's 10 pockets are the largest Morpho PT markets (6 distinct PTs, equal weights, collateral without debt), not
  Belem's book; say so.
- Vault model: severity priors (50 % collateral jump, 40 % oracle mispricing, 10 % depeg); oracle nodes labelled by
  address; "Liquidity crisis" returns $0 loss but withdrawable ≈ $0 — liquidity must be displayed apart from loss;
  EUR-denominated vault shown in USD (FX and peg are decomposed in `vault.asset`, keep both visible).
- `api/analyze.py:5` docstring still documents `mock-fallback` though the code returns 502 (doc drift).
- `docs/frontend/*` older files and `docs/design/countermove/INTEGRATION_MAP.md` claim no Countermove backend exists;
  false since `9532977`.

## C8. Security-sensitive flows

| Flow | Current state | Risk / requirement |
|---|---|---|
| Wallet connection | **None on main** (no EIP-1193/6963 code) | Any future connection must be read-only by default; handle 4001 (user rejected) as neutral |
| Policy authorization (ARM) | `/api/countermove?action=policy-draft` returns validated `setPolicy` calldata; UI says "Sign this…" | No RescueVault is deployed on mainnet and the repo has no deploy script/factory: a sign button would target nothing (or a wrong address). Keep as preview until a deployment exists; if a fork demo is wired, the UI must assert `chainId == 31337` and show the vault address being called |
| Keeper signing | Chain-31337-only keystore signer; plaintext keys refused | Hot key, unaudited contract (security report §7, §9). Never present as production protection |
| API surface | Strict validation (regex ids, ranges, allowlisted URL hosts, never fetched), structured errors, no secrets in responses | Public RPC rate limits; `s-maxage=60` caching on analyze means two users can see the same 60 s-old analysis — show `data_as_of` |
| Frontend rendering | `innerHTML` everywhere but consistently through `esc()`; no `eval`; no third-party origins | Keep the zero-third-party rule (the Claude Design export loads React from unpkg — do not ship that) |
| HTTP headers | `vercel.json` sets none | Add CSP (`default-src 'self'`), `frame-ancestors 'none'`, `Referrer-Policy`, `Permissions-Policy` before any signing UI |
| Deployment | `deploy-vercel.sh` stashes, commits empty, pushes `main` as the owner | Owner-only action; never automated by an agent |
| Real funds | Nothing in the system moves real funds | Keep LIVE (read-only) and SIMULATED (fork) visually unmistakable |

## C9. Incomplete capabilities (do not design as if they existed)
Alerts / Telegram (C5 not done) · wallet → positions · other chains · arbitrary protocols · mainnet RescueVault
deployment · exit-runway endpoint · dedicated Breaking Point engine (the borrower `price_grid` is the honest substitute)
· Whale Impact · Reaction Window · Chain of Blame · Leverage Hunter · Cascade Radar.
