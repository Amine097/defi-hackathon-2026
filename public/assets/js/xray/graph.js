import { clamp, reducedMotion } from './util.js';

const FALLBACK = { chain: '#7f8c9a', yield: '#2ecc71', oracle: '#f1c40f', amm: '#3498db', lending: '#b05cf0', protocol: '#ec6fb0', position: '#ff8a3d' };
const VAR = { chain: '--layer-chain', yield: '--layer-yield', oracle: '--layer-oracle', amm: '--layer-amm', lending: '--layer-lending', position: '--layer-position', protocol: '--layer-protocol' };
export const LAYERS = [
  { key: 'position', name: 'Position / pocket' },
  { key: 'lending', name: 'L5 Lending' },
  { key: 'amm', name: 'L4 PT market / AMM' },
  { key: 'oracle', name: 'L3 Oracle' },
  { key: 'yield', name: 'L2 Yield source / issuer' },
  { key: 'protocol', name: 'Other protocol' },
  { key: 'chain', name: 'L1 Chain' },
];
const RANK = Object.fromEntries(LAYERS.map((l, i) => [l.key, i]));
const RED = '#ff4d4d';
const DASH = '#9b87f5';

export function layerColors() {
  const cs = getComputedStyle(document.documentElement);
  const out = {};
  for (const k of Object.keys(FALLBACK)) out[k] = (cs.getPropertyValue(VAR[k]) || '').trim() || FALLBACK[k];
  return out;
}

function hexA(hex, a) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h.slice(0, 6), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function mix(hexA_, hexB, k) {
  const p = (h) => { const n = parseInt(h.replace('#', '').slice(0, 6), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
  const a = p(hexA_), b = p(hexB);
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * k));
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

function abbrev(n) {
  if (n.isPos) {
    const m = n.label.match(/^P\d+\b/);
    return m ? m[0] : n.id.length <= 4 ? n.id.toUpperCase() : 'YOU';
  }
  const KNOWN = { ethereum: 'ETH', arbitrum: 'ARB', optimism: 'OP', polygon: 'MATIC', chainlink: 'LINK', avalanche: 'AVAX', solana: 'SOL', bitcoin: 'BTC' };
  const first = n.label.split(/[\s/(]+/).filter(Boolean)[0] || n.id;
  const k = KNOWN[first.toLowerCase()];
  if (k) return k;
  const clean = first.replace(/[^A-Za-z0-9\-.]/g, '');
  return clean.length <= 7 ? clean : clean.slice(0, 6) + '…';
}

const LOGO_ALIAS = {
  ethereum: 'eth.svg', weth: 'eth.svg', arbitrum: 'arbitrum.webp',
  tether: 'usdt.svg', circle: 'usdc.svg', wsteth: 'steth.svg', lido: 'lido.webp',
  chainlink: 'link.svg', wbtc: 'btc.svg', bitcoin: 'btc.svg',
  usde: 'ethena.webp', susde: 'ethena.webp', ethena: 'ethena.webp',
  weeth: 'etherfi.webp', eeth: 'etherfi.webp', etherfi: 'etherfi.webp',
  rseth: 'kelp.webp', kelp: 'kelp.webp',
  usds: 'sky.svg', susds: 'sky.svg', ausdc: 'aave.svg',
  morpho: 'morpho.webp', redstone: 'redstone.webp',
  eigenlayer: 'eigenlayer.webp', eigencloud: 'eigenlayer.webp',
  curve: 'curve.webp', euler: 'euler.webp',
};
const logoCache = new Map();
function logoPath(n) {
  const fallback = `/assets/layers/${n.layer}.svg`;
  if (n.isPos) return { path: fallback, fallback };
  const label = n.label.toLowerCase();
  const provider = String(n.meta.provider || '').toLowerCase();
  if (n.layer === 'oracle') {
    if (label.includes('chainlink') || provider.includes('chainlink')) return { path: '/assets/logos/link.svg', fallback };
    if (label.includes('redstone') || provider.includes('redstone')) return { path: '/assets/logos/redstone.webp', fallback };
    if (label.includes('pendle') || /^pt[-\s]/.test(label)) return { path: '/assets/logos/pendle.svg', fallback };
    return { path: fallback, fallback };
  }
  if (n.layer === 'amm' && /^pt[-\s]/.test(label)) return { path: '/assets/logos/pendle.svg', fallback };
  const word = (n.label.split(/[\s/(]+/).filter(Boolean)[0] || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!word || ['cex', 'pt', 'position'].includes(word)) return { path: fallback, fallback };
  return { path: `/assets/logos/${LOGO_ALIAS[word] || `${word}.svg`}`, fallback };
}
function logoFor(n) {
  const { path, fallback } = logoPath(n);
  const key = `${path}|${fallback}`;
  if (!logoCache.has(key)) {
    const img = new Image();
    img.onerror = () => {
      if (img.src.endsWith(fallback)) img.failed = true;
      else img.src = fallback;
    };
    img.src = path;
    logoCache.set(key, img);
  }
  const img = logoCache.get(key);
  return !img.failed && img.complete && img.naturalWidth ? img : null;
}

function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; }

function makeStars(size = 640) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  for (let i = 0; i < 140; i++) {
    const x = Math.random() * size, y = Math.random() * size, r = Math.random() < 0.08 ? 1.3 : Math.random() * 0.8 + 0.2;
    g.fillStyle = `rgba(${180 + Math.random() * 60 | 0},${190 + Math.random() * 50 | 0},255,${0.15 + Math.random() * 0.5})`;
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  return c;
}

export function createGraph(canvas, model, cb) {
  const ctx = canvas.getContext('2d');
  const COL = layerColors();
  const stars = makeStars();
  const cam = { x: 0, y: 0, k: 1 };
  const camTarget = { x: 0, y: 0, k: 1, active: false };
  let W = 0, H = 0, dpr = 1;
  let alpha = 1, alphaTarget = 0;
  let mode = 'force';
  let hover = null, selected = null, focus = null;
  let cascadeState = null;
  let raf = 0;
  let tipEl = cb.tipEl;

  const maxContrib = Math.max(1e-9, ...model.nodes.filter((n) => !n.isPos).map((n) => n.contrib));
  const maxValue = Math.max(1e-9, ...model.positions.map((n) => n.value));
  const N = model.nodes.map((n, i) => {
    const deg = model.inc.get(n.id).length;
    const share = n.isPos ? 0 : n.contrib / maxContrib;
    const r = n.isPos ? 13 + 8 * Math.sqrt(n.value / maxValue) : clamp(8 + 17 * Math.sqrt(share) + 1.6 * Math.sqrt(deg), 8, 30);
    const ang = (i / model.nodes.length) * Math.PI * 2;
    const rank = RANK[n.layer] ?? 3;
    return { n, r, share, color: COL[n.layer] || COL.protocol, label: abbrev(n), seed: hash(n.id),
      x: Math.cos(ang) * 200 + (Math.random() - 0.5) * 40, y: (rank - 3) * 70 + Math.sin(ang) * 80, vx: 0, vy: 0,
      pinned: false, hit: 0, hitAt: Infinity, root: false, tx: 0, ty: 0 };
  });
  const byId = new Map(N.map((s) => [s.n.id, s]));
  const E = model.edges.map((e) => ({ e, s: byId.get(e.src.id), d: byId.get(e.dst.id), seed: hash(e.src.id + '>' + e.dst.id), on: false, from: 0, to: 0, main: false }));
  const big = N.length > 30;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const ow = W, oh = H;
    W = Math.max(1, rect.width); H = Math.max(1, rect.height);
    dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    if (ow) { cam.x += (W - ow) / 2; cam.y += (H - oh) / 2; camTarget.x += (W - ow) / 2; camTarget.y += (H - oh) / 2; }
  }

  function layerTargets() {
    const rows = LAYERS.map((l) => l.key).filter((k) => N.some((s) => s.n.layer === k));
    const gap = clamp(560 / Math.max(1, rows.length - 1), 85, 125);
    const byRow = rows.map((k) => N.filter((s) => s.n.layer === k).sort((a, b) => a.x - b.x));
    byRow.forEach((row, ri) => row.forEach((s, i) => { s.ty = (ri - (rows.length - 1) / 2) * gap; s.tx = i; }));
    const nb = (s) => [...model.out.get(s.n.id).map((e) => byId.get(e.dst.id)), ...model.inc.get(s.n.id).map((e) => byId.get(e.src.id))];
    for (let it = 0; it < 6; it++) {
      byRow.forEach((row) => {
        const space = Math.max(62, Math.max(...row.map((s) => s.r)) * 2 + 34);
        row.forEach((s) => { const ns = nb(s); s._b = ns.length ? ns.reduce((a, o) => a + o.tx, 0) / ns.length : s.tx; });
        row.sort((a, b) => a._b - b._b);
        row.forEach((s, i) => { s.tx = (i - (row.length - 1) / 2) * space; });
      });
    }
    return rows.map((k, ri) => ({ key: k, y: (ri - (rows.length - 1) / 2) * gap }));
  }
  let rowsInfo = [];

  function tick() {
    if (alpha < 0.002 && alphaTarget === 0) return;
    const a = alpha;
    const layered = mode === 'layers';
    for (let i = 0; i < N.length; i++) {
      const p = N[i];
      for (let j = i + 1; j < N.length; j++) {
        const q = N[j];
        let dx = p.x - q.x, dy = p.y - q.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = (Math.random() - 0.5); dy = (Math.random() - 0.5); d2 = 1; }
        const d = Math.sqrt(d2);
        let f = (layered ? 900 : big ? 4200 : 2600) * a / d2;
        const minD = p.r + q.r + (big ? 14 : 36);
        if (d < minD) f += (minD - d) * 0.25;
        const fx = dx / d * f, fy = dy / d * f;
        p.vx += fx; p.vy += fy; q.vx -= fx; q.vy -= fy;
      }
    }
    if (!layered) {
      for (const l of E) {
        const dx = l.d.x - l.s.x, dy = l.d.y - l.s.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const rest = 55 + (l.s.r + l.d.r) * 1.6 + (big ? 10 : 30);
        const f = (d - rest) * 0.03 * a * (0.55 + 0.45 * l.e.t);
        l.s.vx += dx / d * f; l.s.vy += dy / d * f; l.d.vx -= dx / d * f; l.d.vy -= dy / d * f;
      }
    }
    for (const s of N) {
      if (layered) {
        s.vx += (s.tx - s.x) * 0.09 * Math.max(a, 0.2);
        s.vy += (s.ty - s.y) * 0.12 * Math.max(a, 0.2);
      } else {
        s.vx += -s.x * 0.006 * a;
        s.vy += (((RANK[s.n.layer] ?? 3) - 3) * 62 - s.y) * 0.012 * a;
      }
    }
    for (const s of N) {
      if (s === drag || s.pinned) { s.vx = s.vy = 0; continue; }
      s.vx *= 0.55; s.vy *= 0.55;
      s.x += clamp(s.vx, -40, 40); s.y += clamp(s.vy, -40, 40);
    }
    alpha += ((alphaTarget || 0) - alpha) * 0.018;
  }

  function bounds() {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const s of N) { x0 = Math.min(x0, s.x - s.r - 30); x1 = Math.max(x1, s.x + s.r + 30); y0 = Math.min(y0, s.y - s.r - 20); y1 = Math.max(y1, s.y + s.r + 28); }
    if (mode === 'layers') x0 -= 120;
    return { x0, y0, x1, y1 };
  }

  function fit(instant) {
    const b = bounds();
    const padT = 64, padB = 56, padX = 30;
    const k = clamp(Math.min((W - padX * 2) / (b.x1 - b.x0), (H - padT - padB) / (b.y1 - b.y0)), 0.25, 1.8);
    camTarget.k = k;
    camTarget.x = W / 2 - ((b.x0 + b.x1) / 2) * k;
    camTarget.y = padT + (H - padT - padB) / 2 - ((b.y0 + b.y1) / 2) * k;
    camTarget.active = true;
    if (instant || reducedMotion()) { Object.assign(cam, { x: camTarget.x, y: camTarget.y, k: camTarget.k }); camTarget.active = false; }
  }

  function setLayout(m) {
    mode = m;
    N.forEach((s) => { s.pinned = false; });
    if (m === 'layers') rowsInfo = layerTargets();
    alpha = 1;
    if (reducedMotion()) { for (let i = 0; i < 250; i++) tick(); fit(true); }
    else setTimeout(() => fit(), 700);
  }

  const toWorld = (sx, sy) => ({ x: (sx - cam.x) / cam.k, y: (sy - cam.y) / cam.k });

  function curve(l) {
    const x1 = l.s.x, y1 = l.s.y, x2 = l.d.x, y2 = l.d.y;
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const bend = len * 0.12;
    const cx = (x1 + x2) / 2 - dy / len * bend, cy = (y1 + y2) / 2 + dx / len * bend;
    const ux = (cx - x1), uy = (cy - y1), ul = Math.hypot(ux, uy) || 1;
    const vx = (x2 - cx), vy = (y2 - cy), vl = Math.hypot(vx, vy) || 1;
    const sx = x1 + ux / ul * l.s.r, sy = y1 + uy / ul * l.s.r;
    const ex = x2 - vx / vl * (l.d.r + 3), ey = y2 - vy / vl * (l.d.r + 3);
    return { sx, sy, cx, cy, ex, ey, ang: Math.atan2(vy, vx) };
  }
  const qpt = (g, t) => {
    const u = 1 - t;
    return { x: u * u * g.sx + 2 * u * t * g.cx + t * t * g.ex, y: u * u * g.sy + 2 * u * t * g.cy + t * t * g.ey };
  };

  function pickNode(wx, wy) {
    let best = null, bd = Infinity;
    for (const s of N) {
      const d = Math.hypot(s.x - wx, s.y - wy);
      if (d < s.r + 4 / cam.k && d < bd) { best = s; bd = d; }
    }
    return best;
  }
  function pickEdge(wx, wy) {
    const tol = 6 / cam.k;
    let best = null, bd = tol;
    for (const l of E) {
      const g = curve(l);
      for (let i = 1; i < 16; i++) {
        const p = qpt(g, i / 16);
        const d = Math.hypot(p.x - wx, p.y - wy);
        if (d < bd) { bd = d; best = l; }
      }
    }
    return best;
  }

  function nodeVisible(s) { return !focus || focus.has(s.n.id); }
  function edgeVisible(l) { return !focus || (focus.has(l.s.n.id) && focus.has(l.d.n.id)); }

  function draw(now) {
    const rm = reducedMotion();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const ox = ((cam.x * 0.15) % 640 + 640) % 640, oy = ((cam.y * 0.15) % 640 + 640) % 640;
    for (let x = ox - 640; x < W; x += 640) for (let y = oy - 640; y < H; y += 640) ctx.drawImage(stars, x, y);

    ctx.setTransform(dpr * cam.k, 0, 0, dpr * cam.k, dpr * cam.x, dpr * cam.y);
    const k = cam.k;
    const px = 1 / k;

    if (mode === 'layers' && rowsInfo.length) {
      const b = bounds();
      ctx.font = `600 ${11 * px}px system-ui, sans-serif`;
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      for (const row of rowsInfo) {
        ctx.fillStyle = hexA(COL[row.key] || '#8a94a8', 0.05);
        ctx.fillRect(b.x0 + 4, row.y - 34, b.x1 - b.x0 - 8, 68);
        ctx.fillStyle = hexA(COL[row.key] || '#8a94a8', 0.85);
        ctx.fillText((LAYERS.find((l) => l.key === row.key) || {}).name || row.key, b.x0 + 12, row.y);
      }
    }

    const hl = selected || hover;
    for (const l of E) {
      const g = curve(l);
      const vis = edgeVisible(l);
      const near = hl && hl.type === 'node' && (l.s === hl.s || l.d === hl.s);
      const hovE = hover && hover.type === 'edge' && hover.l === l;
      const on = l.on && now >= l.startAt;
      let a = vis ? (big ? 0.28 : 0.42) : 0.05;
      if (near || hovE) a = 0.95;
      const wScreen = (0.7 + 2.4 * l.e.t) * clamp(k, 0.7, 1.5);
      ctx.beginPath(); ctx.moveTo(g.sx, g.sy); ctx.quadraticCurveTo(g.cx, g.cy, g.ex, g.ey);
      if (on) {
        const since = now - l.startAt;
        const pulse = rm ? 0.8 : 0.55 + 0.45 * Math.max(0, 1 - since / 1400) + 0.12 * Math.sin(now / 260 + l.seed * 6);
        ctx.setLineDash([]);
        ctx.strokeStyle = hexA(RED, 0.18 * pulse); ctx.lineWidth = (wScreen + 7) * px; ctx.stroke();
        ctx.strokeStyle = hexA(RED, clamp(pulse, 0.3, 1)); ctx.lineWidth = (wScreen + 0.6) * px; ctx.stroke();
      } else {
        if (l.e.t < 0.5) { ctx.setLineDash([4 * px, 4 * px]); ctx.strokeStyle = hexA(DASH, a * 1.1); }
        else {
          ctx.setLineDash([]);
          const gr = ctx.createLinearGradient(g.sx, g.sy, g.ex, g.ey);
          gr.addColorStop(0, hexA(l.s.color, a)); gr.addColorStop(1, hexA(l.d.color, a));
          ctx.strokeStyle = gr;
        }
        ctx.lineWidth = wScreen * px; ctx.stroke();
      }
      ctx.setLineDash([]);
      if (vis || near) {
        const ah = (5 + 2 * l.e.t) * px * clamp(k, 0.8, 1.4);
        ctx.save(); ctx.translate(g.ex, g.ey); ctx.rotate(g.ang);
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-ah * 1.6, ah * 0.75); ctx.lineTo(-ah * 1.6, -ah * 0.75); ctx.closePath();
        ctx.fillStyle = on ? RED : l.e.t < 0.5 ? hexA(DASH, Math.min(1, a * 1.4)) : hexA(l.d.color, Math.min(1, a * 1.5));
        ctx.fill(); ctx.restore();
      }
      if (!rm && on) {
        const travel = now - l.startAt;
        if (l.wave && travel < l.dur) drawParticle(g, 1 - travel / l.dur, 3.4 * px, 1);
        const ph = (now / 1500 + l.seed) % 1;
        drawParticle(g, 1 - ph, 2.1 * px, 0.75);
      } else if (!rm && (near || hovE) && !on) {
        const ph = (now / 1800 + l.seed) % 1;
        drawParticle(g, 1 - ph, 2 * px, 0.8, l.d.color);
      }
    }

    const order = [...N].sort((a, b) => (a === hl?.s) - (b === hl?.s) || a.hit - b.hit || a.r - b.r);
    for (const s of order) drawNode(s, now, rm, px, k);
  }

  function drawParticle(g, t, r, a, col) {
    const p = qpt(g, clamp(t, 0, 1));
    const c = col || '#ff9a7a';
    const gr = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 3.2);
    gr.addColorStop(0, hexA('#ffffff', a)); gr.addColorStop(0.3, hexA(c, a)); gr.addColorStop(1, hexA(c, 0));
    ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(p.x, p.y, r * 3.2, 0, Math.PI * 2); ctx.fill();
  }

  function shape(s, r) {
    ctx.beginPath();
    ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
  }

  function drawNode(s, now, rm, px, k) {
    const vis = nodeVisible(s);
    const isHit = s.hit > 0 && now >= s.hitAt;
    const isSel = selected && selected.s === s;
    const isHov = hover && hover.type === 'node' && hover.s === s;
    ctx.globalAlpha = vis ? 1 : 0.16;
    const col = isHit ? mix(s.color, RED, clamp(0.35 + s.hit * 0.65, 0, 1)) : s.color;
    const breathe = rm ? 0 : Math.sin(now / 900 + s.seed * 10) * 0.5 + 0.5;
    const r = s.r;

    const haloK = isHit ? 0.55 + 0.35 * s.hit : s.share > 0.3 ? s.share * 0.45 : s.n.isPos ? 0.25 : 0;
    if (haloK > 0) {
      const hr = r * (2.3 + (isHit ? 0.5 * breathe : 0.25 * breathe));
      const gr = ctx.createRadialGradient(s.x, s.y, r * 0.6, s.x, s.y, hr);
      gr.addColorStop(0, hexA(isHit ? RED : s.color, 0.5 * haloK)); gr.addColorStop(1, hexA(isHit ? RED : s.color, 0));
      ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(s.x, s.y, hr, 0, Math.PI * 2); ctx.fill();
    }
    if (isHit && !rm) {
      const since = now - s.hitAt;
      const period = s.root ? 2200 : 1e9;
      const ph = since < 1600 ? since / 1600 : s.root ? ((since - 1600) % period) / 1600 : 2;
      if (ph <= 1) {
        ctx.strokeStyle = hexA(RED, 0.7 * (1 - ph)); ctx.lineWidth = 2 * px;
        ctx.beginPath(); ctx.arc(s.x, s.y, r + 4 + ph * (40 + r), 0, Math.PI * 2); ctx.stroke();
      }
    }

    const gr = ctx.createRadialGradient(s.x - r * 0.35, s.y - r * 0.4, r * 0.1, s.x, s.y, r);
    gr.addColorStop(0, hexA(col, isHit ? 0.95 : 0.75)); gr.addColorStop(0.55, hexA(col, 0.28)); gr.addColorStop(1, '#0b0f17');
    shape(s, r); ctx.fillStyle = '#0b0f17'; ctx.fill(); ctx.fillStyle = gr; ctx.fill();
    ctx.lineWidth = (isSel || isHov ? 2.6 : s.n.isPos ? 2.4 : 1.8) * Math.max(px, 0.6);
    ctx.strokeStyle = col; ctx.stroke();
    if (r * k > 9) { shape(s, r - 3); ctx.lineWidth = 0.7 * px; ctx.strokeStyle = hexA('#ffffff', 0.12); ctx.stroke(); }

    const logo = r * k >= 10 ? logoFor(s.n) : null;
    if (logo) {
      const lr = r - 3.5;
      ctx.save(); ctx.beginPath(); ctx.arc(s.x, s.y, lr, 0, Math.PI * 2); ctx.clip();
      ctx.fillStyle = '#0b0f17'; ctx.fillRect(s.x - lr, s.y - lr, lr * 2, lr * 2);
      ctx.drawImage(logo, s.x - lr, s.y - lr, lr * 2, lr * 2); ctx.restore();
    } else if (r * k >= 13) {
      const fs = clamp(r * 0.5, 7, 13) * (s.label.length > 5 ? 0.85 : 1);
      ctx.font = `700 ${fs}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = hexA('#ffffff', 0.92); ctx.fillText(s.label, s.x, s.y + 0.5);
    }
    if (isSel) {
      ctx.save(); ctx.setLineDash([5 * px, 4 * px]); ctx.lineDashOffset = rm ? 0 : -now / 40 * px;
      ctx.strokeStyle = hexA('#ffffff', 0.85); ctx.lineWidth = 1.4 * px;
      ctx.beginPath(); ctx.arc(s.x, s.y, r + 6, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    }
    const dense = big && k < 1.15;
    const showLabel = isSel || isHov || s.root || (!dense) || r >= 17 || (focus && vis && focus.size <= 14) || (isHit && s.hit >= 0.6 && !s.n.isPos);
    if (showLabel) {
      const text = s.n.isPos && s.label !== 'YOU' && s.n.label.startsWith(s.label) && !(isSel || isHov) ? (dense ? '' : s.n.label.slice(s.label.length).replace(/^[\s·:-]+/, '')) : s.n.label;
      ctx.font = `${isSel || isHov ? 600 : 500} ${11.5 * px}px system-ui, sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.lineWidth = 3.2 * px; ctx.strokeStyle = 'rgba(8,10,16,.92)';
      const ly = s.y + r + 5 * px + (isSel ? 5 : 0);
      ctx.strokeText(text, s.x, ly);
      ctx.fillStyle = isHit ? '#ffb4b4' : '#d4dbea'; ctx.fillText(text, s.x, ly);
    }
    if (isHit && !s.root && (s.lossFrac != null || (s.hit < 0.999 && (!dense || isHov || isSel)))) {
      const t = s.lossFrac != null ? `−${Math.round(s.lossFrac * 100)}% value` : `${Math.round(s.hit * 100)}% shock`;
      ctx.font = `700 ${10 * px}px system-ui, sans-serif`;
      const w = ctx.measureText(t).width + 8 * px;
      const bx = s.x + r * 0.7, by = s.y - r - 6 * px;
      ctx.fillStyle = RED; roundRect(bx - 2 * px, by - 7 * px, w, 14 * px, 7 * px); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(t, bx + 2 * px, by);
    }
    ctx.globalAlpha = 1;
  }
  function roundRect(x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  function frame(now) {
    tick();
    if (camTarget.active) {
      const f = 0.14;
      cam.x += (camTarget.x - cam.x) * f; cam.y += (camTarget.y - cam.y) * f; cam.k += (camTarget.k - cam.k) * f;
      if (Math.abs(camTarget.k - cam.k) < 0.001 && Math.abs(camTarget.x - cam.x) < 0.5) camTarget.active = false;
    }
    draw(now);
    raf = requestAnimationFrame(frame);
  }

  // ---- interaction
  let drag = null, panning = null, moved = false, downAt = null;
  const pointers = new Map();
  let pinch = null;
  const local = (ev) => { const r = canvas.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; };

  function showTip(ev, item) {
    if (!tipEl) return;
    if (!item) { tipEl.hidden = true; return; }
    tipEl.innerHTML = cb.tipHtml(item);
    tipEl.hidden = false;
    const r = canvas.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    const tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
    tipEl.style.left = `${clamp(x + 16, 6, W - tw - 6)}px`;
    tipEl.style.top = `${y + 16 + th > H ? y - th - 12 : y + 16}px`;
  }

  canvas.addEventListener('pointerdown', (ev) => {
    canvas.setPointerCapture(ev.pointerId);
    pointers.set(ev.pointerId, local(ev));
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), k: cam.k, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, x: cam.x, y: cam.y };
      drag = null; panning = null; moved = true;
      return;
    }
    const p = local(ev); const w = toWorld(p.x, p.y);
    downAt = p; moved = false; camTarget.active = false;
    const s = pickNode(w.x, w.y);
    if (s) { drag = s; canvas.style.cursor = 'grabbing'; } else { panning = { x: p.x, y: p.y, cx: cam.x, cy: cam.y }; canvas.style.cursor = 'grabbing'; }
  });
  canvas.addEventListener('pointermove', (ev) => {
    const p = local(ev);
    if (pointers.has(ev.pointerId)) pointers.set(ev.pointerId, p);
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const k = clamp(pinch.k * Math.hypot(a.x - b.x, a.y - b.y) / (pinch.d || 1), 0.2, 4);
      cam.x = pinch.cx - (pinch.cx - pinch.x) * (k / pinch.k); cam.y = pinch.cy - (pinch.cy - pinch.y) * (k / pinch.k); cam.k = k;
      return;
    }
    if (downAt && Math.hypot(p.x - downAt.x, p.y - downAt.y) > 4) moved = true;
    if (drag && moved) {
      const w = toWorld(p.x, p.y); drag.x = w.x; drag.y = w.y; drag.pinned = mode === 'force';
      if (mode === 'force') { alphaTarget = 0.25; alpha = Math.max(alpha, 0.25); }
      showTip(ev, null);
      return;
    }
    if (panning) { cam.x = panning.cx + p.x - panning.x; cam.y = panning.cy + p.y - panning.y; return; }
    const w = toWorld(p.x, p.y);
    const s = pickNode(w.x, w.y);
    const l = s ? null : pickEdge(w.x, w.y);
    hover = s ? { type: 'node', s } : l ? { type: 'edge', l } : null;
    canvas.style.cursor = s ? 'pointer' : l ? 'help' : 'grab';
    showTip(ev, s ? { type: 'node', n: s.n, hit: s.hit > 0 && performance.now() >= s.hitAt ? s.hit : 0 } : l ? { type: 'edge', e: l.e } : null);
  });
  const end = (ev) => {
    pointers.delete(ev.pointerId);
    if (pinch) { if (pointers.size < 2) pinch = null; downAt = null; return; }
    const wasDrag = drag;
    if (!moved && downAt) {
      const w = toWorld(downAt.x, downAt.y);
      const s = pickNode(w.x, w.y);
      if (s) cb.onNodeClick(s.n, { shift: ev.shiftKey || ev.ctrlKey || ev.metaKey });
      else cb.onBackgroundClick();
    }
    if (wasDrag && mode === 'force') alphaTarget = 0;
    drag = null; panning = null; downAt = null;
    canvas.style.cursor = 'grab';
  };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', () => { if (!drag && !panning) { hover = null; showTip(null, null); } });
  canvas.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    camTarget.active = false;
    const p = local(ev);
    const k = clamp(cam.k * Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015)), 0.2, 4);
    cam.x = p.x - (p.x - cam.x) * (k / cam.k); cam.y = p.y - (p.y - cam.y) * (k / cam.k); cam.k = k;
  }, { passive: false });
  canvas.addEventListener('dblclick', (ev) => {
    const p = local(ev); const w = toWorld(p.x, p.y);
    const s = pickNode(w.x, w.y);
    if (s) { s.pinned = false; alpha = Math.max(alpha, 0.3); } else fit();
  });

  const ro = new ResizeObserver(() => resize());
  ro.observe(canvas);
  resize();
  for (let i = 0; i < 320; i++) tick();
  fit(true);
  alpha = reducedMotion() ? 0 : 0.08;
  raf = requestAnimationFrame(frame);

  return {
    fit: () => fit(),
    setLayout,
    get layout() { return mode; },
    select(id) { const s = id ? byId.get(id) : null; selected = s ? { type: 'node', s } : null; },
    setFocus(set) { focus = set && set.size ? set : null; },
    centerOn(id) {
      const s = byId.get(id); if (!s) return;
      const inset = cb.leftInset ? cb.leftInset() : 0;
      camTarget.k = Math.max(cam.k, 0.9); camTarget.x = inset + (W - inset) / 2 - s.x * camTarget.k; camTarget.y = H / 2 - s.y * camTarget.k; camTarget.active = true;
      if (reducedMotion()) { Object.assign(cam, { x: camTarget.x, y: camTarget.y, k: camTarget.k }); camTarget.active = false; }
    },
    playCascade(c, hopMs, posLoss) {
      const t0 = performance.now();
      cascadeState = c;
      for (const s of N) { s.hit = 0; s.hitAt = Infinity; s.root = false; s.lossFrac = posLoss?.get(s.n.id); }
      for (const l of E) l.on = false;
      for (const [id, st] of c.strength) {
        const s = byId.get(id); if (!s) continue;
        s.hit = st; s.hitAt = t0 + c.depth.get(id) * hopMs; s.root = c.depth.get(id) === 0;
      }
      const lookup = new Map(E.map((l) => [l.e, l]));
      for (const x of c.edges) {
        const l = lookup.get(x.e); if (!l) continue;
        l.on = true; l.startAt = t0 + x.from * hopMs; l.dur = Math.max(1, (x.to - x.from) * hopMs); l.wave = x.to === x.from + 1;
      }
    },
    clearCascade() {
      cascadeState = null;
      for (const s of N) { s.hit = 0; s.hitAt = Infinity; s.root = false; }
      for (const l of E) l.on = false;
    },
    destroy() { cancelAnimationFrame(raf); ro.disconnect(); },
  };
}
