# STAY / EXIT

**Goal:** compare the estimated loss if the position remains open to the exit cost and explain the recommendation with its assumptions.

**Code:** `src/defirisk/decision.py` calculates the cost and the verdict; `public/assets/js/xray.js` shows the decision and scenarios.

**Status:** decision logic and executable Pendle SDK exit quotes are implemented. When a quote is unavailable, the backend uses a labeled slippage approximation. Verify quote availability and source in the selected real-data case; broader liquidity constraints belong to [Exit Feasibility](../../features/exit-feasibility/README.md).
