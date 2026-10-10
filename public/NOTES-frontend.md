# Frontend shell notes (FaultLine)

## Files owned by the shell
- `index.html` dashboard/landing
- `assets/css/theme.css` design system (variables: --bg, --bg-elev, --card, --border, --text, --muted, --accent, --stay, --exit, --warn, --layer-chain/yield/oracle/amm/lending/position; classes .btn .btn-primary .btn-ghost .card .kpi .badge .badge-stay .badge-exit .badge-warn .table .container .nav .footer .muted .mono)
- `assets/js/api.js` -> `window.FaultLine = { loadData(), fmtUsd, fmtPct, esc, verdictBadge, sourceBadge, LAYER_META }`
  - `loadData()` resolves `{ data, source }` with source = payload.source (`live|cache|mixed|mock|mock-fallback`) or `'demo'`: tries `/api/analyze`, falls back to `/data/sample.json`.
  - `LAYER_META[layer] = { label, short, color (css var), hex }`.
- `assets/js/shell.js` fills `<header id="nav">` and `<footer id="footer">` (use on xray.html too, include after api.js).
- `assets/brand/logo.svg`

## Run
`python -m http.server 8000 -d public` then open http://localhost:8000

## Status
Dashboard complete: verdict, KPIs, top 3 drivers, 5-layer strip, scenarios, book table, methodology. Numbers come from live discovery; the source badge flags cache/MOCK.

## Left / ideas
Favicon is the logo SVG; no OG image. No payload change requests.
