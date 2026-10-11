// FAULTLINE prototype data. Every figure is copied from a recorded backend artifact in the repo:
// public/data/sample.json (live /api/analyze run, block 26,162,781), docs/core/BELEM_PHASE05_EVIDENCE.json,
// data/fixtures/vault_0xd6d4…_1m.json (live /api/vault run, block 26,164,196),
// data/countermove/demo/latest/summary.json (local Anvil fork run, scenarios S1–S4).
window.FL = (function () {
  const POS = {
    pt: {
      id: 'pt', kind: 'pt', name: 'PT-reUSD-10DEC2026', sub: 'Pendle PT collateral market on Morpho Blue · USDC',
      protocol: 'Morpho Blue · Pendle', network: 'Ethereum', ident: 'Market 0x1e9d6146…fc64',
      identFull: '0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64',
      size: '$1,000,000 hypothetical PT exposure, unlevered', assets: 'PT-reUSD-10DEC2026 · SY-reUSD · reUSD · USDC',
      source: 'RECORDED LIVE RUN', sourceNote: 'Ethereum block 26,162,781 · /api/analyze', verdict: 'REVIEW', graph: true,
      can: [['Analyze', 'Yes'], ['Simulate attack', 'Yes'], ['Arm protection', 'Not applicable: no debt']]
    },
    vault: {
      id: 'vault', kind: 'vault', name: 'Belem RWA EURCV', sub: 'Morpho Vault V2 · asset EURCV · 6 markets',
      protocol: 'Morpho Vault V2', network: 'Ethereum', ident: 'Vault 0xD6d4…48Ec',
      identFull: '0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec',
      size: '$1,000,000 hypothetical deposit', assets: 'rwaEURCV shares · EURCV',
      source: 'RECORDED LIVE RUN', sourceNote: 'Ethereum block 26,164,196 · /api/vault', verdict: 'REVIEW', graph: false,
      can: [['Analyze', 'Yes'], ['Simulate attack', 'Vault scenarios (not wired in prototype)'], ['Arm protection', 'Not applicable: deposit']]
    },
    borrow: {
      id: 'borrow', kind: 'borrow', name: 'Borrower 0xAa34…5Dd5', sub: 'Real borrower on the PT-reUSD / USDC Morpho market',
      protocol: 'Morpho Blue · Pendle', network: 'Ethereum', ident: 'borrower=auto · 0xAa34d20b…5Dd5',
      identFull: '0xAa34d20b…5Dd5',
      size: '$12.17M PT collateral with USDC debt', assets: 'PT-reUSD-10DEC2026 collateral · USDC debt',
      source: 'RECORDED LIVE RUN', sourceNote: 'Phase 0.5 evidence · /api/analyze?borrower=auto', verdict: 'REVIEW', graph: true,
      can: [['Analyze', 'Yes'], ['Simulate attack', 'Yes (losses for $1M unlevered)'], ['Arm protection', 'Policy preview only']]
    },
    fork: {
      id: 'fork', kind: 'fork', name: 'S1 · weETH / USDC borrow', sub: 'Test position on a local Anvil fork of Ethereum',
      protocol: 'Morpho Blue (forked) · RescueVault', network: 'Local fork · chain 31337', ident: 'Fork user A 0x3C44…93BC',
      identFull: '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC',
      size: '10 weETH collateral · 20,838.10 USDC debt', assets: 'weETH collateral · USDC debt · test funds',
      source: 'LOCAL FORK', sourceNote: 'Forked at block 26,164,248 · test funds', verdict: 'WATCHING', graph: false,
      can: [['Analyze', 'Countermove engine'], ['Simulate attack', 'Replay recorded incident'], ['Arm protection', 'Fork demonstration']]
    }
  };

  const NODES = [
    { id: 'pos', layer: 0, x: 70, y: 260, label: 'Your position', short: 'POSITION', hidden: false },
    { id: 'lending', layer: 5, x: 250, y: 330, label: 'Morpho market PT-reUSD / USDC', short: 'Morpho market', hidden: false, p: 0.000196, lgf: 0.7, contrib: 137.2, sev: 0.7, T: 1.0, path: ['pos', 'lending'], cond: 700456, role: 'Lending market holding the PT as collateral', why: 'Liquidations and borrow limits run here. LLTV 91.5%, 88.1% utilized, $14.3M available liquidity, no bad debt.' },
    { id: 'morpho', layer: 5, x: 250, y: 455, label: 'Morpho Blue (protocol)', short: 'Morpho Blue', hidden: true, p: 0.000196, lgf: 0.7, contrib: 96.04, sev: 0.7, T: 0.7, path: ['pos', 'lending', 'morpho'], cond: 490796, role: 'Singleton lending contract behind every Morpho market', why: 'The market is a Morpho Blue singleton market. TVL $11.2B, 2 audits.' },
    { id: 'amm', layer: 4, x: 430, y: 165, label: 'Pendle market PT-reUSD-10DEC2026', short: 'Pendle AMM', hidden: false, p: 0.000393, lgf: 0.6, contrib: 235.8, sev: 0.6, T: 1.0, path: ['pos', 'amm'], cond: 600569, role: 'PT market and AMM curve: the exit route', why: 'The position exits through this pool. $12.41M liquidity, PT implied APY 11.79%, expires 10 Dec 2026.' },
    { id: 'oracle', layer: 3, x: 610, y: 330, label: 'Morpho oracle (ChainlinkOracleV2)', short: 'PT oracle', hidden: true, p: 0.000442, lgf: 0.4, contrib: 141.44, sev: 0.4, T: 0.8, path: ['pos', 'lending', 'oracle'], cond: 321031, role: 'Prices the PT for the lending market', why: 'Single price feed, computed on read, no heartbeat or staleness guard. It reads the Pendle market.' },
    { id: 'feed', layer: 3, x: 610, y: 455, label: 'Ojo (feed provider)', short: 'Ojo feed', hidden: true, p: 0.000442, lgf: 0.4, contrib: 127.3, sev: 0.4, T: 0.72, path: ['pos', 'lending', 'oracle', 'feed'], cond: 289090, role: 'Feed provider behind the oracle', why: 'Ojo prices 2 of 12 Morpho PT markets, about 59% of their supply.' },
    { id: 'underlying', layer: 2, x: 800, y: 165, label: 'reUSD (yield source)', short: 'reUSD', hidden: true, p: 0.000412, lgf: 0.5, contrib: 185.4, sev: 0.5, T: 0.9, path: ['pos', 'amm', 'underlying'], cond: 450810, role: 'Yield-bearing asset wrapped by the PT', why: '0% of the PT is traced to base assets: reUSD does not publish its reserve split.' },
    { id: 'issuer', layer: 2, x: 800, y: 55, label: 're.xyz (issuer)', short: 're.xyz', hidden: true, p: 0.000412, lgf: 0.6, contrib: 177.98, sev: 0.6, T: 0.72, path: ['pos', 'amm', 'underlying', 'issuer'], cond: 432840, role: 'Issuer and manager of reUSD', why: 'TVL $406M, 2 audits, listed for under a year. Yield comes from off-chain reinsurance.' },
    { id: 'usd_usdc', layer: 2, x: 800, y: 290, label: 'USDC (stablecoin)', short: 'USDC', hidden: true, p: 0.01549, lgf: 0.0389, contrib: 433.84, sev: 0.0389, T: 0.72, path: ['pos', 'amm', 'underlying', 'usd_usdc'], cond: 29198, role: 'Accounting asset of reUSD and loan asset of the market', why: 'Severity is the measured mean depth of past USDC depegs (3.9%, low $0.961).' },
    { id: 'base', layer: 2, x: 800, y: 410, label: 'US dollars (bank / T-bills)', short: 'USD reserves', hidden: true, p: 0, lgf: 0.3, contrib: 0, sev: 0.3, T: 0.72, path: ['pos', 'amm', 'underlying', 'usd_usdc', 'base'], cond: 217299, role: 'Base asset, found by look-through', why: 'Failure probability is 0 here because the parent tokens already carry this risk. Shocking it is a what-if only.' },
    { id: 'chain', layer: 1, x: 915, y: 300, label: 'Ethereum', short: 'Ethereum', hidden: true, p: 0.000412, lgf: 0.3, contrib: 123.6, sev: 0.3, T: 1.0, path: ['pos', 'amm', 'chain'], cond: 301074, role: 'Settlement chain', why: 'Both the Pendle market and the Morpho market settle here.' }
  ];

  const EDGES = [
    ['pos', 'amm', 1.0, 'Holds the PT; exits through the Pendle AMM'],
    ['pos', 'lending', 1.0, 'PT posted as collateral on Morpho'],
    ['amm', 'underlying', 0.9, 'SY wraps reUSD'],
    ['underlying', 'issuer', 0.8, 'reUSD is issued and managed by re.xyz'],
    ['underlying', 'usd_usdc', 0.8, 'reUSD is accounted in and redeemable for USDC'],
    ['lending', 'oracle', 0.8, 'Liquidations and borrow limits use this oracle'],
    ['oracle', 'amm', 0.7, 'The feed reads the Pendle market'],
    ['oracle', 'feed', 0.9, 'Price comes from the Ojo feed'],
    ['feed', 'chain', 0.5, 'The feed publishes on Ethereum'],
    ['lending', 'morpho', 0.7, 'The market is a Morpho Blue singleton market'],
    ['lending', 'usd_usdc', 0.3, 'Market liquidity is denominated in USDC'],
    ['amm', 'chain', 1.0, 'Settles on Ethereum'],
    ['lending', 'chain', 1.0, 'Settles on Ethereum'],
    ['underlying', 'base', 0.5, 'Reserve share unknown; 0.5 is an animation weight, not a data point'],
    ['usd_usdc', 'base', 1.0, 'Cash and short-dated US Treasuries held for USDC']
  ];

  const COLS = [
    { x: 70, label: 'POSITION' }, { x: 250, label: '05 LENDING' }, { x: 430, label: '04 PT / AMM' },
    { x: 610, label: '03 ORACLE' }, { x: 800, label: '02 YIELD / ISSUER' }, { x: 915, label: '01 CHAIN' }
  ];

  const SCEN = [
    { id: 'depeg', name: 'Underlying depeg', desc: 'reUSD loses 30% of its value', targets: ['underlying'], sev: '0.30', loss: 271075, exec: 1316, carry: 3680, exit: 4996, mult: 54.3 },
    { id: 'oracle', name: 'Oracle failure', desc: 'The PT oracle misprices collateral (severity 0.40, node default)', targets: ['oracle'], sev: '0.40', loss: 321031, exec: 1316, carry: 3680, exit: 4996, mult: 64.3 },
    { id: 'liq', name: 'Liquidity crisis', desc: 'Pendle AMM impaired (0.50) and exit liquidity halves', targets: ['amm'], sev: '0.50', loss: 500711, exec: 2631, carry: 3680, exit: 6311, mult: 79.3 },
    { id: 'corr', name: 'Correlated stress', desc: 'Depeg, oracle failure and AMM impairment together', targets: ['underlying', 'amm', 'oracle'], sev: '0.30 · 0.50 · 0.40', loss: 752072, exec: 2631, carry: 3680, exit: 6311, mult: 119.2 }
  ];

  const REPLAY = [
    { t: 'T0', title: 'Stable position', block: '26,164,282', chip: 'FORK STATE', body: 'User A borrows 20,838.10 USDC against 10 weETH. LTV 75.00%. The owner armed a policy that triggers at 82%; the market liquidates at 86%. The RescueVault holds 5,000 USDC and 0.05 weETH.', ltv: '75.00%', debt: '20,838.10', reserve: '5,000.00', state: 'WATCHING', nodes: {}, edges: {} },
    { t: 'T1', title: 'A dependency deteriorates', block: 'before 26,164,284', chip: 'SIMULATED SHOCK', body: 'The weETH/ETH exchange-rate feed is replaced on the fork with a value 9.00% lower (anvil_setCode). This did not happen on mainnet.', ltv: '75.00%', debt: '20,838.10', reserve: '5,000.00', state: 'WATCHING', nodes: { feed: 'threat' }, edges: {} },
    { t: 'T2', title: 'The signal propagates', block: '26,164,284', chip: 'MODELLED', body: 'The Morpho oracle composes the shocked feed, so the collateral price falls 9.00% and LTV reaches 82.42%. Countermove also tests a further 8% ETH/USD drop: LTV would be 89.60%, above the 86% LLTV, with a buffer of −836.65 USDC.', ltv: '82.42%', debt: '20,838.10', reserve: '5,000.00', state: 'WATCHING', nodes: { feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', ethusd: 'hypo' }, edges: { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'ethusd-oracle': 'hypo' } },
    { t: 'T3', title: 'FAULTLINE detects the risk', block: '26,164,284', chip: 'FORK OBSERVATION', body: 'The keeper reads the position on-chain: LTV 82.42% is above the 82.00% trigger the owner set, and the follow-on scenario is liquidatable. State moves to DETECTED.', ltv: '82.42%', debt: '20,838.10', reserve: '5,000.00', state: 'DETECTED', nodes: { feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', ethusd: 'hypo', keeper: 'defense' }, edges: { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'ethusd-oracle': 'hypo', 'keeper-pos': 'defense' } },
    { t: 'T4', title: 'The decision engine evaluates actions', block: '26,164,284', chip: 'MODEL DECISION', body: 'REPAY 1,086.50 USDC is the smallest amount that keeps at least 250 USDC of buffer in every scenario. TOP_UP is rejected: the reserve holds 0.05 weETH of the 0.543 needed. FULL_REPAY is rejected: 5,000 USDC is less than the 20,838.10 debt. 5 of 5 pre-send checks pass.', ltv: '82.42%', debt: '20,838.10', reserve: '5,000.00', state: 'PLANNING → VALIDATING', nodes: { feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', keeper: 'defense', vault: 'defense' }, edges: { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'keeper-vault': 'defense' } },
    { t: 'T5', title: 'The defense is executed', block: '26,164,285', chip: 'FORK CONFIRMED', body: 'The keeper calls executeRepay on the RescueVault. Tx 0x4b9254eb…387e2, status 1, 306,222 gas. The user signed nothing during the crisis.', ltv: '78.12%', debt: '19,751.60', reserve: '3,913.50', state: 'EXECUTING → CONFIRMED', nodes: { feed: 'threat', oracle: 'threat', keeper: 'defense', vault: 'defense', market: 'defense', pos: 'defense' }, edges: { 'feed-oracle': 'threat', 'keeper-vault': 'defense', 'vault-market': 'defense', 'market-pos': 'defense' } },
    { t: 'T6', title: 'Proof and outcome', block: '26,164,288', chip: 'VERIFIED ON FORK', body: 'Verified from the receipt and events: RescueExecuted emitted, action id and strategy match the plan, the reserve fell by exactly 1,086.50 USDC, Morpho logged a Repay on behalf of the user. Under the −8% follow-on the LTV would now be 84.93%, below the 86% LLTV.', ltv: '78.12%', debt: '19,751.60', reserve: '3,913.50', state: 'WATCHING', nodes: { feed: 'threat', pos: 'defense', vault: 'defense' }, edges: {} }
  ];

  const RNODES = [
    { id: 'feed', x: 90, y: 90, label: 'weETH / ETH feed', sub: 'shocked −9.00%' },
    { id: 'ethusd', x: 90, y: 250, label: 'ETH / USD feed', sub: 'follow-on −8% (hypothesis)' },
    { id: 'oracle', x: 300, y: 170, label: 'Morpho oracle', sub: 'weETH / USDC' },
    { id: 'market', x: 510, y: 170, label: 'Morpho market', sub: 'LLTV 86%' },
    { id: 'pos', x: 740, y: 170, label: 'Position · user A', sub: '10 weETH · USDC debt' },
    { id: 'keeper', x: 740, y: 300, label: 'Keeper (off-chain)', sub: 'test account #1' },
    { id: 'vault', x: 510, y: 300, label: 'RescueVault', sub: 'owner-funded reserve' }
  ];
  const REDGES = [['feed', 'oracle'], ['ethusd', 'oracle'], ['oracle', 'market'], ['market', 'pos'], ['keeper', 'pos'], ['keeper', 'vault'], ['vault', 'market']];

  const ACTIVITY = [
    { id: 'a1', kind: 'analysis', title: 'Analysis · $1M PT-reUSD-10DEC2026', meta: 'Ethereum block 26,162,781', status: 'RECORDED LIVE RUN', result: 'REVIEW · lean STAY', fields: [['Expected loss', '$1,657 ($171 to $27,532)'], ['Exit side', '$4,996 = $1,316 + $3,680 carry'], ['Exit quote', 'Pendle SDK, simulated eth_call at block 26,162,782'], ['Freshness', 'fresh at capture'], ['Artifact', 'public/data/sample.json']] },
    { id: 'a2', kind: 'analysis', title: 'Analysis · Belem RWA EURCV vault, $1M', meta: 'Ethereum block 26,164,196', status: 'RECORDED LIVE RUN', result: 'REVIEW · point STAY', fields: [['Expected loss', '$632'], ['Exit side', '$2,150'], ['Withdrawal', 'Full via force-deallocate, penalty 0 (simulated eth_call)'], ['Sources', '113 live reads, 0 cached'], ['Artifact', 'data/fixtures/vault_0xd6d4…_1m.json']] },
    { id: 'a3', kind: 'analysis', title: 'Analysis · borrower 0xAa34…5Dd5', meta: 'Ethereum mainnet · Phase 0.5', status: 'RECORDED LIVE RUN', result: 'REVIEW · HF 1.054', fields: [['Distance to liquidation', '5.16%'], ['P(liquidation)', '0.34%'], ['Reason', 'Distance below 10%; PT volatility not modelled'], ['Artifact', 'docs/core/BELEM_PHASE05_EVIDENCE.json']] },
    { id: 'f1', kind: 'fork', title: 'Fork execution S1 · REPAY 1,086.50 USDC', meta: 'Fork block 26,164,285 · chain 31337', status: 'FORK CONFIRMED', result: 'CONFIRMED', tx: '0x4b9254ebda91ddc69a362ebf2b8d88ddb19320f55f507b46b62974b3a51387e2', fields: [['Shock', 'weETH/ETH feed −9.00% (simulated)'], ['LTV', '82.42% → 78.12%'], ['Reserve', '5,000.00 → 3,913.50 USDC'], ['Signed by', 'keeper; no user signature'], ['Verification', '8 checks passed from receipt and events']] },
    { id: 'f2', kind: 'fork', title: 'Fork execution S2 · TOP_UP cbBTC', meta: 'Fork · chain 31337', status: 'FORK CONFIRMED', result: 'CONFIRMED', tx: '0x7ccb73ccc688c2f5414316655a3112b50e8a8f45cbf03d97bf6291e08bca9050', fields: [['Position', 'user B · cbBTC / USDC · cbBTC reserve'], ['Shock', 'BTC feed −9.00% (simulated)']] },
    { id: 'f3', kind: 'fork', title: 'Fork run S3 · no action', meta: 'Fork · chain 31337', status: 'FORK CONFIRMED', result: 'NO_ACTION', fields: [['Position', 'user C · weETH / USDC · tiny reserves, full repay disabled'], ['Outcome', 'No strategy was fundable inside the policy, so nothing was sent']] },
    { id: 'f4', kind: 'fork', title: 'Fork execution S4 · FULL_REPAY', meta: 'Fork · chain 31337', status: 'FORK CONFIRMED', result: 'CONFIRMED', tx: '0xeea9ca52ce4919469bfb9ceaa7ad4209694eb37da986410ea77b765effa6aee5', fields: [['Position', 'user D · cbBTC / USDC · policy: close the debt']] },
    { id: 'h1', kind: 'history', title: 'Validation · real Morpho liquidation', meta: 'Mainnet block 25,829,913', status: 'MAINNET CONFIRMED', result: 'Formula matched', tx: '0x906a5315…e0d', fields: [['What it is', 'A third-party liquidation used to check the liquidation model. Not a FAULTLINE transaction.'], ['HF one block earlier', '0.9977'], ['Seized amount error', '4.2e-11 relative']] },
    { id: 'h2', kind: 'history', title: 'Historical replay · USDC depeg (SVB)', meta: 'Cutoff 2023-03-11', status: 'HISTORICAL DATA', result: 'No look-ahead', fields: [['What it is', 'The risk priors rebuilt with data available before the event. A model check, not a protection event.'], ['Daily close 2023-03-12', '$0.961'], ['Limit', 'Intraday low not in the dataset'], ['Artifact', 'data/fixtures/replay_h04.json']] }
  ];

  return { POS, NODES, EDGES, COLS, SCEN, REPLAY, RNODES, REDGES, ACTIVITY };
})();
