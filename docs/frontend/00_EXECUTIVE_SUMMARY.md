# 00. Executive Summary — FAULTLINE frontend discovery (11 Oct 2026)

## The ten findings that matter

1. **The backend is real and largely complete.** Verified live: dependency discovery (12 nodes, 5 Belem layers + hidden
   issuer / stablecoin / T-bill backing, every oracle feed read), role-aware losses, calibrated LGF, uncertainty bands,
   executable exit quotes re-executed on-chain, HOLD TO MATURITY, real 10-pocket book, incident path, borrower mode with
   a Countermove policy suggestion, Morpho vault analyzer, Countermove S1–S5 on a fork, and a read-only mainnet dry run.
   Tests: pytest 252 ✓ / 17 skipped (live), Node 33 ✓, forge 29 ✓. Production matches `main`.
2. **The UI covers maybe half of it.** HOLD TO MATURITY, the incident path (`shock=&severity=`), stress table,
   sensitivity, shared dependencies, the brief's 11 % exit-cost example, the Countermove suggestion and the dry run have
   **no interface**.
3. **P0 honesty defect:** X-Ray recomputes losses in the browser and ignores loss channels. Failing the oracle shows
   **EXIT, $154k**; the backend says **$761, STAY — no effect without debt**. AMM and Morpho market show EXIT $192k
   (backend: $0). The most visible interaction contradicts the model's main fix.
4. **P0 fallback defect:** on any API failure the UI silently loads a 10 Oct snapshot that predates the role-aware model
   ($321k oracle loss, $501k liquidity loss) and labels it "MOCK".
5. **The "Loading…" baseline** is a slow first load (20–36 s live analysis), not a failure or CSS issue — plus one card
   on the old redesign branch wired to `/exit-cost/{id}`, which never existed.
6. **Backend issues to raise (not to patch in the UI):** the book uses one reinvestment rate for every pocket, producing
   negative exit costs and EXIT verdicts on pockets the shock does not touch; borrower mode mixes a $1M hypothetical
   headline with a $12.7M real borrower; exit timing (exit before the shock is priced) is implicit; the top of the stress
   table (Ethereum, US-dollar base asset) is assumption-driven.
7. **Countermove is fork-only by design.** No RescueVault is deployed anywhere a user could sign; the UI's "Sign this
   setPolicy call" copy overpromises. ARM must be a preview on the hosted site.
8. **Feature specs without code:** Breaking Point engine, Exit Runway, Whale Impact, Reaction Window, Chain of Blame,
   Leverage Hunter, Cascade Radar, Telegram, wallet → positions. Do not present them as features.
9. **Architecture:** keep the zero-build static site; restructure (shared shell, design tokens, one API/status layer),
   remove all client-side financial maths, self-host GSAP/Three.js only where the landing needs them.
10. **Creative:** two directions grounded in the logo's zigzag fault — **A "The Seam"** (the mark as a stone monument
    whose fracture is stapled shut; real-time WebGL) and **B "Seismic Ledger"** (paper-and-ink line field and headline
    that shear along the fault, then re-register; 2D WebGL + SVG). B is recommended under a deadline; A for maximum wow.
    No paid generation needed; Higgsfield is on the free tier (10 credits).

## Decisions needed (details in I)
Deadline still 11 Oct 11:00? · Direction A or B · `/` becomes the landing (dashboard + X-Ray merged) · ARM stays a
preview · explicit labelled snapshot fallback · backend fix for the book carry (C3) · approve dev-only FFmpeg and
Playwright test package.

## Documents
[A](A_PROJECT_UNDERSTANDING.md) · [B](B_FEATURE_COVERAGE_MATRIX.md) · [C](C_BACKEND_RISKS.md) ·
[D](D_CURRENT_FRONTEND_ASSESSMENT.md) · [E](E_UX_RESEARCH_FINDINGS.md) · [F](F_CREATIVE_DIRECTION.md) ·
[G](G_TECHNICAL_RECOMMENDATION.md) · [H](H_PRODUCTION_ROADMAP.md) · [I](I_BLOCKERS_AND_DECISIONS.md) ·
screens in [audit-2026-10-11/](audit-2026-10-11/)
