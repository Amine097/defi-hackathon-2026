# FAULTLINE — Claude Code tooling research and adoption plan

**Date:** 2026-10-10  
**Scope:** Phase 2 — Autonomous Countermove; HTML/CSS/vanilla JS frontend, existing Three.js prototypes, Python risk backend.  
**Goal:** Upgrade visual craft, motion, product usability, and verification without breaking risk calculations or inventing transaction evidence.

## Executive decision

**Do not install every tool.** The existing skills reportedly include Higgsfield MCP, `frontend-design`, Impeccable, UI UX Pro Max, `design-system`, and `dataviz`. Check actual availability (`/mcp`, `/skills`) before adding duplicates.

Install or enable **Context7** plus **one strong browser inspection tool** first; add **deterministic Playwright tests**, **Vercel's web-design-guidelines skill**, and **GSAP for authored motion** where needed. Introduce **Figma**, **21st MCP**, **Theatre.js**, **Rive**, or **XState** only when a concrete need justifies the extra complexity.

> Especially important: the application must distinguish backend event statuses from UI animation states, and a DEMO/fork confirmation from mainnet confirmation. A browser timeline is not transaction proof.

## High-priority shortlist

| Tool | Kind | FAULTLINE benefit | Decision |
|---|---|---|---|
| [Context7](https://github.com/upstash/context7) | MCP / skill | Current documentation for Three.js, animation, UI libraries, and integration code; fewer invented APIs. | **Install if missing** |
| [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) | MCP + optional official skills | Inspect rendered Chrome, performance traces, console, network, layout and WebGL responsiveness. | **Install if missing** |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) + [Playwright Test](https://playwright.dev/docs/test-assertions) | Browser MCP + test runner | Automate real three-stage journeys, visual regression screenshots, backend-error tests. | **Install if missing / create tests** |
| [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) | Agent skill | Catch poor accessibility, layout, focus, forms and UX consistency that design-generation skills miss. | **Add as review skill** |
| [GSAP timelines](https://gsap.com/docs/v3/GSAP/Timeline/) | JS animation library | Synchronize danger propagation, defensive action selection, execution state transition and evidence reveal. | **Evaluate for production motion** |

### Verified install instructions

Run the checks in your **actual WSL Linux environment** first. Earlier in the project, `npx` resolved to a Windows path while Linux `node` was missing; if still true, repair that environment before MCP installation. Do not blindly install packages on Windows and assume Claude Code in WSL can see them.

```bash
command -v node
command -v npx
node -p 'process.platform'  # should report linux in WSL
claude mcp list
```

**Context7:**
```bash
npx ctx7 setup --claude
```
The wizard handles sign-in and MCP/skill setup. Official: https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx

**Chrome DevTools MCP, standalone:**
```bash
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest
```
Alternatively, for official MCP **plus skills**, inside Claude Code: `/plugin marketplace add ChromeDevTools/chrome-devtools-mcp`, then `/plugin install chrome-devtools-mcp@chrome-devtools-plugins`. **Choose one method, not both.** Official: https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/client-configurations.md

**Playwright MCP:**
```bash
claude mcp add playwright npx @playwright/mcp@latest
```
Official: https://github.com/microsoft/playwright-mcp

**Vercel UI review skill:**
```bash
npx skills add https://github.com/vercel-labs/agent-skills --skill web-design-guidelines
```
Official: https://github.com/vercel-labs/web-interface-guidelines

Do not install these simultaneously while Claude is mid-implementation. Finish its current deliverable, restart the Claude session if necessary, then verify `/mcp` and `/skills`.

## Quality/UX verification stack

1. **Playwright Test:** store runnable tests, not throwaway screenshots. For each stage, test first load, configured-but-not-armed, armed with backend acknowledgement, detection, planning, execution pending, confirmed with evidence, failed, no-action, DEMO-only, offline/error, and disabled/revoked. Never build a confirmation out of a client-side timer.
2. **Visual snapshots:** use Playwright `expect(page).toHaveScreenshot()` for stable layouts; freeze deterministic fixture values and avoid comparing frames while Three.js is moving. Save screenshots for 1440x900, 1280x800 and 390x844.
3. **Chrome DevTools:** record actual page performance and interactions on Chrome, including DPR=2 and 44-node fallback. Distinguish slow backend response from slow rendering; record actual device and browser conditions.
4. **Accessibility:** `@axe-core/playwright` checks contrast, landmarks, controls, alerts and key interactions. A visual screenshot cannot verify keyboard or screen-reader usability. Official: https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright
5. **Lighthouse CI:** optionally enforce basic performance/accessibility budgets after app stabilization. Official: https://github.com/GoogleChrome/lighthouse-ci
6. **Human review:** ask two people unfamiliar with the project to describe within 60 seconds what was detected, allowed, chosen, executed, and verified. Fix where they hesitate.

## Tools for a much better immersive result

### GSAP — use first when hand-authored animation is needed

GSAP timelines sequence DOM/SVG and Three.js-controlled numeric properties. Animate **the UI presentation** of events reported by the backend, never the backend status itself. For example, `DETECTED -> PLANNING -> EXECUTING` may be *visualized* in order only if events are present; if the backend jumps to `FAILED`, the UI must show failure immediately, not finish a fictional success sequence. Official timeline docs: https://gsap.com/docs/v3/GSAP/Timeline/

### Theatre.js — optional for a refined cinematic 3D scene

Offers an editor to choreograph Three.js camera, lighting and animated sequences. Use only if GSAP + existing Three.js cannot reach the visual goal, and keep it in an isolated prototype initially. It does not replace real graph data. Official: https://www.theatrejs.com/

### Rive / dotLottie — optional for small state animations

Use for premium shield/armed indicators, subtle action symbols and execution microinteractions. Avoid replacing accessible status text with an animation or shipping animated badges that imply on-chain confirmation. Docs: https://github.com/rive-app/rive-wasm and https://docs.lottiefiles.com/en/runtimes/distributions/js

### XState v5 — optional state-machine library, high functional value

Framework-agnostic and potentially useful for complex frontend lifecycle states. But **the backend remains authoritative**. Frontend statecharts should validate allowable transitions, not generate fake asynchronous blockchain events. Evaluate after inspecting real v3 API contracts; a small handwritten reducer may suffice. Official: https://stately.ai/docs

### Three.js post-processing

Very modest, targeted post-processing may help the focal node and propagation path. Measure performance first; don't restore expensive refraction/bloom that previously stuttered on DPR 2. Official EffectComposer: https://threejs.org/docs/pages/EffectComposer.html

## Optional MCPs / references, not automatic additions

| Tool | Best use | Why not install now? |
|---|---|---|
| [Figma MCP](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/) | Claude reads / writes genuine Figma designs, tokens, components. Claude Code Figma plugin: `claude plugin install figma@claude-plugins-official` | Valuable **if someone will maintain a Figma design**; otherwise another surface and login. |
| [21st MCP](https://github.com/21st-dev/magic-mcp) | Search/inspect/generate UI component patterns. Current install `npx @21st-dev/cli@latest init --client claude` | Many snippets are React/Tailwind; FAULTLINE currently uses static JS. Avoid wholesale imports or framework migration; generation may require account/paid credits. **Old Magic MCP is superseded.** |
| [agent-browser](https://github.com/vercel-labs/agent-browser) | Fast browser automation CLI, screenshot and accessibility snapshots. Skill: `npx skills add vercel-labs/agent-browser` | Useful alternative when MCP context cost is high, but **don't install multiple overlapping browser agents by default**. |
| [Storybook](https://storybook.js.org/docs) | Isolated component-state gallery and visual tests for complex UI teams. | Heavy setup for a static hackathon frontend; small fixture-based HTML test pages may be faster. |
| [React Three Fiber](https://github.com/pmndrs/react-three-fiber) + React UI kits | Complex reusable React + 3D scenes. | Requires React; do not migrate working vanilla Three.js just for tools or templates. |

## A custom skill may matter more than another general design skill

Create `.claude/skills/faultline-countermove-ux/SKILL.md` (with Anthropic's `skill-creator` if available). It should be short and encode project-specific decisions:

- Source of truth: `docs/FAULTLINE_Countermove_v3_Autonomous_Crisis_Response.md`, verified backend endpoints, and known fixtures. Do not assume names/shapes of missing response fields.
- UX story: BEFORE configure/arm -> DURING detect/decide/execute -> AFTER verify/measure.
- Explicit environment tags: `DEMO`, `FORK`, `TESTNET`, `MAINNET` where verified; never display `CONFIRMED` without authoritative receipt evidence.
- Real risk and financial data must be backend-derived; distinguish detection, predicted mitigation, attempted execution, and actual outcome.
- Maintain functional 2D dependency fallback, semantic labels, keyboard access and `prefers-reduced-motion`.
- Screenshot+test gates: viewport matrix; normal/failure/no-action/unavailable; no stale or spurious visual values.
- No mainnet execution and no contract or backend risk-engine edits unless explicitly requested and approved.

Anthropic skill-creator: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator

## Specific work order

**Stage 0 — finish current Claude task.** Do not interrupt the running Countermove implementation for an unrelated installation spree.

**Stage 1 — inspect.** `claude mcp list`, `/mcp`, `/skills`. Identify duplicates and inspect actual Node resolution in WSL.

**Stage 2 — enable** Context7 + one Chrome inspector + Playwright tests. Add the Vercel review skill. Verify each with a concrete one-minute smoke test, including a local URL and a screenshot saved to disk.

**Stage 3 — polish.** Prototype a GSAP crisis-to-defense sequence (no new financial logic). Compare against the existing Three.js animation, including reduced motion, keyboard and performance.

**Stage 4 — verify.** Produce deterministic backend fixture test cases for each Countermove state, compare screenshots, run accessibility/performance checks and resolve confusing labels.

**Stage 5 — optional.** Figma if using a shared design canvas; Theatre.js only if current 3D is visually insufficient; 21st only for inspected adaptable patterns, not automatic React migration.

## Ready-to-send prompt after the current mission

> Review our FAULTLINE Phase 2 frontend and its installed Claude skills/MCPs. Do **not** install everything. First list actual available tools, identify duplicates and check the Node/WSL environment. Propose at most three incremental additions: Context7 for current docs, one Chrome inspection tool if missing, and Playwright Test with reproducible screenshot journeys; optionally add Vercel Web Interface Guidelines for UI audits. Use GSAP only if a small isolated motion prototype proves better than the current implementation. Respect the verified Countermove v3 backend contract, DEMO/FORK provenance, and real execution receipts. No mainnet actions. Benchmark before/after visuals and performance. Ask before paid accounts, new frameworks, installs that alter the app, commits or deployments. Deliver a prioritized plan with commands, evidence and budget estimates. Stop for approval.

## Research provenance

Primary sources: official repositories and documentation linked above; community feedback on real-browser evidence loops: https://www.reddit.com/r/ClaudeCode/comments/1uz1wgp/skillsmcps_for_webpage_testing_in_browser/ . Community anecdotes are not tool performance guarantees. This is an adoption recommendation, **not a claim that any tool was installed or executed in your Claude Code environment**.
