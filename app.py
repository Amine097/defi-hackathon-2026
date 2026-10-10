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

st.subheader("Dependencies")
st.dataframe(pd.DataFrame([n.__dict__ for n in g.nodes]).drop(columns="meta"))
st.subheader("Expected loss by node")
st.bar_chart(pd.Series(sim.node_contrib))
st.subheader("Loss distribution")
st.bar_chart(pd.Series(sim.loss_samples).round(-3).value_counts().sort_index())
# TODO: dependency graph view (pyvis), scenario sliders, assumptions panel
