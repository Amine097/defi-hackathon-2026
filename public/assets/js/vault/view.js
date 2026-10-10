// Vault Risk Analyzer view model (Phase 1). Pure functions, no DOM: formatting, consistency checks and graph layout.
// Every financial figure comes from the backend payload (faultline.vault/1); nothing here recomputes the decision.
// The consistency check only *verifies* the backend identities and reports a contradiction instead of hiding it.

export const ADDR_RE = /^0x[0-9a-fA-F]{40}$/;

export const fmtUsd = (n) => {
  if (n == null || !Number.isFinite(Number(n))) return '—';
  n = Number(n);
  const a = Math.abs(n), s = n < 0 ? '-' : '';
  if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(2) + 'M';
  if (a >= 1e4) return s + '$' + (a / 1e3).toFixed(1) + 'k';
  if (a >= 1) return s + '$' + Math.round(a).toLocaleString('en-US');
  if (a === 0) return '$0';
  return s + '$' + a.toFixed(2);
};
export const fmtPct = (n, d = 1) => (n == null || !Number.isFinite(Number(n)) ? '—' : (Number(n) * 100).toFixed(d) + '%');
export const fmtNum = (n, d = 2) => (n == null || !Number.isFinite(Number(n)) ? '—'
  : Number(n).toLocaleString('en-US', { maximumFractionDigits: d }));
export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const short = (a) => (a && a.length > 14 ? a.slice(0, 8) + '…' + a.slice(-4) : a || '');

// Form -> query string. The server validates authoritatively; this only catches obvious typos before a 10 s call.
export function buildQuery({ address, value_usd, horizon_days, shock, severity }) {
  const a = String(address || '').trim();
  if (!a) return { error: 'Enter a vault address (0x…) or a Morpho / Etherscan vault link.' };
  const q = new URLSearchParams();
  if (/^https?:\/\//i.test(a)) q.set('url', a);
  else if (ADDR_RE.test(a)) q.set('address', a);
  else return { error: 'An address is 0x followed by 40 hexadecimal characters.' };
  q.set('chain_id', '1');
  if (value_usd !== undefined && value_usd !== '') q.set('value_usd', String(value_usd));
  if (horizon_days !== undefined && horizon_days !== '') q.set('horizon_days', String(horizon_days));
  if (shock) { q.set('shock', shock); if (severity !== undefined && severity !== '') q.set('severity', String(severity)); }
  return { query: q.toString() };
}

const VERDICT_CLS = { STAY: 'stay', EXIT: 'exit', REVIEW: 'warn' };
const COLOUR_OF = { STAY: 'green', EXIT: 'red', REVIEW: 'amber' };
// Feasibilities whose route was SIMULATED for the full amount (ordinary redeem or forceDeallocate multicall).
export const EXECUTABLE = new Set(['full', 'full_via_force_deallocate']);

// Verifies the identities the backend promises (P1-06 "no UI/math contradictions") and returns what to display.
export function verdictView(d) {
  const issues = [];
  const v = d && d.verdict;
  if (!VERDICT_CLS[v]) return { cls: 'warn', label: '—', consistent: false, issues: ['missing verdict'] };
  if (d.colour !== COLOUR_OF[v]) issues.push(`colour ${d.colour} does not match ${v}`);
  const exitSide = d.exit_side_usd, margin = d.margin_usd;
  if (Math.abs(exitSide - (d.execution_cost_usd + d.carry_usd)) > 1e-6 * Math.max(1, Math.abs(exitSide))) issues.push('exit side ≠ execution + carry');
  if (Math.abs(margin - (d.expected_loss_usd - exitSide)) > 1e-6 * Math.max(1, Math.abs(margin))) issues.push('margin ≠ loss − exit side');
  const b = d.comparison_basis;
  if (b && Number.isFinite(b.fraction) && d.position_expected_loss_usd != null
      && Math.abs(d.expected_loss_usd - d.position_expected_loss_usd * b.fraction) > 1e-6 * Math.max(1, d.expected_loss_usd)) {
    issues.push('compared loss ≠ position loss × tranche fraction (mixed basis)');
  }
  const pv = d.point_verdict;
  if ((margin > 0 && pv === 'STAY') || (margin < 0 && pv === 'EXIT')) issues.push(`margin sign contradicts point verdict ${pv}`);
  if (v !== 'REVIEW' && pv !== v) issues.push(`firm ${v} but point verdict ${pv}`);
  if (v === 'EXIT' && !EXECUTABLE.has(d.withdrawal_feasibility)) issues.push('EXIT on a non-full withdrawal');
  if (v === 'REVIEW' && d.confidence !== 'low') issues.push('REVIEW should carry low confidence');
  if (typeof d.explanation === 'string' && !d.explanation.startsWith(v)) issues.push('explanation does not start with the verdict');
  const [ll, lh] = d.loss_band_usd || [], [el, eh] = d.exit_band_usd || [];
  if (v === 'EXIT' && !(ll > eh)) issues.push('EXIT but bands overlap');
  if (v === 'STAY' && !(lh < el)) issues.push('STAY but bands overlap');
  const hint = margin > 0 ? 'staying costs more on central values' : margin < 0 ? 'exiting costs more on central values' : 'break-even';
  return {
    cls: VERDICT_CLS[v], label: v, lean: v === 'REVIEW' ? d.lean : null, point: pv,
    marginText: (margin > 0 ? '+' : '') + fmtUsd(margin), hint,
    basisText: basisText(b),
    consistent: issues.length === 0, issues,
  };
}

// Human label of what the compared figures refer to (the backend decides the basis; this only names it).
export function basisText(b) {
  if (!b || b.kind === 'full_position') return 'whole position';
  if (b.kind === 'executable_tranche') return `executable tranche only (${fmtPct(b.fraction, 1)} = ${fmtUsd(b.usd)}); residual expected loss ${fmtUsd(b.residual_expected_loss_usd)} stays exposed`;
  return 'hypothetical: no exit route confirmed now';
}

// Exit routes as table rows (status / capacity / cost come from the backend simulation, never recomputed here).
export function routeRows(exit) {
  const r = (exit && exit.routes) || {};
  const out = [];
  if (r.ordinary) out.push({ name: 'Ordinary redeem', status: r.ordinary.status, capacity: r.ordinary.capacity_usd,
    gas: r.ordinary.gas && r.ordinary.gas.gas_usd, penalty: 0, confirmed: /^simulated/.test(r.ordinary.status || '') });
  if (r.force_deallocate) out.push({ name: 'forceDeallocate + redeem (multicall)', status: r.force_deallocate.status,
    capacity: r.force_deallocate.capacity_usd, gas: r.force_deallocate.gas && r.force_deallocate.gas.gas_usd,
    penalty: r.force_deallocate.penalty_usd, confirmed: /^simulated/.test(r.force_deallocate.status || '') });
  for (const u of r.unconfirmed || []) out.push({ name: `${u.route} (unconfirmed)`, status: u.status, capacity: u.usd, gas: null, penalty: null, confirmed: false });
  return out;
}

const MODE = {
  live: ['live on-chain', 'stay', 'Fetched now from Ethereum RPC, Morpho API, DefiLlama and Chainlink'],
  mixed: ['live + cache', 'warn', 'Some calls were served from cache'],
  cache: ['cached replay', 'warn', 'Real responses replayed from cache; not fresh'],
  offline: ['offline replay', 'warn', 'Deterministic replay of recorded data; not fresh'],
  mock: ['MOCK', 'exit', 'Not real data'], fallback: ['FALLBACK', 'exit', 'Not real data'],
};
export function modeBadge(mode) {
  const [label, cls, tip] = MODE[mode] || ['unknown source', 'exit', 'The payload did not say where its data came from'];
  return { label, cls, tip };
}

export function errorText(status, body) {
  const e = body && body.error;
  if (e && e.message) return `${e.code || 'error'} (${status}): ${e.message}`;
  if (status === 0) return 'Network error: the API is unreachable. No figures are shown rather than stale ones.';
  return `HTTP ${status}: the analysis failed. No figures are shown rather than unverified ones.`;
}

// Nodes eligible for a custom shock: every dependency the backend returned (it rejects anything else with 400).
export function shockOptions(nodes) {
  return (nodes || []).filter((n) => n.id && n.id !== 'pos').map((n) => ({ id: n.id, label: n.label || n.id, role: n.role }));
}

// Column = shortest hop distance from the depositor ("pos"); rows spread nodes of one column. Deterministic.
export function layoutGraph(nodes, edges, w = 900, h = 420) {
  const ids = ['pos', ...(nodes || []).map((n) => n.id).filter((id) => id !== 'pos')];
  const out = new Map(ids.map((id) => [id, []]));
  for (const e of edges || []) if (out.has(e.src) && out.has(e.dst)) out.get(e.src).push(e.dst);
  const depth = new Map([['pos', 0]]);
  const queue = ['pos'];
  while (queue.length) {
    const id = queue.shift();
    for (const nx of out.get(id)) if (!depth.has(nx)) { depth.set(nx, depth.get(id) + 1); queue.push(nx); }
  }
  let maxD = 0;
  for (const id of ids) { if (!depth.has(id)) depth.set(id, -1); maxD = Math.max(maxD, depth.get(id)); }
  const cols = new Map();
  for (const id of ids) { const dd = depth.get(id) < 0 ? maxD + 1 : depth.get(id); if (!cols.has(dd)) cols.set(dd, []); cols.get(dd).push(id); }
  const nCols = Math.max(...cols.keys()) + 1, pos = {};
  for (const [c, list] of cols) list.forEach((id, i) => {
    pos[id] = { x: 60 + (c * (w - 120)) / Math.max(nCols - 1, 1), y: (h * (i + 1)) / (list.length + 1), depth: depth.get(id) };
  });
  return { pos, unreachable: ids.filter((id) => depth.get(id) < 0) };
}

// Nodes shared by several allocations: the dedup evidence the PM needs ("one oracle behind three markets").
export function sharedDependencies(nodes) {
  return (nodes || []).filter((n) => Array.isArray(n.exposed_allocations) && n.exposed_allocations.length > 1)
    .map((n) => ({ id: n.id, label: n.label, role: n.role, count: n.exposed_allocations.length, usd: n.affected_usd_if_fails }))
    .sort((a, b) => b.count - a.count);
}
