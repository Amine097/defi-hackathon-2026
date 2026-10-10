# Chain of Blame · P1

**Goal:** trace an incident from the affected dependency to the positions and losses, distinguishing between observed facts, modeled links and hypotheses.

The [blueprint frontend](../../design/frontend.md) offers the view. The existing simulation in `src/defirisk/core/propagation.py` provides part of the propagation mechanism.

**Status:** simulated propagation present; causal attribution of an actual incident not demonstrated.
