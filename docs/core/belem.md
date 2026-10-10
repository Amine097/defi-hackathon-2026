# Belem Capital Track

## DeFi Risk Dependency Challenge

### Prize Pool

| Rank | Prize |
|------|-------|
| 1st | $1,200 USD |
| 2nd | $600 USD |
| 3rd | $300 USD |

## Objective

Build a working DeFi risk analysis system that automatically
discovers the dependencies behind an on-chain position and
estimates the economic impact when a dependency fails.

The system should help portfolio managers answer:

**Is the expected loss from staying in a position greater than
the cost of exiting it?**

## Dependency Discovery

A DeFi position may depend on several layers:

1. Settlement blockchain (Ethereum, Solana, etc.)
2. Underlying assets and yield sources
3. Price oracles
4. Liquidity venues and AMMs
5. Lending markets
6. Other protocols and smart contracts

The system must identify these dependencies and explain
how failures propagate through the dependency graph.

Example: A Pendle PT position can depend on five distinct
layers, including the settlement chain, yield source,
oracle, AMM market, and lending venue.

## Core Requirements

### 1. Dependency Discovery
- Automatically identify dependencies of an on-chain position.
- Construct a dependency graph.
- Identify indirect and hidden dependencies.
- Use real blockchain and protocol data.

### 2. Impact Estimation
- Model security incidents, market disruptions, and technical failures.
- Estimate potential economic losses.
- Analyze failure propagation across dependencies.
- Provide defensible quantitative estimates.

### 3. Decision Support
- Estimate the risk of keeping a position.
- Estimate exit costs, including slippage and execution fees.
- Compare expected loss against exit costs.
- Produce an actionable STAY or EXIT recommendation.
- Explain the assumptions and reasoning.

### 4. Working Demo
- Build a functional prototype.
- Operate on real data.
- Demonstrate at least one realistic risk scenario.
- Show actionable results for a portfolio manager.

## Possible Technical Approaches

- Graph algorithms and dependency analysis
- Monte Carlo simulations
- Statistical risk models
- Agent-based systems
- On-chain data indexing
- Smart contract analysis
- Protocol and oracle monitoring

## Supported Ecosystems

- EVM-compatible chains
- Solana
- Canton
- Tempo
- Other blockchain ecosystems

## Judging Criteria

| Category | Weight |
|----------|--------|
| Dependency discovery | 30% |
| Impact estimation | 30% |
| Decision usefulness | 25% |
| Working demo on real data | 15% |

## Key Success Factors

- Accurate dependency discovery
- Clear explanation of failure propagation
- Quantitative impact estimation
- Defensible assumptions
- Useful STAY/EXIT recommendation
- Working implementation using real data

## Project Status

See the [documentation index](../README.md) for the current P0/P1/P2 roadmap. This file summarizes the challenge brief; it does not certify that the implementation meets it.

## Resources

Challenge brief:
https://drive.google.com/file/d/1EdpG5Cc-IRRKWB-3NlP5Z4UAeTHzeC5z/view
