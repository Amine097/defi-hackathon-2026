# FAULTLINE — Breaking Point

> **Feature-only implementation specification** · EPFL Hackathon 2026 — Belem Capital Track
> **Priority:** P0 differentiator inside FAULTLINE's existing Core Risk Engine
> **Audience:** Coding agent / LLM implementing only the Breaking Point feature
> **Document version:** 2.1 · 2026-10-10
> **Deliverable:** Tested, integrated feature in the **existing** application — not a new application

---

## 0. Non-negotiable instructions for the coding agent

**The Belem Capital minimum is assumed to be already implemented in the repository.** Before editing code, inspect the existing architecture, components, domain models, tests, API conventions and graph/impact/decision interfaces. Implement **only Breaking Point** and whatever minimal adapters are necessary to integrate it.

**DO NOT rebuild or reimplement:**

- On-chain position discovery or portfolio ingestion;
- The dependency graph, its exploration UI or exposure percentages;
- The existing forward impact estimator / incident simulation engine;
- The STAY/EXIT economic decision engine;
- Whale monitoring, Leverage Hunter, Chain of Blame, Telegram alerts, Exit Feasibility, or Reaction Window;
- A second frontend, backend, database, blockchain indexer, or configuration system.

**Do reuse:** the selected real position, normalized market snapshot, graph dependency IDs, existing exposure/allocation metrics, current health/risk inputs, scenario simulation, loss calculation, provenance system, existing API client and UI components. If an interface does not yet match this document, add a **thin adapter**; do not fork the underlying model. Follow the repository's established technology stack and lint/test conventions. Do not introduce Python/FastAPI or TypeScript/Next.js solely because an example in this specification uses those idioms.

**Never:** invent live blockchain values, fabricate financial loss probabilities, equate an AMM trade with an oracle-price movement without evidence, execute transactions, claim liquidation execution merely because a liquidation threshold is reached, or silently label an unsupported scenario as safe.

At completion, report: files changed, integrated interfaces, real-data vs fixture behavior, exact test commands and results, unsupported cases, remaining limitations. Implement P0 and pass its acceptance tests before starting P1.

### Authority and conflict resolution

1. **Existing repository contracts and actual deployed protocol semantics** take precedence for implementation details, provided they are correct.
2. **Belem challenge brief** defines the product's overall purpose and evaluation criteria.
3. **This document** defines the additional Breaking Point behavior, not the entire Belem submission.
4. Official protocol contracts/SDKs determine exact liquidation semantics and rounding; documentation examples are explanatory, not authoritative over deployed code.
5. If the data is insufficient for a precise result, return `UNSUPPORTED` or `INSUFFICIENT_DATA` with the missing evidence. Do not guess.

---

## 1. Product objective and boundaries

### What is Breaking Point?

**Breaking Point is a reverse stress-testing feature:** it finds the **smallest specified adverse change in an input** that causes a chosen portfolio or position risk condition to be crossed.

Instead of displaying only *“A 10% shock causes a 7% loss”*, FAULTLINE must also answer:

> **“What is the minimum shock that makes this specific position liquidatable or makes its loss exceed my limit, and which dependency would transmit it?”**

The feature's principal output is a **critical threshold with provenance**, not a new risk score or a fabricated probability.

### Relationship to Belem's challenge

Belem's official brief asks the overall product to discover dependencies, quantify the economic impact of an incident, and inform the trade-off between staying and exiting despite execution costs. Its Pendle PT example spans the settlement chain, yield source/issuer, oracle, PT AMM and collateral-lending market. The judging criteria are 30% dependency discovery, 30% impact estimation, 25% decision usefulness and 15% working demo on real data.

**All those baseline capabilities already exist in FAULTLINE by assumption.** Breaking Point extends them with an **inverse question**: find the threshold, then hand it back to the existing impact and STAY/EXIT services. It is not a separate implementation of the baseline.

### Product promise

A portfolio manager selects a position and sees:

1. **Current state:** currently healthy, already breached, unleveraged, or unknown;
2. **Critical shock:** e.g. *“12.50% decrease in Morpho's collateral-oracle price”*;
3. **Outcome:** e.g. *“Position becomes eligible for liquidation”*;
4. **Economic consequence:** the existing impact engine's estimated conditional impact at that threshold, explicitly marked as modeled, not realized;
5. **Dependency path:** evidence-backed causal path from the selected driver to the risk condition, or an explicit `unverified` link;
6. **Trust information:** snapshot block/time, oracle source, assumptions, precision and unsupported scenarios.

### Scope and priority

| Level | Scope | Success condition |
|---|---|---|
| **P0** | Morpho Blue loan collateralized by a Pendle PT: current state and minimum **Morpho oracle collateral-price drop** to liquidation | Accurate, contract-checked threshold using an existing real position snapshot |
| **P0** | Existing forward scenario/impact engine integration | Check the scenario exactly at, just before and just after the threshold; return the impact estimate or a named unsupported result |
| **P0** | Self-contained UI card + critical-threshold visualization in current position page | User can inspect driver, numerical threshold, consequence, assumption, source and scenario without navigating to a new app |
| **P0** | Machine-readable integration contract, deterministic tests and one on-chain demo | Feature can be called by the existing dashboard and incident/decision services |
| **P1** | **Target-loss breaking point** for both levered and unlevered positions | Solve for the minimum supported shock exceeding a manager-defined loss budget, using the existing impact engine |
| **P1** | **Debt-growth breaking point** | Find additional accrued debt that would make an otherwise unchanged lending position liquidatable |
| **P1** | **Configurable concentration-policy breakpoint** (optional RockawayX-inspired preset) | Consume existing portfolio/dependency exposure metrics, show percentage-point headroom to a concentration cap, and solve the smallest **verified valuation/allocation shock** that breaches the cap, if a supported scenario mapping exists |
| **P1** | Dependency-aware scenario drivers | Solve an underlying/issuer or PT-AMM shock *only* when the existing simulator models the verified causal transmission to the actual lending oracle |
| **P2** | Breakpoint heatmap for several positions or an entire portfolio | Compute independent per-position thresholds and aggregate effects without double counting |
| **P2** | Sensitivity comparison and threshold timeline | Compare successive consistent snapshots, not estimate future liquidation timing without a model |
| **OUT** | Whale tracking, alerts, causal blame attribution, routing/executing exits, guessing crash probabilities | Those belong to other features |

**Scope clarification (RockawayX):** the RockawayX dashboard and public concentration limits are **optional P1 inspiration / validation data**. They are **not Belem requirements**, universal liquidation rules or instructions to rebuild the portfolio pipeline. A concentration-policy breach is a mandate-compliance condition, **not** an on-chain liquidation or an automatically realized monetary loss.

**Important:** P0 is a **single verified reverse stress test**, not a promise to simulate every DeFi failure. A risk from an issuer default, bridge outage or smart-contract hack must not be disguised as a 12.5% oracle-price change if no legitimate transmission model exists.

---

## 2. UX specification — only the Breaking Point feature

Integrate the component into the existing position-detail/incident view. Do not create another dashboard. Product design should favor direct investor questions, in the spirit of scenario-based DeFi risk reports such as the publicly available RockawayX vault risk pages, without copying their branding or asserting access to a private conversation.

### Breaking Point card (P0)

```text
┌──────────────────────────────────────────────────────────────────┐
│ BREAKING POINT                                     [LIVE] [↻]    │
│ Selected position: PT-… collateral / loan asset: USDC           │
│                                                                  │
│  ┌──────────────────────────────┐ ┌──────────────────────────┐  │
│  │ Shock to liquidation         │ │ Current health factor    │  │
│  │            −12.50%           │ │          1.1429          │  │
│  │ MORPHO ORACLE PRICE          │ │                          │  │
│  └──────────────────────────────┘ └──────────────────────────┘  │
│                                                                  │
│   HEALTHY  ───────────────●──────────│────────── LIQUIDATABLE   │
│                     0% shock      −12.50%                        │
│                                                                  │
│  What fails?   Collateral becomes eligible for liquidation      │
│  What moves?   Exact Morpho oracle price, NOT necessarily AMM   │
│  Why?          Collateral value × LLTV no longer covers debt     │
│  Impact at threshold: [value from EXISTING impact module]       │
│  Sources: block #…, Morpho market …, oracle … [Show evidence]    │
│  [Simulate at threshold] [Open existing Impact/Decision view]    │
└──────────────────────────────────────────────────────────────────┘
```

**Wireframe values are illustrative fixtures and must never appear as live observations unless actually verified.**

### Required interactions

- Use the **position already selected in FAULTLINE**; do not require entering a second market ID/account unless the existing UI does.
- Default target: `LIQUIDATION_ELIGIBILITY` for a supported borrowing position. If no borrow exists, show `NO_DEBT` and offer `LOSS_LIMIT` only when that P1 capability is installed.
- Clearly show the **driver** (`morpho_oracle_collateral_price`), the **outcome**, and the **unit**. Never show an ambiguous label like `Risk −12.5%`.
- Provide `Simulate at threshold` to feed the critical scenario to the **existing incident/impact simulator**. It must not automatically open a trade or issue a financial instruction.
- Let the user inspect `source block`, `oracle contract`, `loan/collateral assets`, `LLTV`, `debt`, and `snapshot consistency` in a compact expandable evidence view.
- When the result is unknown, stale or unsupported, **replace the numerical claim** with a reason; do not display a colored safe indicator.
- Where the existing impact module returns an economic impact, label it `modeled loss at threshold` and show its currency/unit and limitations. If it cannot compute impact, say `Impact unavailable` rather than recomputing or inventing a number.
- Match current design system, language, color/spacing and accessibility conventions; support keyboard actions and readable mobile states.
- Visual threshold marker must be positioned according to the actual driver domain. If a driver has no finite threshold, do not show a fabricated progress bar position.

### Optional P1 addition — concentration-policy card (do not replace P0 card)

When the pre-existing portfolio/exposure provider supplies valid allocations and an explicit policy, add a compact secondary panel **inside Breaking Point**, not a separate dashboard:

```text
CONCENTRATION BREAKING POINT  [Portfolio: <existing portfolio>]  [Policy: example preset]
Single protocol          23.0% / 25.0%    Headroom +2.0 pp   WITHIN POLICY
Single oracle            41.0% / 40.0%    Headroom -1.0 pp   BREACHED
Correlated-asset group   32.0% / 40.0%    Headroom +8.0 pp   WITHIN POLICY
Single blockchain        59.0% / 60.0%    Headroom +1.0 pp   WITHIN POLICY

Scenario: other-chain assets lose 5% (verified NAV mapping)
Ethereum share after shock: 60.23% -> POLICY BREACH
[Explain denominator] [Evidence] [Send scenario to existing impact engine]
```

Numbers above are **fixtures**, not RockawayX live allocations. The example must show the affected group, the portfolio denominator, baseline and shocked exposure, and the source freshness. No shock threshold is shown unless a quantitative transmission model exists; showing `headroom = cap - current exposure` alone is valid and useful.

### Product separation

| User question | Owner |
|---|---|
| “How close am I to a specific failure threshold?” | **Breaking Point** |
| “How would a dependency failure propagate?” | Existing dependency/incident engine |
| “How much would I lose at this threshold?” | Existing impact engine; Breaking Point only displays its output |
| “Should I stay or exit, given slippage?” | Existing STAY/EXIT engine |
| “Can I get out in time?” | Exit Feasibility / Reaction Window, not Breaking Point |
| “How close is a portfolio dependency to a manager-defined concentration cap?” | **Breaking Point P1**, computed from **existing Exposure % / portfolio metrics** |
| “Which wallets or protocols belong to a correlated-asset group?” | Existing dependency/classification provider; **not** Breaking Point |

---

## 3. Integration contract — adapt to the existing codebase

Do not hardcode an endpoint or file hierarchy before inspecting the repository. Add the smallest public interface consistent with the existing architecture.

### Required upstream capabilities (assumed to exist)

Conceptual interfaces; **map these onto existing types instead of duplicating them**:

```ts
// Existing position / normalized snapshot provider (conceptual)
getSelectedPositionSnapshot(): Promise<PositionSnapshot>

// Existing incident simulator / economic impact (conceptual)
simulateScenario(snapshotId: string, scenario: Scenario): Promise<ScenarioResult>

// Existing graph linkage (conceptual)
getPositionDependencyRefs(positionId: string): DependencyRef[]

// Optional P1 only: reuse the existing portfolio/exposure and scenario system.
getPortfolioExposureSnapshot?(portfolioId: string, snapshotId: string): Promise<PortfolioExposureSnapshot>
```

If the current system does not expose a required immutable snapshot or exact liquidation predicate, add a narrow **adapter** or mark the affected result `INSUFFICIENT_DATA`. Do not copy data-ingestion infrastructure into this feature.

### Breaking Point service contract (required)

```ts
type BreakingPointRequest = {
  positionId?: string;            // required for position-level targets; P1 portfolio-only requests use portfolioId
  snapshotId: string;             // immutable canonical existing snapshot
  portfolioId?: string;           // required for portfolio-level P1 analysis
  target: {
    kind: "LIQUIDATION_ELIGIBILITY" | "LOSS_LIMIT" | "CONCENTRATION_POLICY_BREACH"; // last: P1 only
    lossLimitLoanAssetAtomic?: string;   // only for LOSS_LIMIT (P1)
    policyId?: string;                 // required for CONCENTRATION_POLICY_BREACH (P1)
    exposureGroupId?: string;          // existing graph/exposure taxonomy ID (P1)
  };
  driver: {
    kind: "MORPHO_ORACLE_PRICE_DROP" | "DEBT_GROWTH" | "DEPENDENCY_SHOCK" | "PORTFOLIO_VALUATION_SHOCK" | "POLICY_HEADROOM_ONLY"; // last two: P1 only
    dependencyId?: string;        // REQUIRED for DEPENDENCY_SHOCK
    valuationScenarioId?: string;  // existing impact/valuation scenario (P1)
  };
  settings?: {
    maxShockFraction?: string;    // bounded decimal, e.g. "0.99"
    toleranceFraction?: string;   // bounded decimal, not JS float
  };
};

type BreakingPointStatus =
  | "FOUND"
  | "HEADROOM_ONLY"                 // P1: valid policy margin; no modeled shock breakpoint
  | "ALREADY_BREACHED"
  | "NO_DEBT"
  | "NO_CROSSING_IN_RANGE"
  | "INSUFFICIENT_DATA"
  | "STALE_SNAPSHOT"
  | "UNSUPPORTED_DRIVER"
  | "NON_MONOTONIC"
  | "ERROR";

type BreakingPointResult = {
  positionId?: string;
  snapshotId: string;
  portfolioId?: string; // P1 only
  status: BreakingPointStatus;
  target: BreakingPointRequest["target"];
  driver: BreakingPointRequest["driver"];
  critical: null | {
    shockFraction: string;       // >=0 magnitude of adverse change in specified fractional-shock driver (not generic NAV %)
    shockPercent: string;        // human-readable decimal, e.g. "12.5"
    criticalValueRaw?: string;   // protocol/raw-domain boundary where available
    precision: "EXACT_INTEGER" | "BOUNDED_NUMERICAL" | "APPROXIMATE";
    boundaryConvention: string;  // precise liquidation or strict loss-limit convention
  };
  baseline: {
    healthFactor?: string | null;
    eligibleForLiquidation?: boolean | null;
  };
  concentrationPolicy?: { // P1 only; absent for P0 liquidation analysis
    policyId: string;
    policyVersion: string;
    exposureType: "SINGLE_PROTOCOL" | "SINGLE_ORACLE" | "CORRELATED_ASSETS" | "SINGLE_CHAIN";
    exposureGroupId: string;
    currentFraction: string;     // existing exposure metric, from clearly identified denominator
    capFraction: string;
    headroomPercentagePoints: string; // (cap - current) * 100; negative = breach
    denominatorId: string;
    postShockFraction?: string | null;
    scenarioId?: string | null;
    exposureAsOf?: string;
    // Explicitly mark policy breaches as distinct from LIQUIDATION_ELIGIBILITY.
  } | null;
  impactAtThreshold?: {
    existingScenarioResultId: string;
    modeledLoss?: string | null;
    unit?: string | null;
    modelVersion?: string;
  } | null;
  evidence: {
    chainId?: number;  // P0 position; portfolio P1 may span multiple chains
    chainIds?: number[]; // P1 portfolio
    blockNumber?: number | null;
    timestamp?: string | null;
    consistency: "SAME_BLOCK" | "MIXED_BLOCK" | "FIXTURE";
    oracleAddress?: string | null;
    dependencyIds: string[];
    sources: string[];
    assumptions: string[];
    warnings: string[];
  };
  failureReason?: string | null;
  missingInputs?: string[];
};
```

**P1 request validation:** `CONCENTRATION_POLICY_BREACH` requires `portfolioId`, `policyId`, `exposureGroupId` and a portfolio/exposure snapshot from the existing provider. For a margin-only calculation, use `POLICY_HEADROOM_ONLY` and return `HEADROOM_ONLY` with `critical=null` and valid `concentrationPolicy` metrics. A *shock breakpoint* requires a supported `PORTFOLIO_VALUATION_SHOCK` and an existing validated revaluation mechanism. If the caller explicitly requests an unsupported scenario, return `UNSUPPORTED_DRIVER` with the valid concentration metrics (when available), `critical=null` and a reason. Never invent an arbitrary shock.

All large on-chain quantities and financial decimals use **decimal strings or arbitrary-precision integer types**, not floating-point `number` for intermediate arithmetic. Existing project conventions may use Python dataclasses/Pydantic instead of TypeScript. The schema above describes semantics, not a mandatory language.

### Service behavior

1. Validate request and resolve exactly the requested immutable snapshot.
2. For a position-level target, resolve the current position with existing protocol/SDK helpers and the market's actual oracle price; for a portfolio-policy target, reuse the existing exposure/valuation snapshot instead.
3. Match `(target, driver)` to a supported `BreakingPointSolver`.
4. Find the adverse-shock threshold and verify the *actual target predicate* on both sides, or compute policy headroom only when `POLICY_HEADROOM_ONLY` is selected.
5. Call the existing impact simulator at the threshold if available, **without reimplementing it**.
6. Attach existing dependency IDs and full source/assumption references.
7. Return one typed result; the UI renders it.

No outgoing chain transactions, no private keys, no write-enabled contracts. Log analytical requests but do not log secrets.

---

## 4. P0: Morpho Blue oracle-price liquidation threshold

### Exact financial meaning

This solver answers:

> At fixed collateral quantity, unchanged accrued debt, fixed market LLTV and **a hypothetical decrease in the price returned by Morpho's market oracle**, what is the smallest decrease that makes this borrower eligible for liquidation?

This is **not** automatically the minimum AMM swap, underlying token depeg, whale sale or time to liquidation.

### Required snapshot fields

Consume the existing normalized snapshot containing, at minimum:

- Protocol instance explicitly identified as **Morpho Blue** (do not apply Blue formulas to Morpho Vault / Morpho V2 / Midnight automatically);
- `market_id`, `position_id` / borrower, `chain_id`, unique collateral and loan token addresses;
- `collateral_atomic` (nonnegative integer string);
- `debt_assets_atomic`, **accrued to the snapshot block**, not just borrow shares;
- `oracle_price_raw`, as returned by the market's oracle `price()` (positive integer);
- `lltv_wad`, as an integer in `(0, 1e18]`;
- Token decimals for correct display, oracle contract address and source provenance;
- Common snapshot block/time or an explicit consistency warning.

If the normalized snapshot exposes only borrow shares, invoke the repository's **existing** debt-accrual conversion; do not treat borrow shares as assets. If snapshot values are inconsistent or invalid, return typed failure.

### Raw units and display

Morpho's normalized oracle price uses scale `S=10^36`; LLTV uses WAD `W=10^18`. In loan-token atomic units:

```text
collateral_value_atomic(P) = floor(collateral_atomic * P / S)
liquidation_capacity_atomic(P) = protocol_exact_rounding(
    collateral_value_atomic(P) * lltv_wad / W
)
```

**Use the exact deployed Morpho Blue health predicate and rounding rules** from the official core or canonical SDK; the above is descriptive pseudocode and must not replace checked protocol logic. There may be integer boundary effects. Treat the implementation's actual predicate as the source of truth.

Analytic approximation for a simple healthy position:

```text
HF_current = collateral_value(P0) * LLTV / debt
P_critical ≈ debt / (collateral_amount * LLTV)
critical_drop ≈ 1 - P_critical / P0 = 1 - 1 / HF_current
```

**Important:** `P_critical` is quoted in normalized oracle raw units and must respect `10^36` scaling. The percentage formula is an **approximation** at finite precision. Use it to propose a candidate; then resolve the exact discrete boundary using the canonical on-chain rule. Report an interval or exact integer cutover convention when appropriate; never label a rounded percentage as exact at the smallest unit.

### Required algorithm

1. Validate the market is Morpho Blue, has positive oracle price and supported health semantics.
2. Compute baseline health and liquidation eligibility using existing canonical predicate.
3. If `debt == 0`, return `NO_DEBT` with no liquidation threshold.
4. If baseline is already liquidatable, return `ALREADY_BREACHED` with `shockFraction="0"`, and explain the state.
5. If debt > 0 but collateral == 0, also return `ALREADY_BREACHED` with clear reason.
6. Compute an approximate threshold analytically, then find the discrete boundary using a bounded integer search across hypothetical oracle-price values, verifying the canonical predicate on adjacent values. For a price-drop driver this should be monotone under fixed snapshot inputs.
7. Return the minimal adverse **decrease** from the baseline oracle price that causes eligibility, and state whether eligibility begins at the critical value or immediately below it according to the exact predicate.
8. Reapply the resulting scenario through the existing impact engine, if it supports direct oracle price overrides or scenario injection; otherwise return a valid threshold with `impactAtThreshold=null` and reason.
9. Never claim the liquidation was executed or the protocol incurred bad debt.

### Health vs losses — keep these separate

- **Liquidation eligibility:** on-chain *permission* to liquidate under current rules.
- **Collateral mark-to-market delta:** change in collateral valuation at the hypothetical oracle price, keeping collateral amount unchanged.
- **Position equity mark-to-market delta:** change in valuation of collateral minus debt under the specified model.
- **Liquidation penalty / actual realization:** requires liquidation execution assumptions; use the existing impact module only if it has a verified model.
- **Portfolio NAV impact:** must come from the existing portfolio/impact service; never conflate liquidated debt with investor loss.

### Important oracle/market distinction

A Pendle PT may be priced by an **AMM-derived TWAP** oracle, a **deterministic linear-discount** oracle, or a wrapper that composes multiple price feeds. A large Pendle swap may move executable PT prices without making Morpho's oracle fall in the same proportion (or at the same time). Some deterministic oracles may be insensitive to AMM price in the relevant computation.

P0 therefore speaks strictly about a hypothetical **Morpho oracle price** movement. For a real issuer depeg or whale trade to be converted to this oracle movement, require a validated transmission adapter (P1), and display the dependencies actually involved. **Never assert a causal link merely because the dependency graph contains both protocols.**

### Edge cases

| Situation | Required output |
|---|---|
| No debt | `NO_DEBT`; no liquidation breakpoint; no misleading infinite Health Factor |
| Already at/beyond protocol's threshold | `ALREADY_BREACHED`; zero additional adverse shock |
| No collateral with debt | `ALREADY_BREACHED`, validated inputs and explanation |
| Stale oracle or mixed-block state | `STALE_SNAPSHOT` or `INSUFFICIENT_DATA`, per existing consistency policy; no verified live badge |
| Oracle returns zero / errors | `INSUFFICIENT_DATA`, missing/invalid oracle information |
| Position belongs to wrong protocol | `UNSUPPORTED_DRIVER` or specific validation error |
| Shock constrained to a range that does not breach | `NO_CROSSING_IN_RANGE`, no made-up endpoint |
| Loss scenario and liquidation scenario disagree | Show both outcomes independently; don't assume the same threshold |
| Near-threshold integer precision | Verify raw predicate at adjacent raw oracle prices; exact units prevail over rounded HF |
| Snapshot changed while computation runs | Pin immutable snapshot or fail; never combine old debt with new oracle silently |

---

## 5. Fixture: required deterministic example (not real data)

This test fixture is intentionally artificial and **must be marked `FIXTURE` everywhere**.

```yaml
snapshot_id: breaking-point-fixture-001
protocol: morpho_blue
chain_id: 1
collateral_symbol: PT-EXAMPLE
collateral_decimals: 18
collateral_atomic: "100000000000000000000"    # 100 PT
loan_symbol: USDC
loan_decimals: 6
debt_assets_atomic: "70000000"             # 70 USDC
oracle_price_raw: "1000000000000000000000000" # 1 USDC per PT after Morpho scaling
lltv_wad: "800000000000000000"              # 80%
snapshot_consistency: FIXTURE
```

Expected values from the idealized formula:

| Metric | Expected |
|---|---:|
| Collateral value | 100.00 USDC |
| Debt | 70.00 USDC |
| LTV | 70.00% |
| LLTV | 80.00% |
| Current Health Factor | ~1.142857142857 |
| Approx. critical oracle price | 0.875 USDC / PT |
| Approx. critical price decrease | **12.50%** |
| At hypothetical −10% oracle change | HF ~1.02857143 (healthy) |
| At hypothetical −15% oracle change | HF ~0.97142857 (liquidatable) |
| Collateral marked-value change at −10% | −10 USDC (not realized liquidation loss) |

For exact boundary tests, test **integer raw oracle values on both sides** of the contract-consistent cutoff, including equality. Do not hardcode the idealized `0.875` equality as the only valid protocol result without verifying contract rounding.

---

## 6. P1: additional breakpoints (only after P0 passes)

### 6.1 Loss-budget threshold (supports nonborrowers)

A user chooses a loss budget, e.g. *“What minimum supported shock causes a modeled loss of at least 5% of this position's value?”*

- **Use the existing impact simulator as a black box.** For driver magnitude `x`, evaluate `loss(x)` with stable snapshot/scenario IDs.
- Express the budget in a clear unit: absolute loan-asset units or percent of the existing position/portfolio value with a named denominator.
- Define the comparator explicitly: `loss(x) >= budget` (not `>` unless the user selected strict exceeding).
- Return `FOUND`, `ALREADY_BREACHED`, `NO_CROSSING_IN_RANGE`, `NON_MONOTONIC` or `UNSUPPORTED_DRIVER` as applicable.
- If the simulator returns realized/unrealized/conditional losses differently, preserve the existing engine's definitions and identify the loss model.
- For a pure PT holder **without borrow debt**, do not fabricate a liquidation breakpoint; offer only this loss-budget analysis if the impact model supports it.

### 6.2 Debt-growth breakpoint

At constant collateral amount, unchanged oracle price, unchanged LLTV and no other position flows, find the **smallest additional accrued debt** making the position eligible for liquidation.

Idealized approximation:

```text
critical_total_debt ≈ collateral_value * LLTV
relative_debt_growth ≈ HF_current - 1
```

Check the precise protocol comparator and integer arithmetic. This is **not time to liquidation**. A time horizon requires a rate-accrual model and is outside this feature unless supplied by an existing service.

### 6.3 Dependency-driven shocks: only verified mechanisms

Where the existing Dependency Graph and incident/impact simulator can justify a mapping `driver_shock -> actual oracle price / loss`, offer the following drivers selectively:

- `UNDERLYING_ASSET_DEPEG`: only with an established PT/SY/exchange-rate/oracle transmission rule;
- `PT_IMPLIED_APY_INCREASE`: only with a verified pricing model at the market's maturity and current conditions;
- `PT_AMM_TRADE`: only with an actual AMM curve/quote and a documented oracle transmission path;
- `ORACLE_DATA_FAILURE`: only if the simulator defines how stale, missing, frozen, invalid or delayed feeds affect this specific lending protocol;
- `PORTFOLIO_LOSS_LIMIT`: only if the baseline impact engine supports aggregation without double counting.

If a driver changes executable PT market price but **not** the lending oracle, Breaking Point may return a different breakpoint for *loss threshold* and *liquidation eligibility*, or explicitly `NO_CROSSING_IN_RANGE`. That is expected, not an error.

### 6.4 General inverse solver

```text
input: fixedSnapshot, supportedDriver, failurePredicate, domain, tolerance
output: smallest adverse shock in domain that meets predicate, or typed non-result

1. Validate immutable snapshot and model version.
2. Ensure the driver -> outcome mapping is supported and has evidence.
3. Evaluate predicate at 0 and at maximum admissible shock.
4. Check for invalid/unknown outputs and obvious non-monotonic behavior.
5. If monotonicity is guaranteed by model mathematics or explicit adapter contract,
   use bounded bisection or analytic threshold + exact boundary refinement.
6. If monotonicity is NOT guaranteed, do not falsely claim global minimum from bisection;
   use an explicit supported bounded search or return NON_MONOTONIC/UNSUPPORTED_DRIVER.
7. Verify boundary with solver-domain precision and return neighboring scenario checks.
8. Call the existing impact engine for any at-threshold impact; attach model version.
```

For a continuous/nonlinear simulator, report a **bounded threshold interval**, numerical tolerance, max iterations and assumptions. Avoid converting non-monotonic false negatives into false safety claims. Return a typed error when every simulation point is valid but the threshold cannot be located within the requested range.

---

### 6.5 Configurable concentration-policy breaking points — RockawayX-inspired (P1)

**External reference, NOT Belem's official rules.** RockawayX publishes the following **portfolio concentration hard limits** in its public vault-curation framework. They are useful as an **optional named example preset**, not as universal safety thresholds, forecasted loss percentages or liquidation rules. Do not silently apply them to every portfolio.

| Policy group | Example hard cap | Provenance |
|---|---:|---|
| Single protocol | 25% | RockawayX public risk framework |
| Single oracle | 40% | RockawayX public risk framework |
| Correlated assets | 40% | RockawayX public risk framework |
| Single chain | 60% | RockawayX public risk framework |

Source: https://www.rockawayx.com/insights/rockawayx-vault-curation-an-overview-of-products-capabilities (section **Concentration Hard Limits**, checked 2026-10-10). Preset metadata: `source=RockawayX`, `policy_name=rockawayx_example_2026`, `status=example_reference`, `last_verified=2026-10-10`, editable by the manager, and versioned alongside results. **Do not imply RockawayX endorses FAULTLINE** or that Belem mandates these caps.

#### 6.5.1 Precisely separate three concepts

1. `CONCENTRATION_EXPOSURE`: percentage of a **specified portfolio/mandate denominator** attributable to a dependency; calculated by the **existing** Dependency Exposure / portfolio system.
2. `POLICY_HEADROOM`: how much room remains before a **configurable mandate limit** is exceeded. In percentage points: `100 * (cap_fraction - exposure_fraction)`. Negative means **already over the limit**. At equality, the position is *at limit*, not over it, unless that policy explicitly uses a `>=` breach comparator.
3. `POLICY_BREAKING_SHOCK`: smallest **supported modeled change** to allocations or valuations that makes the policy predicate true, where the change-to-exposure mapping is available. This is optional and conditional; it is **not** the minimal price drop to liquidation. Do **not** turn headroom of `2 pp` into a claim that a 2% market shock will cause a breach.

Use distinct outcome labels `POLICY_LIMIT_BREACH` and `LIQUIDATION_ELIGIBILITY`. One can occur without the other. Crossing a concentration cap **does not itself prove an economic loss**. Link through the existing impact engine only when a shock has separately modeled financial consequences.

#### 6.5.2 Input contract and denominator

- Consume the **existing** portfolio valuation/exposure service, with `portfolioId`, `snapshotId`, NAV/denominator definition and per-position allocation/exposure weights.
- Reuse existing dependency graph IDs to group same protocol, oracle or chain. For `CORRELATED_ASSETS`, a manager-approved correlation group or justified and versioned upstream classification is required. **Breaking Point must not discover or assume correlations itself.**
- Define whether the denominator is total portfolio NAV, deployed capital, gross exposure or vault allocation base; preserve this choice **per policy**. Levered/gross positions can sum above 100% under some definitions and must not be forcibly renormalized.
- De-duplicate the same position **within a single exposure group** before aggregating its exposure; a position can validly contribute to multiple *different* dependency groups. Never sum percentages across unrelated groups to claim total risk.
- The allocation snapshot must be consistent and sourced. If positions are absent, exposures are partial, group classification is unknown, or the data is too stale for the existing quality policy, return the affected metric as `INSUFFICIENT_DATA` / `STALE_SNAPSHOT` with a reason, **not** a false "under limit" result.
- Evaluate each configured group against its configured cap. Do not assume a portfolio has only one protocol, oracle or chain.

#### 6.5.3 Headroom and conditional inverse shock

For a policy group `g`, cap `c_g`, baseline exposure `e_g`:

```text
headroom_percentage_points = 100 * (c_g - e_g)
policy_breached(e_g)       = e_g > c_g    # example strict comparator; override if policy says >=
```

For an **existing supported scenario** `x`, obtain *repriced* position values and portfolio denominator **using the existing scenario/valuation engine**, and recompute `e_g(x)` with the same exposure taxonomy. If monotonicity is established for `e_g(x)` and the threshold predicate, use the general inverse solver in Section 6.4. Otherwise use an explicitly bounded global search with uncertainty or return `NON_MONOTONIC` / `UNSUPPORTED_DRIVER`. Return the minimum representable breaching shock or a clearly labeled threshold infimum/bracket when a strict mathematical `>` boundary has no attainable continuous minimum. Preserve scenario and valuation-model versions.

**Counterintuitive required fixture (why this feature is useful):** assume an unlevered, two-bucket portfolio with one chain comprising 59% of NAV and other chains 41%, no flows, and a 60% single-chain maximum. If the *other chains* lose 5% while the chosen chain's bucket remains unchanged, the chosen chain's share increases to:

```text
post_shock_share = 59 / (59 + 41 * 0.95) = 0.602348... = 60.23% > 60%
```

The policy limit breaches **without any price increase on the concentrated chain**. This fixture tests denominator revaluation; it is **not a live market observation** and cannot be generalized to leveraged NAV without the correct model. A simple *2 percentage-point headroom* example likewise does **not** imply any specific 2% price shock.

If user changes policy cap alone, recalculate policy status/headroom but do **not** describe this administrative edit as a market breaking shock.

#### 6.5.4 UI and reporting

- Reuse the existing portfolio/position view. Render optional **Concentration Breakpoint** under the Breaking Point feature, keeping it visually separate from the P0 liquidation card.
- Show: `group / dependency`, `current %`, `policy cap %`, `headroom in pp`, `status`, `denominator`, `snapshot as-of`, `policy source` and `editable-policy indicator`.
- Only when an actual scenario model exists, show `driver`, `minimum modeled shock`, `post-shock %`, `first crossing convention` and `model assumptions`. Otherwise say `Scenario threshold not available; exposure headroom only`.
- A live result must never borrow values from the RockawayX **preset** as though they were RockawayX **portfolio observations**.

### 6.6 RockawayX Dune data as optional external fixture / scenario input (P1 or P2)

Dune dashboard: https://dune.com/rockawayxvault/rockawayx-dashboard

The linked dashboard is **external context**, not a hard integration requirement for Breaking Point P0. Its dynamically loaded charts/query IDs and full schema have **not been verified**. Do not invent SQL query IDs, addresses, vault allocations, or present dynamically indexed values as guaranteed live.

**If existing FAULTLINE ingestion supports Dune and suitable public queries can be verified:**

1. Enumerate relevant **public query IDs** by inspecting the actual dashboard/queries; record exact query links, owners, schemas, permissible API access and update times. If unavailable, stop and document the blocker.
2. Fetch only the available results using supported Dune APIs (example documented pattern: `GET https://api.dune.com/api/v1/query/{query_id}/results`, header `X-DUNE-API-KEY`); follow current official Dune API documentation and permissions, and keep keys **server-side only**.
3. Validate data provenance: Dune query id, execution id/time if provided, chain/block or data timestamp, reporting currency, decimals, portfolio/vault identity and what allocation actually represents (market assets vs vault holdings vs borrow exposure). Reject incomplete attribution.
4. Convert via the **existing portfolio normalization and exposure pipeline**, not via a custom Breaking Point indexer. Connect it to existing graph IDs only when the relation is independently confirmed.
5. Run concentration headroom and (if modelled) inverse scenario against the pinned snapshot. Clearly badge `Dune indexed / as of <time>`, not `realtime`. RockawayX's vault page states its displayed vault data auto-refreshes every **2 hours**; actual Dune query execution timing still must be measured rather than inferred from this website setting.
6. Offer a **replayable saved snapshot** for a dependable hackathon demo if live query access or fresh results fail; label it `recorded actual data`, include acquisition provenance, and never call it live.

Source for stated website cadence: https://www.rockawayx.com/vaults ("Live · auto-refreshes every 2hrs · Powered by Dune"). API keys, result availability and freshness remain subject to Dune's current API terms and subscription rules: https://docs.dune.com/api-reference/. API keys must not appear in a public repository or browser bundle.

**Explicit ownership boundary:** data import, address discovery and normalized allocation extraction belong to the existing ingestion/Dependency Exposure teams. The Breaking Point feature consumes only their validated snapshots, computes **distance to policy limit / scenario threshold**, and hands supported scenarios to the existing impact engine. If Dune is inaccessible, Breaking Point P0 must still work.

---

## 7. Data integrity, evidence and explainability

The module **consumes** the existing graph/provenance system and adds feature-specific evidence:

- Input position and immutable `snapshot_id`;
- Contract, protocol version, chain ID, market ID, oracle address;
- Block number/time and data consistency status;
- Collateral/debt/LLTV/oracle raw values or stable references to them;
- Scenario driver, shock magnitude, target condition and threshold convention;
- Source of oracle pricing and known distinction from PT AMM execution price;
- Exact algorithm used (`ANALYTIC_REFINED`, `INTEGER_SEARCH`, `BOUNDED_BISECTION`, etc.);
- Engine and model versions, tolerance, status, warnings;
- Graph `dependencyIds` and source evidence for any claimed dependency-to-shock mapping.
- For concentration P1: policy ID/version/source, selected denominator, exposure snapshot and provenance, group classification, cap comparator, headroom (percentage points), modelled valuation scenario, and whether the input was Dune-indexed or directly read on-chain.

Where a relationship is only inferred, explicitly label it as such; where not established, state that Breaking Point is conditional on an imposed oracle-price change. For high-stakes unknown inputs, output `INSUFFICIENT_DATA`, **never 0% shock**, `100% safe`, or a fake certainty score.

Show separate labels for:

1. **Observed** (`on-chain, snapshot pinned`);
2. **Assumed shock** (`user/scenario hypothesis`);
3. **Calculated threshold** (`deterministic result under assumptions`);
4. **Modeled conditional impact** (`existing impact engine`, not an executed loss);
5. **Unsupported/unknown causal link**.

---

## 8. Integration with existing FAULTLINE features

| Existing feature | Inputs from it | Breaking Point returns |
|---|---|---|
| Dependency Graph / Exposure % | Selected position ID, graph nodes/edges, source references | Critical driver, relevant dependency IDs and evidence references |
| Impact Estimation | Scenario runner and loss definitions | Threshold scenario for evaluation; no independent loss model |
| STAY/EXIT | Existing comparison logic and cost calculations | Threshold and scenario IDs, **not** a duplicate action recommendation |
| Leverage Hunter | Existing candidate borrower positions (if available) | Per-position liquidation buffer and boundary; no whale discovery |
| Chain of Blame | Existing causality/evidence chain (if available) | A quantitative threshold attached to a verified mechanism |
| Reaction Window / Telegram | Existing event/alert infrastructure (if later added) | Optional risk-threshold event; never a fabricated time-to-liquidation |
| Portfolio / Dependency Exposure % (P1) | Verified grouped exposures, denominators, policy/portfolio snapshots | Configurable concentration-cap headroom and, with an existing revaluation model, first policy-breaching shock |
| Dune / RockawayX reference data (optional) | Already-normalized, timestamped vault allocation snapshots | Policy analysis only; Breaking Point must not crawl Dune charts or implement a second indexer |

The output should be stable enough for other services to consume while remaining minimal and read-only.

### Recommended internal decomposition (adapt to repo)

```text
BreakingPointController or existing route/component
  └── BreakingPointService
       ├── ExistingSnapshotAdapter          [reuse current data layer]
       ├── MorphoBlueLiquidationSolver      [NEW: core of this feature]
       ├── OptionalInverseImpactSolver     [NEW P1]
       ├── OptionalConcentrationSolver     [NEW P1, reuse Exposure %]
       ├── ExistingImpactEngineAdapter      [thin bridge, no duplication]
       └── EvidenceFormatter               [reuse provenance conventions]
```

Prefer a pure functional solver (`snapshot + target + driver -> result`) separated from network/GraphQL/RPC and UI. Keep integration tests at the adapter boundaries.

---

## 9. Acceptance tests (must be automated)

### P0 required

- **BP-01** Fixture: 100 PT, 70 USDC debt, LLTV 80%, oracle price 1 → idealized 12.5% threshold; exact boundary follows canonical predicate.
- **BP-02** At −10% oracle price, fixture remains healthy; at −15%, it is eligible for liquidation.
- **BP-03** Verify equality and adjacent raw oracle-price integers against Morpho's canonical predicate; no floating point threshold glitches.
- **BP-04** Zero debt returns `NO_DEBT`, no critical liquidation percentage.
- **BP-05** Existing unhealthy position returns `ALREADY_BREACHED` with 0 additional shock.
- **BP-06** Zero collateral with outstanding debt returns `ALREADY_BREACHED` with explicit explanation.
- **BP-07** Invalid price, negative amounts or inconsistent LLTV cannot return a valid numeric threshold.
- **BP-08** Unsupported protocol (e.g. Morpho Midnight) is not misinterpreted as Morpho Blue.
- **BP-09** Mixed-block/stale snapshot is clearly labeled and never presented as a verified live threshold.
- **BP-10** The same immutable snapshot always produces identical raw results and evidence/model identifiers.
- **BP-11** Direct oracle-price change is labeled as **oracle change**; never relabeled as PT market-price change.
- **BP-12** If current Pendle oracle is deterministic/AMM-independent, a hypothetical AMM trade is not silently treated as an oracle change.
- **BP-13** `Simulate at threshold` calls the **existing** forward incident/impact service once, with the correct snapshot and shock; no duplicate impact engine created.
- **BP-14** If impact service cannot simulate a scenario, numeric liquidation threshold remains available but conditional impact is explicitly `unavailable`.
- **BP-15** Component renders driver, threshold, status, evidence and scope warnings; no fabricated live value on API errors.
- **BP-16** Real read-only integration: choose one actual, active compatible Morpho Blue/Pendle borrower; cite verified chain/market/position and reproduce calculation with consistent block context. If no compatible real market exists, report that limitation rather than supplying a fake address.
- **BP-17** Solver may not send blockchain transactions, access private keys or modify on-chain state.
- **BP-18** Near-zero shock and extreme integer values are handled without overflow or misleading rounding.
- **BP-19** Different loan and collateral token decimal precisions display correctly without affecting atomic arithmetic.

### P1 required before P1 is marked complete

- **BP-20** Debt growth trigger equals canonical discrete boundary, not a forecast of liquidation timing.
- **BP-21** User-defined loss limit produces first crossing or a typed `NO_CROSSING_IN_RANGE`.
- **BP-22** A non-monotonic simulation cannot be declared globally minimized using unverified bisection.
- **BP-23** An unlevered PT position cannot be assigned a liquidation threshold but can receive a loss-limit breakpoint when supported.
- **BP-24** Any underlying depeg / PT AMM / yield shock explicitly names its verified transmission path, actual oracle type and limitations.

### Optional P1 concentration-policy and Dune tests

- **BP-25** RockawayX example policy preset contains protocol 25%, oracle 40%, correlated-assets 40%, chain 60%, with source, explicit **example** status and editable version; not Belem default.
- **BP-26** A 23% group exposure against a 25% cap displays **+2.0 percentage points** headroom, not "2% expected loss" or "2% price drop".
- **BP-27** A 41% oracle exposure against a 40% cap is reported as already beyond the mandate cap, **not** liquidatable or financially lost.
- **BP-28** At exactly 40% exposure with a `>` comparator the cap is *at limit* but not breached; scenario solver observes boundary convention.
- **BP-29** Overlapping dependencies (one position across protocol and oracle) do not cause within-group double counting or incorrect sum of unrelated percentages.
- **BP-30** Two-bucket fixture: 59% on one chain and 41% elsewhere; a 5% fall in elsewhere's value raises the first to about **60.23%**, breaching a 60% maximum; a scenario without a denominator revaluation model must not claim this result.
- **BP-31** A 2 pp headroom value must not be converted to a market shock size without a validated scenario model; if missing, `critical=null` and reason are returned.
- **BP-32** Unclassified correlated-asset exposure or missing dependency/denominator cannot return "safe" and must surface `INSUFFICIENT_DATA` or unknown coverage.
- **BP-33** Changing a cap updates headroom/status with versioned policy provenance but is never classified as an actual market shock.
- **BP-34** RockawayX/Dune snapshots and fixture numbers cannot appear as live unless independently validated as such; report `as_of` and stale state.
- **BP-35** If Dune query IDs, schema or credentials are unavailable, P1 integration gracefully degrades and P0 remains functional; no guessed query IDs.
- **BP-36** Dune API keys must be supplied through server-side secrets, not committed to Git or exposed in client HTTP requests.

**Required verification techniques:** unit tests for pure math and boundaries; integration tests with mocked existing upstream services; one read-only real snapshot smoke test. Add regression tests for previously failed scenarios. Keep test fixtures and live data explicitly separated.

---

## 10. Demonstration script (90 seconds, feature-only)

1. Start in the **existing FAULTLINE dashboard**; select an actual compatible position already discovered by the core system.
2. Open **Breaking Point**. Show current Health Factor, the critical **oracle-price** shock and the liquidation eligibility target.
3. Click **Evidence**: reveal Morpho market, oracle address, LLTV, pinned snapshot block and raw-source confidence.
4. Trigger **Simulate at threshold**. The existing impact engine displays the modeled conditional consequence, not a realized liquidation.
5. Change the hypothetical shock to just below and just beyond the boundary: show the condition flipping with contract-accurate rounding.
6. Open the **existing STAY/EXIT view** using the returned threshold scenario. Do **not** implement a second decision engine inside Breaking Point.
7. State the limitation honestly: *“This is the threshold for the oracle price observed by this lending market; a whale swap or issuer incident only affects it when a verified causal path exists.”*

**Optional RockawayX add-on (only if P1 is ready):** show a selected portfolio dependency at 23% under the 25% protocol cap, then open the manager-editable concentration-policy threshold panel; if an actual Dune vault snapshot is available, display the Dune query and `as_of` time. Never substitute this for the core liquidation demonstration.

**Success:** a judge can distinguish an on-chain observation, an imposed market scenario, the first failure threshold and the conditional portfolio consequence within one minute of inspection.

---

## 11. Definition of done and implementation workflow

**The feature is complete (P0) only when:**

- [ ] It is implemented **inside the existing app**, without reconstructing Belem's baseline.
- [ ] It reads an immutable existing real position snapshot or a clearly labeled fixture.
- [ ] It computes baseline health and the first eligible Morpho oracle-price threshold with correct integer/protocol rules.
- [ ] It exposes supported, breached, unlevered, stale and unsupported states accurately.
- [ ] It integrates the threshold scenario with the existing forward impact engine (or reports explicitly why the integration is unsupported).
- [ ] It shows an accessible, responsive card on the existing position page.
- [ ] It displays provenance, assumptions and the oracle-versus-AMM distinction.
- [ ] All **BP-01 through BP-19** tests pass or any external-data-dependent exception is documented rather than falsely marked as passing.
- [ ] A read-only demo has been tested on an actual compatible on-chain borrower, or the absence of one is reported as a blocker, **not** hidden by a fixture.
- [ ] No code from unrelated FAULTLINE features has been duplicated.

### Agent execution order

1. **Inspect**, inventory and map existing repository contracts. Name the files/services to reuse before editing.
2. **Implement pure P0 solver** with canonical Morpho math and unit tests.
3. **Integrate immutable snapshot adapter** with current data provider; avoid duplicate fetching/indexing.
4. **Connect threshold to existing forward impact engine** using current scenario types.
5. **Implement Breaking Point UI component** in existing dashboard; all states and evidence included.
6. **Run tests**, exercise fixture and live read-only scenario, fix failures.
7. **Document result** (what works, proof, limitations, exact commands); only then consider P1, including configurable concentration caps and optional Dune data.

When the repository's real implementation differs from the conceptual interfaces in this specification, prefer minimal adaptation. **Do not generate a fresh standalone repository.**

---

## 12. References and assumptions

### Official and technical sources

- **Belem Capital**, *DeFi Risk Dependency Challenge* (EPFL Hackathon 2026), [provided PDF](../../core/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf) (one page).
- **Morpho Blue** liquidation concepts: https://docs.morpho.org/learn/concepts/liquidation/
- **Morpho Blue** health, collateral and LLTV: https://docs.morpho.org/developers/borrow/concepts/ltv/
- **Pendle** oracle variants: https://docs.pendle.finance/pendle-v2-dev/Oracles/OracleOverview
- **Pendle** TWAP integration: https://docs.pendle.finance/pendle-v2-dev/Oracles/HowToIntegratePtAndLpOracle
- **Pendle** linear discount oracle: https://docs.pendle.finance/pendle-v2-dev/Oracles/DeterministicOracles/LinearDiscountOracle
- Public RockawayX dashboard Dune: https://dune.com/rockawayxvault/rockawayx-dashboard (query identifiers / data schema not yet verified)
- RockawayX risk framework and verified concentration caps: https://www.rockawayx.com/insights/rockawayx-vault-curation-an-overview-of-products-capabilities
- RockawayX vault page, "auto-refreshes every 2hrs" and "Powered by Dune": https://www.rockawayx.com/vaults
- Dune API reference: https://docs.dune.com/api-reference/
- Dune API key safety/terms: https://dune.com/sql-api-terms
- Public RockawayX vault-risk example: https://defillama.com/yields/pool/caa9ffc0-2983-4c18-9556-4e3ad4dfe6ac/risk

### Supplement received from the prior RockawayX conversation (user-supplied)

The feature owner subsequently provided relevant findings from **“Analyze the RockawayX dashboard.”** Those notes identified the public Dune dashboard, suggested real vault allocations as optional data, supplied four concentration hard limits (25/40/40/60), recommended editable risk thresholds and warned that Dune's dynamically loaded query IDs were not available from that earlier analysis. This version records and operationalizes those ideas in **Sections 6.5 and 6.6**.

The four percentages and the website's two-hour auto-refresh text were independently checked against RockawayX's public webpages on 2026-10-10. **The specific Dune query IDs, schema and allocation results have still not been extracted or validated.** Avoid presenting missing Dune data as if verified. The owner-supplied prior-chat notes are contextual guidance, not official Belem rules.

### Final product principle

> **Breaking Point tells the user exactly what has to break, how far the position is from that failure condition, and what the existing FAULTLINE engine estimates at that boundary — without confusing modeling assumptions with observed blockchain facts.**
