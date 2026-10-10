# FAULTLINE Frontend Redesign — Master Progress

**Branch:** `work/frontend-redesign`
**Last updated:** 2026-10-11 (session 2)

---

## Completed Work

### Phase A: Audit & Research (DONE)
- [x] Complete backend-to-frontend capability audit (10 API endpoints, 10 backend services, 6 pages)
- [x] UX research synthesis (Lusion, Cuberto, Morpho, DeFi Saver, WCAG 2.2 AA)
- [x] Design direction from Claude Design export + Higgsfield G4 reference
- [x] Feature coverage matrix with 8 critical gaps identified
- **Files:** `docs/frontend/FEATURE_COVERAGE_MATRIX.md`, `docs/frontend/UX_RESEARCH_SYNTHESIS.md`

### Phase B: Landing Page (DONE — video blocked)
- [x] G4 artifact set as default hero poster in HTML, preload, and JS
- [x] Subtle blue radial glow on artifact hero (`body.artifact .hero::after`)
- [x] Hero film infrastructure ready (`HERO_FILM = null` in landing.js)
- [x] No-flash loading: `<img>` src, `<link rel="preload">`, and JS all point to `hero-artifact.webp`
- [x] `?poster=backdrop` reverts to the original backdrop for review
- [ ] **BLOCKED:** Higgsfield video generation — all video models return `only_mcp_usage_on_trial_is_available`
- **Files modified:** `public/index.html`, `public/assets/js/landing.js`, `public/assets/css/landing.css`

### Phase C: Navigation Unification (DONE)
- [x] Replaced sidebar with horizontal top nav bar for overview, vault, soon pages
- [x] Injected brand + nav links into X-Ray's existing `.xr-top` header
- [x] Added cross-page navigation links to Countermove header (`.cm-nav`)
- [x] Fixed duplicate Countermove link (was listed twice in old sidebar)
- [x] Mobile responsive: nav hidden on xray mobile (<900px), cm-nav hidden on countermove mobile
- [x] Updated theme.css: removed all sidebar CSS (`has-side`, `.side-*`), added `.topnav` styles
- [x] Updated xray.css: removed sidebar toggle padding
- [x] Updated soon.html text: "sidebar" → "navigation"
- [x] Removed empty `<header id="nav">` from vault.html
- **Files modified:** `public/assets/js/shell.js`, `public/assets/css/theme.css`, `public/assets/css/xray.css`, `public/assets/css/countermove.css`, `public/countermove.html`, `public/soon.html`, `public/vault.html`

### Phase D: Visual Polish (DONE)
- [x] Vault CSS enhancement: elevated typography, KPI strip, verdict row, details toggle, graph, mobile
- [x] Overview page: larger verdict text (2.8rem), section headers with borders/uppercase, driver hover states, verdict glow
- [x] Overview page: added "Enter Countermove" CTA button alongside "Open dependency X-Ray"
- [x] Countermove header: 4-column grid (brand, nav, centered phases, right controls)
- [x] Design token bridge: intentional split kept (cinematic Archivo + #04070d for landing; functional IBM Plex + #0b0d11 for product)
- [x] Loading/error states: honest defaults throughout (—, Loading..., not_connected)
- **Files modified:** `public/assets/css/vault.css`, `public/overview.html`

---

## Backend Features — Frontend Coverage

| # | Backend Capability | Frontend Page | Status | Notes |
|---|---|---|---|---|
| 1 | Dependency X-Ray | xray.html | **Working** | Most sophisticated page, custom force graph |
| 2 | Vault Risk Analyzer | vault.html | **Working** | On-chain reads, full result rendering |
| 3 | Countermove demo | countermove.html | **Working** | 3 phases, 4 fixtures, 3D scene |
| 4 | Policy draft encoder | countermove app.js | **Working** | Calldata generated, no wallet signing UI |
| 5 | Risk overview | overview.html | **Working** | KPIs, verdict, scenarios, drivers |
| 6 | Breaking Point | breaking-point.js | **Working** | SVG chart with scenarios |
| 7 | Exit Runway | exit-runway.js | **Partial** | Frontend ready, backend endpoint not deployed |
| 8 | STAY/EXIT decision | overview verdict | **Working** | Uncertainty bands, confidence levels |
| 9 | Live dependency reads | countermove toggle | **Working** | Demo/live switch |
| 10 | Wallet (EIP-6963) | wallet.js | **Working** | Read-only, no signing |

---

## Navigation Map (after redesign)

```
Landing (index.html) — own header
  → Countermove demo, wallet connect, scroll story

Overview (overview.html) — topnav via shell.js
  → X-Ray (button + driver clicks + scenario clicks)
  ← topnav: Overview*, X-Ray, Vault, Countermove

X-Ray (xray.html) — brand + links injected into .xr-top
  ← xr-top: brand, Overview, X-Ray*, Vault, Countermove

Vault (vault.html) — topnav via shell.js
  ← topnav: Overview, X-Ray, Vault*, Countermove

Countermove (countermove.html) — own header + .cm-nav
  ← cm-nav: Overview, X-Ray, Vault
  ← brand: → landing

Soon (soon.html) — topnav via shell.js
  ← topnav: Overview, X-Ray, Vault, Countermove
```

---

## Higgsfield Status

- **Account:** Plus plan, 97 credits available
- **Workspace:** `0bc57638-0688-4cca-b3b8-c4ae91e5bfef`
- **G4 reference uploaded:** Image ID `1f5016a9-db1d-475b-936f-b52fee2a0e9e`
- **Video blocker:** All video models return trial-only error. Need account resolution.
- **Credits spent:** ~0.25 (1 test image generation)
- **Image generation works:** `gpt_image_2_5` model confirmed working

---

## Current Blockers

1. **Higgsfield video:** Trial restriction on all video models despite Plus plan
2. **Exit Runway endpoint:** `/exit-cost/{position_id}` backend not deployed — frontend shows "not connected" honestly
3. **On-chain execution:** RescueVault contract not built — Countermove live mode shows missing contracts
4. **Wallet signing:** No policy authorization or transaction signing UI

---

## Known Defects (to verify in QA)

1. Countermove `.top` header: verify phase tab centering with 4-column grid on desktop
2. X-Ray brand/nav injection: verify on 1440px, 1024px, 768px (hidden <900px)
3. Overview inline `<style>`: functional, could be extracted to `overview.css` for maintainability
4. CRLF warnings in git: Windows/WSL line ending differences (cosmetic, not functional)

---

## Exact Next Steps (for next session)

### Priority 1: Visual QA (do this first)
- Start local server: `cd public && python3 -m http.server 8000`
- Open each page at 1440px, 1024px, 768px, 375px
- Verify: topnav on overview/vault/soon, xray brand+links, countermove cm-nav + phase centering
- Test navigation flow: landing → countermove → overview → x-ray → vault → soon
- Screenshot all pages for review

### Priority 2: Higgsfield (if unblocked)
- `higgsfield account status`
- If video models work: generate 5s Kling 3.0 Pro from G4 start frame (ID: `1f5016a9-db1d-475b-936f-b52fee2a0e9e`)
- Prompt: "Slow camera push toward the monolithic stone structure. The blue lightning crack pulses with energy. Dust particles drift. Dark cinematic."
- Set `HERO_FILM` in landing.js, add video files to `public/assets/landing/`

### Priority 3: Commit and Deploy
- Stage all modified + new files (landing.css, landing.js, docs/frontend/*, etc.)
- Commit with descriptive message covering nav unification + visual polish
- Deploy via `./deploy-vercel.sh` (requires user approval)

---

## Commands for Next Session

```bash
# Verify branch
git checkout work/frontend-redesign
git status
git diff --stat

# Start local dev server
cd public && python3 -m http.server 8000
# Visit: http://localhost:8000/ (landing)
#        http://localhost:8000/overview.html
#        http://localhost:8000/xray.html
#        http://localhost:8000/vault.html
#        http://localhost:8000/countermove.html

# Start backend API
cd .. && python3 -m uvicorn api.analyze:handler --port 8001

# Check Higgsfield
higgsfield account status
higgsfield workspace list
```

---

## All Modified Files (this redesign branch)

### Tracked (modified)
| File | Change |
|---|---|
| `public/index.html` | Hero artifact as default poster, preload updated |
| `public/overview.html` | Verdict glow, typography, section headers, Countermove CTA |
| `public/vault.html` | Removed empty `<header id="nav">` |
| `public/countermove.html` | Added `.cm-nav` product navigation links |
| `public/soon.html` | "sidebar" → "navigation" text |
| `public/assets/js/shell.js` | Complete rewrite: sidebar → top nav bar |
| `public/assets/css/theme.css` | Sidebar → topnav styles, removed `--side-w` |
| `public/assets/css/vault.css` | Enhanced: typography, KPI strip, verdict, details, mobile |
| `public/assets/css/xray.css` | Removed sidebar padding, added mobile `.xr-links` hide |
| `public/assets/css/countermove.css` | `.cm-nav`, 4-col grid, `.steps` center, mobile hide |

### Untracked (new files — need `git add`)
| File | Change |
|---|---|
| `public/assets/js/landing.js` | G4 artifact default, `?poster=backdrop` to revert |
| `public/assets/css/landing.css` | Cinematic landing styles, artifact glow |
| `public/assets/landing/*.webp` | Hero poster, demo screenshots (6 files) |
| `docs/frontend/MASTER_PROGRESS.md` | This progress checkpoint |
| `docs/frontend/FEATURE_COVERAGE_MATRIX.md` | Backend-to-frontend mapping |
| `docs/frontend/UX_RESEARCH_SYNTHESIS.md` | Research synthesis |
