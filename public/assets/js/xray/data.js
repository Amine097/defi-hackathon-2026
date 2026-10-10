const LAYER_ALIAS = {
  chain: 'chain', l1: 'chain', settlement: 'chain',
  yield_source: 'yield', yield: 'yield', issuer: 'yield', asset: 'yield', underlying: 'yield',
  oracle: 'oracle',
  amm: 'amm', dex: 'amm', market: 'amm', liquidity: 'amm',
  lending: 'lending', money_market: 'lending',
  protocol: 'protocol', other: 'protocol', bridge: 'protocol',
  position: 'position', pos: 'position', pocket: 'position',
};

const API_TIMEOUT_MS = 10000;

async function getJson(url, timeout) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, { signal: ctl.signal, cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    if (!j || !Array.isArray(j.nodes) || !Array.isArray(j.edges) || j.error) throw new Error('invalid payload');
    return j;
  } finally {
    clearTimeout(timer);
  }
}

export async function loadPayload() {
  const qs = new URLSearchParams(location.search);
  const src = qs.get('data') || '';
  const tries = [];
  if (src === 'large') tries.push(['/data/sample-large.json', 'demo']);
  else if (src === 'sample') tries.push(['/data/sample.json', 'demo']);
  else {
    const ref = qs.get('ref');
    tries.push([`/api/analyze${ref ? `?ref=${encodeURIComponent(ref)}` : ''}`, 'live']);
  }
  tries.push(['/data/sample.json', 'demo']);
  let lastErr;
  for (const [url, kind] of tries) {
    try {
      return { payload: await getJson(url, API_TIMEOUT_MS), kind, url, src };
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('no data');
}

const num = (v, d = 0) => (Number.isFinite(+v) ? +v : d);

export function normalize(p) {
  const position = Object.assign({ id: 'pos', label: 'Position', chain: '', value_usd: 0, horizon_days: 30, meta: {} }, p.position || {});
  const contrib = p.node_contrib_usd || {};
  const nodes = [];
  const byId = new Map();
  const add = (raw) => {
    if (raw == null || raw.id == null || byId.has(String(raw.id))) return;
    const layerRaw = String(raw.layer || 'protocol').toLowerCase();
    const n = {
      id: String(raw.id),
      label: String(raw.label || raw.id),
      layerRaw,
      layer: LAYER_ALIAS[layerRaw] || 'protocol',
      p_fail: num(raw.p_fail),
      lgf: num(raw.loss_given_failure),
      meta: raw.meta && typeof raw.meta === 'object' ? raw.meta : {},
      contrib: num(contrib[raw.id]),
    };
    nodes.push(n);
    byId.set(n.id, n);
  };
  (p.nodes || []).forEach(add);
  const edges = [];
  for (const e of p.edges || []) {
    if (e == null || e.src == null || e.dst == null || e.src === e.dst) continue;
    for (const id of [e.src, e.dst]) if (!byId.has(String(id))) add({ id, label: id, layer: 'protocol', meta: { placeholder: true } });
    edges.push({ src: byId.get(String(e.src)), dst: byId.get(String(e.dst)), t: Math.max(0, Math.min(1, num(e.transmission, 1))), reason: e.reason || '', meta: e.meta || {} });
  }

  const hasDependents = new Set(edges.map((e) => e.dst.id));
  const hasDeps = new Set(edges.map((e) => e.src.id));
  for (const n of nodes) {
    n.isPos = n.layer === 'position' || n.id === position.id || n.meta.kind === 'position' || n.meta.is_position === true
      || (n.layer === 'protocol' && !hasDependents.has(n.id) && hasDeps.has(n.id) && n.p_fail === 0);
    if (n.isPos) n.layer = 'position';
  }
  if (!nodes.some((n) => n.isPos)) {
    const roots = nodes.filter((n) => !hasDependents.has(n.id) && hasDeps.has(n.id));
    roots.forEach((n) => { n.isPos = true; n.layer = 'position'; });
  }
  const positions = nodes.filter((n) => n.isPos);
  const pockets = (p.book && Array.isArray(p.book.pockets)) ? p.book.pockets : [];
  const decision = Object.assign({ verdict: '', expected_loss_usd: 0, exit_cost_usd: 0, margin_usd: 0, explanation: '' }, p.decision || {});
  const posValue = num(position.value_usd);
  const exitRate = posValue > 0 && decision.exit_cost_usd > 0 ? decision.exit_cost_usd / posValue : 0.011;
  for (const n of positions) {
    const pk = pockets.find((b) => b.label === n.label || b.label === n.id);
    n.value = num(n.meta.value_usd) || (n.id === position.id ? posValue : 0) || num(pk && pk.value_usd) || posValue / positions.length;
    n.exitCostMeta = Number.isFinite(+n.meta.exit_cost_usd) ? +n.meta.exit_cost_usd : null;
  }

  return {
    position, nodes, edges, byId, positions, decision, exitRate,
    scenarios: Array.isArray(p.scenarios) ? p.scenarios : [],
    book: p.book && Array.isArray(p.book.pockets) ? p.book : null,
    totalValue: positions.reduce((s, n) => s + n.value, 0) || posValue,
    horizon: num(position.horizon_days, 30),
  };
}
