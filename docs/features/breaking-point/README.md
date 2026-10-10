# Breaking Point · P0

**Goal:** determine the smallest shock defined on an input (e.g. the oracle price) that makes a position liquidable. The result must indicate the factor, direction, amplitude and threshold reached.

[Detailed specification](spec.md). The module reuses the [core](../../core/README.md) for impact and decision; it does not replace either the loss calculation or STAY/EXIT.

**State:** specified; dedicated liquidation threshold engine not identified in current code. P0 is a priority of the product roadmap, not an explicit obligation of the Belem brief.
