# FAULTLINE — VISUAL RESET (Creative Director Brief for Claude Code)

**Date:** 2026-10-10  
**Status:** New visual direction overriding the *aesthetic/layout choices* of `frontend.md` (NOT the risk-model, financial-integrity, API, accessibility or P0 requirements).  
**Input:** existing FAULTLINE frontend, its backend, screenshot of the current Overview, and `frontend.md`.

## 0. The problem to solve

The current screenshot looks like a generic dark admin dashboard: four equal KPI rectangles, a thin text header, multiple similarly weighted panels, little evidence of a product-specific identity, no dominant visualization or immediately obvious simulation experience. Most content is shown as `Loading…`, leaving the page visually empty. Investigate whether that is a transient capture or a real request failure; do not try to fix an API failure with decorative design.

**Target:** a coherent, impressive, unmistakably FAULTLINE **interactive risk cockpit**: precision of a risk terminal + considered cinematic art direction. It must impress in the first three seconds *and* let a beginner understand the risk in ten seconds. No generic AI-generated SaaS template.

## 1. Scope guardrails (non-negotiable)

- Only **CORE** is functionally implemented: Risk Overview, Dependency Graph / X-Ray, Breaking Point / Stress Lab, Impact Estimation, and STAY/EXIT/REVIEW with the existing backend's capabilities.
- Preserve and integrate already-working core features. No financial-engine rewrite. No fake risk calculations, curves, prices, timestamps, 'LIVE' claims, or fabricated account data.
- Other sidebar items (Whale Impact, Leverage Hunter, Chain of Blame, Exit Runway when its advanced backend does not exist, Smart Alerts) open **branded, beautiful, accessible, honest Coming Soon placeholders**. Do not implement their business logic.
- Existing core Exit Runway unavailable state may remain within a decision panel as long as clearly marked not connected. Its separate advanced module remains Coming Soon.
- Keep the repository's current static HTML/CSS/JS stack unless the user approves a migration. High-end design does not require React.
- Do not commit, deploy, purchase credits, or overwrite destructive files without approval.

## 2. New art direction: “FAULTLINE / Fracture Intelligence”

Make FAULTLINE visually own the concept **of stress propagating through dependencies**. Choose one bold visual moment and keep secondary UI disciplined.

**Atmosphere:** black graphite / deep midnight / warm paper-like off-white for key typography; ember orange or electric vermilion to represent a real fault; restrained teal/cyan for neutral interaction and active selection. Deliberate contrast, careful spacing, tabular financial figures, original type choices. No coin clichés, casino neon, lavender gradients, scattershot glassmorphism, random stock imagery, fake 3D charts.

**Visual signature:** a *live, inspectable dependency network* across most of the Overview, with a coherent “fracture path” that lights up when a user selects a shock. Use real graph nodes/edges from the data. Animations communicate causal propagation; never suggest that a decorative animation is a simulated output.

**Logo/branding:** evolve the fracture motif as a small original mark, dividers, status traces and transitions, not a giant decorative wallpaper.

**Motion:** focused introduction (optional), selection and shock transitions, highlighted causal path, restrained count-up only for valid resolved metrics, accessible reduced-motion fallback. No looped particles, constant graph trembling, video background that competes with analysis, or delayed interactions.

## 3. One visually memorable opening screen

**Structure, not pixel-perfect template:**

```text
┌─ FAULTLINE ─ Overview ─ X-Ray ─ Stress Lab ─ Intelligence (soon) ── Portfolio / Snapshot ─┐
│                                                                                         │
│ KNOW WHAT BREAKS FIRST               MODELED RISK STATUS / PORTFOLIO CONTEXT              │
│ Headline: precise risk diagnosis, not marketing fluff                                      │
│                                                                                         │
│ ┌────────────────────────────────────────────┬─────────────────────────────────────────┐ │
│ │                                            │  FIRST BREAKING POINT                   │ │
│ │        INTERACTIVE DEPENDENCY MAP           │  Large meaningful shock threshold        │ │
│ │        large, elegant, inspectable          │  affected borrower and assumption         │ │
│ │        highlight stress path on selection  │                                         │ │
│ │                                            │  [Choose factor]  [Shock slider]         │ │
│ │                                            │  [Presets]         [RUN STRESS TEST]     │ │
│ │                                            │  Modeled impact / STAY vs EXIT          │ │
│ └────────────────────────────────────────────┴─────────────────────────────────────────┘ │
│  Compact evidence strip: capital | top exposure | modeled loss | data source / freshness │
│  Selected dependency details, affected positions, methodology (on demand)               │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

- **One hero:** meaningful network + stress panel, not four equal oversized metric cards.
- One unmistakable primary action: **Run stress test**; scenarios/presets near it.
- Show the relevant borrower/position for Breaking Point upfront; never imply it is the overall portfolio's $1M position if it isn't.
- Use the full laptop viewport well: one focal composition, not a grid of empty boxes extending below the fold.
- If the graph overwhelms or only has 44 dense nodes, use a curated subgraph by default with `Expand` and search. Never hide node meaning merely to make the graph pretty.
- Result changes must display backend-backed loading/success/error/not-modeled states; show explicit demo mode if offline. If backend only returns a scalar threshold, render a threshold scale, not a fictional curve.

## 4. Pages

1. **Overview:** visually magnetic map + risk cockpit, interactive core only. Present essential risk in a glance, with evidence available on inspection.
2. **X-Ray:** immersive full-width graph, highly legible node selection and causal trails, polished side inspector, responsive fallbacks.
3. **Breaking Point / Stress Lab:** focused simulation workspace, largest calculated stress visualization, clear factor/severity controls and a trustworthy outcome/impact area. Do not copy an invented chart.
4. **STAY / EXIT:** clear decision comparison in the relevant Overview/Stress context; the costs must come from the actual backend. The advanced Exit Runway can remain honest `Not connected`.
5. **P1/P2 pages:** shared Coming Soon template with a distinctive but lightweight visual, one-sentence feature purpose, no fake analytics, and a back-to-core CTA.

## 5. Mandatory tool protocol — prove actual use

**Higgsfield is required. Do not report success based on reading its site.**

1. Inspect locally available Claude Code MCPs, plugins, skills, and Higgsfield CLI. Inspect official Higgsfield capabilities before assuming commands. If auth, credentials or paid credits are required, ask for approval; do not silently spend money. If unavailable, report a specific blocker and stop *Higgsfield-dependent creative generation* rather than pretending it ran.
2. Use **Higgsfield Website Builder / website skill where actually supported** to explore an ambitious FAULTLINE visual concept in an isolated prototype or design output, **not by overwriting the repository**. The official Website Builder can build responsive animated sites, but compatibility with our existing repository/export must be checked rather than assumed.
3. Use Higgsfield generation to produce **at least one genuine visual artifact** that is meaningfully considered for the implemented identity (e.g. fracture identity study / abstract minimalist asset / carefully optimized short product film if justified). If a produced asset harms clarity or performance, document the rejection and regenerate or redesign; do not force irrelevant generated imagery into the analytical UI.
4. Use installed `frontend-design` skill explicitly for compositional choices and implementation. If installed, use **Impeccable** first for design direction or critique, then polish and audit. Use existing relevant skills such as 21st.dev or design guidelines where they add value; don't stack incompatible libraries.
5. Use Chrome DevTools or Playwright to inspect actual DOM, computed styles, network errors and screenshots. No pretend visual QA.
6. Produce `docs/design/TOOL_USAGE.md`: tool/skill name, invocation, what it returned, artifact location, where integrated, or exact blocker.

### Critical separation

Higgsfield concept generation ≠ a verified working risk product. **The production graph, sliders, financial numbers, and decision UI must be coded as real accessible HTML/SVG/JS with validated backend data.** Never pass an AI-generated dashboard screenshot off as the live application.

## 6. Design-first execution, not one giant autopilot redesign

**Phase 0 — repair/test the baseline:** Run the dev server. Investigate why all cards show `Loading…` in the screenshot. Inspect `/api/analyze` network response and JS errors. If backend is unavailable, use an existing **clearly labelled** fixture for visual-development mode, never silently relabel as live. Capture populated, empty and error states.

**Phase 1 — create two DIFFERENT compositions** in isolated prototypes (not two full apps):
- **A. Fracture Map / recommended:** dependency network as the visual hero; right-side stress cockpit; bold fault-line identity.
- **B. Shock Observatory:** large breaking-point stress visualization as the hero; network as a responsive contextual layer.

Use visual references and Higgsfield in this phase. Render **1440×900 screenshots for A and B**, explain the most important visual differences, and let the user choose a preferred direction BEFORE the full frontend refactor. You may recommend A.

**Phase 2 — lock one visual system:** Write short `docs/design/DESIGN_DECISIONS.md` with type, colors, spacing, signature visual, motion, accessible states, and screenshots. Do not drift back to generic symmetrical cards.

**Phase 3 — implement core end-to-end:** progressively integrate the selected design with the existing API. Preserve 100% of supported core behavior. Create scoped Coming Soon placeholders. The main user path must work: Overview → select dependency → inspect causal chain → set shock → backend recalculation → breaking point & impact → STAY/EXIT.

**Phase 4 — measured refinement:** Use Impeccable if available, browser captures at 1440×900 / 1280×800 / 390×844; compare screenshots to the approved concept. Review typography/spacing/motion, clipping, mobile, keyboard, loading, error states. Fix the 3 most consequential deviations then recapture. Validate all core actions and graph interactions; produce a short QA report.

**Phase 5 — user acceptance:** show actual captures of the running frontend, list changed files, backend endpoints exercised, tests and what remains unimplemented. Do not deploy/commit without approval.

## 7. Acceptance gates

- [ ] A **populated** first viewport is compelling and unmistakably about FAULTLINE, not generic cards.
- [ ] Two materially different screenshot concepts were rendered and compared before the major implementation.
- [ ] Higgsfield was demonstrably called through an actual supported workflow, with output evidence, and no unapproved costs.
- [ ] Actual installed skills used and logged; unavailable ones identified by name.
- [ ] One dominant hero element grounded in **real** risk relationships/data, backed by explanation.
- [ ] First-time user can find the relevant dependency, simulate a shock and see a trustworthy decision with minimal guidance.
- [ ] Existing P0 works, including provenance, borrower/portfolio distinction, and N/A states.
- [ ] All P1/P2 navigation destinations show polished Coming Soon placeholders, no faux-live analytics.
- [ ] No perpetual loading, hidden API failures or blank headline figures without explanations.
- [ ] Real browser captures at desktop/mobile, no blocking console issues, no horizontal overflow, keyboard and reduced-motion support.

## 8. Reference links — study attributes, do not copy wholesale

- [Linear's UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui): navigational density, alignment, restraint, precision.
- [Higgsfield Website Builder](https://higgsfield.ai/skills/website): concept/prototype, art direction and animation vocabulary; verify integration/export.
- [Higgsfield CLI](https://higgsfield.ai/mcp?tab=claude-code): check real installed CLI/skills/capabilities.
- [Anthropic frontend-design skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md): singular subject-driven hero and deliberate typographic choices.
- [Impeccable — getting started](https://impeccable.style/tutorials/getting-started/): direction picker, critique, polish, audit.
- [Reddit: How to avoid AI-looking UIs](https://www.reddit.com/r/ClaudeCode/comments/1w6fwbs/if_you_use_claude_code_to_design_uis_how_do_you/): visual references and process.
- [Reddit: Better Claude design skill set](https://www.reddit.com/r/ClaudeAI/comments/1wvffzn/best_claude_frontenddesignuxui_skill_set/): tokens + screenshots + browser loop.

**Note about TikTok:** direct TikTok video pages were unavailable to the researcher. Do not claim particular TikTok workflows have been tested unless you actually opened and verified them.

## 9. Exact message to Claude

> Read `frontend.md` and **this `FAULTLINE_VISUAL_REDESIGN_BRIEF.md`**. This document overrides the conservative visual direction but NOT financial correctness or functional scope. Current result is visually unacceptable: generic dark dashboard, no hero, flat hierarchy and empty/loading cards. I want a distinctive, visually stunning FAULTLINE risk cockpit. Higgsfield and my installed skills are mandatory, and their *actual use* must be documented. First verify the loading state, then create two truly different Higgsfield-informed 1440×900 visual concepts **without replacing the repo**. Show both captures and recommend one before implementing the full visual redesign. Only our core risk functionality becomes operational; P1/P2 sidebar items open polished Coming Soon placeholders. Preserve current backend, verify with Chrome, and do not commit, deploy or spend paid credits without approval.
