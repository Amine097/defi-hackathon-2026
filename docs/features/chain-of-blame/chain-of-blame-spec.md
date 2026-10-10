# Chain of Blame — Historical Incident Investigator (TO DO AFTER THE MAIN FEATURES)

**Project:** Belem Capital EPFL Hackathon 2026 · Pendle X-Ray
**Specification:** v4.2 · Implementation handoff for a coding LLM
**Scope:** An additive feature inside an already-working Pendle X-Ray application
**Other feature:** ExitSense (existing; read-only integration only)
**Reference:** Belem Capital, DeFi Risk Dependency Challenge (provided PDF)

**Changes since v4.1:** requires material, time-ordered, graph-connected upstream evidence and a defensible transmission mechanism for supported hypotheses; compares present-day risk to pre-incident baselines; replaces predictive-accuracy claims with a qualified Historical Model Check; distinguishes direct holding loss from leverage/liquidation exposure; promotes root-cause investigation into P0; adds a real-data feasibility gate before implementation and consistent acceptance tests.

---

## 1. Purpose and boundaries

Chain of Blame answers four questions about a selected Pendle position:

1. **What significant event actually happened?**
2. **Which upstream event plausibly contributed, and through what dependency?**
3. **What did it mean for this position, including leveraged exposure if verifiable?**
4. **Is the original risk factor still present today?**

It is a **historical incident investigator**, not a predictive shock simulator, a causal-proof engine, or a trading recommendation system. If evidence does not support attribution, **"Cause undetermined" is a successful, honest result**.

| Existing product | Responsibility |
|---|---|
| Pendle X-Ray | Already discovers PT dependencies, models hypothetical shocks, and provides the existing position and graph views. |
| **Chain of Blame (build this)** | Detects actual historical anomalies, investigates time-ordered upstream evidence, explains plausible transmission paths, overlays evidence on the existing graph, compares today's conditions with the pre-incident baseline, and optionally asks X-Ray how its **current** model would respond to a similar shock. |
| ExitSense | Already handles stay/exit decisions. Chain of Blame displays its outputs read-only where available; it must not recreate or silently alter the decision engine. |
| Cascade Radar (if present) | Separately evaluates conditional borrower liquidation exposure. Chain of Blame may display its existing output as context; it must not rebuild borrower-level liquidation calculations. |

Assume the Belem challenge baseline is implemented: X-Ray dependency discovery, risk estimation, graph, and stay/exit workflow. **Inspect the repository; the challenge PDF is not an API contract.** Use the application's existing name and UI conventions.

### How this serves Belem's judging criteria
- **Impact estimation (30%)**: show a sourced historical value change, clearly separate direct P&L from leveraged risk, and label any current-model comparison as retrospective context, **not** a verified past forecast.
- **Decision usefulness (25%)**: distinguish a recovered event from a still-active risk factor, with evidence and an optional read-only ExitSense result.
- **Dependency discovery (30%)**: illustrate a defensible, possibly contributory path on X-Ray's existing graph; don't claim the graph proves a causal transmission.
- **Working demo on real data (15%)**: investigate at least one pre-verified real incident with truthful coverage and an optional recorded-data fallback.

### In scope
- Fetch historical observations for the selected PT market, relevant X-Ray dependencies, and a small, comparable market-reference set.
- Detect unusual PT events, investigate possible upstream triggers, record evidence and competing market explanations, and show a UTC timeline.
- Highlight verified dependency edges on the existing graph, with provenance (historical or reconstructed from today's graph).
- Compare current conditions with **pre-incident baselines**; show position-specific direct value changes and any separately verified leverage context.
- Optionally run a **Historical Model Check** through X-Ray's existing scenario function with explicit compatibility limitations.

### Out of scope
- Rebuilding X-Ray's graph, risk engine, price forecasts, ExitSense, or Cascade Radar.
- Simulating a new liquidation cascade or treating market-wide eligible debt as the user's loss.
- Proving causality from sequence/correlation; inventing evidence, probabilities, losses, or causes.
- Training an ML model or letting an LLM choose the root cause.
- A global news feed or a trading-execution system.

### Mandatory rules
- Every numerical claim shows its source, units, time window and event/snapshot time; distinguish actual observations from assumptions.
- Never invent prices, transaction hashes, incidents, market references, causal links, or historical positions.
- Never state that a real incident affected Belem Capital or its funds.
- The feature must degrade to partial evidence, "Cause undetermined", or "Insufficient data" rather than manufacture a narrative.

---

## 2. Core user experience

Add **Chain of Blame — Recent Incidents** to the existing Pendle X-Ray market/position page.

1. Default to **last 7 days** for the selected market; offer **24h, 7d, 30d**, and custom historical ranges (max 180 days by default) for a pre-verified real demo incident.
2. Display incident cards with UTC time, type, severity, measured move, market scope, evidence coverage, and present-day status. Separate *incident detected* from *cause investigated*.
3. Opening an incident shows, in this order:
   - **What happened:** sourced PT anomaly and timestamped observed change.
   - **Where else did it happen?** aligned broad-market and sibling-market context; "Undetermined" if references are missing.
   - **What might have triggered it?** ranked upstream hypotheses and **why they qualify**, competing explanations and missing evidence; else "Cause undetermined".
   - **How could it reach this PT?** meaningful transmission mechanism and highlighted **existing** X-Ray path; historic graph provenance shown.
   - **Timeline:** observed facts vs plausible interpretation, UTC timestamps and links. Never silently bridge data gaps.
   - **Impact:** observed direct PT value change, and **separately** leverage or liquidation context only if available from existing, timestamp-compatible data.
   - **Today:** baseline-versus-now comparison for original price/yield/liquidity/depeg/oracle indicators, and a status: *Transient, resolved* / *Structural, still active* / *Ongoing, monitor* / *Undetermined*.
   - **Historical Model Check (optional):** what today's X-Ray scenario estimates for the documented upstream shock. Only display an error/accuracy statistic when a genuinely comparable historical replay exists (§6.7).
   - **Decision context (optional):** existing ExitSense output, read-only, explicitly current vs historical.
   - **Evidence & limitations:** provider, block/transaction links when verified, observation age and uncovered intervals.
4. "View in X-Ray" applies a reversible highlight to the existing graph. "Clear highlight" restores its original state.
5. Empty states distinguish **"No significant incidents found in this period"** (not "No risk"), **"Insufficient data"**, and **"Cause undetermined"**.

Do not redesign X-Ray, alter its results, or make an unverified model comparison part of the STAY/EXIT verdict.

---

## 3. Example investigation (fictional, not historical data)

**What happened (observed):** PT-Example falls from $100 to $94 (−6%) between 11:00 and 12:00 UTC.

| UTC | Observation | Evidence label |
|---|---|---|
| 10:48 | Underlying stablecoin trades at $0.97 (−3% from peg) | Observed |
| 11:02 | Pendle PT market liquidity falls 23% versus its pre-incident baseline | Observed |
| 11:15 | Cluster of PT sells, **only if verifiable transaction data exists** | Observed if sourced; omit otherwise |
| 12:00 | PT-Example USD price is $94 (−6%) | Observed |

**Scope:** aligned ETH/BTC and comparable PT benchmarks do not show a similarly large move; classify as *underlying-specific* only if enough comparable observations exist.

**Cause investigation:** stablecoin depeg is **material**, **precedes** the PT decline at sufficient timestamp resolution, has a **verified dependency path**, and has a **plausible valuation mechanism**. It is a *supported hypothesis*, not a proven cause. Lower liquidity may have amplified the move; alternative market-wide explanations must be considered.

**Impact:** on an unchanged, verifiably held $100,000 PT position, direct mark-to-market change = −$6,000. Borrowing, equity and liquidation proximity are **separate**, shown only if the relevant historical collateral/debt data exist.

**Today:** PT at $95 (approximately 17% of the earlier decline recovered); underlying at $0.975 versus its $1 peg; liquidity still 20% below its pre-incident baseline. Display **Ongoing, monitor — underlying depeg and low liquidity persist**, unless independent, sourced evidence verifies an active *structural* problem. Low recovery by itself is not proof of structural failure.

**Historical Model Check:** a current X-Ray scenario for a −3% underlying shock might estimate a −5.2% PT response. Label it **"Current model applied retrospectively; not a forecast recorded before the event."** Do not show an accuracy score or −0.8 pp "prediction error" without historically comparable assumptions and units.

If the underlying returns to $1, liquidity normalizes, the PT recovers and observations are fresh, label **Transient, resolved**. All figures and identifiers in this section are fictional examples, never production fixtures presented as historical facts.

---

## 4. Data contracts and adapters

Inspect the repository first and reuse existing chain/market IDs, X-Ray graph IDs, historical feeds, charts, scenario interfaces, and position data. If needed, add the smallest read-only adapter. Verify all actual provider endpoints and schemas against their docs; never guess addresses, URLs or transactions.

### 4.0 Mandatory real-data feasibility gate (before building the full UI)

1. **Choose one real market and real historical time interval**, with chain ID, PT/market ID, documented underlying dependency, and links to actual sources. Market selection is data-driven; do not hard-code the demo incident as an app-wide assumption.
2. Verify **minimum viable evidence**: comparable PT observations before/during the anomaly, a timestamped upstream observation that can be linked to an X-Ray graph node, and a sensible pre-incident baseline. Verify event time vs provider fetch time. Prefer at least one aligned market reference and current observations for the "Today" panel.
3. Record a **coverage matrix** (metric, provider, resolution, first/last event time, missing intervals, units, graph-path provenance) and test whether temporal ordering is meaningful at that resolution.
4. Select a genuinely supportable demo case. If the cause cannot be supported, present the real event and explicitly say "Cause undetermined". If there is no real incident with enough data, report this as a blocker rather than fabricate one.
5. Keep a timestamped recorded snapshot for offline demonstration. Offline data must be visibly marked "Recorded data", with snapshot age; never masquerade as live data.

A real PT series **without** upstream evidence is sufficient to report an anomaly, **not** sufficient to claim a root cause. Do not assume all markets have historical liquidity, oracle or transaction histories.

### 4.1 Observations needed

| Metric | For | Typical source (verify) |
|---|---|---|
| `pt_price_usd` | PT market | Pendle historical data |
| `pt_implied_yield_bps` | PT market | Pendle historical data |
| `market_liquidity_usd` | PT market | Pendle historical data |
| `underlying_price_usd` | USD-pegged or priced upstream tokens | existing price provider / DefiLlama coins |
| `oracle_price` | oracle used where the PT is collateral (if X-Ray's graph has one) | RPC call at historical blocks, or existing feed |
| reference prices | ETH, BTC, 1–2 other Pendle PT markets (incl. a sibling maturity of the same underlying if available) | existing price provider / Pendle |
| transactions | swaps/withdrawals in the PT market | RPC logs / indexer, if available |
| protocol events | pauses, exploits, oracle outages | only from a real, attributable, timestamped source |

### 4.2 Types

Illustrative TypeScript boundary; map to the repository's actual language and models.

```ts
type EvidenceKind = 'market_observation' | 'onchain_transaction'
  | 'protocol_event' | 'external_report';
type ClaimStatus = 'observed' | 'plausible' | 'unresolved';
type IncidentType = 'PT_PRICE_MOVE' | 'IMPLIED_YIELD_SPIKE' | 'PT_LIQUIDITY_DROP'
  | 'UNDERLYING_DEPEG' | 'ORACLE_MARKET_GAP' | 'DEPENDENCY_DISRUPTION';
type IncidentScope = 'market_wide' | 'underlying_specific' | 'market_specific' | 'undetermined';
type PresentStatus = 'transient_resolved' | 'structural_active' | 'ongoing_monitor' | 'undetermined';

interface HistoricalObservation {
  id: string;                // Stable, source-derived ID
  nodeId: string;            // Existing X-Ray node ID or explicit reference series ID
  timestamp: string;         // Actual ISO-8601 UTC event time, not request time
  metric: string;            // PT USD price, implied yield, liquidity, oracle price, etc.
  value: string;             // Decimal encoded as string
  unit: string;
  source: string;
  samplingInterval?: string;
  referenceUrl?: string;
  blockNumber?: string;
  txHash?: string;
}

interface IncidentEvidence {
  observationIds: string[];
  kind: EvidenceKind;
  claim: string;
  references: string[];     // Resolved/verifiable actual references only
}

interface IncidentStep {
  timestamp: string;
  nodeId: string;
  title: string;
  status: ClaimStatus;
  evidence: IncidentEvidence[];
}

interface CauseCriteria {
  materialUpstreamAnomaly: boolean;
  precedesWithSufficientResolution: boolean;
  verifiedGraphPath: boolean;
  supportedTransmissionMechanism: boolean;
  marketConfoundersAssessed: boolean;
}

interface CauseCandidate {
  nodeId: string;
  description: string;
  status: 'supported_hypothesis' | 'unresolved';
  criteria: CauseCriteria;
  mechanism: 'valuation' | 'liquidity' | 'redemption' | 'pricing_dependency' | 'other';
  evidence: IncidentEvidence[];
  counterEvidence: string[];
  graphProvenance: 'historical' | 'current_reconstruction';
}

interface ScopeCheck {
  scope: IncidentScope;
  referenceMoves: Array<{ seriesId: string; changePercent: number; window: string }>;
  limitations: string[];
  // No automatic subtraction of an arbitrary average benchmark from observed PT returns.
}

interface PresentStatusResult {
  status: PresentStatus;
  checkedAt: string;
  baselineAt?: string;
  baselineValue?: string;
  worstValue?: string;
  currentValue?: string;
  metricUnit?: string;
  recoveryRatio?: number;  // Direction-aware for suitable reversible metrics only
  causeStillActive?: boolean | null; // null = insufficient evidence
  structuralEvidence?: string[];    // source-backed; empty does NOT prove structural
  details: string[];
  limitations: string[];
}

interface ModelCheck {
  available: boolean;
  reasonIfUnavailable?: string;
  comparisonMode: 'contextual_only' | 'historically_comparable';
  shock?: { nodeId: string; changePercent: number };
  modeledPtMovePercent?: number;     // Current X-Ray scenario output
  observedPtMovePercent?: number;    // Historical PT change, same numeraire/window
  comparableErrorPoints?: number;    // ONLY for verified comparable historical replay
  assumptions: string[];            // graph version, price unit, maturity, liquidity, model timestamp
  notes: string[];
}

interface ChainOfBlameIncident {
  id: string;
  chainId: string;
  marketId: string;
  positionId?: string;
  type: IncidentType;
  startedAt: string;
  endedAt: string;
  detectedAt: string;
  title: string;
  severity: 'medium' | 'high' | 'critical';
  measuredChanges: Array<{ metric: string; before: string; after: string; changePercent?: number; unit: string }>;
  scope: ScopeCheck;
  steps: IncidentStep[];
  possibleCauses: CauseCandidate[];
  implicatedNodeIds: string[];
  implicatedEdgeIds: string[];      // Existing X-Ray IDs only
  observedPositionImpactUsd?: string; // Direct PT mark-to-market only; not total equity loss
  leverageContext?: {
    collateralChangeUsd?: string;
    debtAtStart?: string;
    equityAtStartUsd?: string;
    healthAtStart?: string;
    healthAfter?: string;
    evidence: IncidentEvidence[];
  };
  modeledImpact?: string;          // Existing X-Ray output, labelled modeled
  modelCheck?: ModelCheck;
  presentStatus: PresentStatusResult;
  decisionContext?: { exitSenseAtStart?: string; exitSenseNow?: string; retrospective?: string };
  limitations: string[];
}
```

### 4.3 Data integrity requirements
- Every number has a source, time window, time resolution and unit; USD price, PT-to-asset exchange rate, implied yield and liquidity are **not interchangeable**.
- PT behavior depends on maturity, yield, quote asset and discount mechanics: do not call normal time-to-maturity convergence an incident.
- Depeg detection applies only to tokens intended to track a particular peg; use the correct reference.
- Historical graph links require at-the-time evidence when available. When only today's X-Ray graph exists, label paths **"Reconstructed using current dependencies; historical topology unverified"**; do not silently infer historical exposure.
- Distinguish **provider fetch time**, on-chain **block time**, and actual sample/event time. Compare events only when ordering is resolvable at the sampling interval.
- Deduplicate one underlying event shared by several positions; compute position consequences individually without double-counting.
- Record **cause-investigation coverage** separately from PT incident-detection coverage. Missing upstream data cannot mean "no upstream cause".

---

## 5. Detection

### 5.1 Procedure
1. Resolve the market, PT and relevant node IDs from the existing X-Ray graph.
2. Load historical PT data and only the relevant upstream/reference series, with observation metadata.
3. Validate timestamp alignment, decimals, denominators, missing intervals and baseline windows.
4. Detect PT anomalies first, then investigate candidate upstream anomalies (§6); allow an anomaly with **no attributable cause**.
5. Coalesce continuing anomalies into stable incidents (default cooldown 30 min); deterministic IDs across reruns.
6. Compute severity (§5.4) and data coverage independently; sort newest first.

### 5.2 Detectors

Trigger an anomaly when either the fixed threshold or a supported volatility-relative threshold is exceeded. Volatility-relative threshold: `k × median absolute change` for the **same metric and comparable window** over a prior 30-day baseline (default `k = 4`). If prior coverage is insufficient, disable that relative rule and show the limitation; do not silently calculate it from sparse data.

| Detector | Illustrative fixed threshold | Gate |
|---|---|---|
| `PT_PRICE_MOVE` | PT USD price moves ≥ 5% over 60 min | ≥2 reliable comparable samples; check underlying/maturity repricing; **P0 incident anchor** |
| `UNDERLYING_DEPEG` | eligible pegged upstream token deviates ≥2% for ≥15 min | confirmed peg and aligned observations; **P0 candidate signal if applicable** |
| Upstream market-price anomaly | relevant dependency's comparable price move exceeds configured threshold | use existing metric detectors on upstream nodes; **P0 candidate signal for non-pegged underlyings**, not a new feed of arbitrary "incidents" |
| `IMPLIED_YIELD_SPIKE` | implied yield changes ≥150 bps over 60 min | exclude normal maturity convergence; **P1 unless reliable history is already available** |
| `PT_LIQUIDITY_DROP` | USD liquidity falls ≥20% over 60 min | consistent pool/definition and timestamps; **P1 or supporting evidence** |
| `ORACLE_MARKET_GAP` | compatible oracle vs market valuation gap ≥2% for ≥30 min | existing collateral-oracle relationship, normalized units; **P1** |
| `DEPENDENCY_DISRUPTION` | verified pause, exploit, outage | actual timestamped attributable record; **P2** |

The **P0 goal is one real PT anomaly with a real, tested upstream investigation**, not every detector. If PT-only data exist, show the observed incident and "Cause undetermined" rather than simulating liquidity or transaction history.

### 5.3 Computation rules
- For meaningful nonzero baseline values, percentage delta = `(after − before) / abs(before)`; for implied yield use basis-point change, not percentage of yield.
- Missing/stale data invalidate or weaken a detector; never fill gaps with zero or imply observations that did not occur.
- Record baseline selection, sample count, coverage, event-time uncertainty and exact threshold that fired.
- Compare reference moves using the **same** UTC time windows and price denomination whenever possible.

### 5.4 Severity (explicit, configurable)
Compute a magnitude ratio `m = observed move / fixed threshold` (use the larger ratio if several detectors fire), then:

| Severity | Rule |
|---|---|
| `critical` | `m ≥ 3`, **or** `m ≥ 2` and present status `structural_active`, **or** observed position impact ≥ configured USD threshold (default $100k) |
| `high` | `m ≥ 2`, **or** anomaly persisted ≥ 3 hours |
| `medium` | otherwise (any detector fired) |

Severity is recomputed when present status changes. Unit tests cover each band.

---

## 6. Investigation (concrete algorithm)

Put evidence and explainable attribution **ahead of** additional detectors. All tunable thresholds and admissible data resolutions live in a single configuration. Attribution results must remain deterministic and auditable.

### 6.1 Anchor
The anchor is the observed event in the card (e.g. PT −6% between 11:00 and 12:00).

### 6.2 Candidate causes
Traverse upstream X-Ray nodes using a bounded, cycle-safe search (max 5 paths per candidate). Seek **observed, material anomalies** in an incident-relevant lookback window (default 6 hours; longer only if supported by evidence). Match node IDs, units, event time and the graph's stated economic dependency. Do not promote an event with an overlapping/too-coarse timestamp into a claim that it "preceded" another event.

For a feasible **P0**, cover the selected PT and at least one real, data-supported upstream asset. Investigate other nodes opportunistically; label gaps rather than treating missing nodes as healthy. Never choose a cause merely because it happens to be the earliest recorded anomaly.

### 6.3 Scope check (market-wide vs local)
Compare aligned returns for broad references (e.g. ETH/BTC) and **relevant** PT peers/sibling maturities over the exact anchor interval. Avoid averaging unrelated series and treating the result as a causal market component.

- Broad benchmarks with material, same-direction moves **and** sufficient coverage → `market_wide` or "market-wide contribution".
- The affected underlying or same-underlying sibling PTs move materially, without similar broad-benchmark shifts → `underlying_specific`.
- The selected PT is unusually affected relative to valid peers → `market_specific`.
- References are missing or incomparable → `undetermined`.

Record individual reference moves, comparison logic, missing coverage, and competing explanations. A market-wide event can **coexist** with an upstream contribution; do not automatically claim exclusivity or subtract an arbitrary reference average from historical PT loss.

### 6.4 Rank candidates by evidence (no invented probabilities)

Each candidate must be evaluated independently on **five explicit checks**:

1. **Material:** upstream move is real, sourced, and significant relative to the correct metric baseline.
2. **Time order:** it started before the downstream anchor at an observation resolution sufficient to establish order.
3. **Path:** the actual X-Ray graph contains the relevant upstream-to-PT edges. Mark a path reconstructed from today's graph as historically unverified.
4. **Mechanism:** explain **how** this specific dependency can transmit value/redemption/liquidity/oracle effects; point to observations or verified product mechanics. Graph adjacency alone is not a mechanism.
5. **Confounders:** inspect meaningful same-window market references, competing upstream events, and contradictory evidence; say when any check is unavailable.

A candidate is `supported_hypothesis` only if **checks 1–4 pass** and the available confounder evidence has been assessed **without an unresolved direct contradiction**. If a key criterion is missing (including unusable market-context coverage that prevents any assessment), show `unresolved`, even if the timing looks persuasive. All language remains "likely contributed" / "consistent with", **not** "proven root cause".

Rank qualifying candidates by evidence completeness, specificity of mechanism, then temporal fit; display competing explanations and counterevidence. No magic 3/4 score, fake confidence %, or causal declaration. If none qualifies, display **"Cause undetermined"**, with what data would be needed. Present broad-market context as an alternative or additional contributor, not proof that the upstream link is false.

### 6.5 Position-specific financial impact

**Direct PT value change** (not total leveraged equity loss):

`observedPositionImpactUsd = PT units held at incident start × (PT USD price at end − PT USD price at start)`.

Only calculate this when the historical PT quantity and comparable price pair are available. If the position changed during the incident, account for timestamped deposits/withdrawals/trades with the existing portfolio ledger, or **do not present a single "realized loss" figure**. Mark this as observed **mark-to-market** change, not automatically realized trading P&L or executable proceeds.

**Leverage consequences** are a separate read-only layer: if timestamp-aligned collateral quantity/value, debt denomination, loan/oracle prices and liquidation rules are available from the existing market/position system (or Cascade Radar when present), show collateral value change, debt, equity `collateral − debt` on the **same valuation basis**, and health/liquidation proximity. No historical leverage data → display "Historical leverage impact unavailable"; don't reuse today's balances as historical ones. A PT value decline can be large relative to equity, but it is **not** a second loss to add to PT mark-to-market decline.

Keep existing X-Ray projected losses and ExitSense exit cost **separate** from observed historical changes. Never add market-wide eligible debt, estimated selling pressure, or an unreliably priced exit to the user's realized loss.

### 6.6 Present-day status — compare against the original baseline

At detail request and refresh, use **fresh observations for the same metric and valuation method as the original incident**, together with a pre-incident baseline:

1. Identify the pre-incident baseline `B`, event extreme `W`, current observation `N`, observation timestamps, and whether the metric's normal level evolves with maturity. Use a meaningful pre-incident window rather than a single stale tick.
2. For a downward price/liquidity event, calculate `recoveryRatio = (N − W)/(B − W)` when `B > W`. For an upward spike use `(W − N)/(W − B)` when `W > B`. Report raw ratio and a **clamped 0–100% recovery display** if desired. For depegs, oracle gaps or yields, use the correct peg/normalized baseline/maturity-adjusted comparator; do not force an invalid recovery ratio.
3. Assess whether the **original risk condition remains** relative to its appropriate baseline: e.g. underlying still below peg, liquidity still 28% below pre-incident, oracle-market gap still open, relevant yield still abnormally high. **Do not just rerun a short-window spike detector**: a week-long depressed level can be dangerous without a new hourly spike.
4. Mark `structural_active` **only** with separately sourced evidence that an underlying structural problem persists (such as an ongoing verified protocol impairment, broken redemption mechanism or sustained unresolved oracle defect). A price remaining low, by itself, does **not** prove structural failure.

| Evidence today | Status |
|---|---|
| Original anomaly substantially recovered **and** identified supporting risk signals have returned to the appropriate baseline, with adequate fresh data | `transient_resolved` |
| Sourced, identifiable structural defect persists, with affected risk indicators still abnormal | `structural_active` |
| Material baseline deviation or suspected contributor persists, **without proof of structural failure**, or recovery is mixed | `ongoing_monitor` |
| Current/pre-incident baseline data missing or too stale to determine status | `undetermined` |

If no root cause was identified, the panel may report **"PT recovered"** or **"PT remains depressed"** as an observation, but it must not claim the cause is resolved. Preserve `causeStillActive = null` when unknowable. Show the underlying measurements and timestamps, not only a colored label. ExitSense stays unchanged/read-only.

### 6.7 Historical Model Check (optional; not proof of prior prediction)

The default check is a **retrospective what-if** using X-Ray's **current** scenario model:

1. For a `supported_hypothesis`, identify the historically observed upstream shock (node, percentage/unit and observation window).
2. If the existing X-Ray scenario function can represent that same shock, run it **unchanged**. Record model/snapshot time, graph provenance, market state, maturity assumptions, asset/numeraire, and the modeled PT metric.
3. Show **side by side**: "Current X-Ray model for a similar −X% shock" and "Historical PT move during that incident". **Do not call this a prediction recorded before the event.**
4. Show an **error in percentage points / model accuracy statistic only if** a historically comparable replay is demonstrably available: appropriately historical topology, market/liquidity/maturity parameters, consistent shock definition, same PT metric, denominator, clock window, and controlled treatment of broad-market moves. If any condition fails, use `comparisonMode: 'contextual_only'` and leave `comparableErrorPoints` absent.
5. Do **not** subtract the simple average of ETH/BTC/PT returns from the realized move unless the X-Ray scenario being compared models the *same* explicitly defined excess-return target with a validated benchmark. Otherwise compare observed/raw returns only as contextual observations, not as a scored error.

If no supported cause or runnable scenario exists, return `available: false` with the reason. Any aggregate MAE/bias is **P2 only** and based exclusively on qualifying historically comparable replays; never aggregate contextual-only differences or tune X-Ray here.

### 6.8 Decision retrospective (read-only, P2)
If ExitSense actually stores timestamped historical recommendations, optionally show its recorded state **at incident start**, and its current result distinctly. Do not generate an invented past recommendation by running today's logic on incomplete historical inputs.

Only show counterfactual "exiting then would have avoided $X" when there are source-backed historical holdings, a realistic **executable** exit estimate for that time and consistently denominated subsequent position values. Otherwise omit it. Do not alter ExitSense's verdict.

### 6.9 Claim labels (mandatory)
- **Observed:** measured change or on-chain action backed by a source. "Pool liquidity decreased 22% between 10:00 and 11:00 UTC."
- **Plausible:** mechanism consistent with evidence, causality not established. "Reduced depth may have amplified price impact."
- **Unresolved:** no defensible explanation. "No verified upstream trigger found in the available data."

Timestamp order alone does not prove causation. Avoid "X caused Y" unless the mechanism is directly demonstrated and citeable. Never generate transaction hashes, dates, links, prices or losses as placeholders in production output.

### 6.10 Text generation
Use deterministic templates filled with computed values. An LLM may only rephrase an already-computed, structured result and must not add facts, numbers or causes. All displayed text keeps its evidence and claim labels.

---

## 7. Implementation architecture

Follow the existing repository's stack, routing, API style, data access, caching and component conventions. Names below are illustrative.

```
Existing Pendle X-Ray market page
  └─ ChainOfBlamePanel (NEW)
      ├─ IncidentFeed (NEW)
      ├─ InvestigationDetail + Timeline + Evidence + Baseline-vs-Today (NEW)
      └─ Existing X-Ray graph: apply/clear incident highlight (ADAPTER)

Existing graph + market/position service ───┐
Existing market data / indexed events ──────┼─ HistoricalObservationAdapter
Minimal missing read-only history source ───┤
Market reference series (ETH, BTC, PTs) ────┘
                     │
                     ▼
            IncidentDetector (NEW) ── severity
                     │
                     ▼
            IncidentInvestigator (NEW) ── evidence rules · scope · baseline-vs-today
                     │                      │
                     │                      └─ X-Ray scenario function (existing, read-only) → optional HistoricalModelCheck
                     ▼
            Incident API / server-side cache ── events → alert layer (if present)
```

### 7.1 API (use native calls/server actions if the app is not REST)
- `GET /api/markets/:marketId/chain-of-blame?range=7d` (also `24h`, `30d`, `custom&from=…&to=…`)
- `GET /api/markets/:marketId/chain-of-blame/:incidentId`
- `GET /api/markets/:marketId/chain-of-blame/model-check?range=30d` — optional contextual check; aggregate scored metrics only when historically comparable

Feed response: `{ incidents, generatedAt, range, detectionCoverage, investigationCoverage, warnings }`. The detail endpoint recomputes **baseline-versus-now status** with freshness checks instead of freezing it in the history cache; unavailable current data must not inherit a stale status.

- Unknown range or invalid custom range (from ≥ to, beyond max): 400. Unknown market/incident: 404/authorization response. Provider outage: degraded coverage with explicit warnings or a typed service error; never a fabricated empty success.
- Validate chain/market IDs and ranges; bound lookback and concurrency; reuse existing auth.
- Cache historical scans by (chain, market, range, data-version/time-bucket); deduplicate concurrent requests. Never serve stale cache as fresh evidence.
- Deterministic incident IDs from chain, market, type and initial time bucket.
- Bounded, cycle-safe graph traversal; cap candidate paths (e.g. 5).

### 7.2 Alerts (if the team's alert layer exists)
Emit events in the shared alert format for: new `high`/`critical` incident, present status changing to `structural_active`, and status returning to `transient_resolved` (as a resolution). Stable `signal_key` per incident. Do not create a new notification system.

### 7.3 Offline demo mode
`DEMO_MODE=offline` serves a **real captured** snapshot of the pre-verified case (observations, evidence, cause assessment, status at recording time, optional model check). Include snapshot time and `offline: true`; show **"Recorded data — status as of [UTC time]"**, not "Today" or "live". Synthetic unit-test fixtures must be marked synthetic and must never be shown as historical events.

### 7.4 Frontend
- Follow the current design system; a panel/tab, not a separate app.
- Cards show measured facts first, then scope, baseline-versus-now status and separate detection/investigation coverage.
- "Today: baseline vs now" and optional "Historical Model Check (current-model retrospective)" are separate, clearly labelled blocks.
- Highlight uses the existing graph API; restore styling on exit or selection change.
- States: loading, partial data, empty ("No significant incidents found"), insufficient data, failure.
- Explorer/provider links only when verified; open safely.

---

## 8. Delivery priority for the hackathon

**Before coding — evidence feasibility gate (mandatory)**
- Inspect the existing repository and verify one **real** PT/market, a concrete UTC historical window, a relevant X-Ray upstream node/path, aligned PT and upstream observations, pre-incident baseline, and source links (§4.0).
- Capture a coverage matrix and an honest offline snapshot. If this cannot be shown, revise the demo scope immediately; never fabricate an incident or source.

**P0 — complete, evidence-backed investigation (must ship)**
- Reuse current X-Ray graph/IDs/market selector; implement a minimal read-only historical adapter and `PT_PRICE_MOVE` anomaly detection.
- Support at least one real upstream metric appropriate to the verified case (e.g. a USD-pegged underlying's depeg or a non-pegged dependency's price change).
- **Implement root-cause criteria (§6.4) now**, with materiality, temporal resolution, graph path, explained mechanism, market confounders and honest `unresolved` outcomes.
- Show the UTC observed timeline, graph highlighting/clear, market-scope check if aligned reference data exist, and evidence/coverage limitations.
- Show **pre-incident baseline vs latest comparable reading** with truthful current-status classification; stale/offline data never labelled live.
- Show directly observed PT/position value change **only when historical holdings exist**; otherwise show the PT move and "Position impact unavailable".
- Provide 7-day/default incident feed plus a custom range opening the **prepared real case**, with offline recorded demo fallback.
- Test detector, cause requirements, unresolved path, timeline ordering, baseline status, missing data, cache provenance and unchanged X-Ray/ExitSense.

**P1 — useful additional depth (after P0 works on real data)**
- `IMPLIED_YIELD_SPIKE`, `PT_LIQUIDITY_DROP`, `ORACLE_MARKET_GAP` where genuine history supports them.
- Read-only, timestamp-compatible collateral/debt/health context for a leveraged position; optional current-model **Historical Model Check** (contextual by default).
- Severity refinements, 24h/30d filters, more incidents/markets and efficient caching.

**P2 — only if time allows**
- Truly comparable historical model replay and scored backtesting; verified past ExitSense recommendations and executable exit retrospectives; alerts, historical graph reconstruction, transaction-level tracing, external protocol-disruption records.

**Quality bar:** one traceable real event, a defensible hypothesis (or an explicit unresolved conclusion), a real X-Ray path, and a baseline-versus-now risk assessment beat six half-implemented detectors or an invented causal story.

---

## 9. Tests and acceptance criteria

### Automated tests
- One PT decline exceeding either valid threshold → one deterministic incident; normal movement → none; insufficient volatility history disables only the relative detector.
- Historical PT and upstream observations retain event timestamps, resolution, data source, units and coverage; stale/missing history is not zero or "no risk".
- Duplicate scans and overlapping intervals generate stable incident IDs; unrelated graph nodes do not appear in this market's cause list.
- Known causality confounder: earlier asset move **without materiality** → not a `supported_hypothesis`.
- Earlier significant asset move **without verified path or economic mechanism** → `unresolved`.
- Timestamp samples that overlap at low resolution → cannot assert upstream "preceded" PT event; do not promote to supported hypothesis.
- A material, resolvably earlier upstream anomaly with verified path/mechanism and assessed market context → `supported_hypothesis`, still phrased as plausible contribution.
- Broad correlated moves or conflicting evidence appear as competing explanations; no unearned causal certainty.
- Cycle-safe traversal, actual X-Ray graph IDs, reversible highlights and valid historic/current graph provenance.
- Scope classification uses genuinely aligned, comparable reference windows; absent references → `undetermined`, not fabricated market correction.
- PT remains 28% below liquidity baseline for days, without another sharp hourly drop → still `ongoing_monitor` (or `structural_active` only with independent structural evidence).
- Low recovery alone → **not** `structural_active`; recovered and risk indicators normalized with fresh data → `transient_resolved`; missing current baseline/observations → `undetermined`.
- Depeg/pegged references, yield/maturity changes and oracle prices use their **proper** comparators; incompatible units cannot create incidents or status changes.
- Direct PT value impact requires historical units and consistent prices; unknown/changed holdings don't produce a made-up realized loss.
- Leverage context is separate, timestamp-consistent, correctly denominated, and never double-counted with direct mark-to-market change.
- Current X-Ray model vs old incident → `comparisonMode: 'contextual_only'`, **no historical error metric**; only equivalent historically reconstructed replays may calculate `comparableErrorPoints`.
- No cause/no runnable X-Ray scenario → unavailable model check with a reason; ExitSense must stay unchanged.
- Provider outages, bad ranges, unavailable credentials and partial API results preserve the baseline app and report explicit coverage limitations.
- Offline case is **real recorded data**, identified by snapshot time, never advertised as live; synthetic fixtures cannot be shown as real incidents.
- Numbers and timeline evidence are sourced, chronological UTC, and labelled `observed`, `plausible`, or `unresolved`.

### Definition of done
A reviewer opens a **verified real Pendle historical incident** and sees: observed PT anomaly, cited UTC timeline, investigation of at least one real upstream dependency, supported-or-unresolved cause assessment, reversible X-Ray graph path highlight, baseline-versus-current comparisons (or honestly unavailable current data), and explicit data limitations. Optional leverage data and Historical Model Check are clearly distinguished from observed history.

If the real incident cannot support a causal hypothesis, the app must still deliver a truthful, useful investigation showing **why attribution is unresolved**. Real demo coverage and repository tests are required; a synthetic story or an attractive UI with fabricated measurements is **not** a completed feature.

---

## 10. Instructions to the coding LLM

Build **only Chain of Blame** as an additive module inside the existing application. Assume Pendle X-Ray, its dependency graph, risk/scenario function and ExitSense already work. Use existing identifiers, APIs, providers and UI conventions. Do not replace graph/layout or implement Cascade Radar/ExitSense.

**Before implementation:** inspect the repository and **verify a genuine demo market and incident** with PT price history, at least one timestamped upstream observation, relevant existing graph connection, evidence URLs, baseline, coverage matrix and workable sampling resolution (§4.0). Report missing data before deciding which metrics can support a cause.

**Implement P0 end to end:** real incident detection → investigation of significant, time-ordered upstream candidates → verify X-Ray path and economic mechanism → assess market confounders → provide a supported *hypothesis* or "Cause undetermined" → display sourced UTC timeline/graph path → evaluate **today vs pre-incident baseline** without confusing persistence with a new shock. Show separate direct PT value change and historical leverage context **only if actual data exist**. Recorded offline demo is explicitly labelled.

**Optional later:** richer detectors, timestamp-compatible leverage context and a **Historical Model Check**. When X-Ray uses current state for an old shock, show it only as a contextual retrospective; never claim a prior prediction or compute a misleading error statistic. Every effect and uncertainty is sourced; no invented incidents, exposures or Belem Capital losses. Preserve current X-Ray and ExitSense behavior.

**Deliverable report:** which existing interfaces were reused, real demo market/time and source coverage, added modules, tested cases, build/test results, unsolved gaps and how to open the working incident view.

**One-line pitch:** "Pendle X-Ray models what could happen. Chain of Blame investigates what did happen, which dependency plausibly contributed, what it meant for the position, and whether the original risk is still present."
