# Cascade Radar: liquidation amplification risk for FaultLine

Status: proposed implementation specification. This document describes the intended feature; it does not imply that borrower discovery or execution quotes are already implemented.

## Concept and purpose

Cascade Radar identifies borrowers vulnerable to liquidation in a Morpho market connected to the Pendle PT position that FaultLine already analyzes. It answers:

> If a dependency shock reduces the lending-oracle value of PT collateral, which borrowers could become liquidatable, how much debt would be exposed, and where could additional selling pressure emerge?

The feature extends FaultLine's existing story:

**Pendle X-Ray dependency shock → explicit Morpho oracle-price scenario → liquidation eligibility → possible collateral selling → potential exit-liquidity stress.**

This is a *risk-amplification radar* for portfolio managers, not a liquidation bot or a full market-cascade simulator. The MVP measures conditional liquidation exposure. It does **not** claim to predict how many liquidations will execute, when collateral will be sold, or how far prices will fall.

## Hackathon scope

Implement one Ethereum Morpho Blue market using a Pendle PT as collateral, selected by the existing Pendle X-Ray discovery pipeline. Use real borrower positions and a timestamped snapshot. Evaluate deterministic lending-oracle shocks locally, including scenarios informed by X-Ray when a defensible mapping exists.

Required MVP:

1. Discover borrowing positions in the selected market.
2. Calculate each borrower's current health and distance to liquidation.
3. Under each assumed oracle-price shock, report newly eligible borrowers, eligible debt, and associated collateral exposure.
4. Show the potential liquidation-amplification channel without treating exposed debt as guaranteed sales.
5. Display data coverage and valuation assumptions, and integrate results into X-Ray's lending-market node and analysis payload.

Optional extension after the MVP works:

- Obtain a current Pendle quote for the portfolio manager's PT exit size.
- Model how an assumed fraction of liquidation collateral sales affects exit execution, using Pendle-specific market mechanics.
- Compare immediate exit with staying through the modeled shock on a consistent valuation basis.

Exclude cross-chain scanning, recursive leverage tracing across wallets, transaction execution, wallet signing, alerts, and historical indexing from the MVP. A borrowing position establishes local collateral/debt exposure; it does not prove that the wallet used borrowed funds to buy more PT.

## Exact user flow

1. Open a real Pendle PT/Morpho analysis in FaultLine.
2. Open a **Cascade Radar** panel on that lending-market node, showing market ID, collateral token, loan token, LLTV, snapshot time, and live/cached/demo status.
3. See borrower count, analyzed debt, market debt, and debt coverage percentage.
4. Inspect a borrower table ordered by the smallest additional price decline needed for liquidation. Allow sorting by debt size too.
5. Choose an **assumed Morpho oracle-price decline**: default scenarios are 0%, 2%, 5%, and 10%; optionally use a slider. If launched from X-Ray, display its underlying asset shock separately from the selected oracle scenario.
6. See eligible and newly eligible borrower counts, their debt, and associated collateral exposure for the selected scenario.
7. Read an explanation such as: "Under a 5% decline in the collateral-to-loan oracle price, 8 analyzed positions become eligible for liquidation, representing $420,000 of debt. The snapshot covers 91% of market debt."

The example numbers above are illustrative, not measured results. Eligibility is conditional on the selected **oracle** shock, not a forecast that liquidation or market-wide selling will occur.

## Connection to Pendle X-Ray

Cascade Radar should **reuse**, not duplicate, the dependency-risk analysis already implemented in X-Ray:

1. X-Ray identifies an affected PT, a connected Morpho lending market, and a dependency or price-shock scenario.
2. Cascade Radar selects that exact lending market and uses its real borrower snapshot.
3. **Shock handoff:** distinguish X-Ray's asset/market-price change from the Morpho oracle-price change. Only convert automatically when the market-specific oracle behavior is modeled and documented; otherwise let the user set an explicit oracle shock and label it as an assumption.
4. Calculate the borrowers and debt that cross the liquidation threshold, then display this as a **potential amplification channel** beside the existing direct shock impact.
5. Do not feed the same collateral-price decline back into X-Ray as a second loss. Forced-sales price impact requires a separate, validated execution/liquidity model.

**Boundary of the feature:** Cascade Radar detects *conditions under which liquidation-driven amplification could begin*. Its MVP does not simulate a self-reinforcing cascade through pools, liquidator routes, and subsequent borrower liquidations. That is an optional later research extension.

## Data collection

### Borrower positions

Use Morpho's public GraphQL API. Query `marketPositions` filtered by the selected market and chain, with the borrower address, collateral quantity, and current borrow assets. Morpho documents these fields and market-wide queries in its [API guide](https://docs.morpho.org/developers/api/morpho/).

Paginate rather than treating the first page as the entire market. Filter out zero-debt positions. Prefer descending debt order if a bounded sample is needed for serverless latency. Deduplicate using chain ID, market ID, and borrower address.

If sampling, calculate and display:

```text
debt_coverage = analyzed_borrow_assets / market_total_borrow_assets
```

Use the same loan asset units and as closely aligned a snapshot as possible. If API timing differences make coverage inconsistent, flag the mismatch instead of claiming complete coverage. Do not extrapolate omitted borrowers' health from aggregate debt.

### Market parameters and oracle

Reuse the existing discovery results for market identity, collateral and loan addresses, and LLTV. Add token decimals and the actual Morpho oracle price. Read the market oracle's `price()` through read-only RPC and apply Morpho's documented price scaling. Do not substitute the first underlying Chainlink feed for the full market oracle: the oracle can compose feeds and vault conversion rates.

Keep raw token quantities as integers and perform valuation with decimal or integer arithmetic. Record API observation time, RPC block number, and cache metadata where available. An API fetch time alone must not be presented as the underlying data's block timestamp.

Morpho liquidation uses oracle-valued collateral relative to debt and LLTV. Follow the protocol's strict liquidation eligibility condition and rounding; equality is the boundary, not a reason to invent an extra buffer. See [Morpho liquidation mechanics](https://docs.morpho.org/learn/concepts/liquidation/).

### Free access and caching

The MVP uses public API reads and read-only RPC, with no on-chain transactions. Morpho documents public access and rate limits in its [getting-started guide](https://docs.morpho.org/developers/api/get-started/). Pendle documents a free API tier in its [API overview](https://docs.pendle.finance/pendle-v2-dev/Backend/ApiOverview). Verify current endpoints and quotas during implementation; they can change.

Reuse `http.py` for caching, but extend cache metadata to retain when data was actually fetched. A fallback response must be marked cached. Pre-warm a bounded market snapshot for the demo and run shock calculations from that snapshot without repeated API calls. Respect rate limits and avoid requesting all borrowers on every page refresh.

## Borrower data model

Add a dedicated borrower record rather than overloading the existing generic `Position.value_usd` field.

| Field | Meaning |
| --- | --- |
| `chain_id`, `market_id`, `borrower` | Unique position identity |
| `collateral_asset`, `loan_asset` | Addresses, symbols, and decimals |
| `collateral_raw`, `borrow_assets_raw` | Integer quantities serialized as strings |
| `oracle_price_raw` | Full market oracle valuation and its documented scale |
| `lltv` | Liquidation threshold as a fraction |
| `collateral_value_loan`, `debt_value_loan` | Values expressed in loan-token units |
| `ltv`, `health_factor` | Current local market health |
| `liquidation_drop_pct` | Additional oracle-price decline to the boundary |
| `eligible_now` | Current eligibility using protocol rules |
| `snapshot` | Source, fetch time, block if known, and cached status |

Optional USD values are for display. Local health calculations should use collateral and debt expressed in the same loan denomination. If loan-token USD pricing is unavailable, keep results in loan units rather than inventing USD values.

## Calculations

Let:

- `C` = collateral value in loan-token units under the current market oracle.
- `D` = outstanding debt in loan-token units, including accrued interest at the snapshot.
- `T` = market LLTV as a fraction.
- `s` = fractional decline in the collateral-to-loan oracle price.

For positive collateral and debt:

```text
LTV = D / C
health_factor = T * C / D
shock_collateral_value = C * (1 - s)
shock_health_factor = T * shock_collateral_value / D
liquidation_boundary_drop = 1 - D / (T * C)
```

Use the protocol condition `D > T * shock_collateral_value` for eligibility, with its actual integer rounding in implementation. The equations above describe the economic relationship. At the boundary the health factor is 1.

For display, clamp a negative boundary drop to zero and separately identify positions already eligible. Zero-debt positions are not leveraged borrowers. Positive debt with zero collateral is already unhealthy; avoid dividing by zero. Missing oracle data produces an unavailable result, never a healthy score.

The default shock holds debt quantity and LLTV fixed. Interest growth, loan-asset repricing, and oracle delays are separate scenarios. **A market-price drop does not automatically produce an equal lending-oracle drop**; the module must preserve that distinction when connected to X-Ray.

### Worked example

Hypothetical collateral value is $1,000,000, debt is $800,000, and LLTV is 86%, assuming a stable $1 loan token.

```text
LTV = 80%
health_factor = 0.86 * 1,000,000 / 800,000 = 1.075
boundary_drop = 1 - 800,000 / 860,000 ≈ 6.98%
```

A 5% oracle-price decline leaves the position above the boundary. A 10% decline makes it eligible. The boundary is approximately 6.98%; do not describe that as a probability of liquidation.

### Scenario aggregates and amplification indicator

For each shock return:

- Number of analyzed borrowers eligible under the shock.
- Number newly eligible compared with the 0% scenario.
- Outstanding debt of eligible borrowers, in loan units and USD when available.
- Collateral quantity and value associated with eligible borrowers.
- Eligible debt as a share of analyzed debt and, separately, total market debt.
- Snapshot coverage, missing-data counts, and assumptions.

Label these values **"debt eligible for liquidation"** and **"collateral of eligible positions."** Show the incremental exposure relative to the 0% baseline as the headline *amplification indicator*. These values are not guaranteed debt repayment, collateral seizure, trading volume, or portfolio loss; do not turn them into an ungrounded cascade probability or price forecast.

## Optional extension: exit-liquidity stress

### Current exit quote

Quote selling the portfolio manager's actual PT quantity into the desired output token through Pendle's supported Hosted SDK endpoint. Validate current request and response schemas before implementation; prefer the current documented endpoint rather than copying a deprecated SDK route.

Store input quantity, expected output, output token, quote time, price reference, route, and fee/gas treatment. Compare quoted proceeds with the same quantity's reference value in a common denomination. Count included fees only once. User-selected slippage tolerance is an execution limit, not the measured price impact.

A quote request spends no transaction gas. A quote is indicative, time-sensitive, and does not guarantee that a collateralized position can be unwound through that swap alone. Repaying debt and releasing collateral requires an executable repayment/unwind route; if that route is unavailable, label the quote as PT sale cost only.

### Stressed selling pressure

To model possible sales, first estimate collateral seized using Morpho's liquidation incentive and repayment rules, capped by available collateral. Then apply an explicit `sale_fraction` between 0 and 1: the fraction assumed to be sold through the chosen Pendle venue. Display this assumption.

Do not equate outstanding eligible debt with PT sell volume. Do not assume every liquidator sells immediately or uses the same pool.

An enlarged present-day swap quote is a useful size-impact proxy but does not simulate a preceding sell wave followed by our exit. A genuine stressed exit estimate requires sequential trades against Pendle-specific simulated market state, including fees and maturity effects. The constant-product formula in the current project is insufficient for claiming this accuracy.

Until that model exists, show liquidation exposure beside the current exit quote and mark stressed exit cost unavailable or explicitly approximate. Do not silently feed an unvalidated stress estimate into the authoritative STAY/EXIT verdict.

## Integration with FaultLine

Suggested implementation locations:

- `sources.py`: paginated Morpho borrower reads and full market oracle reads; optional Pendle quote client.
- `models.py`: borrower and snapshot records with explicit quantity and valuation semantics.
- New `cascade_radar.py`: pure health calculations, shock evaluation, and aggregate exposure.
- `api_payload.py`: optional top-level `cascade_radar` object.
- Dashboard and X-Ray UI: compact **Cascade Radar** summary, borrower table, and oracle-shock selector linked to the lending node.
- `http.py`: trustworthy cache timestamps and provenance.

The proposed `cascade_radar` payload contains `status`, `market_id`, `snapshot`, `coverage`, `borrowers`, `scenarios`, `assumptions`, and optional `exit_quote`. Status distinguishes `live`, `cached`, `demo`, and `unavailable`.

Borrower discovery failure must leave the existing risk analysis usable and show the module as unavailable. Synthetic fixtures must be visibly labeled demo. Missing borrower data is not evidence of zero liquidation risk.

Keep the graph compact: attach aggregate liquidation information to the lending node rather than adding every wallet as a graph node.

For the portfolio manager's own leveraged position, define collateral value, debt, and net equity separately. Compare stay and exit outcomes on the same equity basis. Do not add the whole market's eligible debt to the manager's expected loss or count the same price decline twice through both graph propagation and leverage amplification.

The MVP should report conditional stress results beside the existing probabilistic model. Turning them into expected losses requires explicit scenario probabilities and a consistent outcome model; greater liquidation exposure alone does not justify increasing `p_fail` or claiming an actual price cascade.

## Acceptance criteria

The MVP is complete when:

1. At least one real selected PT/Morpho market returns borrower-level collateral and debt.
2. Pagination or bounded sampling is explicit and debt coverage is visible.
3. Health uses the full market oracle with correct token decimals and scaling.
4. The worked example gives a boundary near 6.98%, remains healthy at a 5% shock, and is eligible at a 10% shock.
5. Tests cover protocol boundary behavior, zero debt, zero collateral, missing oracle data, decimal scaling, duplicate pages, incomplete coverage, and cached provenance.
6. Increasing the shock never reduces eligible debt within a fixed snapshot.
7. The UI distinguishes conditional liquidation eligibility from actual liquidations, selling pressure, and simulated price cascades.
8. A cached snapshot reproduces the same scenario results offline and displays its actual age.
9. X-Ray displays the asset/market shock and Morpho oracle shock separately, or documents a verified mapping between them.
10. Existing analysis remains available if the new data source fails.

The exit extension is complete only when real quote fields and denominations are validated, fee handling is explicit, and any stressed execution estimate documents its market model and routing assumptions.

## Implementation priority and demo

Build borrower discovery and coverage first, then pure shock calculations, then the panel and offline snapshot. Add current exit quotes next. Treat liquidation-sale simulation and integration into the final verdict as stretch work after the core analysis works on real data.

For the demo, open one real market, show data coverage, select a 5% shock, inspect the newly eligible borrowers, and explain the possible selling-pressure channel. If only a baseline quote is implemented, state that stressed execution is the next modeling step.

Pitch: **Pendle X-Ray reveals the initial shock. Cascade Radar shows which real borrowing positions could turn that shock into liquidation-driven selling pressure.**
