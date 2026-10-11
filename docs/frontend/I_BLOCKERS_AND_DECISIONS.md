# I. Blockers and Open Decisions

Only decisions that change what gets built. Recommended answers are first.

| # | Decision | Options | Recommendation | Why it matters |
|---|---|---|---|---|
| 1 | **Is the deadline still Sun 11 Oct (video 09:30, submit 10:30, judging 11:00)?** | Yes → Track 1 (≈ 7 h) · No → Track 2 depth | Confirm now | Determines scope, hero technique and QA depth |
| 2 | **Creative direction** | **B Seismic Ledger** (low risk, fast, distinctive) · A The Seam (max wow, 3D craft risk) | B under the deadline; A if time allows | Drives the landing build and the demo film |
| 3 | Information architecture | **`/` = landing; dashboard + X-Ray merged into `/analyze.html`** (old URLs redirected) · keep four pages | Merge | One analytical journey instead of two overlapping pages |
| 4 | Countermove ARM on the hosted site | **Preview only (calldata, no signing)** · wire a fork-only signing demo locally | Preview only | No RescueVault exists on mainnet and the repo has no deploy path; a sign button would be misleading |
| 5 | Fallback when live APIs fail during the demo | **Explicit, labelled SAVED SNAPSHOT regenerated from the current backend** · UNAVAILABLE only | Snapshot, explicit + labelled | Public RPC/API outages are the main demo risk; silent fallbacks are not acceptable |
| 6 | Backend owner items before the demo | Fix C3 (book carry reference → negative exit costs) and C4 (borrower notional) · leave and label | Fix C3 if possible (≈ 30 min); otherwise UI labels it | The book is in the brief's own example; negative "exit costs" with EXIT badges invite jury questions |
| 7 | Tooling installs (dev-only) | FFmpeg (MP4 demo film) · Playwright test package in `tests/e2e/` | Approve both | WebM capture works without FFmpeg; many submission forms want MP4 |
| 8 | Paid media generation | None · small budget for texture/establishing studies | None for now | Higgsfield is on the free tier (10 credits); the hero is code-rendered |
| 9 | Deployment | Owner runs `deploy-vercel.cmd` after review | Owner only | The script commits and pushes `main` as the owner |

## Not blockers (handled in the implementation)
X-Ray client-side recomputation, silent fallbacks, mobile navigation, copy for SIMULATED/DRY-RUN, staged loading,
missing logos, status chips, reduced motion, CSP headers.
