# G. Technical Recommendation

## G1. Architecture: evolve, do not migrate

Keep the zero-build static site + Python functions on Vercel (see D4 for the rationale). Restructure it:

```
public/
  index.html            landing (brand experience; CTA → analysis)
  analyze.html          the instrument: strata graph + decision rail + scenarios/incident + HTM + book
  vault.html            vault analyzer (result-first)
  countermove.html      ARM → DEFEND → PROVE (recorded fork run + live dry run)
  evidence.html         (optional) tests, GO criteria, sources, methodology
  assets/css/tokens.css base.css components.css   one design system
  assets/js/core/       api.js status.js format.js progress.js evidence.js shell.js
  assets/js/pages/      landing/ analyze/ vault/ countermove/
  assets/vendor/        pinned, self-hosted libs + LICENSE files (no CDN)
```

- Keep old URLs working (`/xray.html` → `/analyze.html` via `vercel.json` redirects; `/vault.html?address=` unchanged).
- View models stay pure functions with `node --test` against fixtures captured from the **current** backend.
- **No financial computation in the browser.** Allowed client maths: formatting, layout, interpolation for animation,
  and clearly labelled what-if calculators (e.g. break-even slider) that never replace a server verdict.

## G2. Data contract layer (`core/api.js`, `core/status.js`)

| Concern | Rule |
|---|---|
| Timeouts | `AbortController`: 70 s for analyze/vault (server cap 60 s), 15 s for countermove; cancel on navigation |
| Errors | Parse structured errors (`{error:{code,status,message}}` and analyze's `{error, code}`); show inline with retry; never substitute data |
| Status | One status model rendered as **text** in an `aria-live` region (table below) |
| Freshness | Show `data_as_of`/block and a ticking age; after 60 s (quote TTL) / 120 s (chain state) mark **STALE — re-run before acting** without altering the verdict |
| Caching | Optional `sessionStorage` of the last payload, displayed as CACHED with its age; per-(node, severity) cache for incident calls |
| Long waits | Staged progress using the real pipeline order and elapsed time (typical 20–35 s); no fake percentages |

| Chip | Source of truth |
|---|---|
| LIVE | analyze `source: live`; vault `mode: live`; countermove `live.status: LIVE`; dry-run `environment.label: LIVE` |
| CACHED / MIXED | analyze `source: cache / mixed` (+ `data_as_of`); vault `mode: cache / mixed / offline` |
| STALE | `decision.freshness.blockers[]` non-empty, or client age > TTL |
| SAVED SNAPSHOT | a static payload deliberately loaded by the UI, regenerated from the current backend, with block and date |
| DEMO | `ref=mock` (`source: mock`) — only on explicit request |
| SIMULATED · FORK | `/api/countermove` recorded run (`environment.chain_id 31337`) |
| DRY-RUN | dry-run `watcher.label` / `decision.label` |
| UNAVAILABLE | HTTP error / timeout, with code |

## G3. Motion and rendering stack

| Layer | Choice | Notes |
|---|---|---|
| Timeline / scroll | **GSAP 3 + ScrollTrigger** (SplitText if needed) | Free for commercial use since Apr 2025 under GSAP's proprietary "no charge" standard license (not MIT) — keep its license file; confirm the current text at gsap.com before shipping |
| Landing 3D (Direction A) | **Three.js** (MIT), custom shaders, selective bloom | Lazy-loaded after first paint; GPU tiering; poster as LCP |
| Landing 2D (Direction B) | WebGL2 line field (raw or a ~25 KB helper such as OGL — check its license) + SVG `clipPath` type shear | Text stays real text |
| App graph | Keep the existing canvas renderer; add strata layout, server-driven cascades, list twin | No new dependency needed |
| Smooth scroll | Native; Lenis only on the landing if at all | Never scroll-jack the app |
| Reduced motion | Every animated element has a static equivalent; pause control for anything > 5 s | WCAG 2.2.2, C39 |

## G4. Assets

- **Fonts:** self-hosted WOFF2 subsets (Archivo variable + IBM Plex Mono; the `work/frontend-redesign` branch already
  contains IBM Plex WOFF2 files that can be harvested). `font-display: swap`, preload the display face only.
- **Images:** posters in AVIF/WebP, rendered from the hero scene; the four missing logos (`us.svg`, `rexyz.svg`,
  `reusd.svg`) replaced by typographic fallbacks.
- **Video (optional):** the hero scene recorded headlessly (Playwright `recordVideo`, WebM) for a low-power fallback and
  the 2-minute demo film. **FFmpeg is not installed** — needed only for MP4/AV1 transcoding (owner approval to install).
- **Generated media:** none required. If approved later, use 2–3 controlled image/texture studies or one establishing
  shot; Higgsfield account is free tier (10 credits); alternatives with stronger image-to-video control exist
  (Kling 3, Runway Gen-4.5, Veo 3.1, Luma Ray) — all paid.

## G5. Performance budget

| Metric | Landing | App pages |
|---|---|---|
| LCP (4G, mid phone) | < 2.5 s (poster image) | < 2.0 s for the shell; data arrives later with progress |
| JS (gzip) | ≤ 200 KB (A) / ≤ 90 KB (B), loaded after paint | ≤ 60 KB per page |
| CLS / INP | < 0.1 / < 200 ms | < 0.1 / < 200 ms |
| GPU | 60 fps desktop, ≥ 30 fps mid phone, auto-downgrade | — |

The real bottleneck is API latency (15–36 s). Frontend mitigations: start the analysis as soon as the user commits
(CTA), keep the shell interactive, reuse the last payload as CACHED. Backend options for the owner: a fast "graph
only" response before the executable quotes, or skipping the 10 book quotes when the book panel is closed
(`DEFIRISK_NO_QUOTE` already exists as an environment switch).

## G6. Security

- Add headers in `vercel.json`: `Content-Security-Policy: default-src 'self'; img-src 'self' data:; connect-src 'self'`
  (+ RPC origins only if a wallet is added), `frame-ancestors 'none'`, `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` minimal, `X-Content-Type-Options: nosniff`.
- No third-party scripts or CDNs (the Claude Design export's unpkg React must not ship).
- Wallet (later, optional): EIP-6963 discovery, read-only by default, chain check, 4001 as neutral, simulated preview
  before any signature; **no signing UI while no RescueVault exists on the connected chain**.
- Keep keeper/fork tooling local; the hosted app never signs or sends.

## G7. QA

- `node --test` view models (existing 33 + new ones for status, incident, HTM, book rows, channel labels).
- Playwright e2e in an isolated `tests/e2e/` package (keeps Vercel's root free of a `package.json`), using the installed
  Chrome (`channel: 'chrome'`): desktop 1440×900 and mobile 390×844 screenshots per route, API-down path, reduced
  motion, keyboard path, "UI numbers equal payload numbers" assertions.
- Backend gate unchanged: pytest, forge, Countermove S1–S5.
