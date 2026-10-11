// Pure view-model for /analyze.html. Every number returned here is a field of the /api/analyze payload; this module
// only selects, classifies, orders and lays out. There is deliberately no loss arithmetic in the browser.

export const BANDS = [
  { key: 'position', label: 'Your position', short: 'Position' },
  { key: 'lending', label: 'Lending market', short: 'L5 Lending' },
  { key: 'amm', label: 'PT market and AMM', short: 'L4 PT market' },
  { key: 'oracle', label: 'Oracle', short: 'L3 Oracle' },
  { key: 'yield', label: 'Yield source and issuer', short: 'L2 Yield source' },
  { key: 'chain', label: 'Settlement chain', short: 'L1 Chain' },
];

/** Which Belem stratum a node belongs to. */
export function bandOf(node, positionId = 'pos') {
  const role = (node.meta && node.meta.role) || '';
  if (node.id === positionId || role === 'position') return 'position';
  if (node.layer === 'lending' || role === 'morpho_blue' || role === 'lending' || role === 'loan_asset') return 'lending';
  if (node.layer === 'amm' || role === 'pendle_core' || role === 'amm') return 'amm';
  if (node.layer === 'oracle' || role === 'oracle' || role === 'feed_provider') return 'oracle';
  if (node.layer === 'chain' || role === 'chain') return 'chain';
  return 'yield';
}

export const ROLE_WORDS = {
  position: 'The analysed position',
  chain: 'Settlement chain',
  issuer: 'Issuer of the yield asset',
  underlying: 'Yield source the PT redeems into',
  backing: 'Backing asset',
  stablecoin: 'Stablecoin the asset is accounted in',
  pendle_core: 'Pendle PT / SY contracts (principal)',
  amm: 'Pendle AMM pool (exit route)',
  oracle: 'Oracle pricing the collateral',
  feed_provider: 'Feed provider behind the oracle',
  lending: 'Morpho market holding the PT',
  morpho_blue: 'Morpho Blue contract (custody)',
  loan_asset: 'Loan asset',
  base_asset: 'Look-through base asset',
  lineage_token: 'Wrapped token in the lineage',
};

export const CHANNEL_WORDS = {
  principal: 'Reaches the value you hold',
  debt: 'Acts only through debt (liquidation)',
  exit: 'Changes only the cost of exiting early',
};

/** The one-sentence decision a judge can read in three seconds. */
export function headline(payload) {
  const d = payload.decision || {};
  const H = (payload.position && payload.position.horizon_days) || d.horizon_days || 30;
  const lb = d.loss_band || {};
  const point = d.point_verdict || d.verdict;
  return {
    verdict: d.verdict,
    lean: d.verdict === 'REVIEW' ? point : null,
    confidence: d.confidence,
    horizon: H,
    stay: { central: d.expected_loss_usd, low: lb.low_usd, high: lb.high_usd },
    exit: { total: d.exit_total_usd, execution: d.exit_cost_usd, carry: d.carry_usd, low: (d.exit_band || {}).low_usd, high: (d.exit_band || {}).high_usd },
    breakeven: d.breakeven_risk_multiplier,
    firm: d.verdict === 'STAY' || d.verdict === 'EXIT',
    reasons: d.reasons || [],
    blockers: (d.freshness && d.freshness.blockers) || [],
    quoteStatus: (d.exit_band || {}).quote_status,
  };
}

/** Log-scale band chart layout: stay band vs exit band on one axis. Returns positions in [0, 1]. */
export function bandLayout(h) {
  const vals = [h.stay.low, h.stay.high, h.stay.central, h.exit.low, h.exit.high, h.exit.total].filter((v) => Number.isFinite(v) && v > 0);
  if (!vals.length) return null;
  const lo = Math.pow(10, Math.floor(Math.log10(Math.min(...vals))));
  const hi = Math.pow(10, Math.ceil(Math.log10(Math.max(...vals))));
  const x = (v) => (Number.isFinite(v) && v > 0 ? (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) : 0);
  const ticks = [];
  for (let t = lo; t <= hi * 1.0001; t *= 10) ticks.push({ v: t, x: x(t) });
  const stay = { a: x(h.stay.low), b: x(h.stay.high), c: x(h.stay.central) };
  const exit = { a: x(h.exit.low), b: x(h.exit.high), c: x(h.exit.total) };
  const ov = [Math.max(stay.a, exit.a), Math.min(stay.b, exit.b)];
  return { stay, exit, ticks, overlap: ov[1] > ov[0] ? ov : null };
}

/** Index server results per node: stress row, uncertainty classes, edges with reach flags. */
export function indexPayload(p) {
  const posId = (p.position && p.position.id) || 'pos';
  const stress = new Map((p.stress_table || []).map((r) => [r.id, r]));
  const unc = new Map(((p.uncertainty && p.uncertainty.nodes) || []).map((n) => [n.id, n]));
  const reach = new Map(((p.uncertainty && p.uncertainty.edges) || []).map((e) => [`${e.src}->${e.dst}`, e.reaches_position]));
  const nodes = (p.nodes || []).map((n) => ({ ...n, band: bandOf(n, posId), hidden: !!(n.meta && n.meta.hidden), stress: stress.get(n.id) || null, unc: unc.get(n.id) || null }));
  const edges = (p.edges || []).map((e) => ({ ...e, reaches: reach.has(`${e.src}->${e.dst}`) ? reach.get(`${e.src}->${e.dst}`) : true }));
  return { posId, nodes, edges, byId: new Map(nodes.map((n) => [n.id, n])) };
}

/** Deterministic strata layout: one row per Belem layer, barycentric ordering inside a row. */
export function strataLayout(index, { width = 900, rowH = 92, top = 46, padX = 150 } = {}) {
  const rows = BANDS.map((b) => ({ ...b, nodes: index.nodes.filter((n) => n.band === b.key) }));
  const pos = new Map();
  const inner = width - padX - 30;
  rows.forEach((r, i) => r.nodes.forEach((n, j) => pos.set(n.id, { x: padX + inner * (j + 0.5) / r.nodes.length, y: top + i * rowH })));
  const nbrs = (id) => index.edges.filter((e) => e.src === id || e.dst === id).map((e) => (e.src === id ? e.dst : e.src));
  for (let pass = 0; pass < 3; pass++) {
    rows.forEach((r, i) => {
      if (i === 0 || r.nodes.length < 2) return;
      const bary = (n) => { const xs = nbrs(n.id).map((m) => pos.get(m)).filter((q) => q && q.y < top + i * rowH).map((q) => q.x); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : pos.get(n.id).x; };
      r.nodes.sort((a, b) => bary(a) - bary(b));
      r.nodes.forEach((n, j) => pos.set(n.id, { x: padX + inner * (j + 0.5) / r.nodes.length, y: top + i * rowH }));
    });
  }
  return { rows, pos, height: top + (rows.length - 1) * rowH + 50, width };
}

/** What the decision rail says when a node is selected: server stress row only. */
export function nodeImpact(node, payload) {
  const r = node.stress;
  const d = payload.decision || {};
  if (!r) return { kind: 'none', text: 'Not reachable from the position in the dependency graph.' };
  const blocked = r.channel && r.channel.blocked_by && r.channel.blocked_by.length ? r.channel : null;
  return {
    kind: blocked ? 'blocked' : 'reaches',
    severity: r.severity,
    transmission: r.transmission,
    loss: r.conditional_loss_usd,
    baseline: d.expected_loss_usd,
    exitSide: r.exit_total_usd,
    verdict: r.verdict_if_shocked,
    path: r.path || [],
    hops: r.hops,
    blockedBy: blocked ? blocked.blocked_by : [],
    note: blocked ? blocked.note : null,
  };
}

/** Book rows with an explicit reason for each backend verdict. Numbers are the backend's, unchanged. */
export function bookRows(book) {
  if (!book || !Array.isArray(book.pockets)) return { rows: [], yieldGain: 0, yieldRows: 0 };
  let yieldGain = 0, yieldRows = 0;
  const rows = book.pockets.map((p) => {
    let reason = 'risk';
    if (p.verdict === 'EXIT' && !p.affected) {
      reason = 'yield';
      yieldRows += 1;
      if (Number(p.exit_total_usd) < 0) yieldGain += -Number(p.exit_total_usd);
    } else if (p.verdict === 'UNKNOWN') reason = 'unknown';
    return { ...p, reason };
  });
  return { rows, yieldGain, yieldRows };
}

/** Exit options over the maturity window, as the backend states them. */
export function maturityView(m) {
  if (!m || m.status !== 'ok') return { applicable: false, reason: (m && m.reason) || 'not available', status: m && m.status, days: m && m.days_to_maturity };
  const by = Object.fromEntries((m.options || []).map((o) => [o.option, o]));
  return { applicable: true, days: m.days_to_maturity, window: m.window, best: m.best_over_window, confidence: m.confidence, exit: by.EXIT, hold: by.HOLD_TO_MATURITY, stay: by.STAY, rule: m.rule, ifAmmFails: m.if_amm_fails };
}

/** Parameter class words for the evidence layer. */
export const CLASS_WORDS = {
  observed: 'observed', calibrated: 'calibrated', 'protocol-derived': 'read from contracts',
  scenario_assumption: 'assumption', not_used: 'not used', unknown: 'unknown',
};
export function isAssumption(node) {
  const u = node && node.unc;
  return !!u && ((u.loss_given_failure && u.loss_given_failure.class === 'scenario_assumption') || (u.p_fail_horizon && u.p_fail_horizon.class === 'scenario_assumption'));
}

/** Sensitivity summary: does any row flip the verdict? */
export function sensitivityView(s) {
  if (!s) return null;
  const all = [...(s.rows || []).map((r) => ({ family: 'Failure probability', setting: `×${r.p_fail_multiplier}`, loss: r.expected_loss_usd, exit: r.exit_total_usd, verdict: r.verdict })),
    ...(s.lgf_rows || []).map((r) => ({ family: 'Loss if it fails', setting: r.setting.split('(')[0].trim(), loss: r.expected_loss_usd, exit: r.exit_total_usd, verdict: r.verdict })),
    ...(s.transmission_rows || []).map((r) => ({ family: 'Transmission', setting: r.setting, loss: r.expected_loss_usd, exit: r.exit_total_usd, verdict: r.verdict }))];
  const verdicts = new Set(all.map((r) => r.verdict));
  return { rows: all, stable: verdicts.size === 1, only: verdicts.size === 1 ? [...verdicts][0] : null, breakeven: s.breakeven_risk_multiplier, note: s.note };
}
