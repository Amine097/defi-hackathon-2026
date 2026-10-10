const EPS = 1e-12;

export function buildIndex(m) {
  m.out = new Map(m.nodes.map((n) => [n.id, []]));
  m.inc = new Map(m.nodes.map((n) => [n.id, []]));
  for (const e of m.edges) {
    m.out.get(e.src.id).push(e);
    m.inc.get(e.dst.id).push(e);
  }
  m.reach = new Map(m.positions.map((p) => [p.id, bestPaths(m, p.id)]));
  return m;
}

function bestPaths(m, root) {
  const best = new Map([[root, { t: 1, prev: null }]]);
  const stack = [root];
  while (stack.length) {
    const x = stack.pop();
    const bx = best.get(x);
    for (const e of m.out.get(x)) {
      const t = bx.t * e.t;
      const cur = best.get(e.dst.id);
      if (!cur || t > cur.t + EPS) {
        best.set(e.dst.id, { t, prev: e });
        stack.push(e.dst.id);
      }
    }
  }
  const hops = bfs(root, (id) => m.out.get(id).map((e) => e.dst.id));
  for (const [id, b] of best) b.minHops = hops.get(id) ?? 0;
  return best;
}

function bfs(root, next) {
  const d = new Map([[root, 0]]);
  const q = [root];
  for (let i = 0; i < q.length; i++) {
    for (const y of next(q[i])) if (!d.has(y)) { d.set(y, d.get(q[i]) + 1); q.push(y); }
  }
  return d;
}

export function pathTo(m, posId, nodeId) {
  const r = m.reach.get(posId);
  if (!r || !r.has(nodeId)) return [];
  const path = [m.byId.get(nodeId)];
  let b = r.get(nodeId);
  let guard = 0;
  while (b && b.prev && guard++ < 200) {
    path.unshift(b.prev.src);
    b = r.get(b.prev.src.id);
  }
  return path;
}

export function closure(m, id, dir) {
  const adj = dir === 'up' ? (x) => m.out.get(x).map((e) => e.dst.id) : (x) => m.inc.get(x).map((e) => e.src.id);
  return new Set(bfs(id, adj).keys());
}

/** failed: Map(id -> lgf). Strength = max transmission product from any failed root; depth = min hops. */
export function cascade(m, failed, minStrength = 0.02) {
  const s = new Map();
  const via = new Map();
  const stack = [];
  for (const id of failed.keys()) { s.set(id, 1); stack.push(id); }
  while (stack.length) {
    const x = stack.pop();
    for (const e of m.inc.get(x)) {
      const y = e.src.id;
      const ns = s.get(x) * e.t;
      if (ns < minStrength || failed.has(y)) continue;
      if (ns > (s.get(y) || 0) + EPS) { s.set(y, ns); via.set(y, e); stack.push(y); }
    }
  }
  const depth = new Map();
  const q = [];
  for (const id of failed.keys()) { depth.set(id, 0); q.push(id); }
  for (let i = 0; i < q.length; i++) {
    const x = q[i];
    for (const e of m.inc.get(x)) {
      const y = e.src.id;
      if (!s.has(y) || depth.has(y) || s.get(x) * e.t < minStrength) continue;
      depth.set(y, depth.get(x) + 1);
      q.push(y);
    }
  }
  for (const id of s.keys()) if (!depth.has(id)) depth.set(id, 1);
  const edges = [];
  for (const e of m.edges) {
    if (!s.has(e.dst.id) || !s.has(e.src.id) || failed.has(e.src.id)) continue;
    if (s.get(e.dst.id) * e.t < minStrength) continue;
    edges.push({ e, from: depth.get(e.dst.id), to: depth.get(e.src.id), main: via.get(e.src.id) === e });
  }
  const events = [...s.keys()]
    .map((id) => ({ node: m.byId.get(id), depth: depth.get(id), strength: s.get(id), via: via.get(id) || null, root: failed.has(id) }))
    .sort((a, b) => a.depth - b.depth || b.strength - a.strength);
  return { strength: s, depth, edges, events, maxDepth: Math.max(0, ...depth.values()) };
}

/** Exit side of the STAY/EXIT comparison = execution cost + carry forgone (same basis as the backend verdict).
 *  exitOverride = what-if execution rate (fraction of value); carry is still added. */
export function exitCostOf(m, p, exitOverride) {
  const carry = p.value * (m.carryRate || 0);
  if (exitOverride != null) return p.value * exitOverride + carry;
  if (p.exitCostMeta != null) return p.exitCostMeta + carry;
  if (p.id === m.position.id && m.decision.exit_total_usd > 0) return m.decision.exit_total_usd;
  if (p.id === m.position.id && m.decision.exit_cost_usd > 0) return m.decision.exit_cost_usd + carry;
  return p.value * m.exitRate + carry;
}

/** Pure presentation of the headline signal, so numbers, colour and wording always agree with the verdict.
 *  margin = central loss - exit side (incl. carry); > 0 = staying costs more. REVIEW is never shown as a firm call. */
export function decisionView(d) {
  const verdict = d.verdict || '';
  const stay = +d.expected_loss_usd || 0;
  const exec = +d.exit_cost_usd || 0;
  const carry = d.carry_usd != null ? +d.carry_usd : 0;
  const exit = d.exit_total_usd != null ? +d.exit_total_usd : exec + carry;
  const margin = stay - exit;
  const point = d.point_verdict || (margin > 0 ? 'EXIT' : 'STAY');
  const side = margin > 0 ? 'stay costs more' : 'exit costs more';
  let cls, hint;
  if (verdict === 'REVIEW') {
    cls = 'warn';
    hint = `central values only · bands overlap or inputs not firm · lean ${point}`;
  } else {
    cls = verdict === 'EXIT' ? 'bad' : 'good';
    hint = side;
  }
  const consistent = point === (margin > 0 ? 'EXIT' : 'STAY') && (verdict === 'REVIEW' || verdict === point);
  return { verdict, point, stay, exec, carry, exit, margin, cls, hint, consistent };
}

/** Conditional loss per position if all `failed` nodes fail for sure. */
export function positionLosses(m, failed, exitOverride) {
  const rows = m.positions.map((p) => {
    const r = m.reach.get(p.id);
    let surv = 1;
    let hops = Infinity;
    const drivers = [];
    for (const [id, lgf] of failed) {
      const b = r.get(id);
      if (!b || id === p.id) continue;
      const h = Math.max(0, Math.min(1, lgf * b.t));
      surv *= 1 - h;
      hops = Math.min(hops, b.minHops);
      drivers.push({ id, h, t: b.t });
    }
    const loss = p.value * (1 - surv);
    const exit = exitCostOf(m, p, exitOverride);
    return { p, loss, exit, exposed: drivers.length > 0, hops, drivers, verdict: loss > exit ? 'EXIT' : 'STAY' };
  });
  const exposed = rows.filter((r) => r.exposed);
  const sum = (arr, f) => arr.reduce((a, r) => a + f(r), 0);
  return {
    rows, exposed,
    stay: sum(exposed, (r) => r.loss),
    exit: sum(exposed, (r) => r.exit),
    optimal: sum(exposed, (r) => Math.min(r.loss, r.exit)),
    exits: exposed.filter((r) => r.verdict === 'EXIT'),
  };
}

export function concentration(m) {
  const total = m.totalValue || 1;
  const sumContrib = m.nodes.reduce((a, n) => a + (n.isPos ? 0 : n.contrib), 0) || 1;
  const list = [];
  for (const n of m.nodes) {
    if (n.isPos) continue;
    const deps = m.positions.filter((p) => m.reach.get(p.id).has(n.id));
    if (!deps.length) continue;
    const direct = deps.filter((p) => m.out.get(p.id).some((e) => e.dst === n));
    const indirect = deps.filter((p) => !direct.includes(p));
    const value = deps.reduce((a, p) => a + p.value, 0);
    const minHops = Math.min(...deps.map((p) => m.reach.get(p.id).get(n.id).minHops));
    list.push({ n, deps, direct, indirect, value, share: value / total, elShare: n.contrib / sumContrib, minHops });
  }
  list.sort((a, b) => b.share - a.share || b.elShare - a.elShare);

  const insights = [];
  const seen = new Set();
  const ranked = [...list].filter((c) => c.indirect.length).sort((a, b) => (b.indirect.length * (0.2 + b.elShare)) - (a.indirect.length * (0.2 + a.elShare)));
  for (const c of ranked) {
    if (insights.length >= 4) break;
    const p = c.indirect.find((x) => !seen.has(x.id)) || c.indirect[0];
    const path = pathTo(m, p.id, c.n.id);
    if (path.length < 3) continue;
    seen.add(p.id);
    insights.push({ c, p, via: path.slice(1, -1), hops: path.length - 1 });
  }
  return { list, insights, sumContrib };
}

/** EL(p) = base + p * L where L is the conditional loss if `node` fails. */
export function breakEven(m, node, lgf, exitTotal) {
  let exposedValue = 0;
  const L = m.positions.reduce((a, p) => {
    const b = m.reach.get(p.id).get(node.id);
    if (b) exposedValue += p.value;
    return a + (b ? p.value * lgf * b.t : 0);
  }, 0);
  const share = m.totalValue > 0 ? exposedValue / m.totalValue : 1;
  const base = Math.max(0, (m.decision.expected_loss_usd || 0) - node.contrib) * share;
  const pStar = L > 0 ? (exitTotal - base) / L : Infinity;
  return { L, base, exit: exitTotal, pStar };
}
