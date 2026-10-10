# Dependency Exposure %

**Goal:** calculate what share of the portfolio depends on each node of the graph, by announcing the denominator and avoiding counting the same position twice.

**Code:** `src/defirisk/core/portfolio.py` calculates results per pocket; `public/assets/js/xray/model.js` calculates the dependencies and concentrations presented in the interface.

**Status:** calculations present. Validate weights, portfolio totals and links to actual positions before interpreting a percentage as an observed exposure.
