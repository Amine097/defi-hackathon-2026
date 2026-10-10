# FAULTLINE — Countermove v3
## Autonomous Dependency-Aware Crisis Response Engine

**Status:** Revised hackathon specification after jury feedback — 10 October 2026
**Purpose:** Explain what changes, which crisis-response strategies we will implement, and how the engine will select and execute them without waiting for the user.

---

## 1. What the jury actually wants

The jury described a practical problem:

> A DeFi crisis, exploit, or cascading failure may start at 4 a.m. or on a Sunday. The user might be asleep. FAULTLINE should already know the defensive actions the user permits, use the position's real dependencies to choose the best feasible response, and **execute the response automatically**.

**Important distinction:** We do **not** need an AI to invent new trades during an attack. We need a reliable engine that **selects among pre-defined, pre-authorized strategies** and executes one when its conditions are met.

### How this changes the previous Countermove

| Previous v2 | New v3 |
|---|---|
| Read risks and recommend a repayment | Monitor risks and **execute** a permitted response |
| User decides and signs during the crisis | User configures permissions, limits, and reserves **before** the crisis |
| Mostly HOLD and debt repayment | Compare several genuinely different defensive actions |
| Show the minimum rescue budget | Use it to decide whether an action is **funded and executable now** |
| Analyze what-if shocks | Combine current conditions, verified dependency scenarios, and execution constraints |
| Success = good recommendation | Success = **confirmed protective on-chain transaction**, or a clear failure/no-action alert |

**New product promise:** *“Configure your emergency defenses once. When a verified crisis threatens your position, FAULTLINE chooses and executes an allowed response—even while you are offline.”*

**Boundary:** This is automated **risk mitigation**, not a guarantee that the system will beat liquidators, stop an exploit, or exit at a favorable price.

---

## 2. The new FAULTLINE pipeline

```text
               BEFORE THE CRISIS
               -----------------
User connects a Morpho position
            |
User selects permitted actions and hard limits
            |
User deposits emergency USDC / eligible collateral
into a restricted rescue reserve (or authorizes a safe
spending mechanism with equivalent limits)
            |
                  ARMED
                    |
                    v
             CRISIS STARTS
             -------------
 [1] WATCHER: on-chain positions + relevant signals
                    |
 [2] DEPENDENCY GRAPH: what actually affects the
     collateral, wrapper, oracle, and liquidation value?
                    |
 [3] CASCADE RADAR: current state + conditional
     dependency-aware stress scenarios
                    |
 [4] COUNTERMOVE: enumerate allowed actions,
     simulate outcomes, reject infeasible options,
     choose the best according to user's policy
                    |
 [5] GUARDRAILS: re-check balances, health, freshness,
     permission limits, gas, and transaction viability
                    |
 [6] EXECUTOR: send the on-chain transaction
                    |
 [7] VERIFY: receipt + new position state; notify user
```

**What each module does:**
- **Dependency Graph / Pendle X-Ray, where relevant:** identifies *why* a position may fail and which actual oracle or collateral dependencies matter.
- **Cascade Radar:** supplies a small set of transparent stress scenarios. They are **not probability forecasts**.
- **Countermove:** asks **“Which authorized action gives the strongest protection in those scenarios, and can it be executed right now?”**
- **Executor:** implements the choice on-chain, under rules fixed by the user in advance.

The key change is **decision support → bounded autonomous action**.

---

## 3. Which crisis-response strategies will we implement?

### Implementation priorities

| Strategy | What it does | Helps with | Hackathon priority |
|---|---|---|---|
| **A. AUTO-REPAY** | Uses pre-funded loan tokens (e.g., USDC) to repay some debt | Liquidation risk from too much debt | **MUST BUILD — autonomous** |
| **B. AUTO-TOP-UP** | Deposits pre-funded, compatible collateral into the threatened Morpho position | Liquidation risk from too little collateral | **MUST BUILD — autonomous** |
| **C. EMERGENCY DEBT CLOSE** | Repays the entire remaining debt if the pre-funded reserve suffices and the policy allows it | Eliminates **borrowing liquidation risk** for that position | **NEXT — autonomous, builds on A** |
| **D. DELEVERAGE + SELL** | Repays debt, releases some collateral, sells it into a safer asset; may require flash liquidity | Liquidation risk **and** continuing collateral price exposure | **STRETCH — only after A/B work** |
| **E. REFINANCE / MARKET SWITCH** | Moves a compatible position to a different Morpho market | A *verified* market-specific oracle/LLTV/rate risk | **STRETCH — only if real compatible markets exist** |
| **F. SHORT / HEDGE** | Opens a short derivative to partially offset asset-price losses | Portfolio price exposure; **not automatically Morpho liquidation risk** | **NOT core MVP** |
| **HOLD / ALERT** | Takes no transaction; logs and notifies | No action needed, or no permitted action is safely feasible | **MUST BUILD as a baseline and safe fallback** |

**Critical terminology:** In a crisis, **increasing leverage** generally makes liquidation risk worse. The protective action is normally **deleveraging** (reducing debt and sometimes reducing collateral exposure). A short position is a hedge, not the same as repaying a loan or closing a Morpho position.

### Strategy A — AUTO-REPAY (core)

**Example:** A user borrowed 8,000 USDC against ETH-linked collateral. After a dependency shock, the position approaches liquidation. FAULTLINE automatically uses **460 USDC from its pre-funded rescue reserve** to repay debt, provided that meets the selected safety target and all permissions.

- **Needed in advance:** USDC reserve; user-approved Morpho market; maximum spend and other policy limits.
- **On-chain action:** Morpho Blue `repay(..., onBehalf=user, ...)`.
- **Why relatively easy:** Morpho permits repayment on behalf of another borrower; it does **not** require authorization to withdraw that borrower's collateral.
- **What changes:** Debt decreases, LTV decreases, borrowing interest expense decreases.
- **What does not change:** The amount of ETH-like collateral held and its gross market exposure.

**Failure cases:** Insufficient USDC; already liquidated; updated debt/price invalidates the plan; transaction delayed or reverted.

### Strategy B — AUTO-TOP-UP (core)

**Example:** The user has very little USDC, but previously deposited eligible WETH into the rescue reserve. FAULTLINE automatically supplies WETH as additional collateral to increase the position's liquidation buffer.

- **Needed in advance:** The **exact collateral token accepted by the selected Morpho market**; pre-funded reserve; maximum collateral commitment.
- **On-chain action:** Morpho Blue `supplyCollateral(..., onBehalf=user, ...)`.
- **Why relatively easy:** Morpho allows supplying collateral for another account.
- **What changes:** Supplied collateral and liquidation buffer increase.
- **What does not change:** Debt stays the same; ETH-like exposure may **increase**.

**Important:** A top-up in a rapidly falling collateral asset can become inadequate quickly. Countermove should compare top-up effectiveness under **the actual dependency-specific stress scenarios**, not just at the present price.

### Strategy C — EMERGENCY DEBT CLOSE (next)

**Example:** The user explicitly permits FAULTLINE to spend up to the remaining 8,000 USDC debt from an already funded reserve to **fully repay** it if a serious crisis occurs.

- **Needed in advance:** Enough loan tokens (including accrued interest and rounding), and explicit permission for a full close.
- **On-chain action:** Full Morpho repayment, with protocol-accurate share/asset handling.
- **Result:** Borrowing liquidation risk becomes zero **once the debt is confirmed as fully repaid**.
- **Limitation:** **This does not sell or withdraw the collateral.** The collateral can still lose market value and may need a separate authorized withdrawal/swap.

This is a separate user policy, but **not a genuinely new technical integration**: it reuses AUTO-REPAY. We should not count it as proof that three independent exit mechanisms were built.

### Strategy D — DELEVERAGE + SELL (stretch; genuinely different)

**Goal:** Reduce debt **and** reduce exposure to the troubled collateral rather than merely adding a financial buffer.

```text
Obtain temporary loan-token liquidity if needed
    -> repay debt
    -> withdraw a safe amount of collateral
    -> swap that collateral into the loan token / safer asset
    -> repay any flash liquidity
    -> return any surplus to the permitted recipient
```

This may require a flash loan, a DEX, a route with strict slippage bounds, and an **atomic** execution path. Morpho allows flash loans, but the full unwind route is **not a built-in Morpho Blue action**. The current Morpho Bundles do not generally compose arbitrary DEX swaps for us.

- **Extra authorization:** Withdrawing collateral **on behalf** of the user needs Morpho authorization or a smart-account execution design.
- **Risk:** Slippage, MEV, liquidity exhaustion, gas spikes, failed routes, flash-loan repayment failure.
- **Hackathon call:** Build *only if* A and B are working end-to-end. Otherwise **simulate and clearly label it as non-executable**.

### Strategy E — REFINANCE (stretch; dependency-specific)

If **two real Morpho markets have the same loan token and collateral token** but different risk parameters or oracle configurations, the user might be able to atomically migrate a borrowing position.

- Morpho's current **BlueBundlesV1** supports full compatible-market borrowing-position migration.
- **Possible benefit:** Reduce a specific liquidation risk when the destination market's actual oracle path, LLTV, liquidity, and borrowing costs make it demonstrably safer.
- **Important:** A different oracle does **not** make an economically impaired asset safe; it may simply report a different price. Do not call this protection unless the economic and liquidation trade-offs are shown.
- **Automation challenge:** The migration entrypoint acts on its **caller**; migrating an ordinary user's position unattended requires an appropriate smart-account/authorization architecture, not just a bot with a transaction key.

**Decision:** Optional only if there is a suitable real market pair and enough time for security testing.

### Why a SHORT is not our first implementation

An ETH short may gain when ETH falls, but **its profits do not automatically reduce the debt or add collateral on Morpho**. A derivative hedge also has its own collateral, funding, liquidation, and exchange risks. We can include it later as a **portfolio hedge**, but the core demo should not confuse *offsetting losses* with *preventing lending liquidation*.

---

## 4. How Countermove chooses the best action

**Never select an action solely from an arbitrary “AI risk score.”** The choice is a deterministic, constraint-aware comparison among actions the user authorized.

For each threatened position and each predefined action, Countermove:

1. Reads the current **accrued debt, collateral, loan token, oracle valuation, LLTV, and reserve balances**.
2. Retrieves verified dependency paths and a small set of conditional shocks from Cascade Radar.
3. Calculates the **post-action liquidation buffer** in every selected stress scenario.
4. Rejects actions that are **not funded, not authorized, unsupported, too expensive, or too slow / uncertain to execute under current conditions**.
5. Among the remaining plans that meet the user's safety target, chooses according to the configured priorities:
   - **First:** obey all hard safety/authorization constraints.
   - **Second:** meet the required buffer **across the chosen scenarios**, if possible.
   - **Third:** preserve emergency liquidity/collateral according to the user's preference; account for transaction costs and risk of failed execution.
6. If no plan meets the target, select the **best bounded mitigation only if the user explicitly allowed partial protection**; otherwise do not transact and send a high-priority warning.

**Simple equations, for one position:**

```text
D            = current accrued debt (loan-token units)
V_s          = current collateral's oracle value under scenario s
LLTV         = market's liquidation threshold
r            = loan tokens repaid
q_s          = scenario-valued collateral added by a top-up
B_s(r,q)     = LLTV * (V_s + q_s) - (D - r)

Target: B_s(r,q) >= safety_margin for EVERY selected scenario s.
```

For **repay**, increase `r`. For **top-up**, increase `q_s` using the *same shock path as the deposited collateral*. For a true sale/deleverage, the model must also deduct collateral sold and adjust debt/swap proceeds. Real protocol math must use token decimals, price scaling, interest accrual, debt shares, and safe rounding.

**Trade-off:** Repaying 500 USDC is not the same economic cost as paying a 500 USDC fee; it reduces debt and consumes liquid reserves. Adding $500 of collateral locks assets and may increase risk-factor concentration. These are different resource commitments, not interchangeable “losses.”

### Worked example — AUTO-REPAY vs AUTO-TOP-UP

*Illustrative only; not real market prices.*

- Current collateral oracle value: **10,000 USDC**; debt: **8,000 USDC**; LLTV: **86%**.
- Stress scenario: underlying collateral loses a further **10%** in the market's actual oracle valuation, so existing collateral becomes **9,000 USDC**.
- User safety policy: after the stress, maintain a **200 USDC buffer below the liquidation debt limit**.

**Option A — Repay:**

```text
Post-shock debt limit = 86% * 9,000 = 7,740 USDC
Allowed debt with buffer = 7,740 - 200 = 7,540 USDC
Minimum repayment = 8,000 - 7,540 = 460 USDC
```

**Option B — Top up:**

```text
Required post-shock collateral value = (8,000 + 200) / 0.86
                                     = 9,534.88 USDC
Extra value needed AFTER the shock   = 534.88 USDC
If the added token suffers the same 10% shock:
  Minimum value to deposit BEFORE shock = 534.88 / 0.90
                                        ≈ 594.32 USDC equivalent
```

**Decision:**
- If there is enough USDC and the user prefers not to lock more volatile collateral, **AUTO-REPAY** may be preferred.
- If there is insufficient USDC but enough *eligible, pre-funded collateral*, **AUTO-TOP-UP** may be the only feasible defense.
- If both are feasible, compare **remaining reserves, capital commitment, fees, and the other dependency scenarios** before choosing.
- If neither achieves the safety target within policy limits, **report no fully safe plan**—do not fabricate certainty.

The values are deterministic **given the modeled scenarios**. They do **not** predict a 10% fall or guarantee on-chain transaction success.

---

## 5. What the user prepares before going offline

Countermove only becomes truly autonomous with **advance permissions and funding**.

### Example rescue policy

```yaml
protected_market: <verified Morpho Blue market ID>
protected_borrower: <user address>
allowed_actions: [REPAY, TOP_UP]
emergency_loan_token_reserve: 1000 USDC
emergency_collateral_reserve: 0.30 WETH
max_repay_per_event: 800 USDC
max_topup_per_event: 0.20 WETH
max_total_spend_or_lock: <user-defined limits>
minimum_retained_reserve: <user-defined amount>
required_scenario_buffer: 200 USDC equivalent
max_execution_gas: <user-defined cap>
allowed_destinations: [Morpho contract / verified market]
automation_enabled: true
```

**The app must not assume it can move tokens from a normal wallet just because the user once clicked “Enable.”** The resources must actually be accessible to the executor, e.g. funds deposited in a **restricted rescue contract** beforehand. A session key or token approval is only a possible authorization mechanism and must be implemented correctly.

### Recommended safe MVP architecture

**User-controlled, pre-funded RescueVault + permissionless trigger / keeper:**

- User deposits a bounded amount of loan token and/or collateral token into `RescueVault`.
- Vault stores the **fixed user, allowed Morpho market(s), asset addresses, spending caps, and expiry/pause controls**.
- When prompted by the watcher, the vault can **only repay debt or add collateral on behalf of the fixed user**.
- Vault never allows the keeper to borrow, send funds to arbitrary recipients, withdraw the user's Morpho collateral, or execute arbitrary calldata.
- The vault reads and checks the relevant on-chain state before calling Morpho; the off-chain strategy engine handles dependency-scenario reasoning.
- User can pause automation and reclaim uncommitted reserves according to explicit withdrawal rules.

**Why this is easier and safer:** Morpho Blue allows **repay** and **supplyCollateral** on behalf of an account. Unlike borrowing or withdrawing collateral, these two operations do not require Morpho's position-management authorization. Therefore A/B can protect an ordinary user's Morpho position without giving the keeper dangerous powers. See Morpho Blue references below.

**Do not give a general-purpose bot unlimited Morpho authorization.** Borrow/withdraw permissions are much more powerful and deserve a separate audited design.

### Who wakes it up at 4 a.m.?

A watcher/automation service reads relevant blocks and calls the executor when a real trigger occurs. The demo can start with a **small Node.js/viem keeper** running against a local fork; a hosted automation service (e.g., Gelato) is optional.

**Important distinction:** The keeper proposes and submits a transaction; **the smart contract enforces limits**. Do not rely on the keeper staying honest or online forever.

---

## 6. Triggering, execution, and fail-safes

### Trigger examples

- Current observed liquidation buffer falls below a user-defined boundary.
- A verified dependency feed deviates sharply or an on-chain incident signal is observed **and** the position is at risk.
- Cascade Radar finds the position fails a selected follow-on stress scenario, and the user's trigger policy explicitly permits acting on that hypothetical scenario.

**Avoid panic trades:** Do not execute purely because Twitter, a dashboard, or an unsupported dependency edge says “crisis.” Also do not treat a stale or reverting oracle as a reliable price.

### Execution sequence

```text
WATCHING -> DETECTED -> PLAN -> GUARD CHECK
                              |
                  +-----------+-----------+
                  |                       |
               PASS                     FAIL
                  |                       |
              SUBMIT TX             ALERT / NO ACTION
                  |
        CONFIRMED / REVERTED / TIMED OUT
                  |
        RE-READ ACTUAL POSITION
                  |
       NOTIFY + COOLDOWN / SAFE RETRY
```

**Minimum safeguards:**

1. **Strict allowlists:** selected Morpho contract, market ID, reserve tokens, beneficiary.
2. **Hard caps:** per-action and cumulative spending/locking; reserve floor; gas-price/fee caps.
3. **No arbitrary keeper transfers:** value may go only toward fixed Morpho repayments/collateral supply for the correct beneficiary.
4. **Freshness and health:** time/block-stamped snapshots; oracle freshness where inspectable; conservative debt/price refresh before transaction.
5. **Idempotence:** record action IDs, re-read state after confirmation, cooldown, no duplicate full-size spends during retries.
6. **Correct accounting:** accrual, debt shares, token decimals, rounding, fees; never accidentally repay the wrong market.
7. **Fail closed on unknowns:** unverified oracle path, unsupported swap/refinance route, missing balance, ambiguous tx state -> no speculative execution.
8. **No safety promise:** liquidators can act first; gas, congestion, RPC failure, oracle failure, or a smart-contract exploit can make rescue impossible.

**Security principle:** It is better for FAULTLINE to **refuse an unverified action and alert** than to execute an irreversible trade based on a wrong dependency assumption.

---

## 7. Exactly what we will show the jury

### Recommended end-to-end demo — realistic MVP

1. User connects one **verified Morpho Blue market** (two positions are optional for portfolio allocation).
2. User configures policy, deposits **USDC and compatible collateral** into the rescue vault, then arms autonomy.
3. Display Dependency Graph / Cascade Radar: which factor threatens the position and how different plausible stress paths affect it.
4. Trigger a reproducible local-fork or controlled-test crisis event.
5. **Countermove compares AUTO-REPAY and AUTO-TOP-UP** with exact computed amounts and rejects one if it is infeasible or worse under the selected objectives.
6. Watcher **submits a real local-fork/test transaction with no new user signature**.
7. Show **transaction hash / emitted event / changed Morpho debt or collateral**.
8. Run a second crisis fixture where resource availability or dependencies make the **other action** preferable; show that it also executes automatically.
9. Show a third fixture: no feasible action -> the system **does not spend funds** and alerts the user.

**If time permits:** Add **EMERGENCY FULL REPAY**, using the same tested repayment path. Only attempt DELEVERAGE + SELL or REFINANCE once autonomous A/B is solid.

### Acceptance criteria

- [ ] At least **two distinct on-chain defenses** can execute unattended: **repay** and **top up**.
- [ ] Each action uses only funds and permissions configured before the crisis.
- [ ] No new wallet confirmation is needed at trigger time.
- [ ] Dependency-specific scenarios can change which action is selected **where genuinely justified**.
- [ ] Current/on-chain post-action state is checked, and results are clearly shown.
- [ ] The engine respects caps, avoids unsupported actions, and handles failures safely.
- [ ] The demo distinguishes **confirmed execution** from **simulated success**.

### Development order

1. **Verify market/oracle and Morpho read path.** Reuse the existing dependency graph and Cascade Radar.
2. **Build/test `RescueVault` repay-only** with a funded reserve and bounded policy.
3. **Add top-up** with the exact verified market collateral token.
4. **Build the scenario-action comparator:** HOLD, REPAY, TOP_UP, optional split allocation.
5. **Add automatic watcher → guarded on-chain execution → receipt verification.**
6. **Test two opposite scenarios and failure handling.**
7. Stretch only afterward: full repay, then evaluate a real unwind/refinance route.

---

## 8. What makes the new idea original?

Existing DeFi apps can automate liquidations protections or repayments. **“Auto-repay when LTV is high” alone is not the novelty.**

Our differentiator is the combined chain:

> **Verified collateral/oracle dependencies → crisis-specific propagation scenarios → user-pre-authorized action set → scenario-aware, resource-constrained selection → bounded autonomous execution → proof of the actual on-chain result.**

The best jury demonstration is **not just one automatic repayment**. It is showing that, for the *same position or two positions with different dependencies*, FAULTLINE chooses **different protective responses** for sound, explainable reasons—and actually executes both within predetermined limits.

---

## 9. Technical references (verified against official documentation)

- **Morpho Blue functions and permissions:** https://docs.morpho.org/developers/contracts/blue/ — `repay` / `supplyCollateral` may target an `onBehalf` account; withdrawals / borrowing have stronger authorization requirements.
- **Current Morpho Bundles:** https://docs.morpho.org/developers/contracts/bundles/ — `BlueBundlesV1` supports repayments, collateral actions and compatible position migrations.
- **Morpho Bundles overview:** https://docs.morpho.org/learn/concepts/bundles/ — **Bundler3 is deprecated** for new integrations; Bundles do not offer arbitrary swap/leverage composition equivalent to old Bundler3 routes.
- **Morpho SDK:** https://docs.morpho.org/developers/sdks/morpho-sdk/ — market reads, simulation helpers, and current write paths.
- **Optional execution automation:** https://www.gelato.cloud/web3-functions — infrastructure option, not a required dependency.

**Unverified until implemented:** Suitable live Morpho markets and their exact oracle paths; practical availability of an unwind/refinance route; actual gas/slippage; the correct handling of all oracle and interest edge cases. These must be validated with fork-based tests.

---

## 10. Final team decision

**Build FAULTLINE as a narrowly permissioned, autonomous emergency defender.**

**Commit to two executable strategies:**

1. **AUTO-REPAY** — rescue using pre-funded loan tokens.
2. **AUTO-TOP-UP** — rescue using pre-funded compatible collateral.

**Add if straightforward:** full debt repayment. **Only stretch if time allows:** actual deleverage/sell or compatible-market refinancing. **Defer shorts and leverage trading.**

Our success condition is simple: *a crisis is detected while the user is offline; the system understands the relevant dependencies, chooses between authorized defenses, executes the chosen defense on-chain, and can prove what happened.*
