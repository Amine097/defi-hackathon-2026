// Vault intelligence presentation helpers. Pure functions, no DOM: plain-language labels for backend enums,
// sentences assembled from decision fields, the dependency-map layout and small SVG charts.
// Nothing here computes a financial result: every amount shown is read from the faultline.vault/1 payload.
import { esc, usd, usdFull, pct, num, short, dateTime } from '../core/format.js';
import { layoutGraph } from './view.js';

export const EXAMPLES = [
  { address: '0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec', name: 'Belem RWA EURCV', version: 'Morpho V2', asset: 'EURCV', note: 'Belem sponsor vault' },
  { address: '0xc207d3f66537D7F66456808379A0E560cF20Da36', name: 'RockawayX Confidential RWA USDC', version: 'Morpho V2', asset: 'USDC' },
  { address: '0xE0181090c22579B6A217f1522cbf8c9f1F0C1965', name: 'RockawayX USDC Yield', version: 'Morpho V2', asset: 'USDC' },
  { address: '0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB', name: 'Steakhouse USDC', version: 'Morpho V1', asset: 'USDC' },
];

export const etherscan = (addr) => `https://etherscan.io/address/${encodeURIComponent(addr)}`;
export const etherscanBlock = (b) => `https://etherscan.io/block/${encodeURIComponent(b)}`;
const ok = (n) => n != null && n !== '' && Number.isFinite(Number(n));

/** Dollar amounts: exact to the dollar (cents under $100), compact from $1M. */
export const money = (n) => (ok(n) && Math.abs(Number(n)) >= 1e6 ? usd(n) : usdFull(n));

/** ×3.22, ×56, ×0.001: enough digits to be meaningful at any magnitude. */
export function multiple(m) {
  if (!ok(m)) return '—';
  m = Number(m);
  if (m >= 10) return `×${m.toFixed(0)}`;
  if (m >= 1) return `×${m.toFixed(2)}`;
  return `×${Number(m.toPrecision(2))}`;
}
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');
const sentence = (s) => { s = cap(String(s || '').trim()); return s && !/[.!?]$/.test(s) ? s + '.' : s; };

// ---------- plain labels for backend enums (the raw value stays available as a tooltip) ----------
const FEAS = {
  full: { label: 'Full exit through ordinary withdrawal', short: 'all', tone: 'stay' },
  full_via_force_deallocate: { label: 'Full exit possible only through forceDeallocate', short: 'all, with forceDeallocate', tone: 'review' },
  partial: { label: 'Only part can be withdrawn now', short: 'part', tone: 'review' },
  zero: { label: 'Nothing can be withdrawn now', short: 'none', tone: 'exit' },
  unknown: { label: 'Withdrawal could not be confirmed', short: 'unconfirmed', tone: 'neutral' },
};
export function feasibility(f) {
  const x = FEAS[f] || { label: f ? `Withdrawal status: ${f}` : 'Withdrawal status unknown', short: f || 'unknown', tone: 'neutral' };
  return { ...x, raw: f || 'null' };
}

const ROUTE = {
  ordinary: 'Ordinary withdrawal',
  ordinary_partial: 'Ordinary withdrawal, for part of the amount',
  ordinary_partial_unsimulated: 'Ordinary withdrawal for part of the amount, not simulated',
  force_deallocate: 'forceDeallocate, then withdraw, in one transaction',
  force_deallocate_partial: 'forceDeallocate, then withdraw, for part of the amount',
};
export const routeLabel = (r) => ROUTE[r] || (r ? r : 'No route confirmed now');

const RSTATUS = {
  simulated: ['Simulated for the full amount', 'stay'],
  simulated_partial: ['Simulated for part of the amount', 'review'],
  not_needed: ['Not needed: ordinary withdrawal covers it', 'neutral'],
  reverted: ['Simulation failed', 'exit'],
  unavailable: ['Could not be simulated', 'neutral'],
  not_simulated: ['Not simulated', 'neutral'],
  theoretical_not_simulated: ['On paper only, not simulated', 'neutral'],
  no_other_liquidity: ['No liquidity in other markets', 'neutral'],
  blocked_by_gate: ['Blocked by a vault gate', 'exit'],
  not_applicable: ['Not available on V1 vaults', 'neutral'],
};
export function routeStatus(s) {
  const [label, tone] = RSTATUS[s] || [s ? cap(String(s).replace(/_/g, ' ')) : 'Unknown', 'neutral'];
  return { label, tone, raw: s || 'null' };
}

export const ROLE = {
  pos: 'Your deposit', lending: 'Vault', vault: 'Vault', adapter: 'Vault adapter', market: 'Morpho market',
  morpho_blue: 'Morpho Blue protocol', collateral: 'Collateral', oracle: 'Price oracle', chain: 'Blockchain',
  stablecoin: 'Deposit asset', fx: 'Exchange rate',
};
const ROLE_GROUP = {
  pos: 'your deposit', lending: 'vault', vault: 'vault', adapter: 'adapter', market: 'markets', morpho_blue: 'protocol',
  collateral: 'collateral', oracle: 'oracles', chain: 'chain', stablecoin: 'asset', fx: 'exchange rate',
};
export const roleLabel = (r) => ROLE[r] || cap(String(r || 'dependency').replace(/_/g, ' '));

const VCLS = { STAY: 'stay', EXIT: 'exit', REVIEW: 'review' };
export const verdictTone = (v) => VCLS[v] || 'neutral';

// ---------- data status ----------
export function statusOf(p) {
  const blockTxt = p && p.as_of_block ? `block ${num(p.as_of_block)}` : '';
  const ts = (p && p.snapshot && p.snapshot.block_timestamp) || (p && p.timestamp);
  const meta = [blockTxt, ts ? dateTime(ts) : ''].filter(Boolean).join(', ');
  const fr = p && p.decision && p.decision.freshness && p.decision.freshness.label;
  const mode = p && p.mode;
  if (mode === 'live') return { key: fr === 'stale' ? 'stale' : 'live', meta };
  if (mode === 'mixed') return { key: 'mixed', meta };
  if (mode === 'cache') return { key: 'cached', meta: `replay, ${meta}` };
  if (mode === 'offline') return { key: 'cached', meta: `offline replay, ${meta}` };
  return { key: 'unavailable', meta: 'unknown data source' };
}

// ---------- decision ----------
export function holdsText(point, m) {
  if (!ok(m)) return '';
  return point === 'EXIT'
    ? `EXIT holds unless the risk is below ${multiple(m)} the estimate.`
    : `STAY holds unless the risk is ${multiple(m)} higher than estimated.`;
}

/** The three-sentence decision story, every figure taken from the decision block. */
export function decisionStory(d) {
  const [ll, lh] = d.loss_band_usd || [];
  return [
    `Staying: expected loss ${money(d.expected_loss_usd)} over ${d.horizon_days} days (range ${money(ll)}–${money(lh)}).`,
    `Exiting costs ${money(d.exit_side_usd)} (execution ${money(d.execution_cost_usd)} + carry forgone ${money(d.carry_usd)}).`,
    holdsText(d.point_verdict, d.breakeven_risk_multiplier),
  ].filter(Boolean);
}

export function basisSentence(d) {
  const b = d && d.comparison_basis;
  if (!b || b.kind === 'full_position') return '';
  if (b.kind === 'executable_tranche') {
    return `Both sides cover only the part you can withdraw now: ${money(b.usd)} (${pct(b.fraction, 1)} of the exposure). ` +
      `The rest keeps an expected loss of ${money(b.residual_expected_loss_usd)} and has to wait for liquidity.`;
  }
  return 'No exit route is confirmed now, so the exit side is hypothetical and cannot produce EXIT.';
}

const overlaps = (a, b) => a && b && a.length === 2 && b.length === 2 && a[0] <= b[1] && b[0] <= a[1];

export function leanText(d) {
  if (d.verdict === 'REVIEW') {
    const lean = d.point_verdict ? `leaning ${d.point_verdict}` : 'no lean';
    if (d.blockers && d.blockers.length) return `Low confidence, ${lean}: some inputs are stale or replayed, so there is no firm call.`;
    if (overlaps(d.loss_band_usd, d.exit_band_usd)) return `Low confidence, ${lean}: the two ranges overlap, so neither side clearly wins.`;
    if (d.point_verdict === 'EXIT') return `Low confidence, ${lean}: only part of the position can leave now, so a full EXIT is not advised.`;
    return `Low confidence, ${lean}: the evidence does not support a firm call.`;
  }
  return `${cap(d.confidence || 'unknown')} confidence: the two ranges do not overlap.`;
}

/** Why a firm verdict is firm, restated from the bands the backend compared. */
export function firmWhy(d) {
  const [ll, lh] = d.loss_band_usd || [], [el, eh] = d.exit_band_usd || [];
  if (d.verdict === 'STAY') return `Even the high end of the staying loss (${money(lh)}) is below the low end of the exit cost (${money(el)}).`;
  if (d.verdict === 'EXIT') return `Even the low end of the staying loss (${money(ll)}) is above the high end of the exit cost (${money(eh)}).`;
  return '';
}

const FRESH_KIND = { onchain_state: 'on-chain state', exit_quote: 'exit quote', market_data: 'market data', priors: 'failure priors' };
const FEAS_TODAY = { partial: 'partial', zero: 'blocked', unknown: 'unconfirmed' };

/** Known backend reason strings rewritten in plain words; anything else is shown as sent, sentence-cased. */
export function plainReason(r) {
  const s = String(r || '').trim();
  let m;
  if ((m = s.match(/^uncertainty bands overlap: staying loss (\$[\d,.]+)-(\$[\d,.]+) vs exit (\$[\d,.]+)-(\$[\d,.]+)$/))) {
    return `The ranges overlap: staying could lose ${m[1]} to ${m[2]}, exiting would cost ${m[3]} to ${m[4]}. Neither side clearly wins.`;
  }
  if ((m = s.match(/^full exit executable only through forceDeallocate: multicall simulated at block (\d+) \(penalty (\$[\d,.]+)(?:, ([\d,]+) gas)?\); liquidity is shared, first come first served$/))) {
    return `A full exit works only with forceDeallocate, which first pulls liquidity from the vault's other markets. ` +
      `Simulated at block ${num(m[1])}: penalty ${m[2]}${m[3] ? `, ${m[3]} gas` : ''}. Liquidity is shared, first come first served.`;
  }
  if ((m = s.match(/^exit not fully executable now \((\w+)\): only ([\d,.]+) (\S+) \((\$[\d,.]+)\) can be withdrawn immediately(.*?), ([\d,.]+) need reallocation \/ waiting -> partial exit, not a 100% EXIT$/))) {
    const how = /even with forceDeallocate/.test(m[5]) ? ', even with forceDeallocate'
      : /theoretical/.test(m[5]) ? '; a forceDeallocate route exists on paper but was not simulated' : '';
    return `Only ${m[4]} (${m[2]} ${m[3]}) can be withdrawn now${how}. The other ${m[6]} ${m[3]} must wait for liquidity, so a full EXIT is not possible today.`;
  }
  if ((m = s.match(/^note: an exit would be (\w+) today \(immediate (\$[\d,.]+) of (\$[\d,.]+)\)$/))) {
    return `An exit today would be ${FEAS_TODAY[m[1]] || m[1]}: ${m[2]} of ${m[3]} could leave immediately.`;
  }
  if (/^carry excluded \(unknown\)$/.test(s)) return 'The yield you would give up is unknown, so it is left out of the exit cost.';
  if ((m = s.match(/^stale (\w+) \((.+)\): no firm verdict$/))) {
    return `Some decisive data is out of date (${FRESH_KIND[m[1]] || m[1]}: ${m[2]}), so there is no firm verdict. Re-run before acting.`;
  }
  if (/^cache\/offline replay/.test(s)) return 'These figures are a dated replay, not live, so there is no firm verdict.';
  if (/^gas of the redeem could not be simulated$/.test(s)) return 'The gas cost of the withdrawal could not be simulated.';
  if ((m = s.match(/^redeem simulation (\w+) although on-chain capacity covers the amount$/))) {
    return `The withdrawal simulation ${m[1] === 'reverted' ? 'failed' : `returned "${m[1]}"`} although the vault seems to hold enough liquidity.`;
  }
  return sentence(s);
}

// ---------- allocations ----------
export function marketPair(item, loanSymbol) {
  return item.collateral_symbol ? `${item.collateral_symbol}${loanSymbol ? ' / ' + loanSymbol : ''}` : 'Idle market (no collateral)';
}
export const oracleText = (addr) => (addr ? `Oracle ${short(addr, 6, 4)}` : '—');
/** LLTV as 77% or 91.5% (no trailing zero). */
export const lltvText = (x) => (ok(x) ? `${Number((Number(x) * 100).toFixed(1))}%` : '—');

/** Bar segments by share of the vault. Markets under 1 % are drawn as one segment, labelled without a summed figure. */
export function allocationSegments(al) {
  const items = (al && al.items ? al.items.slice() : []).sort((a, b) => (b.share_of_vault || 0) - (a.share_of_vault || 0));
  const segs = [], small = [];
  for (const it of items) {
    if ((it.share_of_vault || 0) >= 0.01) {
      segs.push({ kind: 'market', key: it.market_id, label: it.collateral_symbol || 'Idle market', lltv: it.lltv, share: it.share_of_vault, usd: it.supply_usd });
    } else small.push(it);
  }
  if (small.length) {
    segs.push({ kind: 'small', key: 'small', label: `${small.length} smaller market${small.length > 1 ? 's' : ''}`,
      share: small.reduce((s, it) => s + (it.share_of_vault || 0), 0), names: small.map((it) => it.collateral_symbol || 'idle') });
  }
  if ((al && al.idle_share) >= 0.001) segs.push({ kind: 'idle', key: 'idle', label: 'Idle cash', share: al.idle_share, usd: al.idle_usd });
  if ((al && al.unattributed_share) >= 0.001) segs.push({ kind: 'unattributed', key: 'unattributed', label: 'Not attributed', share: al.unattributed_share });
  return segs;
}

// ---------- scenarios ----------
export function forceRouteTag(s) {
  const r = String(s.force_deallocate_route || '');
  if (/^confirmed/.test(r)) return { label: 'Simulated', tone: 'stay' };
  if (/^theoretical/.test(r)) return { label: 'On paper only', tone: 'neutral' };
  if (/^none/.test(r)) return { label: 'No route', tone: 'neutral' };
  return { label: '', tone: 'neutral' };
}

// ---------- FX and peg ----------
export function fxView(p) {
  const a = p && p.vault && p.vault.asset;
  if (!a || !a.currency || a.currency === 'USD' || !a.fx) return null;
  const pegKey = Object.keys(a).find((k) => k.startsWith('peg_vs_'));
  const nodes = (p.dependencies && p.dependencies.nodes) || [];
  return {
    currency: a.currency, symbol: a.symbol, price: a.price_usd, priceSource: a.price_source, priceAge: a.price_age_s,
    pair: a.fx.pair, rate: a.fx.rate, fxSource: a.fx.source, fxUpdated: a.fx.updated_at,
    peg: pegKey ? a[pegKey] : null, decomposition: a.decomposition,
    fxNode: nodes.find((n) => n.role === 'fx'), assetNode: nodes.find((n) => n.role === 'stablecoin'),
    depeg: (p.scenarios || []).find((s) => s.decision_neutral),
    conversion: p.exit && p.exit.usd_conversion,
  };
}

// ---------- dependency map ----------
const ROLE_ORDER = { lending: 0, vault: 0, stablecoin: 1, chain: 2, adapter: 0, fx: 1, market: 0, collateral: 0, oracle: 1, morpho_blue: 2 };

export function nodeShort(n, id, { compact = false } = {}) {
  if (!n || id === 'pos') return 'Your deposit';
  const l = String(n.label || n.id || '');
  const addr = (String(n.id || '').match(/0x[0-9a-fA-F]{40}/) || [])[0];
  switch (n.role) {
    case 'lending': case 'vault': return l.replace(/\s*\(.*\)\s*$/, '');
    case 'adapter': return 'Market adapter';
    case 'market': {
      const m = l.match(/market (\S+) \(LLTV ([\d.]+)%\)/);
      return m ? `${m[1].split('/')[0]}, LLTV ${Number(m[2])}%` : l;
    }
    case 'collateral': case 'stablecoin': return l.replace(/\s*\(.*\)\s*$/, '');
    case 'oracle': return addr ? (compact ? `Oracle ${addr.slice(0, 6)}…` : oracleText(addr)) : l;
    case 'fx': return l.replace(/ exchange rate$/, ' rate');
    case 'morpho_blue': return 'Morpho Blue';
    default: return l;
  }
}

/** Layered layout: columns = hops from the deposit (view.js layoutGraph); rows ordered by the parents' positions. */
export function graphModel(nodes, edges, { colW = 172, gapX = 54, rowH = 38, headH = 34, pad = 10 } = {}) {
  nodes = nodes || []; edges = edges || [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const { pos } = layoutGraph(nodes, edges);
  let maxD = 0;
  for (const id in pos) maxD = Math.max(maxD, pos[id].depth);
  const colOf = (id) => (pos[id].depth < 0 ? maxD + 1 : pos[id].depth);
  const cols = [];
  for (const id of Object.keys(pos)) { const c = colOf(id); (cols[c] = cols[c] || []).push(id); }
  const parents = new Map(), inT = new Map();
  for (const e of edges) {
    if (!pos[e.src] || !pos[e.dst]) continue;
    if (!parents.has(e.dst)) parents.set(e.dst, []);
    parents.get(e.dst).push(e.src);
    inT.set(e.dst, Math.max(inT.get(e.dst) || 0, e.transmission || 0));
  }
  const rank = new Map();
  const cmp = (x, y) => (x === y ? 0 : x < y ? -1 : 1);
  cols.forEach((list, c) => {
    if (!list) return;
    const bary = new Map(list.map((id) => {
      const ps = (parents.get(id) || []).filter((q) => rank.has(q) && colOf(q) < c);
      return [id, ps.length ? ps.reduce((s, q) => s + rank.get(q), 0) / ps.length : 2];
    }));
    const role = (id) => (byId.get(id) || {}).role;
    list.sort((a, b) => cmp(bary.get(a), bary.get(b)) || cmp(ROLE_ORDER[role(a)] ?? 9, ROLE_ORDER[role(b)] ?? 9)
      || cmp(inT.get(b) || 0, inT.get(a) || 0) || cmp(nodeShort(byId.get(a), a), nodeShort(byId.get(b), b)));
    list.forEach((id, i) => rank.set(id, list.length > 1 ? i / (list.length - 1) : 0.5));
  });
  const dense = cols.filter(Boolean);
  const maxRows = Math.max(1, ...dense.map((l) => l.length));
  const W = pad * 2 + dense.length * colW + (dense.length - 1) * gapX;
  const H = headH + maxRows * rowH + pad;
  const at = {};
  dense.forEach((list, c) => list.forEach((id, i) => {
    at[id] = { x: pad + c * (colW + gapX), y: headH + ((maxRows - list.length) * rowH) / 2 + i * rowH + rowH / 2, col: c, row: i };
  }));
  const heads = dense.map((list) => {
    if (list.length === 1 && list[0] === 'pos') return 'Your deposit';
    const groups = [];
    for (const id of list) { const g = ROLE_GROUP[(byId.get(id) || {}).role] || 'other'; if (!groups.includes(g)) groups.push(g); }
    const t = cap(groups.slice(0, 3).join(', '));
    return groups.length > 3 ? t + ', more' : t;
  });
  return { cols: dense, at, W, H, colW, rowH, headH, heads, byId };
}

export function glyph(role, cx, cy, cls = 'vi-glyph') {
  const r = 4.5;
  switch (role) {
    case 'pos': return `<circle class="${cls} is-pos" cx="${cx}" cy="${cy}" r="${r}"/>`;
    case 'lending': case 'vault': return `<rect class="${cls}" x="${cx - r}" y="${cy - r}" width="${2 * r}" height="${2 * r}" rx="1"/>`;
    case 'adapter': return `<rect class="${cls} is-open" x="${cx - r + 1}" y="${cy - r + 1}" width="${2 * r - 2}" height="${2 * r - 2}"/>`;
    case 'market': return `<path class="${cls}" d="M${cx} ${cy - r - 1}L${cx + r + 1} ${cy}L${cx} ${cy + r + 1}L${cx - r - 1} ${cy}Z"/>`;
    case 'morpho_blue': return `<rect class="${cls} is-open" x="${cx - r}" y="${cy - r}" width="${2 * r}" height="${2 * r}"/><rect class="${cls}" x="${cx - 1.6}" y="${cy - 1.6}" width="3.2" height="3.2"/>`;
    case 'collateral': return `<circle class="${cls}" cx="${cx}" cy="${cy}" r="${r}"/>`;
    case 'oracle': return `<path class="${cls}" d="M${cx} ${cy - r - 0.5}L${cx + r + 0.5} ${cy + r - 0.5}L${cx - r - 0.5} ${cy + r - 0.5}Z"/>`;
    case 'chain': { const k = r + 0.5; const pts = [0, 60, 120, 180, 240, 300].map((a) => `${(cx + k * Math.cos((a * Math.PI) / 180)).toFixed(1)},${(cy + k * Math.sin((a * Math.PI) / 180)).toFixed(1)}`).join(' '); return `<polygon class="${cls}" points="${pts}"/>`; }
    case 'stablecoin': return `<circle class="${cls} is-open" cx="${cx}" cy="${cy}" r="${r - 0.5}"/>`;
    case 'fx': return `<circle class="${cls} is-open" cx="${cx}" cy="${cy}" r="${r - 0.5}"/><path class="${cls} is-line" d="M${cx - r + 0.5} ${cy}H${cx + r - 0.5}"/>`;
    default: return `<circle class="${cls} is-open" cx="${cx}" cy="${cy}" r="${r - 1}"/>`;
  }
}

/** One glyph as a tiny inline SVG for legends. */
export const glyphIcon = (role) => `<svg class="vi-glyph-icon" viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">${glyph(role, 7, 7)}</svg>`;

function fit(text, px, charPx = 6.4) {
  const max = Math.max(4, Math.floor(px / charPx));
  return text.length > max ? text.slice(0, max - 1) + '…' : text;
}

export function graphSvg(model, edges, { selected = null } = {}) {
  const { at, W, H, colW, heads, byId, cols } = model;
  const maxEl = Math.max(1e-9, ...[...byId.values()].map((n) => n.expected_loss_usd || 0));
  const linked = new Set();
  if (selected) for (const e of edges) if (e.src === selected || e.dst === selected) { linked.add(e.src); linked.add(e.dst); }
  const head = heads.map((h, c) => {
    const x = cols[c] && at[cols[c][0]] ? at[cols[c][0]].x : 0;
    return `<text class="vi-g-head" x="${x + 2}" y="16">${esc(fit(h, colW, 6))}</text>`;
  }).join('');
  const lines = edges.filter((e) => at[e.src] && at[e.dst]).map((e) => {
    const a = at[e.src], b = at[e.dst];
    let d;
    if (b.col > a.col) {
      const x1 = a.x + colW, x2 = b.x - 5, mx = (x1 + x2) / 2;
      d = `M${x1} ${a.y}C${mx} ${a.y} ${mx} ${b.y} ${x2} ${b.y}`;
    } else {
      const x1 = a.x + colW, x2 = b.x + colW + 5, k = x1 + 26;
      d = `M${x1} ${a.y}C${k} ${a.y} ${k} ${b.y} ${x2} ${b.y}`;
    }
    const on = selected && (e.src === selected || e.dst === selected);
    const w = (0.8 + 2.4 * Math.min(1, Math.max(0, e.transmission || 0))).toFixed(2);
    const t = `${nodeShort(byId.get(e.src), e.src)} depends on ${nodeShort(byId.get(e.dst), e.dst)}: transmission ${num(e.transmission, 3)} (${String(e.relation_type || '').replace(/_/g, ' ')}, ${e.confidence || 'unknown'} confidence)`;
    return `<path class="vi-g-edge${on ? ' is-on' : selected ? ' is-dim' : ''}" d="${d}" stroke-width="${w}" marker-end="url(#vi-arrow${on ? '-on' : ''})"><title>${esc(t)}</title></path>`;
  }).join('');
  const chips = Object.entries(at).map(([id, q]) => {
    const n = byId.get(id);
    const isPos = id === 'pos';
    const label = nodeShort(n, id, { compact: true });
    const el = n && n.expected_loss_usd >= 0.5 ? usd(n.expected_loss_usd) : '';
    const elW = el ? el.length * 6.6 + 8 : 0;
    const share = n ? (n.expected_loss_usd || 0) / maxEl : 0;
    const y0 = q.y - 14;
    const cls = ['vi-g-node', isPos ? 'is-pos' : '', n && n.decision_neutral ? 'is-neutral' : '', id === selected ? 'is-sel' : '',
      selected && !linked.has(id) && id !== selected ? 'is-dim' : ''].filter(Boolean).join(' ');
    const aria = isPos ? 'Your deposit' : `${label}, ${roleLabel(n.role)}${el ? `, expected loss ${el}` : ''}`;
    return `<g class="${cls}" data-id="${esc(id)}" role="button" tabindex="${id === selected ? 0 : -1}" aria-pressed="${id === selected}" aria-label="${esc(aria)}">` +
      `<rect class="vi-g-chip" x="${q.x}" y="${y0}" width="${colW}" height="28" rx="5"/>` +
      (share > 0 && !isPos ? `<rect class="vi-g-share" x="${q.x + 1}" y="${y0 + 25}" width="${Math.max(2, (colW - 2) * share).toFixed(1)}" height="2"/>` : '') +
      glyph(isPos ? 'pos' : n.role, q.x + 13, q.y) +
      `<text class="vi-g-label" x="${q.x + 24}" y="${q.y + 4}">${esc(fit(label, colW - 30 - elW))}</text>` +
      (el ? `<text class="vi-g-el" x="${q.x + colW - 8}" y="${q.y + 4}" text-anchor="end">${esc(el)}</text>` : '') +
      `<title>${esc(isPos ? 'Your deposit (hypothetical exposure)' : `${n.label} (${roleLabel(n.role)})`)}</title></g>`;
  }).join('');
  return `<svg class="vi-graph" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="Dependency map: columns are hops from your deposit">` +
    `<defs><marker id="vi-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,1 L9,5 L0,9 z" class="vi-g-arrow"/></marker>` +
    `<marker id="vi-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,1 L9,5 L0,9 z" class="vi-g-arrow is-on"/></marker></defs>` +
    `${head}<g>${lines}</g><g>${chips}</g></svg>`;
}

/** The same layers as a list of buttons: the readable form of the map on small screens and for screen readers. */
export function layersHtml(model, { selected = null } = {}) {
  const { cols, heads, byId } = model;
  return cols.map((list, c) => `<div class="vi-layer"><h5 class="vi-layer__head">${esc(heads[c])}</h5><div class="vi-layer__chips">${list.map((id) => {
    const n = byId.get(id), isPos = id === 'pos';
    const el = n && n.expected_loss_usd >= 0.5 ? usd(n.expected_loss_usd) : '';
    const cls = ['vi-chip', isPos ? 'is-pos' : '', n && n.decision_neutral ? 'is-neutral' : ''].filter(Boolean).join(' ');
    return `<button type="button" class="${cls}" data-id="${esc(id)}" aria-pressed="${id === selected}">` +
      `<svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">${glyph(isPos ? 'pos' : n.role, 7, 7)}</svg>` +
      `<span>${esc(nodeShort(n, id))}</span>${el ? `<span class="vi-chip__el">${esc(el)}</span>` : ''}</button>`;
  }).join('')}</div></div>`).join('');
}

// ---------- small charts ----------
export function niceTicks(lo, hi, n = 5) {
  if (!(hi > lo)) hi = lo + 1;
  const raw = (hi - lo) / Math.max(1, n);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw * 0.999);
  const t0 = Math.floor(lo / step + 1e-9) * step, t1 = Math.ceil(hi / step - 1e-9) * step;
  const out = [];
  for (let v = t0; v <= t1 + step * 1e-6; v += step) out.push(Number(v.toFixed(10)));
  return out;
}
const f1 = (v) => Number(v).toFixed(1);

/** Two ranges on one axis: what staying could lose, what exiting costs. REVIEW shades their overlap. */
export function bandsSvg(d, W) {
  W = Math.max(260, Math.round(W || 520));
  const [ll, lh] = d.loss_band_usd || [], [el, eh] = d.exit_band_usd || [];
  if (![ll, lh, el, eh].every(ok)) return '';
  const hi = Math.max(lh, eh, d.expected_loss_usd || 0, d.exit_side_usd || 0);
  const ticks = niceTicks(0, hi, W < 420 ? 3 : 5);
  const d1 = ticks[ticks.length - 1] || 1;
  const L = 1, R = 1;
  const x = (v) => L + (Math.max(0, Math.min(v, d1)) / d1) * (W - L - R);
  const rows = [
    { y: 18, label: 'Stay: expected loss', c: d.expected_loss_usd, lo: ll, hi: lh, cls: 'is-stay' },
    { y: 70, label: 'Exit: cost', c: d.exit_side_usd, lo: el, hi: eh, cls: 'is-exit' },
  ];
  const axisY = 118, H = 140;
  let ov = '';
  const oLo = Math.max(ll, el), oHi = Math.min(lh, eh);
  if (oLo <= oHi) {
    const w = Math.max(2, x(oHi) - x(oLo));
    ov = `<rect class="vi-b-overlap${d.verdict === 'REVIEW' ? ' is-review' : ''}" x="${f1(x(oLo))}" y="22" width="${f1(w)}" height="${axisY - 26}"/>` +
      (w > 70 ? `<text class="vi-b-ovtext" x="${f1(x(oLo) + w / 2)}" y="${axisY - 8}" text-anchor="middle">ranges overlap</text>` : '');
  }
  const bars = rows.map((r) => {
    const xl = x(r.lo), xr = x(r.hi), xc = x(r.c);
    return `<text class="vi-b-label" x="${L}" y="${r.y}">${esc(r.label)}</text>` +
      `<text class="vi-b-val" x="${W - R}" y="${r.y}" text-anchor="end"><tspan class="vi-b-strong">${esc(money(r.c))}</tspan> (${esc(money(r.lo))}–${esc(money(r.hi))})</text>` +
      `<rect class="vi-b-band ${r.cls}" x="${f1(xl)}" y="${r.y + 9}" width="${f1(Math.max(2, xr - xl))}" height="16" rx="2"/>` +
      `<rect class="vi-b-mark" x="${f1(Math.min(W - R - 3, Math.max(L, xc - 1.5)))}" y="${r.y + 5}" width="3" height="24" rx="1"><title>${esc(r.label)}: ${esc(money(r.c))}</title></rect>`;
  }).join('');
  const axis = `<path class="vi-axis" d="M${L} ${axisY}H${W - R}"/>` + ticks.map((t, i) => {
    const tx = x(t), anchor = i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle';
    return `<path class="vi-axis" d="M${f1(tx)} ${axisY}v4"/><text class="vi-tick" x="${f1(tx)}" y="${axisY + 16}" text-anchor="${anchor}">${esc(usd(t))}</text>`;
  }).join('');
  const aria = `Staying: expected loss ${money(d.expected_loss_usd)}, range ${money(ll)} to ${money(lh)}. Exiting: cost ${money(d.exit_side_usd)}, range ${money(el)} to ${money(eh)}.`;
  return `<svg class="vi-chart" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(aria)}">` +
    `<defs><pattern id="vi-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" class="vi-hatch-bg"/><path d="M0 0V5" class="vi-hatch-line"/></pattern></defs>` +
    `${ov}${bars}${axis}</svg>`;
}

/** Tornado: expected loss with one dependency's failure probability halved (left end) or doubled (right end). */
export function tornadoSvg(rows, base, W, horizon) {
  rows = (rows || []).filter((r) => ok(r.low_usd) && ok(r.high_usd));
  if (!rows.length || !ok(base)) return '';
  W = Math.max(260, Math.round(W || 560));
  const rowH = 44, top = 30, n = rows.length;
  const lo = Math.min(base, ...rows.map((r) => r.low_usd)), hi = Math.max(base, ...rows.map((r) => r.high_usd));
  const span = hi - lo || Math.abs(hi) || 1;
  const ticks = niceTicks(Math.max(0, lo - span * 0.06), hi + span * 0.06, W < 420 ? 3 : 5);
  const d0 = ticks[0], d1 = ticks[ticks.length - 1];
  const L = 2, R = 2;
  const x = (v) => L + ((v - d0) / (d1 - d0)) * (W - L - R);
  const axisY = top + n * rowH + 4, H = axisY + 40;
  const xb = x(base);
  const body = rows.map((r, i) => {
    const y = top + i * rowH;
    const vals = `${money(r.low_usd)} to ${money(r.high_usd)}`;
    const label = fit(String(r.label || r.id), W - vals.length * 6.6 - 14, 6.3);
    return `<g><title>${esc(`${r.label}: expected loss ${money(r.low_usd)} with its probability halved, ${money(r.high_usd)} doubled`)}</title>` +
      `<text class="vi-b-label" x="${L}" y="${y + 12}">${esc(label)}</text>` +
      `<text class="vi-b-val" x="${W - R}" y="${y + 12}" text-anchor="end">${esc(vals)}</text>` +
      `<rect class="vi-t-low" x="${f1(Math.min(x(r.low_usd), xb))}" y="${y + 19}" width="${f1(Math.max(1.5, Math.abs(xb - x(r.low_usd))))}" height="14" rx="2"/>` +
      `<rect class="vi-t-high" x="${f1(Math.min(x(r.high_usd), xb))}" y="${y + 19}" width="${f1(Math.max(1.5, Math.abs(x(r.high_usd) - xb)))}" height="14" rx="2"/></g>`;
  }).join('');
  const baseTxt = `Central ${money(base)}`;
  const anchor = xb < 60 ? 'start' : xb > W - 60 ? 'end' : 'middle';
  const baseLine = `<path class="vi-t-base" d="M${f1(xb)} ${top - 6}V${axisY}"/><text class="vi-tick is-strong" x="${f1(xb)}" y="${top - 12}" text-anchor="${anchor}">${esc(baseTxt)}</text>`;
  const axis = `<path class="vi-axis" d="M${L} ${axisY}H${W - R}"/>` + ticks.map((t, i) => {
    const tx = x(t), a = i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle';
    return `<path class="vi-axis" d="M${f1(tx)} ${axisY}v4"/><text class="vi-tick" x="${f1(tx)}" y="${axisY + 16}" text-anchor="${a}">${esc(usd(t))}</text>`;
  }).join('') + `<text class="vi-axis-title" x="${W / 2}" y="${axisY + 34}" text-anchor="middle">Expected loss over ${esc(horizon)} days</text>`;
  return `<svg class="vi-chart" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Sensitivity of the expected loss to each dependency's failure probability">${baseLine}${body}${axis}</svg>`;
}

/** Loss of the position if one collateral drops by x % (conditional on the drop). */
export function crashSvg(curve, W) {
  const pts = ((curve && curve.points) || []).filter((q) => ok(q.drop) && ok(q.loss_usd)).sort((a, b) => a.drop - b.drop);
  if (!pts.length) return '';
  W = Math.max(260, Math.round(W || 560));
  const L = 52, R = 12, T = 26, B = 46, H = 230;
  const xt = niceTicks(0, Math.max(...pts.map((q) => q.drop)), W < 420 ? 4 : 5);
  const yt = niceTicks(0, Math.max(1, ...pts.map((q) => q.loss_usd)), 4);
  const x1 = xt[xt.length - 1], y1 = yt[yt.length - 1];
  const x = (v) => L + (v / x1) * (W - L - R), y = (v) => T + (1 - v / y1) * (H - T - B);
  const line = pts.map((q, i) => `${i ? 'L' : 'M'}${f1(x(q.drop))} ${f1(y(q.loss_usd))}`).join('');
  const area = `${line}L${f1(x(pts[pts.length - 1].drop))} ${f1(y(0))}L${f1(x(pts[0].drop))} ${f1(y(0))}Z`;
  const grid = yt.map((t) => `<path class="vi-grid" d="M${L} ${f1(y(t))}H${W - R}"/><text class="vi-tick" x="${L - 6}" y="${f1(y(t) + 4)}" text-anchor="end">${esc(usd(t))}</text>`).join('');
  const xa = xt.map((t) => `<path class="vi-axis" d="M${f1(x(t))} ${H - B}v4"/><text class="vi-tick" x="${f1(x(t))}" y="${H - B + 17}" text-anchor="middle">${t ? '−' : ''}${esc(pct(t, 0))}</text>`).join('');
  const dots = pts.map((q) => `<circle class="vi-c-dot" cx="${f1(x(q.drop))}" cy="${f1(y(q.loss_usd))}" r="3.5"><title>${esc(`Drop ${pct(q.drop, 0)}: loss ${money(q.loss_usd)}`)}</title></circle>`).join('');
  return `<svg class="vi-chart" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(`Loss if ${curve.label} drops: ` + pts.map((q) => `${pct(q.drop, 0)} drop, ${money(q.loss_usd)}`).join('; '))}">` +
    `<text class="vi-axis-title" x="${L}" y="12">Loss if it happens</text>${grid}` +
    `<path class="vi-axis" d="M${L} ${H - B}H${W - R}"/>${xa}<path class="vi-c-area" d="${area}"/><path class="vi-c-line" d="${line}"/>${dots}` +
    `<text class="vi-axis-title" x="${f1(L + (W - L - R) / 2)}" y="${H - 8}" text-anchor="middle">Price drop of ${esc(fit(String(curve.label || '').replace(/\s*\(collateral\)$/, ''), W - 140))}</text></svg>`;
}
