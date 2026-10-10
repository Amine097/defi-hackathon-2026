# FAULTLINE — historical context pack for a fresh Claude Code agent

## Read this first
This pack records earlier product/UX research, visual explorations and a backend-review snapshot. **It is not a snapshot of the current repository** and must not override current code, API contracts, tests, or the official Belem challenge brief. Treat every previous claim of implementation as unverified until independently checked in the live repository.

The user wants to redesign an early FAULTLINE frontend (shown in `baseline/FAULTLINE_BEFORE.png`) into a **world-class, cinematic yet usable DeFi risk protection application**, with genuinely functional user interfaces for all backend-implemented user-facing features.

## Core brief
- FAULTLINE is a DeFi dependency, impact, decision and autonomous crisis-response product.
- Belem judging rubric described by the provided review: dependency discovery 30%, impact estimation 30%, actionable decisions 25%, real-data demo 15%.
- Critical analytical journey: inspect position → discover dependency chain → choose a shock → understand propagating consequences → compare STAY / EXIT / REVIEW (and HOLD TO MATURITY only if supported) → show assumptions, freshness and confidence.
- Additional capabilities to verify in CURRENT backend: Morpho vault analysis; RescueVault/Countermove with ARM → DEFEND → PROVE; possible exit-runway/whale/alerts modules (do not assume implemented).
- Differentiate actual live data, cache/mixed, snapshot, demo fixtures, fork results, pending and confirmed transactions.
- Historical risk review raised concerns about role-aware loss modelling, Pendle AMM vs principal loss, assumptions/LGF, maturity and book heterogeneity. DO NOT repair the financial engine by inventing client values; raise to backend owner.
- Landing: award-level, cinematic art / monumental FAULTLINE logo fracture, not a literal dependency graph occupying the hero. Real graph belongs inside X-Ray/Stress/Risk Analysis.
- Art references: https://activetheory.net/ https://lusion.co/ https://atlasmotion.com/ https://cuberto.com/ https://bruno-simon.com/
- DeFi UX references: Morpho, DeFi Saver, Gauntlet, Arkham, Dune RockawayX: https://dune.com/rockawayxvault/rockawayx-dashboard
- Official challenge PDF and other historic specs may exist in repo or be provided separately. Locate and read them before firm conclusions.

## Priority of truth (important)
1. Actual running current backend + contracts + integration tests and API responses.
2. Official Belem challenge brief and any up-to-date owner-signed product spec.
3. Current repository documentation.
4. This historical context pack (research and examples).
5. Aesthetic reference experiments (never substitute for live functionality).

## Supplied items
- `briefs/`: baseline frontend blueprint (including historical proposed/imagined fields), aesthetic reset notes, tooling research and later Belem backend review.
- `design/Claude_Design_Faultline_Landing.html`: Claude Design exported prototype. Use for composition, timing and motion ideas only. It includes illustrative placeholder financial data; **do not copy it as verified application code**.
- `baseline/FAULTLINE_BEFORE.png`: initial basic dashboard with Loading... states — identify whether API failures or just timing.
- `design/landing-desktop.png`, `design/landing-mobile.png`: prior cinematic-graph composition; user wants a MORE DISTINCTIVE cinematic hero, not to recreate this.
- `design/countermove-*.png`: examples of an ARM/DEFEND/PROVE demo that may or may not exist in the target working tree.
- `design/visual-concepts/`: optional earlier studies, reference only.

## Agent setup gate
Before changes, audit actual repository and current browser UI, map backend endpoints/functions → frontend screens/interactions/tests, inspect installed tools and compare design references. Produce a concise readiness report and a proposed implementation plan. **No commits, deployments, paid generation, real wallet signing or real fund movement during setup.**

## Important constraints
- The backend is intended as the authoritative source for risk calculations and claims.
- Do not promise functionality simply because a markdown specification mentions it.
- Take accessibility, mobile first-screen copy/CTAs, reduced motion, keyboard, wallet rejection, stale/error/empty states and loading performance seriously.
- Avoid unsafe automated blockchain transactions.
- The user expects exceptional art direction and end-to-end QA, not just pretty screenshots.
