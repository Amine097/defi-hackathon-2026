# Exit Feasibility · P2

**Purpose:** estimate whether the position can be exited, taking into account available liquidity, slippage, fees and market conditions.

The [core STAY/EXIT](../../core/stay-exit/README.md) uses an executable Pendle SDK quote where available, with a labeled approximation as fallback. Further liquidity depth, validation and range analysis are proposed in the [Impact Analyzer specification, §8c](../whale-impact/spec.md#8c-making-the-numbers-defensible-and-actionable).

**Status:** executable quote integration is implemented; its availability for a selected live position still needs verification. Full exit feasibility under constrained liquidity is not demonstrated.
