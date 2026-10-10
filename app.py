"""streamlit run app.py (owner: D)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
import streamlit as st

from defirisk.cli import run

st.title("DeFi Risk Dependency - STAY or EXIT")
g, sim, d = run()

col1, col2, col3 = st.columns(3)
col1.metric("Verdict", d.verdict)
col2.metric("Expected loss", f"${d.expected_loss_usd:,.0f}")
col3.metric("Exit cost", f"${d.exit_cost_usd:,.0f}")
st.write(d.explanation)

import streamlit.components.v1 as components

from defirisk.decision import decide, exit_cost
from defirisk.propagation import simulate
from defirisk.scenarios import SCENARIOS, apply
from defirisk.viz import graph_html

st.subheader("Dependency graph")
components.html(graph_html(g, sim.node_contrib), height=520)

st.subheader("Stress scenarios")
for s in SCENARIOS:
    g2 = apply(g, s)
    d2 = decide(g2, simulate(g2), d.exit_cost_usd)
    st.write(f"**{s.name}** - {s.description}: loss ${d2.expected_loss_usd:,.0f} -> {d2.verdict}")

st.subheader("Portfolio view: 10 pockets x 10%, one affected")
from copy import deepcopy

from defirisk.portfolio import Pocket, evaluate_book

sc = st.selectbox("Scenario hitting pocket P0", SCENARIOS, format_func=lambda s: s.name)
book = st.number_input("Book size (USD)", value=10_000_000, step=1_000_000)
pockets = [Pocket(f"P{i}", 0.1, deepcopy(g)) for i in range(10)]
res = evaluate_book(pockets, book, sc, affected={"P0"})
st.dataframe(pd.DataFrame([r.__dict__ for r in res.pockets]).head(3))  # TODO: full table, pocket-specific graphs
st.write(f"Stay everywhere: ${res.total_stay_loss_usd:,.0f} expected loss. "
         f"Best action per pocket: ${res.total_optimal_usd:,.0f} ({res.pct_of_book:.2%} of book).")

st.subheader("Dependencies")
st.dataframe(pd.DataFrame([n.__dict__ for n in g.nodes]).drop(columns="meta"))
st.subheader("Expected loss by node")
st.bar_chart(pd.Series(sim.node_contrib))
st.subheader("Loss distribution")
st.bar_chart(pd.Series(sim.loss_samples).round(-3).value_counts().sort_index())
# TODO: dependency graph view (pyvis), scenario sliders, assumptions panel
