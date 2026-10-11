# E. UX Research Findings (evidence-based)

Two kinds of evidence: **(O)** observed in Chrome 154 during this audit (desktop 1440×900, some mobile), and **(S)**
documented by the cited source. Where a site could not be inspected, it is stated. Third-party screenshots were kept
outside the repository.

## E1. What the financial products actually show

| Product | Evidence | Pattern worth noting |
|---|---|---|
| **Aave** app (home + USDC reserve) | (O) market KPIs in one row; asset table with "Details"; reserve page: reserve size, available liquidity, utilisation 99.88 %, oracle price; supply/borrow cap rings (75.87 %, 84.20 %); APR charts with 1w/1m/6m/1y toggles; collateral block **Max LTV 75 % · Liquidation threshold 78 % · Liquidation penalty 4.5 %** each with an info tip; E-mode blocks including PT-sUSDe categories; "Your info — connect a wallet" empty state | Risk parameters as labelled triplets with definitions; personal data clearly separated and wallet-gated; time-range toggles |
| Aave docs | (S) HF = collateral × weighted liquidation threshold ÷ borrows; HF < 1 liquidatable; partial vs full liquidation rules; links DeFi Saver for auto-repay ([aave.com/help/borrowing/liquidations](https://aave.com/help/borrowing/liquidations)) | Explain the rule with one formula and one worked example |
| **Morpho** app (Belem vault page) | (O) blocked by a **Terms-of-Use acceptance modal**; I did not accept legal terms on the owner's behalf. The modal itself discloses "smart contract failures, oracle failures… You may lose all the assets…" and "transactions are irreversible" | Risk disclosure before first interaction |
| Morpho docs | (S) LTV vs fixed per-market LLTV; HF = collateral × LLTV ÷ borrowed ([LTV](https://docs.morpho.org/developers/borrow/concepts/ltv/), [liquidation](https://docs.morpho.org/learn/concepts/liquidation/)); vault withdrawals only from idle + liquidity-adapter market; permissionless `forceDeallocate` with a penalty ([force-deallocate](https://docs.morpho.org/developers/earn/tutorials/force-deallocate/)); Owner / Curator / Allocator / Sentinel roles and timelocks ([roles](https://docs.morpho.org/curate/concepts/roles/)) | Label exit paths by liquidity source; show who can change risk and how fast |
| **DeFi Saver** | (O) works without a wallet: **Simulate / Track / Connect**; anti-phishing URL banner; empty-state portfolio. "Start simulation" dialog: *"sandboxed environment that fully replicates selected network behaviour… swap liquidity will likely be worse in simulation mode"* — persistent "Simulation started" state. (S) Automation = trigger + target ("Safety ratio"), bots never hold funds, Smart Wallet authorisation, minimum debt below which an enabled strategy **won't execute** ([strategies](https://docs.defisaver.com/protocol/strategies), [use cases](https://help.defisaver.com/features/automation/use-case), [requirements](https://help.defisaver.com/automations/requirements-for-using-automation)) | A sandbox mode announced up-front with its fidelity limits — the model for FAULTLINE's SIMULATED fork; trigger/target pairs; state when automation will silently not fire |
| **Gauntlet** | (O) dashboards hub (Compound, Morpho Vaults) → app.gauntlet.xyz: TVL, featured vaults with **plain-language risk tier** ("Conservative lending yield with low risk"), strategy families with risk descriptions (Prime / Balanced / Frontier), stacked TVL by strategy. (S) VaR split into named scenario families ("Broad market downturn", "Broken correlation"); LaR; before/after paired bars; tooltip on every chart stating method and refresh ([VaR methodology](https://www.gauntlet.xyz/resources/improved-var-methodology), [Risk Dashboard V2](https://governance.aave.com/t/gauntlet-risk-dashboard-v2-launch/12663)) | One-line risk tier in words next to every number; named scenarios; method + refresh cadence on every chart |
| **Arkham** | (O) Cloudflare bot challenge — **not inspected** (no bypass attempted). (S) Visualizer 3.0: filters (date, token, USD, from/to), **list view of every edge**, timeline, multi-entity search, USD sorting ([changelog](https://info.arkm.com/announcements/arkham-visualizer-3-0-is-live)) | A graph always paired with a filterable list |
| **Dune — RockawayX dashboard** (shared by Belem) | (O) HTTP 403 to automated Chrome — **not rendered**. (S/BSA) widget data: TVL $293.56M, 33 vaults, holders, avg deposit, TVL by chain/protocol, vault table incl. **Belem RWA EURCV 0xD6d4…48Ec** | The sponsor thinks in vault addresses: offer the vault list as a picker |

## E2. Usability and accessibility references (S)

- **Response times** — 0.1 s / 1 s / 10 s limits; beyond 10 s show percent-done or explicit progress
  ([NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/), [progress indicators](https://www.nngroup.com/articles/progress-indicators/)).
  Skeletons suit 2–10 s; beyond, named steps ([skeleton screens](https://www.nngroup.com/articles/skeleton-screens/)).
- **Progressive disclosure** — primary decision first, detail on request ([NN/g](https://www.nngroup.com/articles/progressive-disclosure/)).
- **Dashboards** — glanceable, preattentive encodings (length, position) ([NN/g](https://www.nngroup.com/articles/dashboards-preattentive/)).
- **Errors** — next to the source, never colour-only, severity-scaled ([NN/g](https://www.nngroup.com/articles/error-message-guidelines/); WCAG [3.3.1](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html), [3.3.3](https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion.html)).
- **Trust** — design quality, up-front disclosure, current and correct content ([NN/g](https://www.nngroup.com/articles/trustworthy-design/)).
- **Motion** — reduced motion via `prefers-reduced-motion` ([C39](https://www.w3.org/WAI/WCAG21/Techniques/css/C39.html)); pause control for anything auto-playing > 5 s ([2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)); no flashes ([2.3.1](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html)); interaction animation disablable ([2.3.3](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html)).
- **Contrast & targets** — text 4.5:1, UI components 3:1 ([1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)); targets ≥ 24 px ([2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)); focus visible and not obscured ([2.4.7](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html), [2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)).
- **Status messages** announced without focus moves ([4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html), [ARIA alert](https://www.w3.org/WAI/ARIA/apg/patterns/alert/)).
- **Canvas / charts** need an accessible name and a long description or data table ([names](https://www.w3.org/WAI/ARIA/apg/practices/names-and-descriptions/), [complex images](https://www.w3.org/WAI/tutorials/images/complex/)).
- **Wallets** — EIP-6963 multi-wallet discovery ([EIP-6963](https://eips.ethereum.org/EIPS/eip-6963)); EIP-1193 errors, 4001 = user rejected ([EIP-1193](https://eips.ethereum.org/EIPS/eip-1193)); simulated transaction previews before signing ([Tenderly](https://docs.tenderly.co/simulations/transaction-preview)).

## E3. Patterns to adopt in FAULTLINE

1. **Verdict in one sentence, three numbers, one action** (staying risk, exit cost, the flip multiple); everything else
   behind disclosure.
2. **Bands, not points:** stay band and exit band on one axis; overlap is the visual reason for REVIEW.
3. **Liquidation distance** as HF, % drop and trigger/LLTV on one scale (Aave/Morpho conventions; Countermove gauge
   already does this well).
4. **Named scenarios with plain-language severity** and a "hypothesis" tag; a method + refresh note on every chart
   (Gauntlet).
5. **Graph + list twin** with filter and search (Arkham); the list is also the accessible alternative.
6. **Exit paths by liquidity source** ("now via ordinary withdrawal: $411k · full via forceDeallocate: shared,
   first come first served") (Morpho).
7. **Explicit sandbox mode** for anything SIMULATED, announced with its fidelity limits (DeFi Saver): no mempool, no
   MEV, test funds, pinned block.
8. **Trigger + floor + caps** as the core of ARM, with "what this permission can and cannot do" (DeFi Saver, RescueVault
   permission matrix) and the conditions under which it will not act (S3).
9. **Status chip in text**, in a live region, with age: LIVE · CACHED · MIXED · SAVED SNAPSHOT · DEMO · SIMULATED (fork)
   · DRY-RUN · UNAVAILABLE.
10. **Long waits as staged work:** named steps of the real pipeline (Pendle market → Morpho market → oracle feeds →
    lineage → priors → executable quote → on-chain re-execution), elapsed time, typical duration (20–35 s), cancel.
11. **Every error inline with a next step** (retry, switch to recorded demo explicitly, change input).
12. **Risk disclosure up front** (Morpho modal): "model output, not advice; no funds move; fork results are simulated".
13. **Wallet later and read-only first:** EIP-6963 picker, 4001 as neutral dismissal, chain check, simulated preview
    before any signature.
14. **Reduced-motion and pause controls** for the hero and graph animations; no flashing red fracture effects.

## E4. Limits of this research
Morpho app (terms modal not accepted), Arkham (Cloudflare challenge), Dune (403) and Gauntlet's legacy risk dashboards
(redirect/blank shells) could not be inspected visually; their entries rely on official documentation or sponsor
material, as cited. Wallet-connected states of Aave/DeFi Saver were not inspected (no wallet was connected).
