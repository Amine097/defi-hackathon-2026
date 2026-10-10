# DeFi Hackathon 2026 - Belem Capital track

DeFi risk dependency analyzer: discover a position's dependency graph, simulate failures, output STAY/EXIT.
See `PLAN.md` and `docs/belem.md`.

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
- `app.py` Streamlit UI (D)
- `data/mock_graph.json` fixture so everyone can work in parallel
