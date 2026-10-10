# FAULTLINE · Dark spatial intelligence (prototype, Mission 7)

Two visual variants of the same interactive study, sharing one script and the same real data:

- `precision.html` — Variant A, Dark Precision
- `cinematic.html` — Variant B, Dark Cinematic

Isolated from production: nothing in `public/`, `api/` or `src/` is modified. The earlier pale prototype in `../living-structure/` is left intact (this one reuses its vendored Three.js).

## Run

Serve the **repository root** over HTTP (ES modules + data fetch):

    python3 -m http.server 8765
    # http://localhost:8765/docs/design/prototypes/dark-spatial/precision.html
    # http://localhost:8765/docs/design/prototypes/dark-spatial/cinematic.html

## What is real

Graph from `public/data/sample.json` (11 nodes, 15 links) and `sample-large.json` (44 nodes, 77 links, synthetic). Normalisation, propagation, conditional loss, decision view and formatting are the production modules imported read-only (`xray/data.js`, `xray/model.js`, `api.js`).

| Visual property | Payload field |
|---|---|
| Shape and tint | `node.layer` (position, lending, amm, oracle, yield, protocol, chain) |
| Height | the same layer, top to bottom as in the production Layers view |
| Distance from the axis | hops from the position (`reach.minHops`) |
| Body size | `node_contrib_usd` |
| Thick vs thin link | the position holds the link directly vs indirect |
| Link thickness | `edge.transmission` |
| Failed body (solid signal colour) | the node assumed to fail |
| Stressed body (arc around it) | arc length = share of the failure received (`cascade().strength`) |
| Step text | `edge.reason` of the link that carried it |

Dense books: positions plus one aggregate per layer first; selecting a position opens its real subgraph; "Show all N positions on it" expands dependents; a failure shows only what it touches. Aggregates are labelled with their member count and list every member.

## URL parameters

`data=large` · `select=<id>` · `expand` · `group=<layer>` · `fail=<id>` · `at=0..1` · `flat=1` · `reduced` · `perf=1`

`_frame.html?p=precision|cinematic&q=<encoded query>` renders the page in a 390×844 frame (used for the phone captures, because a desktop Chrome window cannot be narrower than about 500 px).
