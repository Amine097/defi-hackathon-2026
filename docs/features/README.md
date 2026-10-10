# Additional Features

These modules rely on the [Core Risk Engine](../core/README.md). Their priority is that of the product, without transforming them into additional requirements of the Belem brief.

## P0 — Priority feature

- [Breaking Point](breaking-point/README.md): minimal shock which crosses a liquidation threshold. Specified, dedicated engine not identified.

## P1 — Threat Intelligence

- [Leverage Hunter](leverage-hunter/README.md): highly indebted positions and risk of cascade. Documented proposal.
- [Whale Impact](whale-impact/README.md): large transactions and potential effect on positions. Specified.
- [Chain of Blame](chain-of-blame/README.md): propagation and responsibilities of an incident. Partial simulation present.

## P2 — Action Layer

- [Exit Feasibility](exit-feasibility/README.md): liquidity, slippage and real costs. Executable Pendle quotes exist; broader liquidity analysis is specified.
- [Telegram Ping](telegram-ping/README.md): automatic alerts. Specified.
- [Reaction Window](reaction-window/README.md): reaction time before liquidation under explicit hypotheses. Specified.
