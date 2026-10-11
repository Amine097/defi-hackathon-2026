# F. Creative Direction

## F0. Ground truth for the brand

- **Logo** (`public/assets/brand/logo.svg`): a square block split into two bone-white slabs (`#ece9e2`) by a jagged
  signal-red fault (`#ff5b3a`) running top to bottom in four segments. This zigzag is the brand's most ownable shape.
  The current UI does not use it: generic blue `#3b82f6`, blue→purple gradient wordmark, system fonts.
- **Promise:** *When DeFi breaks, FAULTLINE moves first.* Story: STABLE → SIGNAL → PROPAGATION → COUNTERMOVE → PROOF.
- **Separation:** the landing is a cinematic brand experience; the application is a precise financial instrument whose
  hero is the real dependency graph. The landing must not be another node graph (the Claude Design export and the
  earlier icosahedron/basalt composition both were; the owner asked for something more distinctive).

## F1. What the references teach (observed in Chrome, not copied)

| Site | Observed | Principle to extract |
|---|---|---|
| Active Theory | Black screen + dot-matrix loader → the studio mark rendered as a single **glass object** in darkness → camera reveals a teal-graded space, particle dust; one pill nav; scroll = camera travel. 727 KB, 1 WebGL canvas, 2 videos | Make the **logo itself a physical object**; earn the reveal with a quiet first frame; almost no chrome |
| Lusion | Percentage preloader → light page with a **framed 3D stage** of physics-driven glossy objects; huge plain type below. Three.js, ~500 KB | Contain the spectacle in a stage; let type carry the message; tactile physics |
| Atlas Motion | Monochrome macro video (hands, lathe) under **giant staggered type**, grid overlay, micro mono labels; scroll shifts into a **painterly sky**. Three.js + video, 6.2 MB, LCP 2.6 s, honours reduced motion | Typography as architecture; a tonal shift as the story's turn |
| Cuberto | Bold grotesk headline, video in rounded frames, stacked dark cards with soft 3D forms; **no WebGL**, 12 videos, honours reduced motion | Restraint + typographic confidence can feel premium without 3D |
| Bruno Simon | The site is a playable 3D world (car, "click to start"), 7.3 MB | Interaction creates memory — but play must not block a financial task |
| Claude Design export | Voxel terrain + glowing node network, Archivo Expanded + IBM Plex Mono, ARM/DEFEND/PROVE chapters, illustrative numbers; React from unpkg | Good chapter structure; the hero image itself is generic "crypto network" |

Common thread of the best: **one iconic object or one typographic gesture, a patient reveal, scroll as narrative time,
very little UI chrome, and a fallback that still looks designed.**

---

## Direction A — **THE SEAM** (monument and containment)

**Idea.** The FAULTLINE mark becomes a monument: a monolith of honed bone-white stone standing in a dark field. Stress
builds; a hairline appears and races down the stone **along the exact zigzag of the logo**, incandescent red inside.
Just before the halves part, the countermove fires: thin graphite-titanium **staples** shoot across the seam at each
joint of the zigzag and lock it. The red cools to an ember line. The block stands — scarred, contained, whole.

**Hero frame (desktop).** Block right of centre, 60 % of viewport height, low camera angle for monumentality; headline
left in three lines; a hairline chapter rail at the bottom (01 STABLE · 02 SIGNAL · 03 PROPAGATION · 04 COUNTERMOVE ·
05 PROOF). Top bar: logo, *Analyze*, *Countermove*, *Evidence* — nothing else.

**Camera and motion (pinned, ~3 viewport heights of scroll; auto-plays once if the user does not scroll).**
1. *Stable* — slow dolly-in, dust drifting toward the stone, idle breathing light.
2. *Signal* — a hairline at the top edge; rack focus to the fracture tip.
3. *Propagation* — the seam runs down; the camera orbits 25° to reveal the **cross-section: five strata** (chain basalt
   at the base … lending at the top). Small mono labels name each stratum as the seam crosses it — the bridge to the
   app's strata graph.
4. *Countermove* — staples fire in sequence (8–12 frames each, slight overshoot), the seam's light drops from red-hot to
   ember; a low-frequency camera shake settles.
5. *Proof* — a line engraves itself into the stone: `block 26,164,299 · repay 1,447.44 USDC · 15/15 checks ·
   SIMULATED` (values from the recorded run, labelled). CTAs: **Analyze the Belem example** · **See the countermove**.

**Interaction.** The cursor is a stress probe: proximity warms the seam; press-and-hold raises stress until the
staples fire (replayable). Keyboard: Space replays; a visible pause control.

**Material language.** Bone limestone/porcelain `#ece9e2` with `#d8d2c4` occlusion and micro-pitting; carbon void
`#07080a`; emissive signal red `#ff5b3a` with a pale hot core; graphite-titanium staples `#9aa3ad` with tight speculars;
fine film grain. No neon, no chromatic aberration, no glitch.

**Typography.** Display: Archivo variable (wide 112–125, 800) set tight; the seam **cuts through the word FAULTLINE** in
the headline and the two halves are stapled too. Data/receipts: IBM Plex Mono. (Both OFL.)

**Mobile.** Portrait suits the vertical fault: block fills the top 55 %, headline below; the sequence plays once
(≈ 10 s) then rests; scroll steps through chapters as discrete states; touch-drag rotates 15°. Low-power tier: a 6-s
H.264/AV1 loop rendered from the same scene; reduced motion: the final sealed frame as an image.

**Implementation.** Three.js with a custom `ShaderMaterial`: beveled block, crack as a signed-distance polyline (the
logo's zigzag) driving emissive mask and vertex displacement; instanced staples; selective bloom on the red channel,
grain, vignette; GSAP ScrollTrigger owns the timeline (uniforms + camera). Poster rendered from the final frame is the
LCP image; WebGL starts after first paint and only on capable GPUs. Budget ≈ 190 KB gz JS, no textures beyond a
procedural noise and a 256-px environment map.

**Strengths / risks.** Most iconic and closest to the logo; Active-Theory-grade memorability; zero media cost. Requires
real lighting/material craft (the gap between "monument" and "cheap CG" is all in the shading) and GPU tiering on
mobile. Estimated craft time: 1.5–3 focused days for agency quality; a credible first version in ~6–8 h.

---

## Direction B — **SEISMIC LEDGER** (editorial instrument, kinetic typography)

**Idea.** The market is a ledger of fine lines — calm, precise, printed. FAULTLINE is the instrument that reads it. A
seismic event buckles the lines; a rupture opens **along the logo's zigzag through the lines and through the headline
itself** — the letters shear apart along the fault and red light seeps from the seam. Then a vertical scan sweeps the
page: the countermove. The sheared halves are pulled back into register, the lines damp to stillness, and a single red
seam remains with a seismograph trace that prints the proof.

**Hero frame.** A bone-paper page (`#ece9e2`, a deliberate contrast to every dark crypto site) with 300–400 hairlines in
ink `#0b0d11`; the headline *WHEN DEFI BREAKS, FAULTLINE MOVES FIRST.* at 12–16 vw on a Swiss grid; layer names set
like seismogram channels in the left margin (CHAIN · ISSUER · ORACLE · PT MARKET · LENDING); a mono ticker at the foot
prints the event log.

**Motion.** A propagating wavelet from an epicentre (damped), the rupture racing down the zigzag, type shear by the
fault's slip vector, then a scanline "countermove" that re-registers everything (GSAP timeline, 6–9 s). Scroll maps to
readings: *Signal* (first tremor on the ORACLE channel), *Propagation* (waves cross channels in order), *Countermove*
(damping sweep), *Proof* (the trace writes `T+0.0 s oracle −5 % detected · T+2.1 s repay 1,447.44 USDC · CONFIRMED · SIMULATED`).
Cursor: a local tremor that damps out (tactile, Lusion-like, in 2D). Click the headline to replay.

**Material language.** Paper, ink, graphite hairlines (0.5–1 px), red used **only** for the fault; precision instrument
details (tick marks, channel labels, timestamps). Reads as "financial press meets seismology lab": credible, rigorous,
memorable.

**Typography.** Display: a high-contrast grotesk with character (candidates: Schibsted Grotesk, Bricolage Grotesque or
Archivo condensed — OFL); data: IBM Plex Mono. The letter shear is the signature gesture.

**Mobile.** The fault is vertical, so portrait works natively: 120 lines, headline in three lines, rupture straight
through the stack; the full sequence fits one screen; reduced motion shows the settled seismogram with the sealed seam.

**Implementation.** WebGL2 line field (raw WebGL2 or OGL ≈ 25 KB; Three.js `LineSegments` also fine) with per-vertex
displacement in the shader; headline as live text duplicated into two clipped halves (SVG `clipPath` from the zigzag)
for the shear, so it stays selectable and accessible; GSAP for the timeline. No models, no textures, ≈ 60–80 KB gz.
Runs at 60 fps on phones.

**Strengths / risks.** Lowest risk, fastest to production quality, excellent performance and accessibility, unusual in
DeFi. Risk: the ridgeline-lines trope (Joy Division) if under-designed — the zigzag shear, the ledger grid and the
channel labels are what make it ours. Estimated: credible version in ~4–5 h, refined in 1–1.5 days.

---

## F2. The application aesthetic (shared by both directions)

- **Palette:** carbon `#0b0d11`, graphite panels `#14171c`, bone ink `#ece9e2`; **signal red `#ff5b3a` only for
  failure / EXIT / the fault**; contained/STAY mineral teal `#5fd0c4`; REVIEW amber `#f2b441` (always with text, never
  colour alone); LIVE/SIMULATED/etc. as text chips.
- **Hero of the app:** the dependency graph as a **cross-section of five strata** (Belem's layers), position on top;
  failures travel upward as a red fracture along server-computed paths; blocked channels drawn dashed with words.
- **Decision rail:** verdict sentence, two bands on one axis, the flip multiple, one primary action.
- **Motion:** only to explain causality (hop-by-hop propagation, numbers settling, staples on Countermove success);
  nothing idles; everything has a reduced-motion equivalent.

## F3. Production techniques compared (hero)

| Technique | Quality | Performance | Accessibility | Cost | Risk |
|---|---|---|---|---|---|
| Real-time WebGL (Three.js + shaders + GSAP) — A | Highest ceiling; interactive; exact brand geometry; crisp at any size | GPU-dependent; needs tiers + poster LCP | Reduced-motion poster, pause control | $0 media; high craft time | Medium–high |
| 2D WebGL line field + SVG kinetic type — B | High if authored; distinctive | Excellent (60 fps mobile) | Easiest; text stays real text | $0 | Low–medium |
| Generated image-to-video (Kling 3, Veo 3.1, Runway Gen-4.5, Luma Ray, Higgsfield as aggregator) | Photoreal potential; weak control of exact zigzag, typography, timing; artefacts and loop seams | 2–6 MB per rendition; poster required | Easy (pause, poster) | Paid credits; many iterations | Medium; brand drift |
| Pre-rendered 3D sequence (Blender) / scroll-scrubbed frames | Very high | Heavy (frames) or video size | Easy | Needs Blender/motion designer (not installed) | Medium (time) |
| Authored SVG/CSS motion only | Clean | Excellent | Easy | $0 | Low; lower "wow" |

**Asset-generation note.** The Higgsfield CLI works and is signed in, but the visible workspace is the **free plan with
10 credits**, and earlier attempts recorded "only_mcp_usage_on_trial_is_available" for video models. No paid
generation was performed. Best use of generation, if approved later: two or three *texture/plate* studies (stone
macro, ember seam) or an establishing shot for the demo film — not the interactive hero itself.

## F4. Recommendation for approval
Build **Direction B as the shipped hero** (fits the time box, performs everywhere, unmistakably FAULTLINE) **or**
Direction A if the owner accepts the higher craft risk for maximum wow — both share the same app aesthetic. In either
case the same real-time scene renders the 2-minute demo film, so no generated video is required. Decision requested in
[I](I_BLOCKERS_AND_DECISIONS.md).
