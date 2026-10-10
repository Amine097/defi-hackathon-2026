# Implementation Spec — Whale Impact Analyzer for "FAULTLINE / Last Exit"

## 0. Context (read first)

We are competing in the **Belem Capital track** of the BSA EPFL hackathon (Lausanne, 10–11 Oct 2026, submission deadline **Sunday 11:00 CEST**).

**Who Belem is (from their official challenge brief):** a Luxembourg-based on-chain asset manager (~$400M AUM, track record since Oct 2020) running **market-neutral yield strategies** across **stablecoin, ETH, BTC and SOL** mandates, via a registered fund, segregated managed accounts and **curated vaults**. They monitor 39+ protocols and 20+ blockchains in real time and report zero security incidents, counterparty defaults or liquidations. **Do not describe any past incident as Belem's** in code, docs or messages.

**The challenge:** automatically identify the dependencies of a position, estimate the economic impact on that position when one of them is affected, and answer: **stay, or is the expected loss high enough to justify exiting despite execution costs?** Their framing: *ten pockets of 10%; one is affected; unwinding costs 11% slippage; exiting is expensive and certain, staying is cheap and uncertain — make that trade-off explicit.*

Judging: dependency discovery 30%, **impact estimation ("is the number defensible") 30%**, decision usefulness 25%, working demo on real data 15%.

### Why "Impact Analyzer" and not "Whale Tracker"

Raw whale tracking is noisy and easy to misread:
- moving funds between wallets of the same owner, or to a custodian, is **not** a sell;
- headline transfer sizes say nothing about what happens to *our* position;
- copy-trading-style "whale signals" are hard to interpret and often misleading.

So this module **does not alert on transfers**. It only reacts to transactions that **touch a tracked market** (swaps in exit pools, withdrawals/borrows/liquidations in lending markets, deposits/withdrawals in vaults), and for each one it answers:

> **"What did this transaction change for us — price, oracle, leverage, liquidations, exit cost — and what should the portfolio manager do?"**

Size alone never makes something important. **Impact** does.

### How this module fits Belem's brief (IMPORTANT — read before anything else)

Belem's whole decision is a comparison between two costs:

- **the cost of staying** — the expected loss if a dependency fails (computed by the team's risk engine);
- **the cost of exiting** — slippage and execution costs (their own example: unwinding one pocket costs 11% in slippage).

**This module owns the "cost of exiting" side.** Its job is to make that number realistic: not "what would I pay if I sold alone, right now, in a calm market", but "what will exiting really cost under stress, when large holders leave before us, and how fast is that cost growing".

| Part of the system | Question it answers |
|---|---|
| Resolver (teammate) | What does the position depend on? |
| Risk engine (teammate) | How much could we lose by **staying** if a dependency fails? |
| **This module** | How much will **exiting** really cost, now and under stress? |
| Verdict (risk engine) | Compare the two → stay or exit, and why |

Three non-negotiable conditions:

1. **Framing.** In code, API names, docs and any user-facing text, present this module as the **exit-cost / liquidity-under-stress layer**. Do not brand it as a "whale tracker". Whales are only one input. Prefer names like `exit_cost`, `liquidity_stress`, `impact` over `whale_*` for public endpoints and headlines (internal module names may keep `whale`).
2. **Plug into the verdict.** The module's numbers must flow into the stay/exit decision. Mandatory outputs per position, exposed at `GET /exit-cost/{position_id}` and pushed to the risk engine when available:
   - `exit_cost_alone_pct` / `_usd` — exiting now, alone;
   - `exit_cost_stressed_pct` / `_usd` — exiting after the worst configured scenario (top holders first, forced liquidations);
   - `stuck_share` — share of the position that cannot be withdrawn immediately (lending/vault positions);
   - `exit_cost_trend` — change over the last 1h/6h/24h (is exiting getting more expensive?);
   - `method`, `assumptions`, `as_of`, `data_sources`.
   If this module only feeds a standalone screen, it contributes almost nothing to the grade. Coordinate the exact payload with the risk engine owner early.
3. **Stay a supporting module.** The dependency graph and the verdict are the core of the project and carry most of the grade (discovery 30%, impact 30%, decision 25%). Never block or delay them. Build in the priority order below and stop where time runs out.

**Priority order for the 24h (overrides any other ordering in this document):**

1. **Market snapshot (context layer, §7)** — available liquidity, oracle price and class, liquidation ladder, exit curve. This is what the risk engine needs most.
2. **What-if mode (§9) with the two differentiating features (§8b)** — exit-queue position ("liquidity covers the 6 largest holders; behind them we are stuck") and forced sellers under a dependency shock ("if USDe loses 5%, 3 leveraged positions will be forced to sell $12M before us; our exit cost goes from 0.4% to 3.8%"). Most useful for the decision, most original, easiest to demo.
3. **`GET /exit-cost/{position_id}`** feeding the verdict (condition 2), with ranges and data-quality fields (§8c.4–8c.5), plus the **time-left countdown (§8d)** and its `TIME_LEFT_SHORT` alert.
4. **Validation against real past trades, time to exit and exit plan (§8c.1–8c.3)** — what makes the numbers defensible and actionable.
5. **Replay of one real past transaction (§12)** and offline demo mode (§8c.6).
6. **Live transaction watcher (§5–6)** — only if 1–5 are done.

**Human actions (not for the agent — the human owner of this module does these):**
- Meet the Belem team early with a first version. Ask which markets/vaults they use as reference cases and how they estimate exit costs today; adapt the configured positions accordingly.
- Agree the exact `GET /exit-cost` payload with the risk engine owner before M5.
- Fill in every address placeholder in `config.yaml`.

**Pitch sentence to keep in mind:** *"The rest of the system tells you what staying could cost. This layer tells you what exiting will really cost — and the verdict compares the two."*

---

## 1. Scope

### In scope
1. **Detection**: watch on-chain events of tracked contracts (Morpho Blue markets, MetaMorpho vaults, Pendle markets; optional DEX pools) and pick up large, market-touching transactions.
2. **Filtering & classification**: drop noise, group related transactions, label actors, classify intent with an explicit confidence level.
3. **Impact pipeline** (the core): market state → price → oracle → leveraged positions & liquidation thresholds → cascade → our position & portfolio.
4. **What-if mode**: run the same pipeline on a **hypothetical** transaction ("what if the largest holder sells $X?").
5. **Context layer**: periodic snapshots of market state, top holders and the liquidation ladder — the baseline the pipeline needs.
6. **TVL concentration** of protocols in the dependency graph (explicitly mentioned in the brief).
7. **Outputs**: impact reports via HTTP API, and events in the shared alert format (consumed by the Telegram layer).
8. **Replay**: run the pipeline on real past transactions for a deterministic demo.

### Out of scope
- Plain ERC-20 transfer alerts. Transfers may be used only as *context* for classification (e.g. "funds came from a CEX"), never as triggers.
- Building the dependency resolver, risk engine or dashboard (integrate via §10).
- Trading.

---

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Chain access | JSON-RPC over `httpx` or `web3.py` (`RPC_URL`, ideally an **archive** node for replay) |
| Indexed data | Morpho GraphQL API (markets, positions, vaults, transactions) |
| API server | `FastAPI` + `uvicorn` |
| Models | `pydantic` v2 |
| Storage | SQLite (`data/impact.db`) |
| Numerics | `numpy` |
| Tests | `pytest`, `pytest-asyncio` |

---

## 3. Project structure

```
impact/
├── README.md
├── .env.example            # RPC_URL, MORPHO_API_URL, ALERTS_URL, ALERTS_KEY, RISK_API_URL, ETHERSCAN_API_KEY (optional)
├── config.yaml
├── requirements.txt
├── abis/                   # ABIs fetched from verified sources (never hand-invented)
├── app/
│   ├── main.py             # FastAPI + background tasks (watcher, context poller)
│   ├── settings.py
│   ├── models.py           # MarketTx, Actor, ImpactStage, ImpactReport, ContextSnapshot, Event
│   ├── store.py
│   ├── sources/
│   │   ├── rpc.py          # eth_getLogs, eth_call (with block number), eth_getCode
│   │   ├── morpho.py       # GraphQL client
│   │   ├── pendle.py       # market state + quotes
│   │   ├── oracles.py      # read Morpho oracle price(), classify oracle type
│   │   └── defillama.py
│   ├── watcher.py          # log polling → MarketTx
│   ├── filters.py          # size thresholds, noise removal, grouping
│   ├── classify.py         # actor labels, intent + confidence
│   ├── context.py          # periodic snapshots: market state, holders, liquidation ladder, exit curve
│   ├── pipeline/
│   │   ├── market_state.py
│   │   ├── price.py
│   │   ├── oracle.py
│   │   ├── leverage.py     # liquidation ladder recomputation
│   │   ├── cascade.py
│   │   └── position.py     # our position + portfolio effects
│   ├── analyzer.py         # runs the pipeline → ImpactReport
│   ├── whatif.py           # hypothetical transactions through the same pipeline
│   ├── tvl_concentration.py
│   ├── impact_text.py      # all templates
│   ├── events.py           # shared alert format
│   └── replay.py
├── data/
│   ├── labels.json
│   └── recorded/
└── tests/
```

---

## 4. Configuration

```yaml
chain_id: 1

positions:
  - id: pt-susde-morpho
    name: "PT-sUSDe · Morpho"
    size_usd: 1000000
    our_address: null                  # optional; if set, compute our own health/queue exactly
    role: borrower_collateral          # supplier | vault_depositor | borrower_collateral | lp
    tracked:
      morpho_markets: ["0x<market_unique_key>"]          # FILL IN — never guess
      metamorpho_vaults: []
      pendle_markets: ["0x<pendle_market_address>"]      # FILL IN — never guess
      dex_pools: []
  - id: pendle-usdc-vault
    name: "Pendle Ecosystem USDC Vault (Morpho)"
    size_usd: 1000000
    role: vault_depositor
    tracked:
      morpho_markets: []               # auto-filled from the vault allocation at startup
      metamorpho_vaults: ["0x<vault_address>"]           # FILL IN — never guess
      pendle_markets: []

contracts:
  morpho_blue: "0x<morpho_blue_singleton>"   # FILL IN from Morpho's official docs; verify on Etherscan

watcher:
  poll_seconds: 30
  confirmations: 2
  max_block_range: 2000

filters:
  min_tx_usd: 250000
  min_share_of_liquidity: 0.02       # OR the tx is ≥ 2% of market liquidity / pool depth
  group_window_minutes: 30           # same actor, same market → one grouped action

severity:                            # impact-based, NOT size-based
  red:
    newly_liquidatable_usd: 5000000
    our_exit_cost_increase_pct: 1.0  # +1 percentage point of exit cost
    oracle_move_pct: 3.0
    liquidity_drop_pct: 30
    our_health_drop_to: 1.10
  orange:
    newly_liquidatable_usd: 1000000
    our_exit_cost_increase_pct: 0.3
    oracle_move_pct: 1.0
    liquidity_drop_pct: 10
    liquidation_within_5pct_usd: 2000000

context:
  poll_minutes: 5
  top_n_holders: 50
  ladder_steps_pct: [1, 2, 3, 5, 8, 10, 15, 20]

cascade:
  max_iterations: 10
  convergence_usd: 10000
```

At startup, print a clear warning listing every placeholder still unfilled. Explain in the README how to find market keys (Morpho app URLs / API), vault addresses, Pendle market addresses and the Morpho Blue singleton address (official Morpho docs, verified on Etherscan).

---

## 5. Detection (watcher)

### 5.1 What to listen to
Fetch ABIs from verified sources (Etherscan verified contracts or official repos) into `abis/`. **Never hand-write event signatures from memory; derive topics from the fetched ABI.**

| Contract | Events of interest | Why |
|---|---|---|
| Morpho Blue (singleton, events indexed by market id) | `Supply`, `Withdraw`, `Borrow`, `Repay`, `SupplyCollateral`, `WithdrawCollateral`, `Liquidate` | Liquidity, leverage and liquidation changes in tracked markets |
| MetaMorpho vaults (ERC-4626) | `Deposit`, `Withdraw`; plus allocation changes (reallocate events, if present in the ABI) | Depositor flows and the vault's market exposure |
| Pendle markets | `Swap` (and liquidity add/remove events from the ABI) | Price moves in the PT exit pool |
| Optional DEX pools | `Swap`, liquidity events | Price sources for market-following oracles |

### 5.2 How
- Poll `eth_getLogs` every `poll_seconds` from the last processed block (minus `confirmations`), filtered by contract address and topics (market id topic for Morpho Blue).
- Fallback / backfill: Morpho GraphQL API transaction history for the tracked markets/vaults (introspect the schema first; do not invent fields).
- Convert raw amounts to USD with the market's asset prices (Morpho API USD fields or on-chain oracle; record which).
- Persist every decoded event as a `MarketTx` (`tx_hash, block, ts, contract, market_id, event, actor, assets, usd_value, raw`).

---

## 6. Filtering & classification

### 6.1 Filters (drop noise early)
Keep a transaction (or grouped action) only if:
- it is one of the market-touching events above, **and**
- `usd_value ≥ min_tx_usd` **or** `usd_value / relevant_liquidity ≥ min_share_of_liquidity`.

Group events from the same actor in the same market within `group_window_minutes` into one **action** (split orders are common).

### 6.2 Actor labelling
Priority: `data/labels.json` → Morpho API (MetaMorpho vault names) → contract detection (`eth_getCode`; Safe detection via `getThreshold()`) → `unknown` (shortened `0x9a3f…c21e`).

### 6.3 Intent classification (with explicit confidence)
| Pattern | Intent | Confidence |
|---|---|---|
| Large `Withdraw` from a lending market or vault | `liquidity_exit` | high (the liquidity effect is certain, motive is not) |
| `Withdraw` followed by a sell of the same asset in a tracked pool within the window | `exit_and_sell` | high |
| Large `Borrow` against the same collateral, repeated | `leverage_increase` | medium |
| `WithdrawCollateral` bringing health near 1 | `deleveraging_risk` | medium |
| `Liquidate` | `forced_selling` | high |
| Large PT sell `Swap` | `price_pressure` | high |
| Deposits / supply | `liquidity_entry` | high (informational) |

Rules: the **impact is computed regardless of intent**; intent only adds context. Never claim to know *why* an actor moved. Use wording like "consistent with an exit", never "the whale is selling because…".

---

## 7. Context layer (baseline the pipeline needs)

Every `context.poll_minutes`, snapshot per tracked market/vault/pool:
- market state: supply, borrow, available liquidity, utilization, LLTV, oracle address;
- **oracle price** via the oracle's on-chain `price()` (Morpho oracles return the collateral price in loan-asset units scaled by 1e36 adjusted for decimals — verify against the Morpho docs and the oracle's ABI);
- top suppliers / borrowers / vault depositors (top N);
- **liquidation ladder**: for each borrower, the oracle-price drop that makes it liquidatable: `drop* = 1 − borrow / (collateral_value_at_oracle × lltv)`; bucket USD by `ladder_steps_pct`;
- **exit curve** of each pool: quotes at several sizes (Pendle API or the risk engine's quote function) → cumulative cost `C(x) = x − out(x)`, monotone interpolation, conservative convex extrapolation (flagged).
- **oracle classification** (from the resolver if available, else heuristics on the oracle contract + manual config): `market_spot`, `market_twap(window)`, `chainlink_like(deviation, heartbeat)`, `fixed_or_linear` (e.g. PT linear discount), `unknown`.

Store in `context_snapshots`, `holder_snapshots`, `ladder_snapshots`, `exit_curves`. Keep a recorder (`cli record --hours N`) writing JSONL for replay.

---

## 8. The impact pipeline (core — every stage returns numbers + method + assumptions)

Input: one action (real or hypothetical) + latest context. Output: an `ImpactReport` made of ordered `ImpactStage`s.

### Stage 1 — Market state
- Lending: liquidity before/after, utilization before/after. A withdrawal reduces available liquidity; a borrow reduces it; a repay/supply increases it.
- Vault: change in vault total assets and in its withdrawable liquidity `idle + Σ min(vault_supply_in_market, market_liquidity)`.
- Output: `liquidity_change_usd`, `liquidity_change_pct`, `utilization_after`.

### Stage 2 — Price
- Swaps: executed price vs pre-trade price (from pool state or the exit curve) → `pool_price_move_pct`.
- Withdrawals/borrows: no direct price move (`0`, method `"no_direct_price_effect"`).
- Hypothetical sells: use the exit curve: `price_move ≈ marginal price at x vs at 0`.

### Stage 3 — Oracle
| Oracle class | Projected oracle move |
|---|---|
| `market_spot` | = pool price move |
| `market_twap(W)` | pool move × min(1, persistence / W); report the move **if the price stays there for W** |
| `chainlink_like` | 0 from a single on-chain trade unless the move exceeds the deviation threshold on the feed's sources; report `"not directly moved; would update if the move persists across sources"` |
| `fixed_or_linear` | 0 — but compute the **oracle–market gap** (`oracle price vs pool price`) and flag growing gaps as **hidden loss**: the position looks healthy but cannot be sold near oracle value |
| `unknown` | report both bounds (0 and = pool move) and mark low confidence |

### Stage 4 — Leverage & liquidation thresholds
- Recompute the liquidation ladder at the new oracle price.
- Outputs: `newly_liquidatable_usd`, `liquidatable_within_2pct_usd`, `liquidatable_within_5pct_usd` (before vs after), number of borrowers affected, shift of the nearest cliff.
- If `our_address` is set: our health factor before/after and our distance to liquidation.

### Stage 5 — Cascade
```
price_drop = stage3.oracle_move
loop up to max_iterations:
    liq_usd = ladder.liquidatable_at(price_drop) − already_liquidated
    if liq_usd < convergence_usd: break
    collateral sold by liquidators → extra pool price move via exit curve C
    oracle move from that pool move (Stage 3 rules)
    price_drop += extra oracle move
```
- Conservative assumptions to state: liquidators sell immediately into the tracked pool, no arbitrage refill between steps.
- For `fixed_or_linear` oracles the cascade is 0 by construction; say so explicitly and point to the oracle–market gap instead.
- Outputs: `cascade_liquidations_usd`, `final_price_drop_pct`, `iterations`.

### Stage 6 — Our position & portfolio
- **Exit cost now vs before**: `C(our_size)` before and after the action (and after the cascade), in % and $.
- **Crowded exit**: cost if the actors who just moved continue (or if the top-3 holders follow): `C(A + our_size) − C(A)`.
- **Stuck share** for suppliers/vault depositors: liquidity left vs our size after the action.
- **Portfolio**: other configured positions sharing the same market/pool/oracle/issuer, with their exposure.
- If the risk engine is available, request an updated verdict with these inputs (§10) and include it.

### Severity
Computed from **impact thresholds** in config (any RED condition → RED; else any ORANGE → ORANGE; else GREEN). Transaction size never sets severity by itself.

### ImpactReport shape
```json
{
  "id": "...", "as_of": "...", "is_replay": false, "is_hypothetical": false,
  "trigger": {"tx_hashes": ["0x..."], "block": 0, "actor": {"address": "0x...", "label": "Vault: <name>", "kind": "vault"},
              "action": "liquidity_exit", "confidence": "high", "usd_value": 8400000},
  "position_id": "pt-susde-morpho",
  "stages": [
    {"stage": "market_state", "metrics": {"liquidity_change_pct": -0.35}, "method": "...", "assumptions": ["..."]},
    {"stage": "price", "metrics": {"pool_price_move_pct": -0.012}, "method": "...", "assumptions": []},
    {"stage": "oracle", "metrics": {"oracle_move_pct": 0.0, "oracle_market_gap_pct": 0.012}, "method": "fixed_or_linear", "assumptions": ["..."]},
    {"stage": "leverage", "metrics": {"newly_liquidatable_usd": 0, "liquidatable_within_5pct_usd": 12000000}},
    {"stage": "cascade", "metrics": {"cascade_liquidations_usd": 0}, "method": "none_fixed_oracle"},
    {"stage": "position", "metrics": {"exit_cost_before_pct": 0.004, "exit_cost_after_pct": 0.009, "stuck_share": 0.18}}
  ],
  "severity": "RED",
  "headline": "A $8.4M withdrawal cut available liquidity by 35%: 18% of our position could not be withdrawn now.",
  "chain_of_effects": ["Liquidity −35%", "No oracle move (fixed-rate oracle)", "Oracle–market gap now 1.2% (hidden loss)", "Exit cost 0.4% → 0.9%"],
  "action": "Reduce exposure while liquidity remains; re-check in 1h",
  "data_sources": ["rpc logs", "Morpho API", "Pendle quotes"],
  "confidence": "high"
}
```

---

## 8b. Differentiating features (build these — they are what makes the module original)

Whale tracking and market-level concentration analysis already exist in the industry (on-chain analytics platforms, professional risk firms). What makes this module original is that everything is computed **for our specific position** and **linked to dependency failures**, which is the core of Belem's brief. Two features carry this; implement both as part of the what-if layer (§9), right after the context layer.

### 8b.1 Exit-queue position ("are we among those who get out?")

**Idea.** When everyone wants out at the same time, available liquidity is not enough for all holders. Tell the manager **how many holders can fully exit before liquidity runs out, and whether our position is among them**.

**Computation (lending markets and vaults):**
```
L = available liquidity (market) or withdrawable liquidity (vault, see Stage 1)
holders_sorted = same-side holders sorted by size, descending (exclude us)
cum = 0; covered = 0
for h in holders_sorted:
    if cum + h.amount > L: break
    cum += h.amount; covered += 1
liquidity_left_after_covered = L − cum

For each k in {0, 1, 3, covered, all_whales}:
    ahead = top-k holders
    our_withdrawable(k) = max(0, min(our_size, L − Σ ahead))
    our_stuck_share(k)  = 1 − our_withdrawable(k) / our_size
our_break_even_rank = smallest k for which our_stuck_share(k) > 0
```
Outputs: `holders_covered_by_liquidity`, `our_break_even_rank` (how many large holders can leave before we start getting stuck), `our_stuck_share` per k, and a sentence such as:
*"Available liquidity covers the 6 largest holders. If they exit before us, our $2.0M would be fully stuck. Exiting before them is the only way to be sure to get out."*

For AMM exits (selling), the equivalent is the crowded-slippage table: exit cost for k = 0, 1, 3, all whales ahead.

**Honesty rule (mandatory in outputs and docs):** there is **no real queue on-chain** — withdrawals are first come, first served. The ranking is a **scenario** ("if larger holders exit before us"), not a prediction of order. Label it `method: "scenario_largest_first"` and say so in the text.

### 8b.2 Forced sellers under a dependency shock ("who will have to sell before us?")

**Idea.** When a dependency fails, some holders have **no choice**: leveraged borrowers close to liquidation are liquidated automatically, and their collateral is **sold by liquidators before we can react**. Identify them, quantify their forced selling, and compute what it does to **our** exit cost. This links whale behaviour directly to dependency failures — the heart of the brief.

**Inputs:**
- a shock on a dependency node, e.g. `{node: "ethena-usde", type: "depeg", magnitude: 0.05}` — from the risk engine's scenario list or a default set per position (depeg 2/5/10/20%, oracle drop 5/10/20%);
- the mapping from that shock to the **oracle price** of each tracked market (from the resolver/risk engine if available; otherwise assume the collateral's market price moves by the shock magnitude, and apply the Stage 3 oracle rules);
- the borrower list and liquidation ladder from the context layer;
- the exit curve of the pool where liquidated collateral is sold.

**Computation:**
```
oracle_move = oracle_rules(shock, oracle_class)          # Stage 3
forced = borrowers whose drop* <= oracle_move             # liquidated at this shock
forced_usd = Σ collateral seized and sold (apply liquidation incentive if known)
run Cascade (Stage 5) starting from oracle_move           # forced sales push price further
A = total forced selling ahead of us
our_exit_cost_after_shock = C(A + our_size) − C(A)        # crowded slippage
```
Outputs:
- `forced_sellers`: list of addresses (labelled), each with collateral at risk and the shock level at which it is liquidated;
- `forced_selling_usd`, `cascade_liquidations_usd`, `final_price_drop_pct`;
- `our_exit_cost_before_pct` vs `our_exit_cost_after_shock_pct`;
- a sentence such as:
  *"If USDe loses 5%, 3 leveraged positions holding $12M of collateral will be liquidated and sold first. Our exit cost would rise from 0.4% to 3.8%."*

**Fixed/linear oracle case (mandatory):** if the oracle does not follow market price, **nobody is liquidated** by the shock and `forced_selling_usd = 0`. Do not stop there: report the **oracle–market gap** created by the shock and state that the position cannot be sold near oracle value — *"No forced sellers (fixed-rate oracle), but a 5% depeg opens a ~5% gap between the oracle and the market price: a hidden loss on exit."*

**Why it matters for the verdict:** it shows that the cost of exiting is **not fixed** — it jumps when a dependency fails, precisely when the manager needs to exit. Push `our_exit_cost_after_shock_pct` per scenario to the risk engine so the verdict can compare "exit now" vs "exit after the shock".

### 8b.3 Alerts for these two features (mandatory)

Both features are recomputed at every context poll (and immediately after any large transaction in a tracked market). They must **ping the portfolio manager** through the alert layer (Telegram) when the situation gets worse — not only be available on request.

| Event `type` | Trigger | Severity | Example message |
|---|---|---|---|
| `EXIT_QUEUE_SHRINKING` | `our_break_even_rank` decreases (fewer large holders can leave before we get stuck), or `our_stuck_share` for the top-3 scenario rises by ≥ 10 points | ORANGE; RED if `our_break_even_rank ≤ 1` (the largest holder alone would leave us stuck) or `our_stuck_share(top3) ≥ 30%` | "Exit queue shrinking: liquidity now covers only the 2 largest holders (was 6). If they leave first, 45% of our position is stuck." |
| `FORCED_SELLERS_RISK` | For the default shock set, forced selling ahead of us at a **small** shock (≤ 5%) grows by ≥ 30% or crosses a USD threshold, i.e. leveraged positions moved closer to liquidation | ORANGE; RED if `our_exit_cost_after_shock_pct` at a 5% shock ≥ 3× the current exit cost | "Leverage building up: a 5% USDe depeg would now force $12M of sales before us (was $4M). Our exit cost in that case: 3.8% vs 0.4% today." |
| `FORCED_SELLERS_TRIGGERED` | A **real** shock is reported (a `DEPENDENCY_SHOCK` event from the risk engine/oracle monitor, or an observed oracle/market move) and the shock analysis shows forced sellers being liquidated now | RED | "USDe at 0.95: 3 leveraged positions are being liquidated ($12M). Forced sales hit the exit pool before us — exit cost now 3.8%." |

Rules:
- Emit on every evaluation with the **current** severity (including GREEN) and a stable `signal_key` (`EXIT_QUEUE_SHRINKING:<position_id>`, `FORCED_SELLERS_RISK:<position_id>:<node_id>`), so the alert layer can deduplicate and send "resolved" messages.
- Every message states the **effect on our exit** and a recommended **action** (e.g. "exit before the largest holders", "reduce exposure while forced selling is not yet triggered").
- For fixed/linear oracles, `FORCED_SELLERS_*` events are replaced by an `ORACLE_MARKET_GAP` event describing the hidden loss.
- Respect the honesty rules: the queue is a scenario, forced selling is computed from current positions and may change.

### API additions
| Method & path | Returns |
|---|---|
| `GET /exit-cost/{position_id}/queue` | exit-queue position (§8b.1) |
| `POST /exit-cost/{position_id}/shock` body `{node_id, shock_type, magnitude}` | forced sellers + our exit cost after the shock (§8b.2) |
| `GET /exit-cost/{position_id}/shocks` | cached results for the default shock set |

### Tests
- Queue: liquidity covers exactly k holders; we are fully/partly/not stuck; break-even rank correct; method label present.
- Forced sellers: borrowers just above/below the threshold; cascade increases forced selling monotonically with shock size; fixed oracle → zero forced sellers + non-zero gap reported; our exit cost after shock ≥ before.

---

## 8c. Making the numbers defensible and actionable

Belem grades "is the number defensible" (30%) and "stay or exit, and why" (25%). These additions turn the module's outputs from estimates into numbers a risk team can trust and act on.

### 8c.1 Validate the exit-cost model against reality (highest value)

**Idea.** Compare what our model would have predicted for real past trades with what those trades actually paid.

**Procedure:**
1. Find the largest past sells in each tracked exit pool over the last 14–30 days (Pendle market `Swap` events or the Pendle API; never invent routes — verify).
2. For each trade, compute the **realized cost**: executed price vs the pre-trade price. Pre-trade price = pool/market state at `block − 1` via archive `eth_call` on a view/preview function of the market or router, if one exists in the verified ABI; otherwise the implied price of the previous trade in the same block range (flag `method`).
3. Compute the **predicted cost** with our exit-curve method, using the state at `block − 1` when possible; otherwise the nearest recorded curve rescaled by the liquidity ratio (flag `context_approximation: true`).
4. Report per trade: size, realized %, predicted %, error. Aggregate: mean absolute error, bias (do we over- or under-estimate?), number of trades.
5. Use the measured error to size the ranges in §8c.4.

For lending markets, validate the liquidity model the same way: for past large withdrawals, compare predicted liquidity after the action with the actual market state after the block.

Output: `GET /exit-cost/validation` and a one-line summary usable in the pitch, e.g. *"On 12 real trades, our model's error was 0.2 percentage points on average, slightly conservative."* If too few trades exist, say so explicitly; never fabricate a validation.

### 8c.2 Time to exit

**Idea.** Not only "how much does exiting cost", but **"how long does it take to exit at an acceptable cost"**.

**Model (AMM exits):**
- Split our size `S` into `n` equal tranches spaced by `Δt`.
- Liquidity recovery: after a large trade, arbitrage pulls the pool back. Estimate a **recovery half-life** from history (how fast the pool price reverts after past large swaps); if not measurable, default to 30 minutes and flag it as an assumption.
- Cost of a tranche = `C(S/n)` if the pool has recovered, else interpolate with the residual impact of previous tranches (exponential decay with the half-life).
- For target costs `{0.25%, 0.5%, 1%, 2%}`, find the minimal `n` and total time `n × Δt` that keep the total cost under the target.

**Lending/vault exits:** time to withdraw stuck funds depends on borrowers repaying, which is not reliably predictable. Report the current utilization and state "release timing uncertain"; do not invent a duration.

Output example: *"To exit $1M for less than 0.5% total cost: 6 tranches over ~3 hours. Immediately: 0.9%."*

### 8c.3 Exit plan

**Idea.** Turn the numbers into a concrete recommendation: **how much to exit now, and how to exit the rest**.

**Method:** enumerate simple plans — immediate share `∈ {0, 25, 50, 75, 100%}`, remainder in `n ∈ {1…8}` tranches every `Δt` — and score each:
```
plan_cost = exit cost of all tranches (8c.2)
          + expected loss accrued on the remaining exposure while waiting
            (hazard rate × LGD × remaining size × time, from the risk engine)
```
Pick the plan with the lowest total. If the risk engine does not provide a hazard rate, fall back to the plan that meets a target cost with the least time, and say the waiting risk was not priced.

Output example: *"Exit 40% now (0.4%), the rest in 3 tranches over 2h. Total expected cost $6.1k vs $9.0k for an immediate full exit and $14.2k for waiting 24h."*

The plan is a **recommendation for a human**; never present it as an instruction to execute automatically.

### 8c.4 Ranges, not single numbers

Every headline number gets a `low` / `central` / `high`:
- exit-curve uncertainty from the validation error (8c.1) or, if unavailable, ±25% on the cost curve (flagged);
- liquidity uncertainty: available liquidity ±20%;
- liquidation ladder uncertainty: oracle class `unknown` → both bounds (Stage 3).

Display as *"Stressed exit cost: 2.4%–3.8% (central 3.1%)"*. Ranges must widen, never narrow, when data is approximated or stale.

### 8c.5 Data quality and transparency

Every response includes:
- `freshness_seconds` per data source, with a staleness threshold (default 15 min) above which the output is marked `stale`;
- `approximations`: list of what was approximated (extrapolated curve, nearest snapshot instead of block-exact state, default half-life, unknown oracle class…);
- `missing`: inputs that could not be fetched.

Conclusion texts mention the most important caveat in plain words, e.g. *"(curve extrapolated beyond $5M)"*. A severity can never be RED based only on approximated or stale data without saying so.

### 8c.6 Demo resilience

- `DEMO_MODE=offline` serves the latest recorded snapshots, curves and validation results from `data/recorded/` without any network call, with every response flagged `offline: true`.
- Pre-compute and cache all demo scenarios (queue, shocks, time to exit, plan) at startup.
- Target: every demo endpoint answers in under 1 second.

### API additions
| Method & path | Returns |
|---|---|
| `GET /exit-cost/validation` | backtest of the exit-cost model on real past trades (8c.1) |
| `GET /exit-cost/{position_id}/time-to-exit` | tranches and duration per target cost (8c.2) |
| `GET /exit-cost/{position_id}/plan` | recommended exit plan with cost breakdown (8c.3) |

All existing exit-cost outputs gain `low`/`central`/`high`, `freshness_seconds`, `approximations`, `missing`.

### Tests
- Validation: realized vs predicted computed correctly on a synthetic trade; "insufficient data" when fewer than 3 trades.
- Time to exit: more tranches never increase total cost when Δt ≥ recovery time; target unreachable → explicit message.
- Plan: with zero hazard, the cheapest plan is the slowest; with high hazard, immediate exit wins.
- Ranges: low ≤ central ≤ high; ranges widen when approximations are present.
- Staleness: data older than the threshold marks the output `stale`.

---

## 8d. Time left to exit (countdown)

**Idea.** Answer the manager's most urgent question in one number: **"how much time do I have left before exiting becomes too expensive or impossible?"** — based on the trends we actually observe, not on a static snapshot.

### 8d.1 Three runways (each computed per position)

From the recorded snapshots (§7), fit the recent trend of each quantity over a short and a long window (default 1h and 6h; robust linear fit, or exponential if the series is shrinking proportionally). Extrapolate forward until a threshold is crossed:

| Runway | Quantity tracked | Deadline = time until… |
|---|---|---|
| **Liquidity runway** | available liquidity `L(t)` (market or vault withdrawable liquidity) | `L(t) < our_size` (we start getting stuck), and `L(t) < our_size × (1 + safety_margin)` as an earlier warning |
| **Exit-cost runway** | our exit cost `cost(t)` (alone, and stressed) | `cost(t) > max_acceptable_exit_cost`. Default threshold = the **break-even exit cost** from the risk engine (the exit cost at which exiting stops being worth it vs. staying); fallback = config value (e.g. 1%) |
| **Liquidation runway** | distance between current oracle price and the nearest large liquidation cliff (§7 ladder), and the oracle price drift | price reaches the cliff at the current drift (only for oracles that follow market price) |

**Time left = minimum of the three deadlines**, with the binding runway named ("limited by liquidity").

If no quantity is moving adversely, return `time_left: null` with status `"no_deadline"` and the sentence *"No adverse trend: no exit deadline at the moment."* Never show a countdown without an adverse trend.

### 8d.2 Ranges and honesty

- Compute deadlines with both fit windows (1h and 6h) and a ±1 standard-error band on the slope → report `time_left_low` / `central` / `high`.
- Require a minimum history (default ≥ 6 snapshots over ≥ 30 min); otherwise return `status: "insufficient_history"`.
- Label everything as an **extrapolation of current trends**: `method: "trend_extrapolation"`. Text must say "at the current pace", never "will happen at".
- Cap displayed horizons at 72h ("> 72h").
- Recompute at every context poll and immediately after a large transaction (§5). A sudden event (e.g. a large withdrawal) updates the runway at once, since `L(t)` jumps.

### 8d.3 Outputs

`GET /exit-cost/{position_id}/time-left`:
```json
{
  "position_id": "pt-susde-morpho",
  "as_of": "...",
  "status": "deadline",
  "time_left_hours": {"low": 2.1, "central": 3.4, "high": 5.0},
  "binding_runway": "liquidity",
  "runways": {
    "liquidity":   {"hours": 3.4, "current": 14200000, "threshold": 1000000, "trend_per_hour": -3900000},
    "exit_cost":   {"hours": 7.8, "current_pct": 0.004, "threshold_pct": 0.012, "trend_pct_per_hour": 0.001},
    "liquidation": {"hours": null, "note": "fixed-rate oracle: no liquidation cliff from market moves"}
  },
  "headline": "About 3.5 hours left (2–5h) before our position starts getting stuck, at the current pace of withdrawals.",
  "method": "trend_extrapolation",
  "assumptions": ["Withdrawal pace of the last 1h/6h continues", "No new deposits"],
  "data_quality": {"freshness_seconds": 120, "history_points": 36, "approximations": []}
}
```
`status` ∈ `deadline | no_deadline | insufficient_history | stale`.

The dashboard shows it as a countdown next to the verdict: *"Time left to exit: ~3h30 (2–5h) · limited by liquidity"*.

### 8d.4 Alerts

Event `TIME_LEFT_SHORT`, emitted at every evaluation with a stable `signal_key` (`TIME_LEFT_SHORT:<position_id>`):

| Central time left | Severity |
|---|---|
| > 12h or no deadline | GREEN |
| 2h – 12h | ORANGE |
| < 2h | RED |

Also emit when the time left **drops by ≥ 50%** between two evaluations (e.g. 8h → 3h after a large withdrawal), even if the severity band does not change — this is the most useful ping. Message example:
*"⏳ Time left to exit: ~3h (was 8h). A $8.4M withdrawal accelerated the liquidity drain. Action: exit before the largest holders."*

### 8d.5 Tests
- Flat series → `no_deadline`; shrinking series → finite deadline; growing exit cost → exit-cost runway; fixed oracle → no liquidation runway.
- Fewer than 6 points → `insufficient_history`.
- Ranges ordered (low ≤ central ≤ high); horizon capped at 72h.
- A jump in liquidity (large withdrawal) shortens time left immediately and triggers `TIME_LEFT_SHORT` when it drops ≥ 50%.

---

## 9. What-if mode

`POST /impact/simulate` with `{position_id, actor: "top1|top3|<address>|custom", action: "withdraw|sell|borrow", usd_value}` → same pipeline, `is_hypothetical: true`.
Precompute and cache standard scenarios per position every context poll:
- "largest supplier withdraws everything",
- "top-3 holders sell $X into the exit pool",
- "10% oracle-price drop" (to show the cascade).
These answer the manager's question *"how bad could it get, and how expensive would exiting become?"* even when no large transaction is happening.

---

## 10. Integration

### Provided (HTTP)
| Method & path | Returns |
|---|---|
| `GET /health` | status, last processed block, last context poll, unfilled placeholders |
| `GET /exit-cost/{position_id}` | **Main output for the verdict:** exit cost alone vs stressed (% and $), stuck share, 1h/6h/24h trend, method, assumptions (see §0) |
| `GET /impact/recent?position_id=&min_severity=&limit=` | recent ImpactReports |
| `GET /impact/{id}` | one report |
| `POST /impact/simulate` | hypothetical report (§9) |
| `GET /context/{position_id}` | latest market state, top holders, ladder, exit curve, oracle class |
| `GET /concentration/tvl` | protocols in the graph, TVL, chain share, severity |

Every response includes `as_of`, `data_sources`, and per-number `method`/`assumptions` where relevant.

### Consumed (optional, with fallbacks)
- Risk engine (`RISK_API_URL`): position size/address, exit-quote function, `POST /api/verdict` with our impact inputs. Agree the exact shapes with the team; fall back to local computations.
- Resolver: oracle class and protocol nodes per position. Fallback: `config.yaml`.

### Events (shared alert format, consumed by the Telegram layer)
```json
{
  "ts": "...", "source": "whale_watcher", "type": "LARGE_TX_IMPACT",
  "position_id": "pt-susde-morpho", "node_id": "morpho-market-<key>",
  "severity": "RED",
  "title": "$8.4M withdrawal: liquidity −35%, 18% of position stuck",
  "details": ["Actor: Vault <label> (consistent with an exit)", "No oracle move (fixed-rate oracle)",
              "Exit cost 0.4% → 0.9%"],
  "action": "Reduce exposure while liquidity remains",
  "metrics": {"liquidity_change_pct": -0.35, "stuck_share": 0.18, "exit_cost_after_pct": 0.009},
  "signal_key": "LARGE_TX_IMPACT:pt-susde-morpho:<tx_hash>",
  "link": "http://localhost:3000/impact/<id>"
}
```
Other event types from this module: `LIQUIDATION_CLIFF_NEAR`, `ORACLE_MARKET_GAP`, `LIQUIDITY_DRAIN`, `CROWDED_EXIT_COST`, `TVL_CONCENTRATION`, and the three events of §8b.3: `EXIT_QUEUE_SHRINKING`, `FORCED_SELLERS_RISK`, `FORCED_SELLERS_TRIGGERED`. Emit GREEN states too (stable `signal_key`) so the alert layer can send "resolved". If `ALERTS_URL` is empty, append to `data/events.jsonl`.

---

## 11. TVL concentration (brief requirement)

For each protocol node of a position (resolver or config): protocol TVL and `chain_share = protocol TVL on chain / chain TVL` from DefiLlama (`https://api.llama.fi/protocols`, `https://api.llama.fi/v2/chains` — verify shapes; cache 1h). Severity by thresholds; list positions depending on each concentrated protocol.

---

## 12. Replay (critical for the demo)

- `cli find-large-tx --days 14 --position pt-susde-morpho`: scan logs (or the Morpho API) for the largest market-touching actions in tracked markets over the period; store candidates.
- `cli replay-tx <tx_hash>`: run the pipeline with context **at block − 1** via archive `eth_call`/historical snapshots when available; otherwise use the nearest recorded snapshot and mark `context_approximation: true`.
- `cli replay-session data/recorded/<file>.jsonl --speed 60`: replay recorded snapshots + transactions.
- All replayed reports carry `is_replay: true`; events are labelled `[REPLAY]` by the alert layer.

Goal: in the pitch, show a **real past transaction** from a tracked market and its full chain of effects in a few seconds.

---

## 13. Storage

```sql
CREATE TABLE IF NOT EXISTS market_tx (tx_hash TEXT, log_index INTEGER, block INTEGER, ts TEXT, contract TEXT,
  market_id TEXT, event TEXT, actor TEXT, assets REAL, usd_value REAL, raw_json TEXT,
  PRIMARY KEY (tx_hash, log_index));
CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, actor TEXT, market_id TEXT, intent TEXT, confidence TEXT,
  usd_value REAL, first_ts TEXT, last_ts TEXT, tx_hashes_json TEXT);
CREATE TABLE IF NOT EXISTS impact_reports (id TEXT PRIMARY KEY, ts TEXT, position_id TEXT, severity TEXT,
  is_replay INTEGER, is_hypothetical INTEGER, report_json TEXT);
CREATE TABLE IF NOT EXISTS context_snapshots (ts TEXT, scope_id TEXT, scope_type TEXT, state_json TEXT);
CREATE TABLE IF NOT EXISTS holder_snapshots (ts TEXT, scope_id TEXT, side TEXT, address TEXT, amount_usd REAL,
  collateral_usd REAL, borrow_usd REAL);
CREATE TABLE IF NOT EXISTS ladder_snapshots (ts TEXT, market_id TEXT, drop_pct REAL, liquidatable_usd REAL);
CREATE TABLE IF NOT EXISTS exit_curves (ts TEXT, pool_id TEXT, size_usd REAL, out_usd REAL, method TEXT);
CREATE TABLE IF NOT EXISTS labels (address TEXT PRIMARY KEY, label TEXT, kind TEXT, source TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS watcher_state (key TEXT PRIMARY KEY, value TEXT);  -- last processed block, etc.
```
Timestamps in UTC ISO 8601.

---

## 14. Tests

- `test_filters.py`: transfers never trigger; small tx dropped; tx ≥ 2% of liquidity kept even below `min_tx_usd`; grouping of split orders.
- `test_oracle_stage.py`: each oracle class gives the expected move; fixed oracle yields 0 move and a gap; unknown yields bounds.
- `test_leverage.py`: ladder recomputation, newly liquidatable amounts, our health factor.
- `test_cascade.py`: converges; zero for fixed oracle; monotone in initial shock; respects max iterations.
- `test_position.py`: exit cost before/after, crowded cost ≥ alone cost for convex curves, stuck share.
- `test_severity.py`: a huge tx with no impact is GREEN; a moderate tx that pushes $5M into liquidation is RED.
- Live test behind `RUN_LIVE_TESTS=1`: decode real logs from one tracked market over a recent block range.

---

## 15. Milestones

Follows the priority order in §0 ("How this module fits Belem's brief").

1. **M1 (≤1h):** settings, store, Morpho schema introspected, one real market/vault/pool read (state + oracle price + oracle class).
2. **M2 (≤1.5h):** context layer: liquidity, liquidation ladder, exit curve; poller + recorder running continuously. **Start early and keep it running.**
3. **M3 (≤3h):** pipeline stages 1–6 + severity + tests, driven by hypothetical actions first.
4. **M4 (≤2h):** what-if endpoint + cached standard scenarios + **§8b exit-queue position and forced sellers under shock**, with tests.
5. **M5 (≤2h):** `GET /exit-cost/{position_id}` + push to the risk engine (agree payload with its owner) + events + **time-left countdown (§8d)** with tests.
5b. **M5b (≤3h):** §8c — validation on real past trades, time to exit, exit plan, ranges, data-quality fields, with tests.
6. **M6 (≤1h):** replay of one real past transaction (`find-large-tx`, `replay-tx`) + offline demo mode (§8c.6).
7. **M7 (≤1.5h, only if M1–M6 are done):** live watcher decoding real events; filters; grouping; labels.
8. **M8 (≤1h):** TVL concentration, README, demo script.

Commit after each milestone; keep a README "Status" section.

---

## 16. Definition of done

- [ ] `GET /exit-cost/{position_id}` returns exit cost alone vs stressed, stuck share and trend on real data, and the risk engine's verdict uses it.
- [ ] Public names and texts present the module as the exit-cost / liquidity-under-stress layer, not a "whale tracker".
- [ ] Validation (§8c.1) runs on real past trades (or explicitly reports insufficient data) and its error feeds the ranges.
- [ ] Time to exit and exit plan (§8c.2–8c.3) return concrete tranches, durations and cost breakdowns.
- [ ] Every headline number has a low/central/high range and data-quality fields (freshness, approximations, missing).
- [ ] `DEMO_MODE=offline` serves all demo endpoints in under 1 second without network.
- [ ] Exit-queue position (§8b.1) works on real data and is labelled as a scenario, not a prediction.
- [ ] Time-left countdown (§8d) returns a range and the binding runway from recorded history, `no_deadline` when nothing moves adversely, and emits `TIME_LEFT_SHORT`.
- [ ] `EXIT_QUEUE_SHRINKING`, `FORCED_SELLERS_RISK` and `FORCED_SELLERS_TRIGGERED` events are emitted (§8b.3) and reach Telegram through the alert layer (or `data/events.jsonl`).
- [ ] Forced sellers under a dependency shock (§8b.2) works for at least one shock on real data, including the fixed-oracle case.
- [ ] (If time allows, M7) Watcher decodes real market-touching events for at least one Morpho market, one vault and one Pendle market.
- [ ] Plain transfers never produce reports.
- [ ] Each report shows the full chain of effects with numbers, methods, assumptions, confidence and a recommended action.
- [ ] Severity is impact-based (test proves a large no-impact tx stays GREEN).
- [ ] Oracle stage handles at least `market_spot`, `fixed_or_linear` and `unknown` correctly, including the oracle–market gap.
- [ ] What-if endpoint works and standard scenarios are cached per position.
- [ ] Replay of at least one real past large transaction works end to end.
- [ ] Events emitted in the shared format (or `data/events.jsonl`).
- [ ] TVL concentration computed for one position's protocols.
- [ ] All tests pass; no secrets committed; placeholders documented; README lists real vs approximated vs replayed data.

---

## 17. Demo script

1. *"We don't alert on whale transfers — moving funds between wallets means nothing. We only look at transactions that touch markets we depend on, and we measure their impact."*
2. Replay a real past large withdrawal/sell in a tracked market → show the chain: liquidity −X% → price −Y% → oracle (moves or not, and why) → liquidation ladder shift → cascade → **our exit cost before/after**.
3. Show the fixed-oracle case: *"No liquidation, but the oracle–market gap grew: a hidden loss."*
4. What-if: *"If the largest depositor leaves, 18% of our position is stuck and exiting costs 3.1% instead of 0.4%."*
4b. Exit queue: *"Liquidity covers the 6 largest holders. Behind them, our $2M is stuck — exiting first is the only safe option."*
4c. Dependency shock: *"If USDe loses 5%, these 3 leveraged positions are forced to sell $12M before us. Our exit cost jumps from 0.4% to 3.8% — exactly when we would need to leave."*
4c-bis. Countdown: *"At the current pace of withdrawals, about 3h30 left (2–5h) before our position starts getting stuck."* Then replay a large withdrawal and show the countdown drop from 8h to 3h, with the Telegram ping.
4d. Plan: *"To keep the exit cost under 0.5%: exit 40% now, the rest in 3 tranches over 2 hours."*
4e. Credibility: *"We checked the model against 12 real past trades: average error 0.2 points, slightly conservative."*
5. Tie back to Belem's trade-off: *"This is the 'expensive and certain' side of the decision, measured live — and it feeds the stay/exit verdict."*

---

## 18. Rules for the AI agent

- **Never invent addresses, market keys, ABIs, event signatures, API routes or schema fields.** Fetch, introspect, or leave clearly marked placeholders.
- Every number is traceable: `as_of`, `data_sources`, `method`, `assumptions`, `confidence`.
- Prefer conservative assumptions and state them.
- Never infer motives as facts; describe actions and impact.
- Distinguish real, approximated, hypothetical and replayed outputs everywhere.
- Pure functions for stages, filters and severity so they are testable.
- Timeouts on all calls; max 3 retries with backoff; never crash the watcher on one failure; persist the last processed block.
- Do not reference any specific past incident as involving Belem Capital.
- If something is ambiguous or impossible, choose the simplest reasonable option, implement it, and document it under "Deviations from spec" in the README.
