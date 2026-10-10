# FAULTLINE — Frontend Research, UI/UX Blueprint & Claude Code Playbook

## 0. Design decision in one minute

**You have to build a _risk command center_, not a DEX clone or a generic crypto dashboard.** The jury must understand in a few seconds:

1. **Where is the portfolio exposed?** → dependency mapping + exposure.
2. **What shock would cause it to tip over?** → **Breaking Point**, the centerpiece of the demo.
3. **How much could the portfolio lose?** → impact simulation, with scenarios and assumptions.
4. **What can we do?** → STAY / EXIT and feasibility of an exit, when this data exists.

**Recommended visual direction:** institutional financial terminal, modern, sober and very readable. Almost black slate background, well-defined data areas, careful typography, risk orange used sparingly, clear graphics and _progressive disclosure_. No cyberpunk neon, no permanent decorative animation, no uniform cards to fill the screen.

**Defensible differentiation:** a **single selection** of asset, protocol or dependency synchronizes **the graph, the exposure, the Breaking Point, the financial impact and the decision**. The product tells a causal chain, not five independent graphs.

**Execution priority:** first the **Risk Overview** page and the **Breaking Point** interaction; then **Dependency Explorer**; finally the intelligence/alerting layer if it really exists.

---

## 1. Search for comparable products

### 1.1 Direct references

| Product | Searchable reference | What we remember for FAULTLINE | What we avoid copying |
|---|---|---|---|
| **DeFi Saver** | [Dashboard metrics](https://help.defisaver.com/features/defi-saver-dashboard) · [Risk ratios](https://help.defisaver.com/features/defi-saver-dashboard/health-safety-and-collateral-ratio) | Health ratio, liquidation threshold, metrics by position and details on demand. The **liquidation price can be N/A** with several collaterals: good example of UX prudence. | The complexity of position/trading management interfaces, not very useful in an analysis app. |
| **Gauntlet Risk Dashboard** | [Moonwell example](https://dashboards.gauntlet.xyz/protocols/moonwell/markets/base/assets/cbeth?fullscreen=asset_latest_liquidation_curve) · [Dashboards overview](https://governance.aave.com/t/gauntlet-risk-dashboard-v2-launch/12663) | **Liquidations at Risk**, VaR, market statistics, **liquidation curves**, data freshness. Make a page that looks like a risk analyst work tool. | Dozens of series from the home screen. |
| **Morpho Vaults** | [Example vault with Allocation / Risk](https://app.morpho.org/arc/vault/0x389abDf4355e0cF4f19298179991705a98f21c18/galaxy-eurc) · [Curators](https://morpho.org/curators) | Clear distinction between **allocation / exposure / risk**; filters by market, collateral and adapter; structured terminology. | A flow centered on depositing into a vault rather than analyzing multiple dependencies. |
| **Dune** | [RockawayX Dashboard — link provided by Belem](https://dune.com/rockawayxvault/rockawayx-dashboard) · [Data Hub](https://dune.com/data-hub) | Dashboard structure + graphics + onchain data + analytical depth; good point of comparison with the data actually available. | A wall of SQL charts with no decision hierarchy. |
| **Arkham Visualizer / Tracer** | [Visualizer](https://codex.arkm.com/the-intelligence-platform/visualizer) · [Tracer](https://codex.arkm.com/the-intelligence-platform/tracer) | Navigable graph, filters, link clicking, entity detail and relationship exploration. | Confuse **transaction flow** and **dependency relationships**: they are two distinct graphs. |

**Search Limit:** The RockawayX public link on Dune is accessible, but its dynamic graphical content was not reliably retrievable in this search. You must open it **in a browser** to identify its exact datasets, metrics and graphs; **do not assign anything to the dashboard by assumption**. This document is based on its reference role and on interfaces whose capabilities are documented.

### 1.2 Concrete lessons learned from this comparison

- **DeFi Saver →** show distance to a threshold, not just an abstract score. Show the unit, the calculation method and the cases where the threshold cannot be calculated.
- **Gauntlet →** put current metrics, shock exposure and liquidation curve side by side. Show `updated_at`, network and scenario conditions.
- **Morpho →** distinguish wallet, position, market, collateral, oracle, protocol and chain; Do not mix these dimensions in a single pie chart.
- **Dune →** offer inspectable data and traceability to the source; the FAULTLINE UI must turn data into **a diagnosis**, not merely display another chart.
- **Arkham →** make the graph **actionable**: search, hover, selection, detail panel, causal path. Edges are not decoration.

### 1.3 UX sources / technical tools used

- [Anthropic — official frontend-design skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills) and [CLAUDE.md](https://code.claude.com/docs/en/memory)
- [Microsoft — Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Chrome DevTools MCP — Claude Code integration](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md)
- [shadcn/ui — Vite installation](https://ui.shadcn.com/docs/installation/vite)
- [React Flow — custom nodes](https://reactflow.dev/learn/customization/custom-nodes)
- [TanStack Table — React documentation](https://tanstack.com/table/latest/docs/framework/react)

> **Reading rule:** external references inspire patterns and serve to verify capabilities; The design choices below are **recommendations for FAULTLINE**, not supposed features present in competitors.

---

## 2. Positioning and main user

### 2.1 Target audience

- **Primary:** risk analyst / DeFi portfolio manager / vault analyst.
- **Secondary:** hackathon juror understanding financial fundamentals but not all DeFi plumbing.
- **Fundamental question:** _“If this dependence breaks or if the price moves, what part of my portfolio suffers, at what threshold, and what action remains possible? »_

### 2.2 Product promise (UI copy)

**FAULTLINE**
**Know what breaks first.**
_Subtitle :_ “Map dependencies. Stress-test positions. See the path to liquidation.”

Avoid vague phrases like _AI-powered next-generation security platform_. Do not promise “real-time risk” without proving the freshness of the data and the refresh mode.

### 2.3 The three layers of risk must remain distinct

1. **Concentration / dependence:** how much of the portfolio depends on one entity or component.
2. **Liquidation of a leveraged position:** financial threshold calculated according to the rules of the protocol; concerns **eligible borrowing positions**, not all deposits.
3. **Loss under scenario:** modeled losses during a falling price, a depeg, an oracle failure, a protocol failure, etc. **A smart-contract incident is not equivalent to a price drop**.

The UI should never confuse “$exposed”, “$potentially liquidated” and “$actually lost”.

---

## 3. Information architecture: screens and navigation

### 3.1 Sidebar

```text
FAULTLINE

WORKSPACE
  ◉ Risk Overview             P0 — home page
  ◈ Dependency Explorer       P0 — graph and exposure
  ◌ Stress Lab                P0 — Breaking Point + impact
  ≋ Positions                 P0 — table drill-down

INTELLIGENCE display only if data available
  ◇ Leverage Hunter           P1
  ◇ Whale Impact              P1
  ◇ Chain of Blame            P1

ACTION display only if function implemented
  → Exit Analysis             P0/P2 depending on backend support
  ◉ Alerts                    P2

Footer: Data Sources · Methodology · Settings
```

**Hackathon recommendation:** limit initial navigation to **Overview / Dependency Graph / Stress Lab** + discrete secondary sections. A sidebar overloaded with unfinished features harms the demo.

### 3.2 Persistent header

To the right of the sidebar, a compact bar, common to the pages:

- **Workspace / portfolio selector**: demo portfolio, address or loaded portfolio.
- **Network selector**: All chains / Ethereum / Base / Arbitrum… only if supported.
- **Snapshot timestamp**: `As of 13:42 UTC` + age info + `Live`, `Delayed`, `Snapshot`, `Demo` indicator.
- **Search / command palette**: search for a protocol, an asset or a dependency, if feasible.
- **Help**: legend / method; no “Connect Wallet” if the app does not actually require a signature.

### 3.3 Proposed routes (adapt to the routing already in place)

```text
/                       -> redirect /overview
/overview -> risk summary
/dependencies           -> graph + inspector
/stress                 -> Breaking Point simulator
/positions -> position table
/positions/:id -> position details
/intelligence/* -> if P1 available
/exit -> comparison, if implemented
```

**Do not replace a router already in place** simply to adhere to this proposal.

---

## 4. Design system — chosen visual direction

### 4.1 Text moodboard

**“Institutional risk terminal with editorial precision.”** Character references: density and seriousness of Gauntlet, readability of Morpho, exploration of Arkham, visual finish of a premium financial SaaS tool.

- **Dark mode by default**; possible light mode after the demo.
- **Sober surfaces:** no invasive glassmorphism, light shadows, clear separators.
- **Main visual signal:** a fracture/threshold line that crosses the stress curve and propagates to the graph; no need for 3D illustrations.
- **Controlled density:** useful dashboard in 1440 × 900 without scrolling on 3 screens.
- **Single accent:** cyan/blue for selection and interaction; orange/red reserved for risk.

### 4.2 Proposed palette (tokens, not color coded everywhere)

```css
:root {
  --bg: #0A1018;           /* canvas */
  --surface: #111A25;      /* panels */
  --surface-raised: #182432;
  --border: #293747;
  --text: #F1F5F9;
  --text-muted: #9BADBF;
  --accent: #66D5E8;       /* selection / interaction */
  --positive: #45C6A3;     /* action favorable */
  --warning: #F7B955;      /* seuil proche */
--critical: #FF6F6A;     /* proven risk / liquidation */
  --neutral: #7F91A6;
}
```

These hexes are a starting point. Check the **real contrasts** (text, badges, chart labels, focus states) and adjust them before validation. Do not encode states by color alone: ​​text, shape/icon and value must be sufficient.

### 4.3 Typography

- **Titles / UI:** `Manrope` or `IBM Plex Sans`; choose **one** direction, then stick with it throughout. Default: IBM Plex Sans for technical credibility.
- **Numbers / tabular data:** `IBM Plex Mono`, with `font-variant-numeric: tabular-nums`.
- Page titles 24–30 px, panel titles 14–16 px, metrics 28–40 px, labels 12–13 px, body 14–15 px.
- Monospace only for numbers, units, timestamps, addresses and technical labels; not for long paragraphs.

### 4.4 Layout and components

- Fixed sidebar **220–240 px**; compact header **60–68 px**; content with `max-width` suitable for graphics, not a central tunnel.
- Gutters **16–24 px**, card radius **10–12 px**; strict alignment of titles, metrics and charts.
- Reusable components: `MetricCard`, `RiskBadge`, `SourceTag`, `FreshnessIndicator`, `TokenIcon`, `ProtocolIcon`, `SectionHeader`, `EntityInspector`, `ScenarioPreset`, `AssumptionTooltip`, `EmptyState`, `DataWarning`.
- Icons: `lucide-react`, consistent symbols. No emoji in the final interface.
- Effects: functional transitions 120–200 ms; respect `prefers-reduced-motion`; do not constantly animate the edges of the graph.

### 4.5 Financial microcopy — precise terminology

| To display | Avoid |
|---|---|
| `Exposed capital` | `Money lost` for simple exposure |
| `Modeled loss` / `Estimated loss` | `Guaranteed loss` |
| `Liquidation threshold` | `Crash prediction` |
| `Price shock to first liquidation` | `Breaks at -12%` without identifying the factor |
| `Unsupported` / `Not modeled` | `0 risk` for absent data |
| `Snapshot · 10 min old` | `LIVE` if the data is a snapshot |
| `Simulated — no transaction will be executed` | EXIT button suggesting an effective sale |

---

## 5. Screen A — Risk Overview (P0, jury screen)

### 5.1 Goal

In **less than 10 seconds**, a person should see **exposure**, **critical dependency**, **break point** and **plausible impact**. Breaking Point must be visible **without navigation**.

### 5.2 Illustrative desktop wireframe (1440 × 900)

```text
┌─────────────────┬────────────────────────────────────────────────────────────────────────┐
│ FAULTLINE       │ Portfolio: Demo Vault ▾  Network: All ▾  Snapshot 13:42 UTC · Demo     │
│                 ├────────────────────────────────────────────────────────────────────────┤
│ ◉ Overview      │ Risk Overview                                      [Methodology ↗]     │
│ ◈ Dependencies  │ See where concentration turns into liquidation risk.                   │
│ ◌ Stress Lab    │                                                                        │
│ ≋ Positions     │  [Capital monitored]  [Top dependency]  [First break]  [Modeled loss]  │
│                 │                                                                        │
│                 │ ┌─────────────────────────────────────────┬──────────────────────────┐ │
│                 │ │ DEPENDENCY MAP                          │ CRITICAL EXPOSURES       │ │
│                 │ │                                         │                          │ │
│                 │ │  [Vault] ─ [Aave] ─ [Oracle]            │ 1  Chainlink ...  62%   │ │
│                 │ │          ╲ [Curve] ─ [Stablecoin]      │ 2  USDC ...       41%   │ │
│                 │ │                                         │ 3  Aave ...       29%   │ │
│                 │ │ [Filters]  [Fit view] [Fullscreen]      │ [Open graph →]           │ │
│                 │ └─────────────────────────────────────────┴──────────────────────────┘ │
│                 │                                                                        │
│                 │ ┌─────────────────────────────────────────┬──────────────────────────┐ │
│                 │ │ BREAKING POINT                          │ DECISION SUPPORT         │ │
│                 │ │                                         │                          │ │
│                 │ │  First liquidation: ETH -18.4%*        │ Scenario: ETH -20%       │ │
│                 │ │  [health factor vs price shock]         │ Model loss: $...         │ │
│                 │ │             │ threshold                │ Exit cost: $...          │ │
│                 │ │  [Open Stress Lab →]                    │ Stay/Exit: ...           │ │
│                 │ └─────────────────────────────────────────┴──────────────────────────┘ │
└─────────────────┴────────────────────────────────────────────────────────────────────────┘
* figures purely illustrative, do not display them as actual calculations.
```

### 5.3 Four headline metrics

1. **Capital monitored — $**: calculation basis explained (NAV, gross collateral, amount exposed — according to backend).
2. **Top dependency — name + %**: % of the portfolio dependent on this node, according to the backend definition.
3. **First breaking point — factor + shock %**: **first modeled liquidation among eligible positions**, *or* `Not available` (see §7).
4. **Modeled downside — $ or %**: loss according to **a defined and visible scenario**, not a raw figure without hypothesis.

The “First break” metric has to be the most memorable. No false “Risk 92/100” score if no model provides it.

### 5.4 Key interaction

`Click on “USDC” dependency` → highlighting of exposed positions, `Dependency Inspector` panel, updating of metrics calculated for the selected scope (if backend allows it), `View in Graph` and `Stress this dependency` buttons. Data that cannot be recalculated with the scope remains explicitly marked `Portfolio-wide`; **do not claim they have been filtered**.

---

## 6. Screen B — Dependency Explorer (P0)

### 6.1 Structure

- **70% of the area**: interactive graph with zoom/pan, selection and mini-legend.
- **30%**: resizable inspection panel or fixed drawer for the selected node.
- Filter bar: `Entity type`, `Chain`, `Protocol`, `Minimum exposure`, `Risk state`; search field and `Reset` button.

### 6.2 Graph semantics — non-negotiable

- **Node:** `portfolio | position | protocol | assets | oracle | chain | vault | bridge | other`, **only really recognized types**.
- **Directed edge:** relation `depends_on | uses_oracle | collateralized_by | deployed_on | invested_in | other`, from the data, with meaning defined by contract.
- **Node size:** visual exposure *if available and comparable value*, otherwise standard size by type.
- **Color/outline:** risk state or category, never two contradictory semantics.
- **Opacity:** nodes not linked to the selection attenuated; the propagation path remains visible.
- **“Why exposed?” panel :** list of positions and paths that connect the portfolio to the dependency.
- **Cycle:** if the data contains a loop, render it without duplicating the amounts; the exposure percentage is provided by the backend, not by naive summation of descendants.

### 6.3 Inspector example

```text
CHAINLINK ORACLE
Type: Oracle             Chain: Ethereum
Dependent positions: 7    Exposed capital: $... / ...%

Why it matters
  Portfolio → Aave V3 → WETH market → Chainlink ETH/USD
  Portfolio → Morpho → ... → Chainlink ETH/USD

[Inspect positions]  [Simulate oracle incident]
Source · block #... · updated ... · View evidence ↗
```

**Important:** if `Exposed capital` or path are not present, display `Unavailable` or **hide the detail**, rather than falsely inferring an exposure from the node size.

### 6.4 UX optimizations

- Default: **relevant subgraph**, not 250 unreadable nodes. `Expand neighbors` / `Show all` on request.
- Two modes: `Exposure map` (coloring by %) and `Failure path` (propagation under scenario), second mode only if data provided.
- Clicking on an edge reveals **relationship type**, source, exposure factor and trust if available.
- `Fit to view`, `Reset filters`, `Esc` key to deselect, keyboard navigation/fallback list accessible.
- Indicate `Graph is a dependency model, not a transaction flow` in the legend.

---

## 7. Screen C — Stress Lab / Breaking Point (P0, differentiating)

**This screen is the heart of the project.** The design must make it understandable **what minimal shock** would trigger a **first liquidation** and which positions would then be affected.

### 7.1 Financial principles to be preserved

- **Breaking Point is not a probability.** `-18%` means a conditional shock in a model, **not** “18% chance of liquidation”.
- A shock is defined **by factor** (`ETH/USD`, `USDC/USD`, collateral price, spread, etc.) and by **direction** (increase/decrease); a single universal % is irrelevant.
- The threshold depends on the **protocol, assets, debt, health factor and model assumptions**.
- A position **without a liquidable loan** does not necessarily have a liquidation threshold: use `N/A · No eligible debt`, never `0%`.
- An **oracle** or **smart-contract** incident does not automatically have a calculable “minimum price shock”; show `Not modeled` or other crash result if backend distinguishes it.
- If the loans include several collaterals, the reactions can be **non-linear**; do not extrapolate a simple single liquidation price formula.

### 7.2 Screen layout

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ STRESS LAB                                         [Scenario: ETH selloff ▾] [Reset]   │
│ Explore the smallest modeled shock that triggers a liquidation.                         │
├───────────────────────────────┬──────────────────────────────────────────────────────────┤
│ SCENARIO BUILDER              │  BREAKING POINT                         [Model info]     │
│                               │                                                          │
│ Shock factor                  │  ETH/USD ↓ -18.4%* to first liquidation                  │
│ [ETH/USD ▾]                   │  Position: Aave V3 / WETH-backed USDC debt               │
│                               │                                                          │
│ Change (%)                    │  Health factor                                           │
│ [-30% ━━━●━━━━━━ 0%]          │  2.0 ┤                                                   │
│ [-30.0]                       │  1.5 ┤── current ───────╲                                 │
│                               │  1.0 ┼ - - - - - - - - -● - liquidation threshold        │
│ Presets                       │      0%      -10%      -18.4%       -30%                │
│ [-5%] [-10%] [-20%] [-30%]    │                                                          │
│                               │  [Current state] [At breaking point] [Selected shock]   │
│ [Run scenario]                │                                                          │
├───────────────────────────────┴──────────────────────────────────────────────────────────┤
│ CONSEQUENCES                                                                              │
│ [Positions affected]  [Debt at risk]  [Estimated loss]  [Liquidity needed]                │
│                                                                                          │
│ Position          Protocol  HF current  HF stressed  Breakpoint  Estimated impact        │
│ ...               ...       ...         ...          ...         ...                     │
│                                                                                          │
│ [View impact calculation]       [Compare stay vs exit]                                    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
* valeurs illustratives uniquement.
```

### 7.3 Display of the main result

**Recommended wording:** `First modeled liquidation at ETH −18.4%` (figure **only** if the API returns this value). Below: `Position [X] · Aave V3 · liquidates at health factor ≤ 1.00` **only if this threshold is valid for the configured protocol/market**. For other protocols, use `liquidation criterion` + received rule.

To the right of the metric, small map: `Current HF`, `HF at selected shock`, `Liquidation threshold`, `Model version`.

### 7.4 Essential visualization

**Courbe x/y :**

- X axis: shock of the **selected factor** in % (zero clearly identified).
- Y axis: `Health factor` or `Distance to liquidation` depending on the motor output.
- Horizontal line: liquidation threshold **backend source**.
- Vertical marker: first break point.
- Additional marker: shock currently chosen by the user.
- “Liquidation possible” zone: slight critical tint (never remove labels).
- Exact tooltip: shock%, stressed price (if relevant), calculated health, position, hypotheses; consistent formatting.

If the API only provides **the threshold** and **not a series of simulations**, do not make a curve that claims to be calculated. Instead, display **a graduated scale with the threshold** or request a curve endpoint. This is a fundamental point of trust.

### 7.5 Detailed interactions and states

1. The user chooses a risk factor and a preset `ETH -20%`.
2. Sliders do not trigger 50 backend calls per second: local state + appropriate debounce; `Run scenario` button if expensive calculation.
3. The result area displays `Calculating…` **without keeping outdated values ​​presented as current**.
4. Metrics update **atomically** from the same `scenario_id` / same timestamp.
5. The position table is sorted by **increasing liquidation distance**.
6. Clicking on a line opens its detail and highlights its path in the graph, if available.
7. Clicking `Reset` restores exactly the initial scenario; `Share scenario` only if URL/query params actually reproduce the state.

**States to manage:** `Idle`, `Loading`, `Success`, `No liquidation within modeled range`, `Not modeled`, `Unsupported factor`, `Stale snapshot`, `Backend error`, `Invalid input`. The states “no liquidation within range” and “risk = zero” are **not** synonymous.

### 7.6 Scenario variants (only if compatible engine)

- `Asset selloff`: reduction of collateral.
- `Stablecoin depeg`: loss of a stablecoin's peg.
- `Correlated crash`: several factors vary together, from an explicit **matrix/rule** of the backend.
- `Oracle divergence`: divergence/delay/oracle unavailability event; render as an **incident** if no direct liquidation calculation exists.

**Do not confuse** price simulation and logical failure of a protocol. Any unsupported variant should be left inactive, not masked.

### 7.7 Integration requirements with the Breaking Point engine

The frontend **never invents** the liquidation results. On the TypeScript side, build an adapter to the current backend response. Example of an **indicative target** model (to be **adapted**, this is not a documented existing API):

```ts
// Desirable interface types, to map to actual contracts.
type ResultStatus =
  | 'computed' | 'not_applicable' | 'not_modeled'
  | 'outside_range' | 'insufficient_data' | 'error';

type BreakingPointView = {
  status: ResultStatus;
  portfolioId: string;
  scopeId?: string;
  scenarioId: string;
  asOf: string;                 // ISO 8601
  chainId?: number;
  factor: { id: string; label: string; unit: '%' | 'USD' | 'bps' };
  firstLiquidation?: {
    positionId: string;
    shockPercent: number;      // signe explicite : ex -18.4
    thresholdValue?: number;
    currentValue?: number;
  };
  samples?: Array<{
    shockPercent: number;
    healthFactor?: number;
    distanceToLiquidation?: number;
  }>;
  impactedPositions?: Array<{
    positionId: string;
    status: 'safe' | 'near_threshold' | 'liquidatable' | 'unknown';
    currentHealthFactor?: number;
    stressedHealthFactor?: number;
    estimatedLossUsd?: number;
  }>;
  methodology?: { version?: string; assumptionLabels?: string[] };
  errorMessage?: string;
};
```

**Criteria:** a percentage is not a fraction without definition; `-18.4` != `-0.184`. The USD components and the `Health Factor` are distinct. Separate `null`, `undefined`, `0`, `not modeled`, `N/A`. Optional fields **do not always exist**: do not make `0` by default.

---

## 8. D–F screens — other features, without inflating the scope

### 8.1 Positions (P0)

Filterable and sortable table: `Position`, `Chain`, `Protocol`, `Collateral`, `Debt`, `Exposure`, `Health factor`, `Breaking point`, `Modeled impact`, `Data status`. Priority to **available** columns, not an empty grid. Click on line → details with origin and link to pre-filtered Stress Lab.

### 8.2 Impact Estimation & STAY/EXIT (P0)

On the selected scenario: two columns **same assumptions and timestamp**:

```text
STAY                                EXIT
Modeled downside: $...              Exit costs: $...
Positions at risk: ...              Liquidity / slippage: ...
Scenario assumptions: ...           Executability: ...

[Recommendation from backend] [Why?] [Evidence]
```

**Caution:** `STAY` / `EXIT` should appear as **template output**, not guaranteed advice. If the exit analysis is not calculated, `Exit analysis unavailable`; do not invent fees, gas or slippage. `EXIT` is **not** a trade execution button unless a real trade has been implemented with user consent.

### 8.3 P1 Threat Intelligence

- **Leverage Hunter:** `Liquidation proximity × Debt/exposure` table; positions closest to the threshold at the head; aggregated views if available and legitimate public addresses.
- **Whale Impact:** verified onchain flows → timestamped events → assets/protocols concerned; **do not automatically infer the future price** of a transaction.
- **Chain of Blame:** causal graph of a selected incident with `observed` / `modeled` / `inferred` distinction; path `source → impacted dependency → affected positions → loss`.

These elements must not block P0. If the backend is missing, do not add false screens filled with static data presented as live.

### 8.4 P2 Action Layer

- **Exit Feasibility:** market depth, liquidity, fees, slippage and restrictions, if retrieved/calculated.
- **Telegram Alerts:** only if **true** service + permissions + connection status; simulation message explicitly marked as test.
- **Reaction Window:** display an **estimate depending on a speed scenario** (e.g. `% per minute`) only if the model provides assumptions and estimated time. A price threshold alone does **not** provide a reliable lead time.

---

## 9. The jury demo: a 90-second walkthrough

**Demonstration dataset:** **synthetic** snapshot, consistent between graph, positions, metrics and simulation. Label `Demo data`. For the figures below, it is necessary to **construct a mathematically coherent dataset** or replace them with existing results; The values ​​below should not be displayed as authentic.

1. **0–15 s: Overview.** `This portfolio looks diversified, but 62%* depends on the same oracle.` Point out a common dependency behind several positions.
2. **15–35 s: Graph.** Click on the node, highlight the positions and the causal path. _“The risk is not obvious by looking at protocol names alone.”_
3. **35–65 s: Stress Lab.** Apply `ETH −20%`; display a breakpoint at `−18.4%*`, the position(s) concerned, the curve and the updated table.
4. **65–80 s: Impact.** Show **estimated** losses and what constitutes exposure, liquidation and loss.
5. **80–90 s: Decision.** Compare STAY/EXIT or show a possible action **only if calculation available**; otherwise end with the diagnosis and its proofs.

`*` Narrative values ​​**fictional** to illustrate the scenario. Replace with a single fixture calibrated with the data actually returned by the engine; the maps and curves must correspond to the same parameters.

**Presentation mode:** be able to switch to `Demo snapshot` without wallet / keys / RPC. No infinite spinner in the event of a network outage. The interface should always indicate that demo mode is active. **Never display a demo snapshot as a live stream.**

---

## 10. Recommended frontend stack (adapt to existing repository)

| Need | Recommended choice | Why / limit |
|---|---|---|
| Application | **React + TypeScript + Vite** if existing client app or greenfield; **Next.js** if already used | Do not migrate frameworks during the hackathon without reason. |
| Styles | **Tailwind CSS + CSS variables** | Speed ​​+ controllable tokens. |
| Accessible components | **shadcn/ui + Radix primitives** | Dialogs, selects, drawers, tooltips, tabs, skeleton table. Highly customize. |
| Iconography | **lucide-react** | Consistency. |
| Dependency graph | **@xyflow/react (React Flow)** | Custom nodes/edges, zoom, pan, selection, minimap; predict automatic layout and performance. |
| Graph layout | **dagre** or **elkjs** depending on complexity | DAG → dagre is often enough; dense graphs/cycles → adapt carefully. |
| Stress series | **Recharts** if already present, otherwise stable library of the repo | Reference lines, markers, tooltips; check cost of custom overlays. |
| Positions | **TanStack Table** if advanced filter/sorting needs | _headless_ table, without imposing a style. Be careful of APIs that evolve between versions. |
| API / cache | **TanStack Query** or tool already present | Network states, cache, invalidation, refetch and freshness. |
| Data validation | **Zod**, so useful for the network boundary | Runtime contracts must be validated, not simply cast in TS. |
| UI testing | **Playwright** | Browser navigation and screenshots. |
| Unitary | **Vitest + Testing Library** if Vite project | Mapping functions, formatting, filters, states and interactions. |

**Anti-patterns:** add a blockchain engine in React components, recode Breaking Point on the client side, 5 graphics libraries, unverified dependencies, heavy animations, hardcoded simulation in `page.tsx`, monolithic files of 1500 lines.

### 10.1 Illustrative frontend architecture

```text
src/
  app/
    router.tsx
    AppShell.tsx
  pages/
    OverviewPage.tsx
    DependenciesPage.tsx
    StressLabPage.tsx
    PositionsPage.tsx
  features/
    overview/
    dependencies/
      DependencyGraph.tsx
      DependencyNode.tsx
      DependencyInspector.tsx
      graph-layout.ts
    breaking-point/
      BreakingPointPanel.tsx
      ScenarioBuilder.tsx
      StressCurve.tsx
      ImpactedPositionsTable.tsx
    positions/
  components/
ui/ # shadcn primitives, if used
    risk/
      RiskBadge.tsx
      FreshnessIndicator.tsx
      DataSourceLink.tsx
      MetricCard.tsx
  lib/
api/ # HTTP client, adapters and schemas
    format/                # USD, %, dates, locale
data/ # clearly labeled demo fixtures
    types/
  styles/
    tokens.css
```

**Technical boundary:** `API response → runtime validation → typed view-model adapter → components`. No component should assume the backend format without adapting. All screens must be able to share the **same** `scenarioId`, `portfolioId`, `selectedDependencyId`, `snapshotAt`.

---

## 11. Skills and tools to add to Claude Code

**Update 10/10/2026:** for viral tools (Higgsfield, Impeccable, 21st.dev, UI UX Pro Max), also see **§19**: verified research, official setup, visual review protocols and specific prompts. **Install a little, test a lot.**

### 11.1 What to install, by priority

| Priority | Expansion | Function | Source/installation |
|---|---|---|---|
| **P0** | **Anthropic `frontend-design`** | Voluntary graphic choices, typography, composition, avoid generic rendering. | [Official Skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md); in Claude Code, try `/plugin` then search for `frontend-design`. If the marketplace fails, use the local skill method (§11.3). |
| **P0** | **Playwright MCP** | Claude opens the app, clicks, tests navigation, responsive and retrieves captures/states. | [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp) |
| **P0** | **CLAUDE.md from the repository** | Permanent rules on data, components, style and quality. | [Official guide](https://code.claude.com/docs/en/memory); model §12. |
| **P0** | **Skill custom `faultline-frontend`** | Translate this specification into a controlled implementation. | `.claude/skills/faultline-frontend/SKILL.md`; model §13. |
| **P1** | **Chrome DevTools MCP** | Inspect layout, console, network and performance when Playwright alone is not enough. | [Chrome DevTools MCP Documentation](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md) |
| **P1** | **Playwright Test** (repo tests) | Deterministic tests independent of the chat context Claude. | [Playwright](https://playwright.dev/) |
| **P2** | **Skill custom `ui-qa`** | Recurring test checklist and visual audit. | Simple `SKILL.md` local; see §13.2. |
| **P1 after P0** | **Impeccable** | Audit, critique, refinement of the interface. | [Official installation](https://impeccable.style/tutorials/getting-started/) and protocol §19. |
| **P2 if necessary** | **21st.dev MCP / Higgsfield** | Ready-to-adapt components / marketing assets and visual concept. | **See limits and setup §19; not required for the risk engine**. |

The official `frontend-design` plugin appears in the Anthropic directory, but users have documented **installation issues according to marketplace status**. Don't waste 45 minutes on the install: a local `SKILL.md` file from official recommendations is a valid fallback. [Documented issue reference](https://github.com/anthropics/claude-plugins-official/issues/1438).

### 11.2 Useful commands

In a terminal, at the root of the repo (depending on environment / permissions):

```bash
# Playwright MCP (command provided by Microsoft)
claude mcp add playwright npx @playwright/mcp@latest

# Optional: Chrome DevTools MCP (project command)
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest

# Check installed servers
claude mcp list
```

In the Claude Code session:

```text
/plugin
/skills
/doctor
```

The Chrome DevTools plugin also offers a **plugin + skills** installation:

```text
/plugin marketplace add ChromeDevTools/chrome-devtools-mcp
/plugin install chrome-devtools-mcp@chrome-devtools-plugins
```

**Caution:** only install MCPs/skills from trusted sources and check permissions; An MCP browser can access pages and session data. Never place RPC or API keys in a committed prompt, capture or fixture. Check the versions present in the project before any addition.

### 11.3 Structure of Claude instructions to commit

```text
repo/
CLAUDE.md # stable and short rules
  docs/
    FAULTLINE_FRONTEND_RESEARCH_AND_CLAUDE_SPEC.md
  .claude/
    skills/
      faultline-frontend/
SKILL.md #project UI workflow
      ui-qa/
SKILL.md # visual and functional audit
```

Claude Code skills are folders containing a `SKILL.md` with YAML metadata; they can be triggered automatically by their description or via a `/skill-name` command. See the [official documentation](https://code.claude.com/docs/en/skills) for versioning and loading intricacies.

---

## 12. Template ready to copy in `CLAUDE.md`

> Copy the **contents of this block** into `CLAUDE.md` at the root and adjust the commands after inspection of the repository.

```md
# FAULTLINE — Instructions for Claude Code

You are building the FAULTLINE DeFi dependency risk frontend for a hackathon.

## Source of truth
- Read `docs/design/frontend.md` before changing frontend UI.
- First inspect the repository, package scripts, existing components, actual backend types and API routes.
- The backend's existing financial/risk engines are authoritative. Do NOT rewrite Breaking Point, exposure, impact or Stay/Exit calculations in the frontend.
- Do NOT fabricate risk scores, price series, liquidation data, APYs, wallet balances or API responses and present them as live.
- Demo fixtures are allowed only if labeled "Demo data" and coherent across views.

## UX principle
- Build an institutional DeFi risk command center, not a DEX/trading clone.
- Primary sequence: Dependency -> Exposure -> Breaking Point -> Modeled loss -> Decision.
- Breaking Point is the visual and interaction centerpiece.
- Every meaningful selection must have a real effect on visible data or navigation.
- All numerical outputs must show units, scenario/scope and freshness as appropriate.
- Distinguish not-applicable, not-modeled, zero, and missing data.
- Never claim a risk calculation is real time unless refresh/freshness proves it.

## Visual conventions
- Dark-first, clean, restrained, content-led; use centralized design tokens.
- Precise typography, tabular numerals, meaningful state colors and accessible contrast.
- No neon crypto look, decorative 3D backgrounds, random gradients or gratuitous animation.
- Support laptop viewport 1440x900 and narrow layouts down to 375px.
- Keep graphs readable with filters, selection, inspection, fit-to-view and empty states.

## Engineering constraints
- Preserve the current framework, router, package manager, conventions and existing APIs when reasonable.
- TypeScript strict typing, reusable components, view-model adapters, validation of untrusted network data.
- No silent fallback from failed API to plausible-looking demo results.
- Never hardcode secret keys or expose them in client bundles.
- Avoid additional dependencies unless there is a clear benefit.
- Keep scenario selection, dependency selection and snapshot coherent across pages.

## Work protocol
1. Audit the existing app before implementation and state what is already available.
2. Identify backend contracts and list unsupported states before building visualizations.
3. Implement the smallest complete vertical slice (Overview + Breaking Point).
4. Run lint/typecheck/tests/build using real project scripts.
5. Open the page in a browser and inspect at least 1440x900 and 390x844.
6. Fix visual glitches, console errors, dead controls, overflow and data inconsistencies.
7. Summarize changed files, tested flows, known limitations and remaining mock/demo inputs.
```

---

## 13. Custom FAULTLINE skill — ready to copy

### 13.1 `.claude/skills/faultline-frontend/SKILL.md`

```md
---
name: faultline-frontend
description: Build, refine or review FAULTLINE's DeFi risk frontend. Use whenever creating or changing a dashboard page, dependency graph, Breaking Point simulator, portfolio risk visualization, risk data integration or risk-related UI component.
---

# FAULTLINE Frontend Implementation Skill

## Goal
Build a polished, financially honest, interactive institutional risk terminal using the design and product spec in `docs/design/frontend.md`.

## Required first steps
1. Read the spec and current repo architecture.
2. Inventory actual backend endpoints and response shapes; do not invent API contracts.
3. Identify any existing UI framework, routing, charts and component library; reuse first.
4. Produce a short implementation plan with concrete files and acceptance criteria.

## Aesthetic brief
Dark-first and precise. Emphasize the causal connection between a selected dependency, exposure, liquidation breakpoint, modeled impact and decision. Make Breaking Point the hero visualization. Use consistent tokens, refined typographic hierarchy, sparse signals of critical risk, and strong whitespace discipline.

## Component rules
- Use typed view models and shared formatters.
- Use loading, empty, unavailable, not-modeled, error, stale and demo states.
- Preserve units, scope, timestamp and methodology in financial data.
- Use keyboard-accessible controls; avoid color-only risk encoding.
- A graph edge represents a documented dependency, not an arbitrary correlation.
- Never render a fictitious stress curve if only a scalar threshold is available.

## Verification loop
1. Run typecheck, lint, tests and build where scripts are available.
2. Start the app; inspect it via Playwright MCP if installed.
3. Test 1440x900 and 390x844, plus empty/error/stale states.
4. Check navigation, scenario controls, selection synchronization and console errors.
5. Critique the screenshot: hierarchy, clipping, spacing, alignment, contrast, semantics.
6. Iterate until the interface is clean and all visible interactive controls function.

## Stop conditions
Never silently replace missing API data with hardcoded 'real' data.
Never claim a wallet action or alert succeeded without genuine backend confirmation.
Report which elements are real, simulated or not yet supported.
```

### 13.2 `.claude/skills/ui-qa/SKILL.md` (optional, but very useful)

```md
---
name: ui-qa
description: Audit and test FAULTLINE frontend quality, screenshot fidelity, responsiveness, semantics, accessibility and true end-to-end interactions. Use after creating or changing user-facing components or routes.
---

# FAULTLINE UI QA

Test the running application, not only the source code.

- Check at 1440x900, 1280x800, 768x1024 and 390x844.
- Check no horizontal overflow, clipped labels, unreadable tables or off-screen drawers.
- Check hover/focus states and keyboard navigation.
- Check graph pan/zoom/select/clear/filter/inspect; provide fallback list if necessary.
- Check stress scenario selection, loading, results, reset, errors and stale data.
- Check unit formatting and that current portfolio/snapshot/scenario are consistent.
- Verify demo/synthetic data is clearly labeled and unavailable data is not shown as zero.
- Review screenshots critically; fix 3 most severe visual issues and retest.
- Run available build/typecheck/tests. Report concrete evidence and failures.
```

---

## 14. Prompt master to give to Claude Code

> This prompt assumes that the `.md` is committed to `docs/` and that Claude works in the hackathon repository.

```text
You are the lead product designer and senior frontend engineer for FAULTLINE.

Read, fully understand, and implement:
  docs/design/frontend.md
  CLAUDE.md
  Section 19 of the frontend spec (visual-director workflow, optional creative tools)

Objective:
Ship a memorable, production-quality frontend for the EPFL / Belem Capital
DeFi dependency-risk hackathon. The backend baseline required by the challenge
is assumed to be implemented already. Do not replace existing risk algorithms.

Follow this process strictly:

PHASE 1 — Repository and API audit
- Inspect package.json, routes, styles, components, test setup and available backend APIs.
- Determine what is real, partially implemented or missing; list any spec/API mismatches.
- Reuse the existing framework and only install truly necessary dependencies.
- Keep a minimal plan with files and realistic checkpoints.

PHASE 2 — Design foundation
- Create coherent tokens, typography, shell, sidebar, header, risk statuses and
  reusable components. Match the specific visual direction from the spec.
- No generic AI dashboard aesthetics. The result should feel like a real financial
  analyst workstation: restrained, deliberate and immediately legible.

PHASE 3 — Functional P0 vertical slice
- Risk Overview with real/high-fidelity data mapping and key metrics.
- Dependency Explorer with selectable graph nodes and relevant inspector.
- Breaking Point Stress Lab with meaningful scenario controls and actual backend
  results. If only a threshold is available, render a threshold gauge, not an invented curve.
- Link scope and selections so the same scenario drives related visualizations.
- Implement honest loading, empty, unsupported, stale and error states.

PHASE 4 — Polish and proof
- Run appropriate scripts (lint, typecheck, unit tests, production build).
- If browser automation is available, inspect 1440x900 and 390x844 screenshots.
- Interact with every visible control and fix broken or dead behavior.
- Verify spacing, clipping, chart labels, tooltips, contrast and keyboard access.
- Iterate at least once after a visual review.

Delivery requirements:
- Summarize actual file changes and where data comes from.
- List every placeholder/fixture and clearly mark whether it is demo only.
- Explain exactly how to run and demonstrate the app in 90 seconds.
- No false claims of real-time data, no fake computation, no decorative fake
  features, no hardcoded risk numbers posing as genuine engine output.
- Prioritize one exceptional, reliable path over ten unfinished screens.

Start now with Phase 1. Do not redesign the backend or generate code blindly
before inspecting the repository.
```

---

## 15. Acceptance criteria — delivery checklist

### P0 — required

- [ ] In 10 seconds, the Overview responds to **exposure / breaking point / impact**.
- [ ] Sidebar, header and maps work at **1440 × 900** without overflow.
- [ ] Navigable graph, selectable nodes, understandable links, informed inspector.
- [ ] A selected dependency remains identified in the views that support it.
- [ ] Breaking Point displays **factor + direction + % of shock + affected position + criterion**.
- [ ] The stress graph uses **calculated data**, never a false curve.
- [ ] Scenario changes produce real loading/result/error states.
- [ ] The risk numbers are explicitly contextualized (scope, scenario, unit, date).
- [ ] Non-liquidatable/non-calculated positions are not shown as `0 risk`.
- [ ] All visible buttons actually do something, or are clearly disabled.
- [ ] Reliable and **identified** offline demo mode, without confusion with live.
- [ ] Build + typecheck + available tests pass; console without blocking errors.
- [ ] Desktop + mobile browser captures inspected and major defects corrected.

### P1 — differentiation

- [ ] Table of filterable/sortable positions and linked to the graph and stress.
- [ ] Interpretable dependency paths, visualization of the impact radius.
- [ ] History/simulation presets if this provides real value.
- [ ] Leverage Hunter / Whale Impact / Chain of Blame only with reliable data.

### P2 — bonus

- [ ] Really connected alerts, with verifiable delivery status.
- [ ] Exit simulation which distinguishes cost estimates and executable orders.
- [ ] Sharing/exporting reproducible scenarios.
- [ ] Reaction Window with explicit assumptions and no artificial precision.

---

## 16. Pitfalls to absolutely avoid

1. **The huge donut chart:** it often hides shared dependencies and causality.
2. **The arbitrary “risk score”:** false or non-traceable score destroys credibility.
3. **The illegible graph:** provide grouping, filters, selection and detail panel.
4. **The invented curve:** an isolated threshold is not enough to interpolate health factors over an entire range.
5. **Duplicate %:** shared exposures **may overlap**; their sum is not necessarily 100%.
6. **The mock that pretends to be live:** display `DEMO / snapshot` honestly.
7. **The false EXIT:** never give the impression that a click executes a transaction if the app does not do so.
8. **The absence of a source:** each critical figure must be linked to a method, a period or an endpoint.
9. **Slicing by features only:** quality is in the synchronization between features.
10. **The race for plugins:** `frontend-design` + Impeccable (polish) + MCP browser + in-house skills > twenty unknown skills. Higgsfield and 21st.dev are **optional** and documented in §19.

---

## 17. Recommended development order for the hackathon

| Ordre | Livrable | Estimation relative | Pourquoi |
|---|---|---|---|
| **1** | Repo audit + API contract + safe demo dataset | Short | Immediately reduces integration errors. |
| **2** | Shell + tokens + header + Overview | Medium | Defines the level of visual quality visible at first glance. |
| **3** | Stress Lab / Breaking Point **real** | High | **Main analytical “wow moment”**; priority investment. |
| **4** | Interactive Dependency Graph + inspector | Medium/high | Makes the notion of dependence tangible. |
| **5** | Cross navigation Graph ↔ Stress ↔ Positions | Medium | Product differentiator; avoids the “widget collage” effect. |
| **6** | Impact + STAY/EXIT neatly exposed | Medium | Closes the “so what?” loop. |
| **7** | Visual QA + reliable off-grid demo | Medium | More important to the judges than a flimsy P2 feature. |
| **8** | P1/P2 if real time remaining | Varies | Bonus only once solid P0. |

**Recommended arbitration:** in the event of a lack of time, sacrifice P1/P2 screens before sacrificing **the readability of the Breaking Point**, the consistency of the figures or the demo route.

---

## 18. Verifiable references and usage notes

**Products:**

1. DeFi Saver — [Dashboard](https://help.defisaver.com/features/defi-saver-dashboard), [Health / Safety Ratio](https://help.defisaver.com/features/defi-saver-dashboard/health-safety-and-collateral-ratio), [Automation](https://defisaver.com/features/automation).
2. Gauntlet — [Risk Dashboard example](https://dashboards.gauntlet.xyz/protocols/moonwell/markets/base/assets/cbeth?fullscreen=asset_latest_liquidation_curve), [Risk Dashboard V2 / Aave](https://governance.aave.com/t/gauntlet-risk-dashboard-v2-launch/12663), [indicator explanations](https://discuss.jup.ag/t/gauntlets-real-time-dashboard-explained/20114).
3. Morpho — [Vault](https://app.morpho.org/arc/vault/0x389abDf4355e0cF4f19298179991705a98f21c18/galaxy-eurc), [Curator concept](https://docs.morpho.org/learn/concepts/curator/), [Data dashboards](https://docs.morpho.org/developers/ecosystem/data-dashboards/).
4. Arkham — [Visualizer](https://codex.arkm.com/the-intelligence-platform/visualizer), [Tracer](https://codex.arkm.com/the-intelligence-platform/tracer).
5. Dune — [RockawayX Dashboard](https://dune.com/rockawayxvault/rockawayx-dashboard), [Dune Data Hub](https://dune.com/data-hub).

**Claude and frontend:**

6. Anthropic — [Official frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), [Claude Code skills](https://code.claude.com/docs/en/skills), [Project instructions](https://code.claude.com/docs/en/memory), [Plugin directory](https://github.com/anthropics/claude-plugins-official).
7. Microsoft — [Playwright MCP](https://github.com/microsoft/playwright-mcp) ; Google Chrome — [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md).
8. [shadcn/ui](https://ui.shadcn.com/docs/installation/vite), [React Flow](https://reactflow.dev/learn/customization/custom-nodes), [TanStack Table](https://tanstack.com/table/latest/docs/framework/react).

**Notes:**
- Research conducted on **10/10/2026**, based on public pages and cited documentation.
- This document **does not replace** the official Belem specifications: the capture of P0/P1/P2 priorities provided by the team is treated as a scope reference, but no additional requirements from the PDF are invented.
- To resolve product ambiguity, **the official Belem requirements + the APIs actually present in the repo take precedence** over the layout, lib or copy proposals of this document.

---

**Final decision:** build **an elegant Overview + an impeccable Stress Lab Breaking Point + an understandable Dependency Graph**, all linked to the same scenario and the same data. It's a stronger demonstration than a twenty-tab interface.

---

## 19. Extension 2026 — Higgsfield, “premium” skills and artistic direction method for Claude Code

> **Read and apply BEFORE generating or modifying the frontend.** This chapter complements §§4, 11–16. It does not replace business priority: **all P0 must be exact, interconnected, usable, and demonstrable before style effects**.
>
> **Decision:** use a tight trio — `frontend-design` (direction), **Impeccable** (critique/polish), **Playwright** (real proof) — plus **21st.dev** (components, if necessary). **Higgsfield is optional** for identity and assets; do not delegate the analytical dashboard to him. Add other skills only if a concrete lack is identified.

### 19.1 What the tools and discussions show (and what it means)

| Tool / source | Capacity verified | Value in FAULTLINE | Important limit | Decision |
|---|---|---|---|---|
| [Higgsfield — Website Builder](https://higgsfield.ai/skills/website) | Official skill which generates a **responsive site**, with interactions and multimedia sequences based on a brief. | Explore a visual proposition, create a marketing concept / presentation landing separate from the application. | Examples mainly narrative “showcase”. **Neither the clean export of existing code, nor the conservation of the repository architecture are guaranteed by the page consulted.** | **Optional, exploration only**, not P0 code base. |
| [Higgsfield CLI / MCP](https://higgsfield.ai/mcp?tab=claude-code) | Generation of images/videos from Claude Code by CLI/skills; MCP connection from Claude web/desktop. | Concept illustration, discreet abstract background, possible short video sequence of **pitch**, export of a suitable visual. | Connection, subscription/credits and usage rights to verify. Outputs **are not inspectable React components**. | Only if a necessary asset is actually missing. |
| [Anthropic — Frontend Design](https://claude.com/plugins/frontend-design) | Official skill against AI template rendering; imposes a coherent aesthetic direction. | Choice of an “institutional risk terminal” composition, identity and typography. | A bold direction must **remain subordinate to the clarity of the risk**; skill does not magically provide quality. | **Priority 1**. |
| [Impeccable](https://impeccable.style/tutorials/getting-started/) | Visual and UX review skill with `audit`, `critique`, `polish`, `distill` and other commands. | Correct proportions, details, hierarchy, noise, states, design consistency. | **Iteration** tool, not a justification for endlessly reshaping the design. | **Priority 1**, after first functional version. |
| [21st.dev MCP](https://21st.dev/mcp) | Search and retrieval of components, React/Tailwind patterns, UI generation depending on access. | Find a good `drawer`, `command palette`, `empty state`, `tabs` or `tooltip` and adapt the code. | Dependencies, compatibility, component license, graphic homogeneity. **Magic MCP was replaced by the 21st MCP** in 2026. | **Priority 2**, only if really speeding up. |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Repository of patterns, palettes, styles, typography, stacks. | Comparative inspiration if Claude has difficulty setting a direction. | Redundant with `frontend-design` + Impeccable, sometimes generic recommendations. | **Alternative, no mandatory installation**. |
| [Vercel — web-design-guidelines](https://github.com/vercel-labs/agent-skills) | Ergonomics/accessibility/performance audit following web rules. | Objective final validation, including focus, states, keyboard, contrasts. | Complete the tests; does not automatically inspect real UX without a browser. | **Priority 2** for audit. |
| [Context7](https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx) | Versioned library documentation in Claude Code. | Avoid APIs invented for React Flow, shadcn, Recharts, TanStack, etc. | Not a “beautiful design generator”. | Optional if doc errors or recent libs. |
| [Official Figma MCP](https://help.figma.com/hc/en-us/articles/39888612464151-Claude-Code-and-Figma-Set-up-the-MCP-server) | Structured access to models and tokens **if the team uses Figma**. | Enforcing the approved design rather than interpreting an image. | No point if the team has neither a Figma file nor any intention of using it. | Conditional. |
| **Playwright MCP / Playwright Test** | Real browser inspection and repeatable testing. | Check that the UI is truly premium AND usable, not just clean JSX. | Requires app launched and browsers configured. | **Non-negotiable for UI acceptance** (or documented manual audit if unavailable). |

**Reading from Reddit (qualitative signal, not scientific benchmark):**

- A [thread `r/ClaudeDesign` from October 2, 2026](https://www.reddit.com/r/ClaudeDesign/comments/1wvfgec/best_claude_frontenddesignuxui_skill_set/) notably mentions **21st.dev**, **Impeccable**, inspiration from real interfaces and iterative visual feedback.
- The thread [`r/ClaudeCode` on “AI slop”](https://www.reddit.com/r/ClaudeCode/comments/1p9srut/finally_figured_out_why_claudes_ui_generations/) insists on **an explicitly chosen aesthetic** rather than “modern sleek dashboard”.
- Another [thread about stacking skills](https://www.reddit.com/r/ClaudeCode/comments/1u8c5qi/design_skills/) reports mixed results and overlap. Avoid installing every popular extension.
- [Reddit feedback on Higgsfield MCP](https://www.reddit.com/r/claude/comments/1wf6rpy/how_do_you_create_nice_modern_websites_with_claude/) suggests an interest in the videos/assets but also mentions the cost. **None of these comments prove that they improve the quality of a DeFi dashboard.**

**Operational conclusion:** TikTok clips often show the end result and not failed attempts, cost, correction screenshots or functional limitations. For this hackathon, the “pro rendering” must come from **information architecture, tokens, precise execution, real data and browser control**.

### 19.2 “Premium but sober” stack: setup in stages

#### Tier A — essential setup (do now)

In **Claude Code** (if the plugin is not already present):

```text
/plugin install frontend-design@claude-plugins-official
```

In the **project** terminal, adapting if Playwright is already configured:

```bash
# Prerequisites: Claude Functional code, compatible Node/npm environment.
claude mcp add playwright npx @playwright/mcp@latest
claude mcp list
```

After installation, ask Claude to **verify** that he can open the local server, click, take a screenshot, read the console and test a scenario change. **Do not say “installed” without checking.** The `frontend-design` plugin may experience marketplace issues: try `/plugin` or the local solution in §11 if necessary.

#### Tier B — polish pro (install only after first version of the Overview)

```bash
# Install in the repo, following the official prompts.
# Impeccable Node.js request >= 22.18 in the 2026 consultation.
npx impeccable install
```

Then in Claude Code:

```text
/impeccable init
/impeccable audit
/impeccable critique
/impeccable distill
/impeccable polish
```

**Important:** these commands are **design tools**, not commands to be executed blindly one after the other. Use critique and audit, group corrections, recapture, then stop. The designer must be able to say “this is enough”.

#### Tier C — components and conditional audits

```bash
#21st current MCP; choose `claude` in setup; requires account and key depending on usage.
npx @21st-dev/cli@latest init --client claude

# Additional Vercel audit (optional after Playwright).
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines

# Living technical documentation (optional, useful if API lib uncertain).
npx ctx7 setup --claude
```

- Before copying a 21st.dev component: **examine its source and license**, its size, its dependencies, the keyboard focus and its compatibility with Tailwind/shadcn from FAULTLINE.
- If an existing shadcn/ui component is sufficient, **prefer the existing component**. Never mix four design systems unnecessarily.
- Do not follow 2025 tutorials using exclusively the old **Magic MCP**: it is now grouped in **21st MCP**; old Magic keys have been reset ([official migration](https://github.com/21st-dev/magic-mcp/blob/main/llms-install.md)).
- Alternatives to choose, not to stack: `npx ui-ux-pro-max-cli init --ai claude` to enrich aesthetic references **instead of Impeccable** if this style of workflow is preferable. The two can coexist technically but there needs to be **a single design authority** for FAULTLINE.

#### Tier D — Higgsfield, only with a clear need and a validated budget

For **Claude Code**, the **official** documentation recommends the CLI:

```bash
# Official commands: run voluntarily, not in an auto-install script.
npm i -g @higgsfield/cli
higgsfield auth login
npx skills add higgsfield-ai/skills
```

For **Claude web/desktop**, the officially documented route is **Connectors → Higgsfield** with the URL `https://mcp.higgsfield.ai/mcp` then authentication. These are **two different paths**. [CLI / MCP](https://higgsfield.ai/mcp?tab=claude-code) · [Integration Guide](https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent).

**Authorization and budget:** request human approval before any purchase, paid generation, OAuth connection or import of sensitive assets. The [Higgsfield credits documentation](https://higgsfield.ai/creator-hub/help-center/credits/how-credits-work) describes a variable cost per generation. Check usage rights and final format before integration.

**Authorized use for FAULTLINE:**

1. **Identity:** explore 2–3 static variants of a minimalist “rift/fracture” texture, without using rough protocol logos; choose at most one variant.
2. **Presentation:** possibly generate a short cinematic shot or a launch video **outside** of the monitoring app; the team decides if this demo time is better than a live simulation.
3. **Useful asset:** create a static visual for the empty initial state, a pitch slide or a non-critical area. Export an optimized, locally reviewed and licensed local file.
4. **Prohibited:** making dependency graphs or liquidation curves as simple images, creating false encrypted results, adding a full-page video hindering the controls, depending on Higgsfield to render the Overview.

**ROI rule:** if there are less than 3 hours before the demo or if the P0s do not pass, **do not install Higgsfield**. The best investment is then the correction of the app and the fluidity of the jury process.

### 19.3 Process imposed on Claude — from brief to “premium agency” result

**Claude must act simultaneously as product designer and QA manager, but work in explicit steps.** No big bang, no “improve the entire UI” without diagnosis.

**Step 0 — Baseline and project protection (15–30 min)**

- Read this specification and that of the challenge, `CLAUDE.md`, the components, the routes, the API contracts and the code already implemented.
- Capture **the existing** at `1440 × 900`, `1280 × 800` and `390 × 844` if an application is already running, with date and commit.
- Note in `docs/UI_BASELINE.md` what works, what is broken, mocked data, components already available. **Do not touch DeFi calculations**.
- Prepare a plan of 4 milestones maximum, each milestone being deliverable and testable.

**Step 1 — Brief and visual directions (20–40 min)**

- Summarize user, value proposition, three main actions and 90 s demo.
- Compare **3 very short directions** (without building 3 apps): (A) *Institutional Risk Terminal* — **preferred**, (B) *Editorial Fintech*, (C) *Dense Analytics Console*. Give benefits/risks for UX.
- Choose **A by default** unless the team provides conflicting direction. **Lock** the palette and fonts from §4 instead of iterating endlessly.
- Document: spacing scale, borders, radius, text sizes, even fonts, iconography, density, hierarchy, state colors, motion tokens; create `docs/DESIGN_DECISSIONS.md`.
- Identify 3 functional references (DeFi Saver, Morpho, Gauntlet) and 2 finishing quality references (shadcn design system / 21st.dev examples if available). **Reinterpret**, do not clone.

**Step 2 — Low-fidelity UX before cosmetic (15–30 min)**

- Make a simple `Overview` layout with: **main risk**, **exposed capital**, **breaking point**, **impact**, **decision** and a large analytical component.
- Only one relevant **primary CTA** per screen; simulation actions must be obvious.
- The jury must be able to answer without help in 10 seconds: **“What does this portfolio depend on? What breaks first? What are we losing? »**
- Each term (`health factor`, `dependency exposure`, `STAY / EXIT`, `slippage`) has a one-sentence **tooltip** or context-sensitive help.
- The “see why” button should allow you to trace the **path of causality** from impact to dependence; visible link between views.
- Do not hide P0 functions behind a hover-only, special gesture, onboarding or deep menu.

**Step 3 — Implement a flawless vertical slice (60–120 min)**

- Build **a single complete screen** before generalizing: shell, Overview and selection of a dependency synchronized with the `Breaking Point` panel.
- Use **controlled components and typed view-models**: the same selection and the same scenario power the views. Explicitly define `loading`, `error`, `empty`, `stale`, `unsupported`, `demo`, `success`.
- Put **real interactive SVG/canvas graphics** for the curves and **React Flow** (or existing stack) for the dependency links, not “magnificent” images that lie about the data.
- Set the first experience without connecting a wallet if a clearly labeled example dataset facilitates the demo; then allow a change of portfolio.
- Maintain a **controlled information density**; rich desktop, simplified and scrollable mobile, not an overwritten copy of the desktop.

**Step 4 — Check in browser and correct in batches (2 rounds maximum per milestone)**

- Start the frontend, open **the real local URL** with Playwright.
- Capture `1440 × 900`, `1280 × 800`, `390 × 844`; if necessary `768 × 1024`.
- Read **console errors**, failed requests and loading states; check keyboard focus, click targets, scrolling, overlays, contrasts, `prefers-reduced-motion`.
- Perform a complete flow: select a dependency → open its detail → modify the shock → observe the breaking point / impact → consult STAY/EXIT → return to the initial scenario.
- Classify the defects **blocking / important / cosmetic** and correct them **together**. Take a second capture after correction; **do not continue in a loop without limit**.
- Ask Impeccable to `crit` then `polish` **only** when the user flow works. Use suggestions compatible with the design tokens; reject those that reduce accessibility or introduce an unrelated visual style.

**Step 5 — “Design freeze” + P0 verification (30–60 min)**

- Freeze tokens and large layouts after 2 visual cycles. Priority then to reliability, data and demo.
- Do a final Vercel/web-design-guidelines audit if installed, plus Playwright Test, lint, build, types.
- Deliver before/after captures, a test table with status and the list of **true** limitations, including `demo`, `stale` modes and unmodeled dependencies.
- Provide a “90-second” demo tour, without delicate manual adjustment or fragile external dependence.

### 19.4 Brief ready to send to Higgsfield (OPTIONAL — assets only)

> Only launch this generation if the team has approved it and if a budget exists. The objective is **NOT** to have a generative AI draw the risk graphs.

```text
Create up to 3 VISUAL CONCEPT assets for FAULTLINE, a serious institutional
DeFi dependency-risk analysis app used by risk analysts. This is NOT a gaming,
crypto trading or memecoin product. The visual identity is a subtle fault line
or connected stress fracture: a precise technical trace on a dark slate ground.

Palette reference: #0A1018, #111A25, #293747, restrained #66D5E8 accent;
reserve orange/red for meaningful risk states in the actual product UI.

Deliver (1) a tasteful static SVG-like conceptual backdrop or raster equivalent
with generous negative space, (2) a minimalist wordmark exploration, and (3)
optionally a 3–5s silent product-intro motion study. No human figures,
no generic purple gradients, no 3D spinning coins, no neon cyberpunk,
no mock numerical data, no simulated protocol logos, no fake UI components.

This is DESIGN INSPIRATION, not executable product UI.
The existing React dashboard, live dependency graph and real financial charts
will be implemented separately by Claude Code. Prefer static assets; motion
is disposable and must not be part of the critical user path.
```

### 19.5 Prompt “artistic director + engineer” ready to give to Claude Code

```text
You are FAULTLINE's lead fintech product designer, senior React engineer and
visual QA lead. Build a PROFESSIONAL, UNDERSTANDABLE, CREDIBLE risk-analysis app,
not an animated startup marketing page.

FIRST read:
- docs/design/frontend.md (especially sections 0,
  4, 11, 14, 15 and 19)
- CLAUDE.md and the official hackathon requirement verification document, if present
- actual repository/frontend/api data contracts

Working rules:
1. P0 correctness and usability > visual polish > optional modules > effects.
2. Activate Anthropic frontend-design if available; follow OUR design tokens.
   If installed, use Impeccable for AUDIT/CRITIQUE/POLISH after functionality.
   Use 21st.dev only when an existing UI component genuinely saves time.
3. Higgsfield is OPTIONAL: use only for bounded brand/visual assets with explicit
   approval for credentials and paid credits. Do NOT generate the graph/charts as
   images and do not replace the repo with a one-shot website builder.
4. Keep the UI immediately understandable: 3 navigation groups, clear scenario,
   plain-language tooltips, one primary action per screen, details on demand.
5. Strongly prioritize Breaking Point; graph, exposure, impact and STAY/EXIT
   must be logically connected through the same typed shared state.
6. No fake risk engine values, fake "LIVE" labels, arbitrary probabilities,
   decorative dead buttons, invisible important actions or invented API fields.
7. Before implementing: show a brief repository audit, design-system choices,
   implementation order, and exactly which 3–5 browser states you'll verify.
8. Implement the first complete Overview vertical slice before expanding.
9. Open the actual app with Playwright. Screenshot desktop and mobile. Test a
   real risk-analysis user journey. Fix all blockers and key visual defects.
   Do two bounded QA passes and deliver evidence (screenshots + test results).
10. Finish with a report: what is real vs simulated, what tests ran, what still
    needs work, and the 90-second jury demonstration walkthrough.

Definition of "looks professionally designed":
- visual hierarchy instantly highlights the primary risk and threshold;
- typography, alignment, density, borders, spacing and colors are consistent;
- readable charts with correct labels and provenance;
- purposeful micro-interactions, never animation noise;
- all states and responsive layouts feel intentionally designed;
- accessibility and functional correctness are not sacrificed for the hero shot.

If a plugin/skill isn't installed, report it and continue with available tools.
Never install paid tools, use paid credits, change credentials or overwrite
existing backend logic without explicit approval. Start with the repo audit.
```

### 19.6 Visual/UX validation grid to execute before saying “finished”

A **note should be based on captures and interactions**, not on Claude's impression. On each criterion, mark `PASS / FAIL / N/A` and proof (capture, URL, test or component). **Critical FAIL blocks delivery.**

| Domain | Concrete verification | Severity if failure |
|---|---|---|
| Comprehension in 10 seconds | Cold test: a juror identifies exposure, critical dependence, first threshold and impact without explanation. | **Blocking** |
| Navigation | Find `Overview`, `Dependencies`, `Breaking Point` in one click; Clear feedback and selection status. | **Blocking** |
| Semantic coherence | Same asset/dependency selected in graph, metrics and stress; same scenario/date. | **Blocking** |
| Data Truth | Accessible provenance, snapshot and hypotheses; no fictitious numbers displayed as real. | **Blocking** |
| Graph readability | Labels/units, direction of shock, legend, accessible tooltip; no cut graphs. | **Blocking** |
| Design systems | No unexplained discrepancies in fonts, spacing, radius, colors, states and icons. | Important |
| Hierarchy | A major metric, parsimonious risk emphasis, easy to spot “decision” zone. | Important |
| UX States | Loading, error, empty, stale data, unsupported, demo mode actually managed. | **Blocking** |
| Actions | Each visible control has a behavior; no decorative or disabled CTAs for no reason. | **Blocking** |
| Keyboard / a11y | Visible focus, logical order tab, contrast, labels, access to graph information by alternative means. | Important |
| Responsive | No overflow at 390/768/1280/1440 px; priority to content and an accessible table. | Important |
| Performance | No heavy continuous animation; the graph remains manipulable with the demo dataset. | Important |
| Security / trust | No client-side secrets, no fake action executed, no transaction printing without real confirmation. | **Blocking** |
| Refinement | Pixel alignment, negative space, consistent icons, precise tooltips, neat hover/focus. | Cosmetic/important |

**QA deliverables**: `docs/UI_QA_REPORT.md`, `artifacts/ui/` captures (or location already planned by the project), incident table sorted by priority and test scripts. **Do not claim that Playwright filmed if only reasoning about the code was done.**

### 19.7 Anti-overdesign / anti-waste of time safeguards

The context is a **risk hackathon**, not a landing page competition:

- **Invest 70% of frontend time** on the critical path and data/state quality, **20%** on design/QA, **10% maximum** on optional assets. These are indicative ratios, to be adjusted if P0 blocks.
- **Do not install 5 redundant skills** and ask everyone to “take control”. A written design system remains the source of truth; a tool = a role.
- **Higgsfield ≠ product dependency**: no loading on the critical path, no non-essential animation on Breaking Point, and no rendering of risk figures as images.
- **No backend redesign** during polish passes. A beautifully presented false figure is worse than a sober and accurate map.
- **The UX is complete when the user understands and acts**, not when the dashboard looks like a compilation of trends.

### 19.8 Official links and additional sources (accessed October 2026)

1. [Higgsfield Website Builder](https://higgsfield.ai/skills/website); [Claude Code CLI](https://higgsfield.ai/mcp?tab=claude-code); [integration](https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-connect-higgsfield-to-ai-agent); [credits](https://higgsfield.ai/creator-hub/help-center/credits/how-credits-work).
2. [Anthropic — frontend-design](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md), [official plugin](https://claude.com/plugins/frontend-design).
3. [Impeccable — getting started](https://impeccable.style/tutorials/getting-started/) and [GitHub source](https://github.com/pbakaus/impeccable).
4. [21st MCP — migration and commands](https://github.com/21st-dev/magic-mcp/blob/main/llms-install.md), [21st.dev](https://21st.dev/mcp).
5. [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) ; [Vercel agent-skills](https://github.com/vercel-labs/agent-skills) ; [Context7](https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx) ; [Figma MCP](https://help.figma.com/hc/en-us/articles/39888612464151-Claude-Code-and-Figma-Set-up-the-MCP-server).
6. Community discussions: [design skills](https://www.reddit.com/r/ClaudeDesign/comments/1wvfgec/best_claude_frontenddesignuxui_skill_set/), [avoiding generic output](https://www.reddit.com/r/ClaudeCode/comments/1p9srut/finally_figured_out_why_claudes_ui_generations/), [stacking skills and its limits](https://www.reddit.com/r/ClaudeCode/comments/1u8c5qi/design_skills/), [Higgsfield for websites](https://www.reddit.com/r/claude/comments/1wf6rpy/how_do_you_create_nice_modern_websites_with_claude/).

---
