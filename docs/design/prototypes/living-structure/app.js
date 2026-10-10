// FAULTLINE · Living structure — isolated feasibility prototype.
// Graph, propagation and conditional loss all come from the EXISTING production modules, imported read-only:
//   normalize()                    public/assets/js/xray/data.js
//   buildIndex/cascade/positionLosses  public/assets/js/xray/model.js
// Nothing here invents a node, an edge or a number.
import * as THREE from './vendor/three.module.min.js';
import { normalize } from '../../../../public/assets/js/xray/data.js';
import { buildIndex, cascade, positionLosses } from '../../../../public/assets/js/xray/model.js';
import { usd } from '../../../../public/assets/js/xray/util.js';

const Q = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches || Q.has('reduced');
const HOP_MS = 520;

// Bottom to top. Same vertical order as the production "Layers" view (graph.js LAYERS, reversed).
const TIERS = ['chain', 'protocol', 'yield', 'oracle', 'amm', 'lending'];
const TIER_NAME = { chain: 'Settlement chain', protocol: 'Protocol', yield: 'Yield source', oracle: 'Oracle', amm: 'PT market', lending: 'Lending market', position: 'Position' };
const WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve'];
const C = { ink: 0x14161b, core: 0x4a5364, lime: 0xd5ff3f, red: 0xd92f17, steel: 0xdfe5ee };

const S = { m: null, mode: 'normal', sel: null, hover: null, casc: null, loss: null, t0: 0, freezeAt: null, lite: Q.has('lite'), flat: Q.has('flat') };
let renderer, scene, camera, raycaster, glass, nodeGroup, edgeGroup, guideGroup, ringSel;
const rimMat = new THREE.MeshBasicMaterial({ color: 0x1b2230, side: THREE.BackSide, transparent: true, opacity: 0.16, depthWrite: false });
const N = new Map(); // id -> { n, pos, r, shell, core, label }
const E = [];        // { e, base, pulse, len }
const tiersUsed = [];
const cam = { az: -0.55, pol: 1.2, dist: 14, fit: 14 }, goal = { ...cam };
let dirty = true, lastActive = 0, bound = 4;

// ---------------------------------------------------------------- layout (deterministic, from the graph)
const hash = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };

function layout(m) {
  const used = TIERS.filter((t) => m.nodes.some((n) => !n.isPos && n.layer === t));
  const gap = 1.05, y0 = -((used.length - 1) * gap) / 2;
  const tierY = Object.fromEntries(used.map((t, i) => [t, y0 + i * gap]));
  const half = Math.max(1, ((used.length - 1) * gap) / 2);
  const P = new Map(), ang = new Map();
  const pos = m.positions;
  const posR = pos.length > 1 ? Math.max(0.95, pos.length * 0.13) : 0;
  pos.forEach((p, i) => { const a = (i / pos.length) * Math.PI * 2; if (pos.length > 1) ang.set(p.id, a); P.set(p.id, new THREE.Vector3(Math.cos(a) * posR, 0, Math.sin(a) * posR)); });

  // breadth-first from the positions along real edges, so a node sits near what depends on it
  const order = [], seen = new Set(pos.map((p) => p.id)), q = pos.map((p) => p.id);
  for (let i = 0; i < q.length; i++) for (const e of m.out.get(q[i])) if (!seen.has(e.dst.id)) { seen.add(e.dst.id); q.push(e.dst.id); order.push(e.dst); }
  for (const n of m.nodes) if (!seen.has(n.id)) order.push(n);
  let k = 0;
  for (const n of order) {
    const nb = [...m.out.get(n.id).map((e) => e.dst.id), ...m.inc.get(n.id).map((e) => e.src.id)].filter((id) => ang.has(id));
    if (nb.length) { let sx = 0, sy = 0; for (const id of nb) { sx += Math.cos(ang.get(id)); sy += Math.sin(ang.get(id)); } ang.set(n.id, Math.atan2(sy, sx) + (hash(n.id) - 0.5) * 0.5); }
    else ang.set(n.id, (k++) * 2.39996 + 0.6);
  }
  const radii = {};
  for (const t of used) {
    const list = m.nodes.filter((n) => !n.isPos && n.layer === t).sort((a, b) => ang.get(a.id) - ang.get(b.id));
    const cnt = list.length;
    if (cnt > 1) { // even slots around the tier, keeping the neighbour-driven order and overall orientation
      const step = (Math.PI * 2) / cnt; let sx = 0, sy = 0;
      list.forEach((n, i) => { const d = ang.get(n.id) - i * step; sx += Math.cos(d); sy += Math.sin(d); });
      const base = Math.atan2(sy, sx); list.forEach((n, i) => ang.set(n.id, base + i * step));
    }
    const y = tierY[t];
    const R = Math.max(2.5, cnt * 0.42, posR + 1.4) * (1 - 0.2 * (y / half) ** 2); // spindle silhouette, not a stack of shelves
    radii[t] = R;
    for (const n of list) { const a = ang.get(n.id), r = R * (0.94 + hash(n.id + 'r') * 0.12); P.set(n.id, new THREE.Vector3(Math.cos(a) * r, y + (hash(n.id + 'y') - 0.5) * 0.3, Math.sin(a) * r)); }
  }
  return { P, tierY, used, radii, half };
}

// ---------------------------------------------------------------- geometry per dependency layer
function lathe(fn) { const pts = []; for (let i = 0; i <= 28; i++) { const t = i / 28; pts.push(new THREE.Vector2(Math.max(0.0001, fn(t)), -1 + 2 * t)); } return new THREE.LatheGeometry(pts, 40); }
const GEO = {
  position: () => new THREE.SphereGeometry(1, 48, 32),
  lending: () => new THREE.SphereGeometry(1, 40, 28).scale(0.86, 1.04, 0.86),
  amm: () => new THREE.SphereGeometry(1, 40, 28).scale(0.5, 1.4, 0.5),
  oracle: () => lathe((t) => Math.sin(Math.PI * t) ** 0.35 * (0.34 + 0.48 * Math.abs(Math.cos(Math.PI * t)) ** 1.3)),
  yield: () => lathe((t) => 0.95 * Math.sin(Math.PI * t) ** 0.8 * (1 - 0.5 * t)),
  protocol: () => new THREE.CapsuleGeometry(0.55, 0.9, 10, 28),
  chain: () => new THREE.SphereGeometry(1, 40, 24).scale(1.15, 0.42, 1.15),
};

function gradientTexture(w, h, paint) { const c = document.createElement('canvas'); c.width = w; c.height = h; paint(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; }

// ---------------------------------------------------------------- scene
function initScene() {
  const canvas = $('stage');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  scene = new THREE.Scene();
  scene.background = gradientTexture(1024, 576, (g, w, h) => {
    const r = g.createRadialGradient(w * 0.1, h * 0.02, 0, w * 0.35, h * 0.3, w * 0.95);
    r.addColorStop(0, '#eef1f6'); r.addColorStop(0.3, '#c9ced9'); r.addColorStop(0.7, '#a9b0bf'); r.addColorStop(1, '#8a91a2');
    g.fillStyle = r; g.fillRect(0, 0, w, h);
  });
  scene.fog = new THREE.Fog(0xaab1c0, 10, 26);
  const envTex = gradientTexture(512, 256, (g, w, h) => {
    const v = g.createLinearGradient(0, 0, 0, h); v.addColorStop(0, '#f6f8fc'); v.addColorStop(0.5, '#b9c0cd'); v.addColorStop(1, '#6f778a'); g.fillStyle = v; g.fillRect(0, 0, w, h);
    const k = g.createRadialGradient(w * 0.3, h * 0.2, 0, w * 0.3, h * 0.2, w * 0.2); k.addColorStop(0, 'rgba(255,255,255,1)'); k.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = k; g.fillRect(0, 0, w, h);
    g.fillStyle = 'rgba(28,34,48,.8)'; g.fillRect(w * 0.6, h * 0.36, w * 0.14, h * 0.4); g.fillRect(w * 0.05, h * 0.5, w * 0.06, h * 0.3); // a dark panel so the glass has something to reflect
  });
  envTex.mapping = THREE.EquirectangularReflectionMapping;
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromEquirectangular(envTex).texture; pm.dispose();
  scene.add(new THREE.HemisphereLight(0xf2f5fa, 0x6c7486, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-6, 8, 5); scene.add(key);
  camera = new THREE.PerspectiveCamera(30, 1, 0.1, 80);
  raycaster = new THREE.Raycaster();
  nodeGroup = new THREE.Group(); edgeGroup = new THREE.Group(); guideGroup = new THREE.Group();
  scene.add(guideGroup, edgeGroup, nodeGroup);
  ringSel = new THREE.Mesh(new THREE.TorusGeometry(1, 0.014, 8, 72), new THREE.MeshBasicMaterial({ color: C.ink }));
  ringSel.visible = false; scene.add(ringSel);
  setMaterial();
  addEventListener('resize', resize); resize();
}

function setMaterial() {
  glass = S.lite
    ? new THREE.MeshStandardMaterial({ color: 0xf2f6fb, transparent: true, opacity: 0.3, roughness: 0.08, metalness: 0.15, envMapIntensity: 1.4, depthWrite: false })
    : new THREE.MeshPhysicalMaterial({ color: 0xf1f5fa, roughness: 0.03, metalness: 0, transmission: 1, thickness: 0.55, ior: 1.22, envMapIntensity: 1.5, specularIntensity: 1, attenuationColor: new THREE.Color(0xb4c2d6), attenuationDistance: 2.4 });
  for (const v of N.values()) v.shell.material = glass;
  $('status').textContent = S.lite ? 'Simplified materials' : '';
  dirty = true;
}

function disposeGroup(g) { for (const o of [...g.children]) { g.remove(o); o.geometry && o.geometry.dispose(); if (o.material && o.material !== glass && o.material !== rimMat) o.material.dispose(); } }

function build(m) {
  disposeGroup(nodeGroup); disposeGroup(edgeGroup); disposeGroup(guideGroup); N.clear(); E.length = 0; $('labels').innerHTML = ''; tiersUsed.length = 0;
  const L = layout(m);
  const maxC = Math.max(1e-9, ...m.nodes.map((n) => n.contrib || 0));
  const dense = m.nodes.length > 20 ? 0.82 : 1;
  for (const n of m.nodes) {
    const single = m.positions.length === 1;
    const r = n.isPos ? (single ? 0.8 : 0.3) : (0.24 + 0.22 * Math.sqrt((n.contrib || 0) / maxC)) * dense;
    const shell = new THREE.Mesh((GEO[n.layer] || GEO.protocol)(), glass);
    shell.scale.setScalar(r); shell.position.copy(L.P.get(n.id)); shell.userData.id = n.id; shell.renderOrder = 2;
    const core = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), new THREE.MeshStandardMaterial({ color: C.core, roughness: 0.45, metalness: 0.1, emissive: 0x000000 }));
    core.scale.setScalar(r * (n.isPos ? 0.2 : 0.26)); core.position.copy(shell.position);
    const rim = new THREE.Mesh(shell.geometry, rimMat); rim.scale.setScalar(r * 1.035); rim.position.copy(shell.position); rim.renderOrder = 1;
    nodeGroup.add(core, rim, shell);
    const label = document.createElement('div'); label.className = 'lbl' + (n.isPos ? ' pos' : ''); label.textContent = n.label; label.style.display = 'none'; $('labels').appendChild(label);
    N.set(n.id, { n, pos: shell.position, r, shell, core, label, w: 0 });
  }
  const up = new THREE.Vector3(0, 1, 0);
  const unit = new THREE.CylinderGeometry(1, 1, 1, 8, 1, true), unitUp = unit.clone().translate(0, 0.5, 0);
  for (const e of m.edges) {
    const a = N.get(e.src.id).pos, b = N.get(e.dst.id).pos, dir = a.clone().sub(b), len = dir.length(); dir.normalize();
    const rad = (0.007 + 0.011 * e.t) * dense;
    const base = new THREE.Mesh(unit, new THREE.MeshStandardMaterial({ color: C.steel, roughness: 0.35, metalness: 0.7, transparent: true, opacity: 0.9 }));
    base.position.copy(a).add(b).multiplyScalar(0.5); base.quaternion.setFromUnitVectors(up, dir); base.scale.set(rad, len, rad);
    // failure travels from the dependency (dst) to whatever depends on it (src)
    const pulse = new THREE.Mesh(unitUp, new THREE.MeshBasicMaterial({ color: C.red }));
    pulse.position.copy(b); pulse.quaternion.setFromUnitVectors(up, dir); pulse.scale.set(rad * 2.4, 0.0001, rad * 2.4); pulse.visible = false;
    edgeGroup.add(base, pulse); E.push({ e, base, pulse, len, rad });
  }
  for (const t of L.used) {
    const pts = []; for (let i = 0; i <= 96; i++) { const a = (i / 96) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * L.radii[t], L.tierY[t], Math.sin(a) * L.radii[t])); }
    guideGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: C.ink, transparent: true, opacity: 0.07 })));
    const el = document.createElement('div'); el.className = 'tier'; el.textContent = TIER_NAME[t]; $('labels').appendChild(el); tiersUsed.push({ y: L.tierY[t], el });
  }
  bound = Math.max(L.half + 0.9, Math.max(...Object.values(L.radii)) + 0.7);
  cam.fit = goal.dist = cam.dist = bound / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * (innerWidth < 860 ? 1.25 : 1.12);
  scene.fog.near = cam.fit - bound * 0.9; scene.fog.far = cam.fit + bound * 3.2;
  for (const v of N.values()) v.w = 0;
  dirty = true;
}

function resize() {
  const c = $('stage'), w = c.clientWidth, h = c.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  if (w >= 860) camera.setViewOffset(w, h, -w * 0.14, h * 0.02, w, h); else camera.clearViewOffset(); // keep the structure right of centre, clear of the text
  camera.updateProjectionMatrix(); dirty = true;
}

// ---------------------------------------------------------------- state
const neighbours = (id) => new Set([...S.m.out.get(id).map((e) => e.dst.id), ...S.m.inc.get(id).map((e) => e.src.id)]);

function select(id, focus = true) {
  const v = N.get(id); if (!v) return;
  S.mode = 'selected'; S.sel = id; S.casc = null; S.loss = null;
  // bring the selection to the near side, off-axis so it never hides behind the position
  if (focus && !S.flat) { const a = Math.atan2(v.pos.x, v.pos.z) - 0.75; let d = a - goal.az; d = Math.atan2(Math.sin(d), Math.cos(d)); goal.az += d; }
  panel(); syncList(); dirty = true;
}
function clearSel() { S.mode = 'normal'; S.sel = null; S.casc = null; S.loss = null; panel(); syncList(); dirty = true; }
function fail(id) {
  const n = S.m.byId.get(id); if (!n || n.isPos) return;
  const failed = new Map([[id, n.lgf]]);           // same call the production X-Ray makes (xray.js)
  S.mode = 'failure'; S.sel = id; S.casc = cascade(S.m, failed); S.loss = positionLosses(S.m, failed); S.t0 = performance.now();
  panel(); syncList(); dirty = true;
}
function failT() { // elapsed, in hops
  const max = (S.casc ? S.casc.maxDepth : 0) + 0.6;
  if (S.freezeAt != null) return S.freezeAt * max;
  if (REDUCED) return max;
  return Math.min(max, (performance.now() - S.t0) / HOP_MS);
}

function panel() {
  const m = S.m, el = $('ctx');
  document.body.classList.toggle('failing', S.mode === 'failure');
  if (S.mode === 'normal') {
    el.innerHTML = `<div class="hint"><svg viewBox="0 0 28 28" fill="none" stroke="#14161b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M15 15l9 3.2-3.9 1.9L18.2 24z"/></svg><span>Select a dependency to see what leans on it.</span></div>
      <div class="row"><button class="primary" id="pick">Show me the largest one</button></div>`;
    $('pick').onclick = () => { const top = m.nodes.filter((n) => !n.isPos).sort((a, b) => (b.contrib || 0) - (a.contrib || 0))[0]; if (top) select(top.id); };
    return;
  }
  const n = m.byId.get(S.sel);
  const dep = m.out.get(n.id).map((e) => e.dst.label), by = m.inc.get(n.id).map((e) => e.src.label);
  if (S.mode === 'selected') {
    const why = m.inc.get(n.id)[0];
    el.innerHTML = `<div class="kind">${esc(TIER_NAME[n.layer] || n.layer)}</div><h2>${esc(n.label)}</h2>
      ${why && why.reason ? `<p>${esc(why.src.label)}: ${esc(why.reason)}.</p>` : ''}
      <dl><dt>Relied on by</dt><dd>${by.length ? by.map(esc).join(', ') : 'nothing directly'}</dd><dt>Depends on</dt><dd>${dep.length ? dep.map(esc).join(', ') : 'nothing further'}</dd></dl>
      <div class="row">${n.isPos ? '' : '<button class="primary" id="doFail">Simulate its failure</button>'}<button class="ghost" id="clr">Clear</button></div>`;
    if (!n.isPos) $('doFail').onclick = () => fail(n.id);
    $('clr').onclick = clearSel; return;
  }
  const ev = S.casc.events.filter((x) => !x.root);
  const hitPos = ev.filter((x) => x.node.isPos);
  el.innerHTML = `<div class="kind">Dependency failure, assumed to happen</div><h2>If ${esc(n.label)} fails</h2>
    <ol>${ev.map((x) => `<li class="${x.node.isPos ? 'pos' : ''}"><span>${esc(x.node.label)}<small>${esc(TIER_NAME[x.node.layer] || '')}, hop ${x.depth}</small></span><b>${Math.round(x.strength * 100)}%</b></li>`).join('') || '<li><span>Nothing depends on it</span><b></b></li>'}</ol>
    <div class="sum">${hitPos.length ? `<b>${esc(usd(S.loss.stay))}</b>conditional loss across ${hitPos.length} position${hitPos.length > 1 ? 's' : ''}, from the existing X-Ray model (loss given failure ${Math.round(n.lgf * 100)}%).` : 'It does not reach a position above the model threshold.'}</div>
    <p class="note">Percentages are how much of the failure is transmitted along the real edges. This is not a price-driven liquidation; the breaking point is a separate analysis and is not shown here.</p>
    <div class="row"><button class="primary" id="again">Replay</button><button class="ghost" id="clr">Clear</button></div>`;
  $('again').onclick = () => { S.freezeAt = null; fail(n.id); }; $('clr').onclick = clearSel;
}

function buildList() {
  const m = S.m, order = ['position', ...[...TIERS].reverse()];
  $('list').innerHTML = order.map((t) => { const ns = m.nodes.filter((n) => n.layer === t); return ns.length ? `<h3>${esc(TIER_NAME[t])}</h3>` + ns.map((n) => `<button data-id="${esc(n.id)}">${esc(n.label)}</button>`).join('') : ''; }).join('');
}
function syncList() { $('list').querySelectorAll('button').forEach((b) => b.setAttribute('aria-current', String(b.dataset.id === S.sel))); }

// ---------------------------------------------------------------- per-frame visuals
const tmp = new THREE.Vector3(), camRight = new THREE.Vector3();
function paint() {
  const sel = S.sel, nb = sel && S.mode === 'selected' ? neighbours(sel) : null;
  const T = S.mode === 'failure' ? failT() : 0, cs = S.casc;
  for (const [id, v] of N) {
    const mat = v.core.material; let c = C.core, em = 0, k = 1;
    if (S.mode === 'selected') { if (id === sel) { c = C.lime; em = 0.9; k = 1.25; } else if (!nb.has(id)) k = 0.8; }
    if (S.mode === 'failure') {
      const d = cs.depth.get(id);
      if (d != null && T >= d) { const s = cs.strength.get(id) || 0, grow = REDUCED || S.freezeAt != null ? 1 : clamp((T - d) / 0.5, 0, 1); c = C.red; em = 0.3 + 0.35 * s; k = 1 + (0.25 + 0.55 * s) * grow; }
      else k = 0.8;
    }
    mat.color.setHex(c); mat.emissive.setHex(em ? c : 0); mat.emissiveIntensity = em; mat.toneMapped = !em;
    v.core.scale.setScalar(v.r * (v.n.isPos ? 0.3 : 0.34) * k);
  }
  const hot = new Map(); if (cs) for (const x of cs.edges) hot.set(x.e, x);
  for (const x of E) {
    const bm = x.base.material; let op = N.size > 20 ? 0.55 : 0.9, hex = C.steel;
    if (S.mode === 'selected') { const on = x.e.src.id === sel || x.e.dst.id === sel; op = on ? 1 : 0.16; hex = on ? C.ink : C.steel; }
    x.pulse.visible = false;
    if (S.mode === 'failure') {
      const h = hot.get(x.e); op = h ? 0.5 : 0.13;
      if (h) { const p = clamp(T - h.from, 0, 1); if (p > 0) { x.pulse.visible = true; const w = x.rad * (h.main ? 2.6 : 1.5); x.pulse.scale.set(w, Math.max(0.0001, x.len * p), w); } }
    }
    bm.opacity = op; bm.color.setHex(hex);
  }
  ringSel.visible = !!sel;
  if (sel) { const v = N.get(sel); ringSel.position.copy(v.pos); ringSel.scale.setScalar(v.r * (v.n.layer === 'amm' ? 1.75 : v.n.layer === 'chain' ? 1.5 : 1.4)); ringSel.quaternion.copy(camera.quaternion); ringSel.material.color.setHex(S.mode === 'failure' ? C.red : C.ink); }
  return S.mode === 'failure' && S.freezeAt == null && !REDUCED && T < cs.maxDepth + 0.6;
}

function labels() {
  const w = $('stage').clientWidth, h = $('stage').clientHeight, many = N.size > 14;
  const show = new Map(); // id -> priority
  const add = (id, p) => { if (!show.has(id) || show.get(id) < p) show.set(id, p); };
  if (S.mode === 'normal') { for (const [id, v] of N) if (!many || v.n.isPos) add(id, v.n.isPos ? 2 : 1); }
  if (S.mode === 'selected') { add(S.sel, 9); for (const id of neighbours(S.sel)) add(id, 5); }
  if (S.mode === 'failure') { const T = failT(); add(S.sel, 9); for (const x of S.casc.events) if (T >= x.depth) add(x.node.id, x.node.isPos ? 8 : 6 - Math.min(4, x.depth) * 0.5 + x.strength); }
  if (S.hover) add(S.hover, 7);
  const cx = tmp.set(0, 0, 0).project(camera).x;
  const placed = [], items = [];
  if (w >= 860) for (const id of ['headline', 'sub', 'src', 'ctx']) { const r = $(id).getBoundingClientRect(); placed.push({ x: r.left - 12, y: r.top - 8, w: r.width + 24, h: r.height + 16 }); } // never write over the text
  if (w >= 860) for (const t of tiersUsed) { tmp.set(0, t.y, 0).project(camera); placed.push({ x: w - 190, y: (-tmp.y * 0.5 + 0.5) * h - 12, w: 190, h: 24 }); }
  for (const [id, v] of N) {
    const el = v.label, pr = show.get(id);
    if (pr == null) { if (el.style.display !== 'none') el.style.display = 'none'; continue; }
    tmp.copy(v.pos).project(camera);
    if (tmp.z > 1) { el.style.display = 'none'; continue; }
    items.push({ id, v, pr: pr - tmp.z * 0.5, sx: (tmp.x * 0.5 + 0.5) * w, sy: (-tmp.y * 0.5 + 0.5) * h, right: tmp.x >= cx });
  }
  items.sort((a, b) => b.pr - a.pr);
  const bodies = [];
  for (const [id, v] of N) { tmp.copy(v.pos).project(camera); if (tmp.z < 1) bodies.push({ id, x: (tmp.x * 0.5 + 0.5) * w, y: (-tmp.y * 0.5 + 0.5) * h, r: 0 }); }
  camRight.setFromMatrixColumn(camera.matrixWorld, 0);
  const pxR = (v) => { tmp.copy(v.pos).project(camera); const a = tmp.x; tmp.copy(v.pos).addScaledVector(camRight, v.r).project(camera); return Math.abs(tmp.x - a) * 0.5 * w; };
  for (const b of bodies) b.r = pxR(N.get(b.id)) * 0.9;
  for (const it of items) {
    const el = it.v.label;
    el.className = 'lbl' + (it.v.n.isPos ? ' pos' : '') + (it.id === S.sel ? (S.mode === 'failure' ? ' hit' : ' sel') : '');
    if (el.style.display === 'none') el.style.display = '';
    if (!it.v.w) it.v.w = el.offsetWidth; const lw = it.v.w + (it.id === S.sel ? 8 : 0), lh = 26, off = pxR(it.v) * 1.25 + 10;
    const y = it.sy - lh / 2, xs = it.right ? [it.sx + off, it.sx - off - lw] : [it.sx - off - lw, it.sx + off];
    const free = (x) => x >= 8 && x + lw <= w - 8 && !placed.some((r) => x < r.x + r.w + 6 && x + lw + 6 > r.x && y < r.y + r.h + 4 && y + lh + 4 > r.y)
      && !bodies.some((b) => b.id !== it.id && x < b.x + b.r && x + lw > b.x - b.r && y < b.y + b.r && y + lh > b.y - b.r);
    let x = xs.find(free);
    if (x == null) { if (it.pr < 5) { el.style.display = 'none'; continue; } x = clamp(xs[0], 8, w - lw - 8); }
    placed.push({ x, y, w: lw, h: lh }); el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
  }
  for (const t of tiersUsed) { tmp.set(0, t.y, 0).project(camera); t.el.style.transform = `translateY(${((-tmp.y * 0.5 + 0.5) * h - 10).toFixed(1)}px)`; }
}

function placeCamera() {
  const s = Math.sin(cam.pol);
  camera.position.set(cam.dist * s * Math.sin(cam.az), cam.dist * Math.cos(cam.pol), cam.dist * s * Math.cos(cam.az));
  camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
}

// ---------------------------------------------------------------- loop, with measured frame times
const perf = { warm: 0, dts: [], done: false, last: 0, auto: [] };
function frame(now) {
  requestAnimationFrame(frame);
  if (!S.m || S.flat) return;
  const k = REDUCED ? 1 : 0.14; let moving = false;
  for (const key of ['az', 'pol', 'dist']) { const d = goal[key] - cam[key]; if (Math.abs(d) > 1e-4) { cam[key] += d * k; moving = true; } else cam[key] = goal[key]; }
  if (Q.has('perf') && !perf.done) { goal.az += 0.004; moving = true; }
  if (moving || dirty) lastActive = now;
  const animating = S.mode === 'failure' && S.freezeAt == null && !REDUCED && failT() < S.casc.maxDepth + 0.6;
  if (!(moving || dirty || animating || now - lastActive < 120)) { perf.last = 0; return; } // render on demand: an idle page costs nothing
  dirty = false;
  placeCamera(); paint(); renderer.render(scene, camera); labels();
  if (perf.last) {
    const dt = now - perf.last;
    if (!S.lite && !Q.has('perf') && perf.auto.length < 40) { perf.auto.push(dt); if (perf.auto.length === 40) { const med = [...perf.auto].sort((a, b) => a - b)[20]; if (med > 42) { S.lite = true; setMaterial(); } } }
    if (Q.has('perf') && !perf.done) { if (perf.warm++ > 45) perf.dts.push(dt); if (perf.dts.length >= 240) report(); }
  }
  perf.last = now;
}
function report() {
  perf.done = true; const a = [...perf.dts].sort((x, y) => x - y), avg = a.reduce((s, x) => s + x, 0) / a.length;
  const gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info'), inf = renderer.info;
  const out = { dataset: Q.get('data') || 'sample', nodes: N.size, edges: E.length, material: S.lite ? 'lite' : 'transmission', viewport: `${innerWidth}x${innerHeight}@${renderer.getPixelRatio()}`,
    frames: a.length, avg_ms: +avg.toFixed(2), median_ms: +a[a.length >> 1].toFixed(2), p95_ms: +a[Math.floor(a.length * 0.95)].toFixed(2), max_ms: +a[a.length - 1].toFixed(2),
    draw_calls: inf.render.calls, triangles: inf.render.triangles, geometries: inf.memory.geometries, textures: inf.memory.textures,
    gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown', ua: navigator.userAgent.replace(/^.*(Chrome\/[\d.]+).*$/, '$1') };
  $('perf').textContent = JSON.stringify(out, null, 1);
  fetch('/__perf', { method: 'POST', body: JSON.stringify(out) }).catch(() => {});
}

// ---------------------------------------------------------------- input
function bind() {
  const c = $('stage'); let down = null;
  const pick = (ev) => { const r = c.getBoundingClientRect(); raycaster.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), camera); const hit = raycaster.intersectObjects([...N.values()].map((v) => v.shell), false)[0]; return hit ? hit.object.userData.id : null; };
  c.addEventListener('pointerdown', (ev) => { down = { x: ev.clientX, y: ev.clientY, moved: 0 }; c.setPointerCapture(ev.pointerId); });
  c.addEventListener('pointermove', (ev) => {
    if (down) { const dx = ev.clientX - down.x, dy = ev.clientY - down.y; down.moved += Math.abs(dx) + Math.abs(dy); down.x = ev.clientX; down.y = ev.clientY;
      if (down.moved > 5) { c.classList.add('drag'); goal.az -= dx * 0.006; goal.pol = clamp(goal.pol - dy * 0.004, 0.72, 1.72); } return; }
    const id = pick(ev); if (id !== S.hover) { S.hover = id; c.classList.toggle('hot', !!id); dirty = true; }
  });
  c.addEventListener('pointerup', (ev) => { const was = down; down = null; c.classList.remove('drag'); if (was && was.moved <= 5) { const id = pick(ev); if (id) select(id); else if (S.mode !== 'normal') clearSel(); } });
  c.addEventListener('pointerleave', () => { if (S.hover) { S.hover = null; dirty = true; } });
  c.addEventListener('wheel', (ev) => { ev.preventDefault(); goal.dist = clamp(goal.dist * Math.exp(ev.deltaY * 0.001), cam.fit * 0.6, cam.fit * 1.45); }, { passive: false });
  c.addEventListener('keydown', (ev) => { const k = ev.key; if (k === 'ArrowLeft') goal.az -= 0.2; else if (k === 'ArrowRight') goal.az += 0.2; else if (k === 'ArrowUp') goal.pol = clamp(goal.pol - 0.1, 0.72, 1.72); else if (k === 'ArrowDown') goal.pol = clamp(goal.pol + 0.1, 0.72, 1.72); else if (k === '+' || k === '=') goal.dist = Math.max(cam.fit * 0.6, goal.dist * 0.9); else if (k === '-') goal.dist = Math.min(cam.fit * 1.45, goal.dist * 1.1); else return; ev.preventDefault(); });
  addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && S.mode !== 'normal') clearSel(); if ((ev.key === 'r' || ev.key === 'R') && !ev.metaKey && !ev.ctrlKey) resetView(); });
  $('reset').onclick = resetView;
  $('viewList').onclick = () => { const l = $('list'); l.hidden = !l.hidden; $('viewList').setAttribute('aria-expanded', String(!l.hidden)); };
  $('list').addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) select(b.dataset.id); });
  $('d11').onclick = () => load('sample'); $('d44').onclick = () => load('large');
}
function resetView() { goal.az = -0.55; goal.pol = 1.2; goal.dist = cam.fit; dirty = true; }

// ---------------------------------------------------------------- data
async function load(which) {
  const file = which === 'large' ? 'sample-large' : 'sample';
  const r = await fetch(`../../../../public/data/${file}.json`, { cache: 'no-store' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const payload = await r.json();
  const m = buildIndex(normalize(payload));
  S.m = m; S.mode = 'normal'; S.sel = null; S.casc = null; S.hover = null;
  $('d11').setAttribute('aria-pressed', String(which !== 'large')); $('d44').setAttribute('aria-pressed', String(which === 'large'));
  const deps = m.nodes.filter((n) => !n.isPos).length, np = m.positions.length;
  $('headline').textContent = `${WORDS[deps] || deps} ${deps === 1 ? 'thing holds' : 'things hold'} ${np > 1 ? `these ${WORDS[np] ? WORDS[np].toLowerCase() : np} positions` : 'this position'} up.`;
  $('sub').textContent = 'Each body is one dependency. Each filament is a real link between two of them. Height is the dependency layer.';
  $('src').textContent = `${m.position.label} · ${m.nodes.length} nodes, ${m.edges.length} links · ${payload.source ? 'saved run of the real pipeline' : (m.position.meta && m.position.meta.synthetic ? 'synthetic demo book' : 'bundled example')}`;
  buildList(); if (!S.flat) { build(m); resetView(); cam.az = goal.az; cam.pol = goal.pol; }
  panel();
}

(async function main() {
  try { if (S.flat) throw new Error('flat requested'); initScene(); }
  catch (e) { S.flat = true; document.body.classList.add('no3d'); $('list').hidden = false; $('status').textContent = '3D view unavailable here. The list gives the same dependencies and the same simulation.'; }
  bind();
  try { await load(Q.get('data') === 'large' ? 'large' : 'sample'); }
  catch (e) { $('headline').textContent = 'The example data did not load.'; $('sub').textContent = 'Serve the repository root over HTTP and open this page from there (see README). ' + e.message; return; }
  if (Q.get('az')) cam.az = goal.az = +Q.get('az');
  if (Q.get('at') != null) S.freezeAt = clamp(+Q.get('at'), 0, 1);
  if (Q.get('select')) { select(Q.get('select')); if (!S.flat) cam.az = goal.az; }
  if (Q.get('fail')) { select(Q.get('fail')); if (!S.flat) cam.az = goal.az; fail(Q.get('fail')); if (S.freezeAt == null && Q.has('end')) S.freezeAt = 1; }
  if (Q.has('list')) { $('list').hidden = false; }
  requestAnimationFrame(frame);
})();
