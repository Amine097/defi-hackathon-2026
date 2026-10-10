# Dependency Graph

**Goal:** identify and visualize dependencies between a position, its protocols, assets, oracles, markets and blockchain, including indirect relationships.

**Code:** `src/defirisk/discovery.py` builds the graph; `public/assets/js/xray/graph.js` displays it. [Initial mockup](mockup.html).

**Status:** Real-data discovery and graph rendering are implemented. Verify on a real position that each node and edge has an identifiable source; example graphs are not sufficient evidence.
