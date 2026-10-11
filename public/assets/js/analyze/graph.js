// Strata graph: one row per Belem layer, position on top. Draws server data only: edges carry their channel,
// a selected node lights the path the BACKEND reported for it (stress_table[].path), never a client estimate.
import { esc, usd } from '../core/format.js';
import { BANDS, strataLayout, ROLE_WORDS } from './view.js';

let W = 900;
const BOX = { w: 156, h: 58 };
const PADX = 14;

export function shortLabel(label) {
  const s = String(label || '').replace(/\s*\([^)]*\)\s*/g, ' ').replace(/\s+/g, ' ').trim();
  return s.length > 30 ? s.slice(0, 29) + '…' : s;
}

export function shortLabelExport(s) { return shortLabel(s); }

function edgePath(a, b) {
  const y1 = a.y + BOX.h / 2, y2 = b.y - BOX.h / 2;
  if (b.y > a.y) {
    const m = (y1 + y2) / 2;
    return `M${a.x},${y1} C${a.x},${m} ${b.x},${m} ${b.x},${y2}`;
  }
  const yy1 = a.y - BOX.h / 2, yy2 = b.y + BOX.h / 2, m = (yy1 + yy2) / 2;
  return `M${a.x},${yy1} C${a.x},${m} ${b.x},${m} ${b.x},${yy2}`;
}

export function impactText(n) {
  if (!n.stress) return { t: '', zero: true };
  const ch = n.stress.channel;
  if (ch && ch.blocked_by && ch.blocked_by.length) return { t: ch.blocked_by.includes('exit') && !ch.blocked_by.includes('debt') ? 'exit cost only' : 'no effect, no debt', zero: true };
  return { t: `if it fails ${usd(n.stress.conditional_loss_usd)}`, zero: false };
}

export function renderGraph(svg, index, { onSelect, width } = {}) {
  W = Math.max(660, Math.round(width || svg.parentElement.clientWidth || 900));
  const maxRow = Math.max(...BANDS.map((b) => index.nodes.filter((n) => n.band === b.key).length), 1);
  BOX.w = Math.max(128, Math.min(190, Math.floor((W - PADX - 30) / maxRow) - 18));
  // Sparse rows get wider boxes so labels are not truncated needlessly.
  const rowW = new Map(BANDS.map((b) => {
    const k = Math.max(1, index.nodes.filter((n) => n.band === b.key).length);
    return [b.key, Math.max(BOX.w, Math.min(236, Math.floor((W - PADX - 30) / Math.max(k, 3)) - 18))];
  }));
  const ROWH = 98;
  const lay = strataLayout(index, { width: W + 16, padX: PADX, rowH: ROWH, top: 30 + BOX.h / 2 });
  lay.height = BANDS.length * ROWH;
  svg.setAttribute('viewBox', `0 0 ${W} ${lay.height}`);
  svg.setAttribute('width', W);
  svg.setAttribute('height', lay.height);
  const bands = lay.rows.map((r, i) => {
    const y = i * ROWH;
    return `<g class="g-band"><rect x="0" y="${y}" width="${W}" height="${ROWH}"></rect>
      <line x1="0" x2="${W}" y1="${y + ROWH}" y2="${y + ROWH}"></line>
      <text x="2" y="${y + 17}">${esc(r.short)}<tspan class="b2" dx="10">${esc(r.key === 'position' ? '' : r.label)}</tspan></text></g>`;
  }).join('');
  const defs = `<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" fill="var(--bone-4)"/></marker></defs>`;
  const edges = index.edges.map((e) => {
    const a = lay.pos.get(e.src), b = lay.pos.get(e.dst);
    if (!a || !b) return '';
    const cls = `g-edge${e.channel === 'debt' ? ' is-debt' : e.channel === 'exit' ? ' is-exit' : ''}`;
    return `<path class="${cls}" data-src="${esc(e.src)}" data-dst="${esc(e.dst)}" d="${edgePath(a, b)}"><title>${esc(e.reason || '')}</title></path>`;
  }).join('');
  const nodes = index.nodes.map((n) => {
    const p = lay.pos.get(n.id);
    if (!p) return '';
    const isPos = n.id === index.posId;
    const w = isPos ? Math.max(BOX.w, 230) : (rowW.get(n.band) || BOX.w);
    const chars = Math.floor((w - 20) / 7.4);
    const fit = (s) => { s = shortLabel(s); return s.length > chars ? s.slice(0, chars - 1) + '…' : s; };
    const imp = impactText(n);
    const sub = isPos ? (index.posSub || 'your position') : (n.hidden ? 'hidden dependency' : (ROLE_WORDS[n.meta && n.meta.role] || n.layer || '').replace(/\s*\([^)]*\)/, ''));
    const aria = `${n.label}. ${ROLE_WORDS[n.meta && n.meta.role] || ''}.${imp.t ? ' Backend stress run: ' + imp.t + '.' : ''}`;
    return `<g class="g-node${isPos ? ' is-pos' : ''}${n.hidden ? ' is-hidden' : ''}" data-id="${esc(n.id)}" tabindex="${isPos ? -1 : 0}" role="button" aria-label="${esc(aria)}" transform="translate(${p.x - w / 2},${p.y - BOX.h / 2})">
      <rect width="${w}" height="${BOX.h}" rx="5"></rect>
      <text x="11" y="20">${esc(isPos ? fit(index.posLabel || 'Your position') : fit(n.label))}</text>
      <text class="sub" x="11" y="35">${esc(fit(sub))}</text>
      ${imp.t ? `<text class="imp${imp.zero ? ' is-zero' : ''}" x="11" y="50">${esc(imp.t)}</text>` : ''}
    </g>`;
  }).join('');
  svg.innerHTML = defs + bands + `<g class="g-edges">${edges}</g><g class="g-nodes">${nodes}</g>`;
  svg.querySelectorAll('.g-node:not(.is-pos)').forEach((g) => {
    const pick = () => onSelect && onSelect(g.dataset.id);
    g.addEventListener('click', pick);
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
  });
  return lay;
}

/** Highlight the server-reported path of a node. blocked = the backend says the failure cannot reach the position. */
export function highlight(svg, path, { blocked = false, selected = null } = {}) {
  const onPath = new Set(path || []);
  const pairs = new Set();
  for (let i = 0; i + 1 < (path || []).length; i++) pairs.add(`${path[i]}->${path[i + 1]}`);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  svg.querySelectorAll('.g-edge').forEach((p) => {
    const k = `${p.dataset.src}->${p.dataset.dst}`;
    const hit = pairs.has(k);
    p.classList.toggle('is-path', hit);
    p.classList.toggle('is-blocked', hit && blocked);
    p.classList.toggle('is-dim', !!selected && !hit);
  });
  svg.querySelectorAll('.g-node').forEach((g) => {
    const id = g.dataset.id;
    g.classList.toggle('is-sel', id === selected);
    g.classList.toggle('is-blockedsel', id === selected && blocked);
    g.classList.toggle('is-onpath', onPath.has(id) && id !== selected && !g.classList.contains('is-pos') && !blocked);
    g.classList.toggle('is-dim', !!selected && !onPath.has(id));
  });
  // hop-by-hop reveal, from the failing node up to the position (the order the backend's path implies)
  if (!reduce && !blocked && path && path.length > 1) {
    const order = [];
    for (let i = path.length - 1; i > 0; i--) order.push(`${path[i - 1]}->${path[i]}`);
    order.forEach((k, j) => {
      const el = [...svg.querySelectorAll('.g-edge')].find((p) => `${p.dataset.src}->${p.dataset.dst}` === k);
      if (!el) return;
      const len = el.getTotalLength();
      el.style.strokeDasharray = `${len}`;
      el.style.strokeDashoffset = `${len}`;
      el.getBoundingClientRect();
      el.style.transition = `stroke-dashoffset 420ms cubic-bezier(.2,.7,.1,1) ${j * 300}ms`;
      el.style.strokeDashoffset = '0';
      setTimeout(() => { el.style.transition = ''; el.style.strokeDasharray = ''; el.style.strokeDashoffset = ''; }, j * 300 + 520);
    });
  }
}

export function legendHtml() {
  return `<span><i></i>reaches the value you hold</span><span><i class="debt"></i>acts only through debt</span>
    <span><i class="exit"></i>changes only the exit cost</span><span><i class="hid"></i>hidden dependency</span><span><i class="path"></i>failure path (backend)</span>`;
}
