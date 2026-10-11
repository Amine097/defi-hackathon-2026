# H. Production Roadmap

Two tracks. **Track 1** assumes the `PLAN.md` deadline still holds (Sun 11 Oct, video 09:30, submission 10:30,
judging 11:00) — about 7 hours of build after approval. **Track 2** is the full redesign after the hackathon.
Every phase keeps the backend gate green (pytest, forge, Countermove S1–S5) and changes no backend calculation.

## Track 1 — hackathon critical path (≈ 7 h)

### Phase 0 · Truth fixes (≈ 1 h, P0)
- X-Ray dollar values from the server only: node failure → `stress_table` row; channel-blocked edges dashed with words
  ("only matters with debt", "exit cost only"); delete the "client propagation check"; label break-even as a what-if.
- Replace silent `sample.json` fallbacks with **UNAVAILABLE + Retry**; regenerate a snapshot from the current backend
  and offer it only as an explicit, labelled **SAVED SNAPSHOT** (block + date).
- Book rows with a negative exit side shown as "yield rebalance — not a risk signal" (numbers untouched).
- One shared header on all pages (Countermove reachable on mobile); policy-draft copy → "Policy preview (calldata).
  Requires a RescueVault — local fork demo only."

**Accept when:** Playwright asserts UI loss = `stress_table[id].conditional_loss_usd` for oracle, AMM, market, issuer;
502 shows UNAVAILABLE (no numbers); no negative exit cost carries an EXIT badge; nav reachable at 390 px.

### Phase 1 · Decision instrument (≈ 2 h, P0 — Belem 30 % + 30 % + 25 %)
- Analysis page: strata graph (5 Belem layers, hidden nodes revealed), verdict sentence + stay/exit bands + flip
  multiple, **HOLD TO MATURITY strip**, scenarios with channel notes, **incident panel** (dependency + severity →
  `?shock=&severity=`, cached per pair), evidence bar (status chip, block, ticking age, TTL), staged progress for the
  20–35 s wait.
- Book panel: Belem's 10 × 10 % example, hit dependency selector, **"11 % exit cost (brief)" toggle**
  (`exit_cost_pct=0.11`), shared-dependency table.

**Accept when:** issuer at 50 % renders "$360k vs $5.5k → EXIT · 2 pockets hit, exit 2"; 11 % toggle renders 2 EXIT /
8 STAY / 2.5 % of book; HTM shows three costed options; REVIEW never styled as STAY/EXIT; all numbers equal the payload.

### Phase 2 · Landing hero (≈ 2–2.5 h, P0 first impression)
- Chosen direction (B fits the time box; A possible as "A-lite" with a poster fallback): fracture → countermove →
  proof sequence, chapter rail, CTAs *Analyze the Belem example* · *See the countermove*.
- Poster as LCP, lazy GPU code, reduced-motion static frame, pause control, 390 px layout.

**Accept when:** LCP < 2.5 s, 60 fps desktop / ≥ 30 fps mid phone, no numbers except labelled SIMULATED values from
the recorded run, Lighthouse accessibility ≥ 95.

### Phase 3 · Countermove ARM → DEFEND → PROVE (≈ 1.5 h, P1)
- Default to **S5** (Belem's PT example). ARM: policy as trigger / floor / caps / reserves + "what it can and cannot
  do"; DEFEND: replayable timeline (WATCHING → DETECTED → PLANNING → VALIDATING → EXECUTING → CONFIRMED), actions
  compared, plus a **LIVE dry run** panel on a real mainnet borrower; PROVE: receipt, 15/15 checks, unchanged user
  nonce, SIMULATED chip on every fork value.
- Link the analysis page's borrower mode (`countermove_suggestion`) to the ARM preview.

**Accept when:** S1–S5 render unchanged values; dry run shows LIVE block and no transaction field; SIMULATED and LIVE
can never be confused.

### Phase 4 · QA and demo film (≈ 1 h)
Screens at 1440 / 1024 / 768 / 390, keyboard path, contrast, reduced motion, API-down path; record the 90-second path
with Playwright `recordVideo`; the owner deploys (empty-commit script) after review.

## Track 2 — after the hackathon

| Phase | Scope | Acceptance |
|---|---|---|
| 5 | Direction A real-time monument (if chosen) at agency quality; vault page result-first (allocation treemap, exit-route ladder, curator roles, FX vs peg, sponsor vault picker) | Lighthouse perf ≥ 90 mobile; 0 jargon enums in UI |
| 6 | Breaking Point instrument (from `price_grid`), stress table + sensitivity tornado, evidence page (tests, GO criteria, sources) | Every chart has method + refresh note |
| 7 | Backend items in C3–C6 (owner): per-pocket carry reference, borrower notional, post-shock exit, assumption bands | Regression tests + updated fixtures |
| 8 | Read-only wallet (EIP-6963) → positions; RescueVault deployment path (contract + audit) before any signing UI; alerts (C5); CSP headers | Security review; signing only on a chain where the vault exists |

## The 90-second judge demo (reproducible)

Pre-flight: open the analysis 2 minutes before (Vercel caches 60 s), keep a labelled SAVED SNAPSHOT ready in case the
public RPCs fail, run the live dry run once.

| Time | Screen | What the judge sees | Criterion |
|---|---|---|---|
| 0:00–0:08 | Landing | The fault opens through the mark; the countermove locks it. *When DeFi breaks, FAULTLINE moves first.* → **Analyze the Belem example** | Story |
| 0:08–0:25 | Analysis | LIVE, block N: $1M PT-reUSD on Morpho. Five Belem layers, then the hidden ones: issuer re.xyz, USDC, T-bill backing; every oracle feed read on-chain | Discovery 30 % |
| 0:25–0:45 | Incident | Click the oracle (Belem's layer-3 incident): *no effect without debt — it only liquidates borrowers*. Issuer at 50 %: **$360k loss vs $5.5k exit → EXIT**. Book: 2 of 10 pockets share it; with the brief's 11 % exit cost: exit those 2, book loss 2.5 % | Impact 30 % |
| 0:45–0:60 | Decision | Baseline REVIEW, lean STAY (risk must be ×6.8 higher), bands shown. *Is there better than exiting?* **HOLD TO MATURITY: $1.5k vs $9.2k over 60 days** | Decision 25 % |
| 0:60–0:80 | Countermove | S5, SIMULATED fork: Ojo PT feed −5 % → LTV 85 % → 89.5 % crosses the 88 % trigger → **repay 1,447.44 USDC ~2.1 s after detection, no user signature, 15/15 checks**. Then LIVE dry run on a real borrower: WATCHING / HOLD | Real data 15 % + "and then what?" |
| 0:80–0:90 | Proof | 252 backend tests · 29 contract tests · every number sourced, every status labelled. *FAULTLINE moves first.* | Trust |
