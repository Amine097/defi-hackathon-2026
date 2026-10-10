# FAULTLINE · Living structure (feasibility prototype)

Isolated 3D study for the "Specimen / Living structure" direction. Not part of the production frontend; nothing in `public/`, `api/` or `src/` was changed.

## Run it

The page uses ES modules and reads the example data over HTTP, so it must be served from the **repository root**:

    python3 -m http.server 8765        # from the repo root
    # then open http://localhost:8765/docs/design/prototypes/living-structure/index.html

Opening `index.html` with `file://` will not work.

## What is real

- Graph: `public/data/sample.json` (11 nodes, 15 links, saved run of the real pipeline) and `public/data/sample-large.json` (44 nodes, 77 links, synthetic demo book).
- Normalisation, propagation and conditional loss are the **production modules, imported read-only**: `normalize` (`public/assets/js/xray/data.js`), `buildIndex`, `cascade`, `positionLosses` (`public/assets/js/xray/model.js`), and the `fmtUsd` formatter (`public/assets/js/api.js`).
- One body per node, one filament per edge. Height = dependency layer (same order as the production "Layers" view). Body size = `node_contrib_usd`. Filament thickness = edge `transmission`.
- A dependency failure is shown as a failure travelling along edges. It is never presented as a price liquidation.

## Controls

Click a body to select it · "Simulate its failure" · drag to turn · scroll or +/- to zoom · arrow keys turn (canvas focused) · `R` or "Reset view" · `Esc` clears · "List view" gives every dependency as a button (also the fallback when WebGL is unavailable).

## URL parameters (used for the screenshots)

`data=large` · `select=<node id>` · `fail=<node id>` · `at=0..1` (freeze the propagation) · `lite=1` (simplified materials) · `flat=1` (no 3D) · `reduced` (reduced motion) · `perf=1` (measure 240 frames, shown bottom right)

## Files

- `index.html`, `app.js` — the prototype
- `vendor/three.module.min.js` — Three.js r160 (MIT, licence alongside), vendored so there is no build step
- `shots/` — captures at 1440×900, 1366×768 and 390×844

## Known limits

See the Mission 6 report. In short: stylised glass rather than photoreal; the 44-node graph is dense; mobile layout is a first pass; the font is loaded from Google Fonts here and would need self-hosting in production.
