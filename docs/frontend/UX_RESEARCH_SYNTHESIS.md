# FAULTLINE — UX Research Synthesis

## 1. Interactive Studio Benchmarks

### Lusion / Active Theory — Cinematic Immersion
- **3D as narrative, not decoration**: Every visual element serves the story. The dependency graph should explain relationships, not just look impressive.
- **Scroll-driven revelation**: Content unfolds with scroll position. The ARM → DEFEND → PROVE sequence is perfect for this.
- **Dark-field confidence**: Pure black backgrounds (#000–#050) with selective lighting create premium authority. Applied: our `#04070d` base.
- **Custom typography as identity**: Both studios use type as the primary visual element, not illustrations.

### Cuberto — UX Clarity
- **Strategy first, aesthetics second**: Beautiful interfaces that serve clear user goals.
- **Purposeful microinteractions**: Hover states, transitions, and feedback confirm actions without overwhelming.
- **Information hierarchy through type scale**: Large differentials between heading weights create scannable layouts.
- **Restraint**: Avoid decorative animation. Every moving element should communicate state change.

### Atlas Motion — Material Quality
- **Physically convincing materials**: Our G4 artifact uses machined basalt, satin graphite — these must feel real.
- **Volumetric lighting**: Single directional light source, not flat ambient fill.
- **Cinematic framing**: Hero imagery uses the right 40% of frame; left stays open for copy.

## 2. DeFi Product Patterns

### Morpho
- **Unified dashboard**: All positions visible in one view with key metrics (APY, balance, health).
- **Vault-centric architecture**: Users think in terms of vaults and positions, not protocols.
- **Clear risk tiers**: Visual indicators for curator quality, oracle reliability, market isolation.
- **Minimal chrome**: Dense data presented cleanly without decorative elements.

### DeFi Saver — Automation UX
- **Smart wallet paradigm**: Advanced operations require a smart contract wallet.
- **Rule-based automation**: Users define conditions (stop-loss, take-profit, leverage adjust) — FAULTLINE's policy model is similar.
- **Single-transaction batching**: Complex operations bundled into one tx — our RescueVault does this.
- **Clear automation status**: Users can see what's armed, what's watching, what's been triggered.

### Key DeFi UX Principles
- Transaction simulation before confirmation (show expected outcomes).
- Clear separation of read-only operations from state-changing transactions.
- Wallet connection ≠ authorization. FAULTLINE correctly separates these.
- Gas estimation visible before signing.
- Block explorer links for verification.

## 3. Financial Dashboard Design

### Data Visualization Hierarchy (Nielsen Norman Group)
- **Z-pattern scanning**: Users scan dashboards top-left → top-right → bottom-left → bottom-right.
- **7-element limit**: No more than 7 competing elements above the fold.
- **Preattentive processing**: Length and 2D position communicate quantity fastest.
- **Confirmation patterns**: Financial confirmations must show action + amount + costs + irreversibility.

### Risk Communication
- **Show risk before action**: Every state-changing operation must display what could go wrong.
- **Color semantics**: Green = safe/gain, Red = danger/loss, Amber = warning/review, Blue = information/action.
- **Quantify uncertainty**: Use ranges and confidence intervals, not point estimates.
- **Causes over symptoms**: Explain WHY a position is at risk (oracle dependency, liquidity depth), not just THAT it is.

### Dark Theme Accessibility (WCAG 2.2 AA)
- Body text: minimum 4.5:1 contrast; aim for 7:1 on dark backgrounds.
- Background no darker than `#121212` for text regions (our cards use `#0a101d`).
- Increase font weight in dark mode: 400 → 500 or 600 to fight halation.
- Never use pure red text on dark backgrounds — it fails contrast.
- Chart colors need 3:1 minimum against background.
- Off-white text (`#eef2f9`) over `#04070d` gives ~15:1 — excellent.

## 4. Hero Video Best Practices

### Performance
- Poster-first LCP strategy: static image loads first, video lazy.
- `fetchpriority="high"` on poster image; never `loading="lazy"`.
- Target ≤ 4MB file size for hero video.
- `preload="metadata"` for above-fold video.
- H.264/WebM with aggressive compression.

### Playback
- Required attributes: `muted autoplay loop playsinline`.
- `prefers-reduced-motion: reduce` → show poster only.
- IntersectionObserver to pause when offscreen.
- Play/pause control always available.
- Poster fallback for any video failure.

## 5. Design Decisions for FAULTLINE

### Applied Principles
1. **Cinematic hero, functional product**: The landing creates emotional impact; product screens prioritize clarity.
2. **ARM/DEFEND/PROVE as scroll narrative**: Three-act structure with sticky viewport, scroll-driven transitions.
3. **Data source transparency**: Every number carries its provenance (LIVE / SIMULATED / cached / mock).
4. **Progressive disclosure**: Landing → Demo → Full product. No forced onboarding.
5. **Single typography system**: Archivo (expanded, variable weight) for hierarchy; IBM Plex Mono for data.
6. **Three-color signal system**: `--blue` (#03abfa) for brand/info, `--red` (#ff5d47) for risk/exit, `--mint` (#27b7ff) for defense/stay.
7. **Dark-field design**: `#04070d` base, `#0a101d` cards, `#eef2f9` primary text.
8. **Material identity**: The G4 artifact (machined basalt + blue fault) is the brand centerpiece.
9. **No fake transactions**: CONFIRMED requires receipt + verification. Simulated data always labelled.
10. **Mobile-first data hierarchy**: On mobile, show verdict → key metric → action, hide secondary visualizations.
