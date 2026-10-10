"""Graph visualization (owner: D). Returns HTML for st.components.v1.html.

TARGET: the "Pendle X-Ray" node graph in docs/mockups/pendle-xray-node-graph.html.
TODO: load that file as a template and inject DepGraph + simulate() output as JSON
(replacing its hardcoded N/E/POS arrays). The pyvis version below is a temporary placeholder.
"""
from .models import DepGraph

COLORS = {"chain": "#6c7a89", "yield_source": "#2ecc71", "oracle": "#f1c40f",
          "amm": "#3498db", "lending": "#9b59b6", "protocol": "#e74c3c"}


def graph_html(g: DepGraph, contrib: dict | None = None) -> str:
    from pyvis.network import Network

    contrib = contrib or {}
    net = Network(height="500px", width="100%", directed=True, bgcolor="#111", font_color="white")
    for n in g.nodes:
        size = 15 + min(40, contrib.get(n.id, 0) / max(g.position.value_usd, 1) * 4000)
        net.add_node(n.id, label=n.label, color=COLORS.get(n.layer, "#999"), size=size,
                     title=f"{n.layer} | p_fail={n.p_fail} | LGF={n.loss_given_failure}")
    for e in g.edges:
        net.add_edge(e.src, e.dst, title=e.reason)
    return net.generate_html()
