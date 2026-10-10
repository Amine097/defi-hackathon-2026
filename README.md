# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
See `PLAN.md` and `docs/belem.md`.

## UI direction: Pendle X-Ray node graph
The main view is an interactive node graph (nodes = chain, yield source, oracle, PT market/AMM, lending, position pockets).
Click a node to simulate its failure and watch it propagate; the side panel shows STAY vs EXIT.
Prototype with mock data: `docs/mockups/pendle-xray-node-graph.html` (open in a browser).

## Setup
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env

## Run
    python -m pytest
    streamlit run app.py
    cd src; python -m defirisk.cli

## Layout
- `src/defirisk/models.py` shared schema (Position, Node, Edge, DepGraph)
- `discovery.py` real-data discovery (A) - currently mock
- `propagation.py` graph + Monte Carlo (B/C)
- `decision.py` exit cost + verdict (C)
- `viz.py` node graph rendering (currently pyvis placeholder; target = X-Ray prototype)
- `portfolio.py` book of pockets, one hit, stay vs exit
- `scenarios.py` stress overrides; `http.py` cached API calls
- `app.py` Streamlit UI (D)
- `data/mock_graph.json` fixture so everyone can work in parallel
