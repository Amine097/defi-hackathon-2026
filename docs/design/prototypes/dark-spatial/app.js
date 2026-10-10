// FAULTLINE · Dark spatial intelligence — isolated prototype (Mission 7). Two visual variants, one code path.
// Graph, propagation, conditional loss and formatting come from the EXISTING production modules, imported read-only.
// Every visual distinction below maps to a field of the payload; nothing is invented.
import * as THREE from '../living-structure/vendor/three.module.min.js';
import { normalize } from '../../../../public/assets/js/xray/data.js';
import { buildIndex, cascade, positionLosses, closure, decisionView } from '../../../../public/assets/js/xray/model.js';

const Q = new URLSearchParams(location.search);
const V = document.body.dataset.variant === 'b' ? 'b' : 'a';
const F = window.FaultLine;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches || Q.has('reduced');
const HOP_MS = V === 'b' ? 900 : 700;
const WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve'];

// ---- semantic system: one row per backend `layer` (data.js LAYER_ALIAS). Order = top to bottom, as in the production Layers view.
const KIND = {
  position: { name: 'Position', plural: 'Positions', color: 0xefe9dc, css: 'var(--c-position)', glyph: '<circle cx="9" cy="9" r="5.2"/><ellipse cx="9" cy="9" rx="8" ry="2.6" fill="none" stroke="currentColor" stroke-width="1.3"/>' },
  lending: { name: 'Lending market', plural: 'Lending markets', color: 0xc9d0de, css: 'var(--c-lending)', glyph: '<rect x="3.5" y="3.5" width="11" height="11"/>' },
  amm: { name: 'PT market', plural: 'PT markets', color: 0x3987e5, css: 'var(--c-amm)', glyph: '<circle cx="9" cy="9" r="5" fill="none" stroke="currentColor" stroke-width="3.4"/>' },
  oracle: { name: 'Oracle', plural: 'Oracles', color: 0xc98500, css: 'var(--c-oracle)', glyph: '<path d="M9 1.5 16 9 9 16.5 2 9z"/>' },
  yield: { name: 'Asset or yield source', plural: 'Assets and yield sources', color: 0x199e70, css: 'var(--c-yield)', glyph: '<ellipse cx="9" cy="9" rx="7" ry="3.6"/>' },
  protocol: { name: 'Protocol', plural: 'Protocols', color: 0xd55b9d, css: 'var(--c-protocol)', glyph: '<path d="M9 1.8 15.2 5.4v7.2L9 16.2 2.8 12.6V5.4z"/>' },
  chain: { name: 'Blockchain', plural: 'Blockchains', color: 0x6f7c93, css: 'var(--c-chain)', glyph: '<rect x="1.5" y="6.5" width="15" height="5"/>' },
};
const TIER_ORDER = ['position', 'lending', 'amm', 'oracle', 'yield', 'protocol', 'chain'];
const glyph = (k) => `<svg viewBox="0 0 18 18" fill="currentColor" style="color:${KIND[k].css}" aria-hidden="true">${KIND[k].glyph}</svg>`;
const GEO = {
  position: () => new THREE.SphereGeometry(1, 48, 32),
  lending: () => new THREE.BoxGeometry(1.5, 1.5, 1.5),
  amm: () => new THREE.TorusGeometry(0.82, 0.34, 20, 48).rotateX(Math.PI / 2),
  oracle: () => new THREE.OctahedronGeometry(1.15, 0),
  yield: () => new THREE.CylinderGeometry(1, 1, 0.5, 40),
  protocol: () => new THREE.CylinderGeometry(0.95, 0.95, 1.25, 6),
  chain: () => new THREE.BoxGeometry(2.1, 0.42, 2.1),
};
const TH = V === 'b'
  ? { bg: ['#101a30', '#070b15', '#03050a'], fog: 0x05080f, fogK: [0.55, 2.3], fov: 34, pol: 1.3, az: 0.42, metal: 0.72, rough: 0.26, env: 1.5, key: 2.6, rim: 2.2, edge: 0x8fa2c8, signal: 0xff5d47, offX: 0.13, glow: true }
  : { bg: ['#0f182b', '#0a111f', '#070b15'], fog: 0x080d18, fogK: [0.9, 3.4], fov: 25, pol: 1.22, az: 0.3, metal: 0.45, rough: 0.42, env: 1.15, key: 2.3, rim: 1.4, edge: 0xa9b6d0, signal: 0xff5d47, offX: 0.14, glow: false };

const S = { payload: null, m: null, mode: 'normal', sel: null, selGroup: null, focus: null, expanded: null, hover: null, casc: null, loss: null, t0: 0, freezeAt: null, flat: Q.has('flat'), view: null, which: 'sample' };
let renderer, scene, camera, raycaster, nodeGroup, edgeGroup, fxGroup, ringSel;
const N = new Map();   // id -> visual record for a real node
const G = new Map();   // layer -> visual record for an aggregate (dense overview only)
const E = [];          // one record per real edge
const GE = [];         // pooled lines: position -> aggregate
const tierEls = new Map();
const cam = { az: TH.az, pol: TH.pol, dist: 14, fit: 14, ty: 0 }, goal = { ...cam };
let dirty = true, lastActive = 0;
const hash = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };
const tex = (w, h, paint) => { const c = document.createElement('canvas'); c.width = w; c.height = h; paint(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; };

// ---------------------------------------------------------------- what is shown (progressive disclosure, never altering the graph)
const hopsFrom = (m, posIds, id) => { let h = Infinity; for (const p of posIds) { const b = m.reach.get(p).get(id); if (b) h = Math.min(h, b.minHops); } return h; };
function computeView() {
  const m = S.m, multi = m.positions.length > 1;
  const v = { ids: new Set(), groups: [], gedges: [], edges: new Set(), anchors: [], dimPos: new Set(), ghost: new Set(), overview: false };
  if (S.mode === 'failure' && !multi) { // one position: keep the structure where it is, let the untouched parts recede
    for (const n of m.nodes) { v.ids.add(n.id); if (!S.casc.depth.has(n.id)) v.ghost.add(n.id); } for (const e of m.edges) v.edges.add(e); v.anchors = [m.positions[0].id]; return v;
  }
  if (S.mode === 'failure') {           // a book: only what the failure actually touches
    for (const x of S.casc.events) v.ids.add(x.node.id);
    for (const x of S.casc.edges) v.edges.add(x.e);
    v.anchors = S.casc.events.filter((x) => x.node.isPos).map((x) => x.node.id);
    if (!v.anchors.length) v.anchors = m.positions.map((p) => p.id);
    return v;
  }
  if (!multi) { for (const n of m.nodes) v.ids.add(n.id); for (const e of m.edges) v.edges.add(e); v.anchors = [m.positions[0].id]; return v; }
  if (!S.focus) {                       // dense book, nothing chosen: positions + one aggregate per dependency layer
    v.overview = true;
    for (const p of m.positions) v.ids.add(p.id);
    v.anchors = m.positions.map((p) => p.id);
    for (const t of TIER_ORDER.slice(1)) { const mem = m.nodes.filter((n) => !n.isPos && n.layer === t); if (mem.length) v.groups.push({ layer: t, members: mem }); }
    for (const p of m.positions) for (const g of v.groups) { const c = g.members.filter((n) => m.reach.get(p.id).has(n.id)).length; if (c) v.gedges.push({ pos: p.id, layer: g.layer, count: c }); }
    return v;
  }
  const anchors = new Set([S.focus]);   // one position's real subgraph
  for (const id of m.reach.get(S.focus).keys()) v.ids.add(id);
  if (S.expanded) for (const id of closure(m, S.expanded, 'down')) { v.ids.add(id); if (m.byId.get(id).isPos) anchors.add(id); }
  for (const p of m.positions) if (!v.ids.has(p.id)) { v.ids.add(p.id); v.dimPos.add(p.id); }
  for (const e of m.edges) if (v.ids.has(e.src.id) && v.ids.has(e.dst.id) && !v.dimPos.has(e.src.id)) v.edges.add(e);
  v.anchors = [...anchors]; return v;
}

// ---------------------------------------------------------------- layout: height = layer, distance from the axis = hops from the position
function layoutView(v) {
  const m = S.m, P = new Map(), ang = new Map();
  const shown = [...v.ids].map((id) => m.byId.get(id));
  const tiers = TIER_ORDER.filter((t) => shown.some((n) => n.layer === t) || v.groups.some((g) => g.layer === t));
  const gap = v.overview ? 1.1 : 1.12, top = ((tiers.length - 1) * gap) / 2;
  const tierY = Object.fromEntries(tiers.map((t, i) => [t, top - i * gap]));
  const pos = shown.filter((n) => n.isPos), act = pos.filter((n) => !v.dimPos.has(n.id)), dim = pos.filter((n) => v.dimPos.has(n.id));
  const fan = (list, R, spread, y) => list.forEach((n, i) => { const a = list.length > 1 ? -spread + (2 * spread * i) / (list.length - 1) : 0; ang.set(n.id, a); P.set(n.id, new THREE.Vector3(Math.sin(a) * R, y, Math.cos(a) * R)); });
  if (v.overview) fan(act, 4.6, 1.3, tierY.position);
  else { fan(act, act.length > 1 ? 1.5 : 0, 0.9, tierY.position); dim.forEach((n, i) => { const a = Math.PI + (i - (dim.length - 1) / 2) * 0.34; P.set(n.id, new THREE.Vector3(Math.sin(a) * 4.6, tierY.position + 0.15, Math.cos(a) * 4.6)); }); }
  v.groups.forEach((g, i) => { const a = (i % 2 ? 0.55 : -0.55); P.set('g:' + g.layer, new THREE.Vector3(Math.sin(a) * 1.7, tierY[g.layer], Math.cos(a) * 1.7)); });

  const deps = shown.filter((n) => !n.isPos);
  const hop = new Map(deps.map((n) => [n.id, hopsFrom(m, v.anchors, n.id)]));
  const finite = [...hop.values()].filter(Number.isFinite), maxHop = finite.length ? Math.max(...finite) : 1;
  for (const [id, h] of hop) if (!Number.isFinite(h)) hop.set(id, maxHop + 1);
  const inView = (e) => v.edges.has(e);
  const direct = deps.filter((n) => hop.get(n.id) === 1).sort((a, b) => TIER_ORDER.indexOf(a.layer) - TIER_ORDER.indexOf(b.layer) || a.id.localeCompare(b.id));
  if (act.length === 1) direct.forEach((n, i) => ang.set(n.id, direct.length > 1 ? -1.05 + (2.1 * i) / (direct.length - 1) : 0));
  const order = [...deps].sort((a, b) => hop.get(a.id) - hop.get(b.id) || a.id.localeCompare(b.id));
  for (const n of order) {
    if (ang.has(n.id)) continue;
    const par = [...m.inc.get(n.id).filter(inView).map((e) => e.src.id), ...m.out.get(n.id).filter(inView).map((e) => e.dst.id)].filter((id) => ang.has(id));
    if (par.length) { let sx = 0, sy = 0; for (const id of par) { sx += Math.sin(ang.get(id)); sy += Math.cos(ang.get(id)); } ang.set(n.id, Math.atan2(sx, sy) + (hash(n.id) - 0.5) * 0.3); }
    else ang.set(n.id, (hash(n.id) - 0.5) * 2.2);
  }
  const rad = (n) => Math.min(2.0 + 1.15 * (hop.get(n.id) - 1), 5.2) + (act.length > 1 ? 1.2 : 0);
  for (const t of tiers) { // keep bodies of one layer apart along the arc
    const list = deps.filter((n) => n.layer === t).sort((a, b) => ang.get(a.id) - ang.get(b.id));
    for (let it = 0; it < 60; it++) for (let i = 0; i + 1 < list.length; i++) {
      const a = list[i], b = list[i + 1], need = 1.15 / ((rad(a) + rad(b)) / 2), d = ang.get(b.id) - ang.get(a.id);
      if (d < need) { const push = (need - d) / 2; ang.set(a.id, ang.get(a.id) - push); ang.set(b.id, ang.get(b.id) + push); }
    }
    for (const n of list) { const a = ang.get(n.id), r = rad(n); P.set(n.id, new THREE.Vector3(Math.sin(a) * r, tierY[t] + (hash(n.id + 'y') - 0.5) * 0.24, Math.cos(a) * r)); }
  }
  let R = 2; for (const p of P.values()) R = Math.max(R, Math.hypot(p.x, p.z));
  return { P, tierY, tiers, hop, bound: Math.max(top + 1.2, R + 0.9) };
}

// ---------------------------------------------------------------- scene
function initScene() {
  renderer = new THREE.WebGLRenderer({ canvas: $('stage'), antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = V === 'b' ? 1.12 : 1.02;
  scene = new THREE.Scene();
  scene.background = tex(1024, 576, (g, w, h) => {
    const r = g.createRadialGradient(w * 0.62, h * (V === 'b' ? 0.34 : 0.42), 0, w * 0.62, h * 0.45, w * 0.78);
    r.addColorStop(0, TH.bg[0]); r.addColorStop(0.5, TH.bg[1]); r.addColorStop(1, TH.bg[2]); g.fillStyle = r; g.fillRect(0, 0, w, h);
  });
  scene.fog = new THREE.Fog(TH.fog, 10, 30);
  const env = tex(512, 256, (g, w, h) => { // studio: dark room, one soft key, one cool rim strip
    g.fillStyle = '#05070c'; g.fillRect(0, 0, w, h);
    const k = g.createRadialGradient(w * 0.3, h * 0.22, 0, w * 0.3, h * 0.22, w * 0.2); k.addColorStop(0, '#ffffff'); k.addColorStop(0.5, 'rgba(190,205,235,.55)'); k.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = k; g.fillRect(0, 0, w, h);
    const r = g.createLinearGradient(w * 0.7, 0, w * 0.86, 0); r.addColorStop(0, 'rgba(0,0,0,0)'); r.addColorStop(0.5, 'rgba(120,160,255,.75)'); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.fillRect(w * 0.7, h * 0.25, w * 0.16, h * 0.5);
    const f = g.createLinearGradient(0, h * 0.75, 0, h); f.addColorStop(0, 'rgba(0,0,0,0)'); f.addColorStop(1, 'rgba(60,80,120,.45)'); g.fillStyle = f; g.fillRect(0, h * 0.75, w, h * 0.25);
  });
  env.mapping = THREE.EquirectangularReflectionMapping;
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromEquirectangular(env).texture; pm.dispose();
  scene.add(new THREE.HemisphereLight(0x9fb2d8, 0x0a0f1a, V === 'b' ? 0.5 : 0.75));
  const key = new THREE.DirectionalLight(0xfff4e6, TH.key); key.position.set(-5, 9, 6); scene.add(key);
  const rim = new THREE.DirectionalLight(0x6f9bff, TH.rim); rim.position.set(7, 2, -6); scene.add(rim);
  camera = new THREE.PerspectiveCamera(TH.fov, 1, 0.1, 90);
  raycaster = new THREE.Raycaster();
  nodeGroup = new THREE.Group(); edgeGroup = new THREE.Group(); fxGroup = new THREE.Group(); scene.add(edgeGroup, nodeGroup, fxGroup);
  ringSel = new THREE.Mesh(new THREE.TorusGeometry(1, 0.022, 8, 96), new THREE.MeshBasicMaterial({ color: 0xffffff, fog: false })); ringSel.visible = false; fxGroup.add(ringSel);
  if (TH.glow) { // B only: a soft pool of light and static dust for depth. Sprites, not post-processing.
    const pool = new THREE.Mesh(new THREE.PlaneGeometry(26, 26), new THREE.MeshBasicMaterial({ map: tex(256, 256, (g, w) => { const r = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); r.addColorStop(0, 'rgba(90,120,190,.34)'); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.fillRect(0, 0, w, w); }), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    pool.rotation.x = -Math.PI / 2; pool.position.y = -5.2; pool.name = 'pool'; scene.add(pool);
    const pts = new Float32Array(360 * 3); for (let i = 0; i < 360; i++) { pts[i * 3] = (hash('x' + i) - 0.5) * 26; pts[i * 3 + 1] = (hash('y' + i) - 0.5) * 16; pts[i * 3 + 2] = (hash('z' + i) - 0.5) * 26; }
    const dust = new THREE.Points(new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(pts, 3)), new THREE.PointsMaterial({ color: 0x9db4e6, size: 0.035, transparent: true, opacity: 0.5, depthWrite: false }));
    scene.add(dust);
  }
  addEventListener('resize', resize); resize();
}
const glowTex = () => tex(128, 128, (g, w) => { const r = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,120,90,.7)'); r.addColorStop(1, 'rgba(255,90,60,0)'); g.fillStyle = r; g.fillRect(0, 0, w, w); });
let GLOW, HALO;

const STEEL = new THREE.Color(0xc3ccdd);
const tint = (kind) => (kind === 'position' ? new THREE.Color(KIND.position.color) : new THREE.Color(KIND[kind].color).lerp(STEEL, V === 'b' ? 0.3 : 0.22));
function makeBody(kind, isGroup) {
  const mat = new THREE.MeshStandardMaterial({ color: tint(kind), metalness: kind === 'position' ? 0.25 : TH.metal, roughness: kind === 'position' ? 0.3 : TH.rough, envMapIntensity: TH.env, transparent: true, flatShading: kind === 'oracle' || kind === 'protocol' });
  const mesh = new THREE.Mesh(GEO[kind](), mat);
  if (kind === 'position') { const ring = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.035, 8, 96).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0xefe9dc, metalness: 0.6, roughness: 0.3, transparent: true })); ring.rotation.z = 0.32; mesh.add(ring); mesh.userData.ring = ring; }
  if (kind === 'position' && TH.glow) { const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: HALO || (HALO = tex(128, 128, (g, w) => { const r = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2); r.addColorStop(0, 'rgba(255,244,225,.55)'); r.addColorStop(0.4, 'rgba(150,175,235,.16)'); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.fillRect(0, 0, w, w); })), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false })); halo.scale.setScalar(5.2); mesh.add(halo); mesh.userData.halo = halo; }
  if (isGroup) { const sh = new THREE.Mesh(mesh.geometry, new THREE.MeshBasicMaterial({ color: KIND[kind].color, wireframe: true, transparent: true, opacity: 0.35 })); sh.scale.setScalar(1.28); mesh.add(sh); mesh.userData.shell = sh; }
  return mesh;
}
function rec(mesh, r, label) {
  const arc = new THREE.Mesh(new THREE.TorusGeometry(1, 0.05, 8, 80, Math.PI * 2), new THREE.MeshBasicMaterial({ color: TH.signal, fog: false })); arc.visible = false; fxGroup.add(arc);
  return { mesh, r, label, pos: mesh.position, tgt: new THREE.Vector3(), a: 0, ta: 0, s: 1, ts: 1, arc, arcFor: -1, w: 0, hop: 0 };
}
function mkLabel(cls, text) { const el = document.createElement('div'); el.className = 'lbl ' + cls; el.textContent = text; el.style.display = 'none'; $('labels').appendChild(el); return el; }

function build(m) {
  for (const g of [nodeGroup, edgeGroup, fxGroup]) for (const o of [...g.children]) { if (o === ringSel) continue; g.remove(o); o.traverse((c) => { c.geometry && c.geometry.dispose(); c.material && c.material.dispose(); }); }
  N.clear(); G.clear(); E.length = 0; GE.length = 0; tierEls.clear(); $('labels').innerHTML = '';
  if (TH.glow && !GLOW) GLOW = glowTex();
  const single = m.positions.length === 1, maxC = Math.max(1e-9, ...m.nodes.map((n) => n.contrib || 0)), dense = single ? 1 : 0.86;
  for (const n of m.nodes) {
    const r = n.isPos ? (single ? 0.74 : 0.36) : (0.2 + 0.19 * Math.sqrt((n.contrib || 0) / maxC)) * dense; // size = node_contrib_usd
    const mesh = makeBody(n.layer, false); mesh.userData.id = n.id; nodeGroup.add(mesh);
    N.set(n.id, Object.assign(rec(mesh, r, mkLabel(n.isPos ? 'pos' : '', n.label)), { n }));
  }
  for (const t of TIER_ORDER.slice(1)) { const mem = m.nodes.filter((n) => !n.isPos && n.layer === t); if (!mem.length || single) continue;
    const mesh = makeBody(t, true); mesh.userData.group = t; nodeGroup.add(mesh);
    G.set(t, Object.assign(rec(mesh, 0.26 + 0.018 * mem.length, mkLabel('grp', `${KIND[t].plural} · ${mem.length}`)), { layer: t, members: mem })); }
  const unit = new THREE.CylinderGeometry(1, 1, 1, 8, 1, true), unitUp = unit.clone().translate(0, 0.5, 0);
  for (const e of m.edges) {
    const base = new THREE.Mesh(unit, new THREE.MeshBasicMaterial({ color: TH.edge, transparent: true, opacity: 0 }));
    const fill = new THREE.Mesh(unitUp, new THREE.MeshBasicMaterial({ color: TH.signal, transparent: true, fog: false })); fill.visible = false;
    const head = TH.glow ? new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false })) : new THREE.Mesh(new THREE.SphereGeometry(1, 14, 10), new THREE.MeshBasicMaterial({ color: 0xffffff, fog: false }));
    head.visible = false;
    const arrow = new THREE.Mesh(new THREE.ConeGeometry(1, 2.6, 12), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, fog: false })); arrow.visible = false;
    edgeGroup.add(base, fill, head, arrow);
    E.push({ e, base, fill, head, arrow, a: 0, ta: 0, direct: e.src.isPos }); // direct = the position itself holds this link
  }
  for (let i = 0; i < m.positions.length * 6; i++) { const l = new THREE.Mesh(unit, new THREE.MeshBasicMaterial({ color: TH.edge, transparent: true, opacity: 0 })); l.visible = false; edgeGroup.add(l); GE.push({ mesh: l, a: 0, ta: 0, from: null, to: null, w: 0 }); }
  for (const t of TIER_ORDER) { const el = document.createElement('div'); el.className = 'tier'; el.innerHTML = `<span>${esc(KIND[t].plural)}</span>${glyph(t)}`; el.style.display = 'none'; $('labels').appendChild(el); tierEls.set(t, el); }
  applyView(true);
}

// recompute what is visible and where it should sit; bodies then ease to their targets
function applyView(snap) {
  const m = S.m, v = S.view = computeView(), L = v.L = layoutView(v);
  for (const [id, x] of N) { const on = v.ids.has(id), p = L.P.get(id); x.ta = on ? (v.dimPos.has(id) ? 0.28 : v.ghost.has(id) ? 0.16 : 1) : 0; x.ts = v.dimPos.has(id) ? 0.6 : (v.overview ? 0.7 : 1); x.hop = L.hop.get(id) || 0; if (p) x.tgt.copy(p); if (snap || REDUCED || (x.a < 0.02 && on)) { x.pos.copy(x.tgt); if (snap || REDUCED) { x.a = x.ta; x.s = x.ts; } } }
  for (const [t, x] of G) { const on = v.groups.some((g) => g.layer === t), p = L.P.get('g:' + t); x.ta = on ? 1 : 0; if (p) x.tgt.copy(p); if (snap || REDUCED || x.a < 0.02) { x.pos.copy(x.tgt); if (snap || REDUCED) x.a = x.ta; } }
  for (const x of E) x.ta = v.edges.has(x.e) ? 1 : 0;
  GE.forEach((g, i) => { const d = v.gedges[i]; g.ta = d ? 1 : 0; if (d) { g.from = N.get(d.pos); g.to = G.get(d.layer); g.w = d.count; } });
  cam.fit = L.bound / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * (innerWidth < 860 ? 1.2 : v.overview ? 1.22 : 1.08);
  goal.dist = clamp(goal.dist, cam.fit * 0.6, cam.fit * 1.45); if (snap) goal.dist = cam.dist = cam.fit; else goal.dist = cam.fit;
  scene.fog.near = cam.fit - L.bound * TH.fogK[0]; scene.fog.far = cam.fit + L.bound * TH.fogK[1];
  for (const x of [...N.values(), ...G.values()]) x.w = 0;
  dirty = true;
}
function resize() {
  const c = $('stage'), w = c.clientWidth, h = c.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  if (w >= 860) camera.setViewOffset(w, h, -w * TH.offX, 0, w, h); else camera.clearViewOffset();
  camera.updateProjectionMatrix(); dirty = true;
}

// ---------------------------------------------------------------- state
const nbr = (id) => new Set([...S.m.out.get(id).map((e) => e.dst.id), ...S.m.inc.get(id).map((e) => e.src.id)]);
const anchorIds = () => (S.focus ? [S.focus] : S.m.positions.map((p) => p.id));
function face(v) { if (S.flat || !v) return; const a = Math.atan2(v.tgt.x, v.tgt.z) - 0.35; let d = a - goal.az; d = Math.atan2(Math.sin(d), Math.cos(d)); goal.az += d * 0.7; }
function select(id, opt = {}) {
  const m = S.m, n = m.byId.get(id); if (!n) return;
  const multi = m.positions.length > 1;
  S.mode = 'selected'; S.casc = null; S.loss = null; S.selGroup = null;
  if (multi && n.isPos) { S.focus = id; S.expanded = null; }
  else if (multi && !S.focus) { const p = m.positions.find((q) => m.reach.get(q.id).has(id)); S.focus = p ? p.id : null; }
  else if (multi && S.focus && !m.reach.get(S.focus).has(id) && !(S.expanded && closure(m, S.expanded, 'down').has(id))) { const p = m.positions.find((q) => m.reach.get(q.id).has(id)); if (p) { S.focus = p.id; S.expanded = null; } }
  S.sel = id; applyView(opt.snap); if (opt.focus !== false) face(N.get(id)); panel(); syncList();
}
function selectGroup(layer) { S.mode = 'selected'; S.sel = null; S.selGroup = layer; S.casc = null; panel(); syncList(); dirty = true; }
function clearSel() { S.mode = 'normal'; S.sel = null; S.selGroup = null; S.casc = null; S.loss = null; S.expanded = null; applyView(); panel(); syncList(); }
function backToBook() { S.focus = null; clearSel(); resetView(); }
function fail(id, opt = {}) {
  const n = S.m.byId.get(id); if (!n || n.isPos) return;
  const failed = new Map([[id, n.lgf]]);                          // same call as the production X-Ray (xray.js)
  S.mode = 'failure'; S.sel = id; S.selGroup = null; S.casc = cascade(S.m, failed); S.loss = positionLosses(S.m, failed); S.t0 = performance.now();
  applyView(opt.snap); panel(); syncList();
}
const failEnd = () => (S.casc ? S.casc.maxDepth : 0) + 0.8;
function failT() { if (S.freezeAt != null) return S.freezeAt * failEnd(); if (REDUCED) return failEnd(); return Math.min(failEnd(), (performance.now() - S.t0) / HOP_MS); }

// ---------------------------------------------------------------- HTML information layer (real payload fields only)
const kindRow = (k, extra) => `<div class="kind">${glyph(k)}<span>${esc(KIND[k].name)}${extra ? ' · ' + esc(extra) : ''}</span></div>`;
function finance() { // position context; every number is read from the payload
  const p = S.payload, m = S.m, d = decisionView(m.decision), liq = p.liquidation, syn = m.position.meta && m.position.meta.synthetic;
  const deps = m.nodes.filter((n) => !n.isPos && n.contrib > 0).sort((a, b) => b.contrib - a.contrib), tot = deps.reduce((s, n) => s + n.contrib, 0);
  const bp = liq && liq.mode === 'borrower_position' && liq.distance_to_liquidation_pct != null
    ? `<dd>Collateral price −${(liq.distance_to_liquidation_pct * 100).toFixed(1)}%<small>reference borrower, health factor ${Number(liq.health_factor).toFixed(2)}. A price shock, separate from dependency failures.</small></dd>`
    : `<dd>Not available<small>${liq && liq.mode ? 'no leveraged position in this run' : 'not in this payload'}</small></dd>`;
  return `<dl>
    <dt>Size</dt><dd>${F.fmtUsd(m.totalValue || m.position.value_usd)}<small>${m.horizon} day horizon${syn ? ' · synthetic demo book' : ''}</small></dd>
    <dt>Largest dependency</dt><dd>${deps.length ? esc(deps[0].label) + `<small>${F.fmtPct(deps[0].contrib / tot, 0)} of modeled loss</small>` : 'Not available'}</dd>
    <dt>Engine verdict</dt><dd>${esc(d.verdict || 'Not available')}${d.verdict === 'REVIEW' ? `<small>leans ${esc(d.point)}, not a firm call</small>` : ''}</dd></dl>
    <details><summary>Stay or exit, and breaking point</summary><dl>
    <dt>If you stay</dt><dd>${F.fmtUsd(d.stay)}<small>expected loss over the horizon</small></dd>
    <dt>If you exit</dt><dd>${F.fmtUsd(d.exit)}<small>execution plus carry forgone</small></dd>
    <dt>Breaking point</dt>${bp}</dl></details>`;
}
function panel() {
  const m = S.m, el = $('ctx'), multi = m.positions.length > 1;
  document.body.classList.toggle('failing', S.mode === 'failure');
  if (S.mode === 'normal' && !S.focus) {
    el.innerHTML = `${kindRow('position', multi ? `${m.positions.length} positions` : '')}<h2>${esc(m.position.label)}</h2>${finance()}
      <div class="row"><button class="primary" id="pick">${multi ? 'Open the largest position' : 'Show the largest dependency'}</button></div>
      <p class="note">${multi ? 'Dependencies are grouped by layer. Select a position to open its own dependencies.' : 'Select any body to trace what leans on it.'}</p>`;
    $('pick').onclick = () => { const list = multi ? [...m.positions].sort((a, b) => b.value - a.value) : m.nodes.filter((n) => !n.isPos).sort((a, b) => (b.contrib || 0) - (a.contrib || 0)); if (list[0]) select(list[0].id); };
    return;
  }
  if (S.selGroup) {
    const g = S.view.groups.find((x) => x.layer === S.selGroup);
    el.innerHTML = `${kindRow(S.selGroup, 'grouped')}<h2>${esc(KIND[S.selGroup].plural)} · ${g.members.length}</h2><p>Every item below is a real node. Select one to open the position that relies on it.</p>
      <div class="members">${g.members.map((n) => `<button data-id="${esc(n.id)}">${esc(n.label)}</button>`).join('')}</div><div class="row"><button class="ghost" id="clr">Clear</button></div>`;
    el.querySelector('.members').onclick = (ev) => { const b = ev.target.closest('button'); if (b) select(b.dataset.id); }; $('clr').onclick = clearSel; return;
  }
  const n = m.byId.get(S.sel || S.focus);
  const back = multi ? '<button class="ghost" id="book">All positions</button>' : '';
  if (S.mode !== 'failure') {
    if (n.isPos) {
      const direct = m.out.get(n.id).map((e) => e.dst.label), all = m.reach.get(n.id).size - 1;
      el.innerHTML = `${kindRow('position')}<h2>${esc(n.label)}</h2>
        <dl><dt>Size</dt><dd>${F.fmtUsd(n.value)}</dd><dt>Relies directly on</dt><dd>${direct.map(esc).join(', ') || 'nothing'}</dd><dt>Indirectly on</dt><dd>${Math.max(0, all - direct.length)} more<small>${all} dependencies in total</small></dd></dl>
        ${multi ? '' : finance()}<div class="row">${back}<button class="ghost" id="clr">Clear</button></div>`;
    } else {
      const h = hopsFrom(m, anchorIds(), n.id), by = m.inc.get(n.id), dep = m.out.get(n.id), why = by.find((e) => S.view.ids.has(e.src.id)) || by[0];
      const tot = m.nodes.reduce((s, x) => s + (x.isPos ? 0 : x.contrib), 0), others = m.positions.filter((p) => m.reach.get(p.id).has(n.id)).length;
      el.innerHTML = `${kindRow(n.layer, Number.isFinite(h) ? (h === 1 ? 'direct dependency' : `indirect, ${h} links from the position`) : '')}<h2>${esc(n.label)}</h2>
        ${why && why.reason ? `<p>${esc(why.src.label)} relies on it: ${esc(why.reason)}.</p>` : ''}
        <dl><dt>Relied on by</dt><dd>${by.length ? by.map((e) => esc(e.src.label)).join(', ') : 'nothing directly'}</dd><dt>Depends on</dt><dd>${dep.length ? dep.map((e) => esc(e.dst.label)).join(', ') : 'nothing further'}</dd>
        <dt>Share of modeled loss</dt><dd>${tot > 0 && n.contrib > 0 ? F.fmtPct(n.contrib / tot, 0) : 'Not available'}<small>${n.contrib > 0 ? F.fmtUsd(n.contrib) + ' expected, from the engine' : ''}</small></dd></dl>
        <div class="row"><button class="primary" id="doFail">Simulate its failure</button>${multi && others > 1 && S.expanded !== n.id ? `<button class="ghost" id="exp">Show all ${others} positions on it</button>` : ''}${back}<button class="ghost" id="clr">Clear</button></div>`;
      $('doFail').onclick = () => fail(n.id);
      if ($('exp')) $('exp').onclick = () => { S.expanded = n.id; applyView(); panel(); };
    }
    if ($('book')) $('book').onclick = backToBook; $('clr').onclick = clearSel; return;
  }
  const ev = S.casc.events.filter((x) => !x.root), hit = ev.filter((x) => x.node.isPos), L = S.loss;
  el.innerHTML = `<div class="kind">${glyph(n.layer)}<span>Dependency failure, assumed to happen</span></div><h2>If ${esc(n.label)} fails</h2>
    <ol class="steps" id="steps"><li data-d="0" class="on"><b>${esc(n.label)}</b><span class="pct">fails</span><small>The starting assumption.</small></li>
    ${ev.map((x) => `<li data-d="${x.depth}"><b>${esc(x.node.label)}</b><span class="pct">${Math.round(x.strength * 100)}%</span><small>${x.via ? esc(x.via.reason || 'depends on ' + x.via.dst.label) + '. ' : ''}Link ${x.depth}${x.node.isPos ? ', reaches the position' : ''}.</small></li>`).join('')}</ol>
    ${hit.length ? `<div class="sum"><div><small>Conditional loss, ${hit.length} position${hit.length > 1 ? 's' : ''}</small><b>${F.fmtUsd(L.stay)}</b></div><div><small>Cost to exit ${hit.length > 1 ? 'them' : 'it'}</small><b>${F.fmtUsd(L.exit)}</b></div></div>
` : '<p>It does not reach a position above the model threshold.</p>'}
    <p class="note">X-Ray model, if the failure is certain (loss given failure ${F.fmtPct(n.lgf, 0)}); a point comparison, not the engine's verdict${S.m.decision.verdict ? `, which stays ${esc(S.m.decision.verdict)}` : ''}. Percentages are the share passed along each real link. Not a liquidation from a price move: the breaking point is a separate analysis.</p>
    <div class="row"><button class="primary" id="again">Replay</button><button class="ghost" id="backsel">Back</button></div>`;
  $('again').onclick = () => { S.freezeAt = null; fail(n.id); }; $('backsel').onclick = () => select(n.id, { focus: false });
}
function buildList() {
  const m = S.m;
  $('list').innerHTML = TIER_ORDER.map((t) => { const ns = m.nodes.filter((n) => n.layer === t); return ns.length ? `<h3>${esc(KIND[t].plural)}</h3>` + ns.map((n) => `<button data-id="${esc(n.id)}">${esc(n.label)}</button>`).join('') : ''; }).join('');
  $('legend').innerHTML = `<summary>How to read it</summary><ul class="shapes">${TIER_ORDER.filter((t) => m.nodes.some((n) => n.layer === t)).map((t) => `<li>${glyph(t)}${esc(KIND[t].name)}</li>`).join('')}</ul>
    <ul><li><span class="ln"></span>Held directly by the position</li><li><span class="ln thin"></span>Indirect link</li><li>Height is the layer. Size is the share of modeled loss.</li></ul>`;
}
function syncList() { $('list').querySelectorAll('button').forEach((b) => b.setAttribute('aria-current', String(b.dataset.id === S.sel))); }

// ---------------------------------------------------------------- per-frame
const tmp = new THREE.Vector3(), tmp2 = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), camRight = new THREE.Vector3(), white = new THREE.Color(0xffffff), sig = new THREE.Color(TH.signal), cc = new THREE.Color();
function span(mesh, a, b, rad, lenK = 1) { tmp.copy(b).sub(a); const len = tmp.length(); if (len < 1e-4) { mesh.visible = false; return 0; } tmp.normalize(); mesh.quaternion.setFromUnitVectors(up, tmp); mesh.scale.set(rad, Math.max(1e-4, len * lenK), rad); return len; }
function paint(dt) {
  const k = REDUCED ? 1 : 1 - Math.pow(0.001, dt / 520); let moving = false;
  const selPos = S.sel && S.m.byId.get(S.sel).isPos, sel = S.sel, nb = sel && S.mode === 'selected' ? (selPos ? S.view.ids : nbr(sel)) : null, // a selected position keeps its whole subgraph lit
     T = S.mode === 'failure' ? failT() : 0, cs = S.casc;
  const failing = S.mode === 'failure', end = failing ? failEnd() : 0;
  for (const x of [...N.values(), ...G.values()]) {
    const d = x.tgt.distanceTo(x.pos); if (d > 1e-3) { x.pos.lerp(x.tgt, k); moving = true; } else x.pos.copy(x.tgt);
    if (Math.abs(x.ta - x.a) > 0.004) { x.a += (x.ta - x.a) * k; moving = true; } else x.a = x.ta;
    if (Math.abs(x.ts - x.s) > 0.004) { x.s += (x.ts - x.s) * k; moving = true; } else x.s = x.ts;
    const mat = x.mesh.material, id = x.n ? x.n.id : null; let op = x.a, sc = x.r * x.s, em = 0; x.arc.visible = false; x.state = '';
    cc.copy(tint(x.n ? x.n.layer : x.layer));
    if (S.mode === 'selected' && id) { if (id === sel) sc *= 1.14; else if (!nb.has(id) && !x.n.isPos) op *= 0.34; }
    if (S.mode === 'selected' && S.selGroup && !id) { if (x.layer === S.selGroup) sc *= 1.12; }
    if (failing && id && cs.depth.has(id)) {
      const dpt = cs.depth.get(id), st = cs.strength.get(id) || 0;
      if (dpt === 0) { cc.copy(sig); em = 0.55; x.state = 'failed'; }                     // failed: the whole body takes the signal colour
      else if (T >= dpt) { const g = REDUCED || S.freezeAt != null ? 1 : clamp((T - dpt) / 0.45, 0, 1); x.state = 'stressed';     // stressed: keeps its own colour, gains an arc = share received
        if (x.arcFor !== st) { x.arc.geometry.dispose(); x.arc.geometry = new THREE.TorusGeometry(1, Math.min(0.055, 0.02 / x.r), 8, 80, Math.PI * 2 * st); x.arcFor = st; }
        x.arc.visible = true; x.arc.position.copy(x.pos); x.arc.quaternion.copy(camera.quaternion); x.arc.rotateZ(Math.PI / 2); x.arc.scale.setScalar(x.r * 1.75 * (0.7 + 0.3 * g));
        if (TH.glow && g < 1) { sc *= 1 + 0.18 * Math.sin(g * Math.PI); moving = true; } }
      else op *= 0.45;
    }
    mat.color.copy(cc); mat.emissive.copy(em ? sig : cc); mat.emissiveIntensity = em || (V === 'b' ? 0.1 : 0.05); mat.opacity = op; mat.depthWrite = op > 0.6;
    x.mesh.visible = op > 0.015; x.mesh.scale.setScalar(sc);
    if (x.mesh.userData.ring) x.mesh.userData.ring.material.opacity = op; if (x.mesh.userData.halo) x.mesh.userData.halo.material.opacity = op * (failing ? 0.4 : 1); if (x.mesh.userData.shell) x.mesh.userData.shell.material.opacity = 0.35 * op;
  }
  const hot = new Map(); if (cs) for (const h of cs.edges) hot.set(h.e, h);
  for (const x of E) {
    if (Math.abs(x.ta - x.a) > 0.004) { x.a += (x.ta - x.a) * k; moving = true; } else x.a = x.ta;
    const A = N.get(x.e.src.id), B = N.get(x.e.dst.id); x.fill.visible = x.head.visible = x.arrow.visible = false;
    if (x.a < 0.015) { x.base.visible = false; continue; }
    const rad = (x.direct ? 0.022 : 0.009) + 0.008 * x.e.t; let op = (x.direct ? 0.9 : 0.42) * x.a, hex = TH.edge;
    if (S.mode === 'selected' && sel && !selPos) { const on = x.e.src.id === sel || x.e.dst.id === sel; op = (on ? 1 : 0.1) * x.a; if (on) hex = 0xffffff; }
    if (failing) { const h = hot.get(x.e); op = (h ? (h.main ? 0.5 : 0.2) : 0.06) * x.a; }
    x.base.visible = true; x.base.position.copy(A.pos).add(B.pos).multiplyScalar(0.5); const len = span(x.base, B.pos, A.pos, rad); x.base.material.opacity = op; x.base.material.color.setHex(hex);
    if (S.mode === 'selected' && sel && !selPos && (x.e.src.id === sel || x.e.dst.id === sel) && len > 0.5) { // arrow points at what is depended on
      x.arrow.visible = true; tmp.copy(B.pos).sub(A.pos).normalize(); x.arrow.quaternion.setFromUnitVectors(up, tmp); x.arrow.position.copy(B.pos).addScaledVector(tmp, -(B.r * 1.25 + 0.16)); x.arrow.scale.setScalar(0.05); x.arrow.material.opacity = x.a; }
    if (failing) { const h = hot.get(x.e); if (h && h.main) { const p = clamp(T - h.from, 0, 1); if (p > 0) { // the signal runs from the failed dependency toward whatever relies on it
      x.fill.visible = true; x.fill.position.copy(B.pos); span(x.fill, B.pos, A.pos, rad * 2.1, p); x.fill.material.opacity = 0.95;
      if (p < 1 || T < end - 0.05) { if (p < 1) { x.head.visible = true; x.head.position.copy(B.pos).lerp(A.pos, p); x.head.scale.setScalar(TH.glow ? 0.9 : 0.075); } } } } }
  }
  for (const g of GE) { if (Math.abs(g.ta - g.a) > 0.004) { g.a += (g.ta - g.a) * k; moving = true; } else g.a = g.ta;
    if (g.a < 0.015 || !g.from || !g.to) { g.mesh.visible = false; continue; }
    const on = S.hover && (S.hover === g.from.n.id || S.hover === 'g:' + g.to.layer); g.mesh.visible = true; g.mesh.position.copy(g.from.pos).add(g.to.pos).multiplyScalar(0.5); span(g.mesh, g.to.pos, g.from.pos, 0.006 + 0.0022 * g.w); g.mesh.material.opacity = (on ? 0.85 : 0.2) * g.a; }
  const sx = sel ? N.get(sel) : (S.selGroup ? G.get(S.selGroup) : null);
  ringSel.visible = !!sx && sx.a > 0.1;
  if (ringSel.visible) { ringSel.position.copy(sx.pos); ringSel.quaternion.copy(camera.quaternion); ringSel.scale.setScalar(sx.r * (sx.n && sx.n.isPos ? 2.3 : 2.05)); ringSel.material.color.copy(failing ? sig : white); }
  return moving || (failing && S.freezeAt == null && !REDUCED && T < end);
}

function labels() {
  const c = $('stage'), w = c.clientWidth, h = c.clientHeight, wide = w >= 860, v = S.view, failing = S.mode === 'failure', T = failing ? failT() : 0;
  const want = new Map(), add = (key, p) => { if (!want.has(key) || want.get(key) < p) want.set(key, p); };
  const few = v.ids.size <= 16;
  for (const id of v.ids) { const x = N.get(id), n = x.n;
    if (v.dimPos.has(id)) { if (S.hover === id) add(id, 7); continue; }
    if (failing) { const d = S.casc.depth.get(id); if (d != null && T >= d) add(id, d === 0 ? 10 : n.isPos ? 9 : 7 - Math.min(3, d) * 0.4); else if (n.isPos) add(id, 6); continue; }
    if (n.isPos) add(id, 6); else if (S.mode === 'selected' && S.sel) { if (id === S.sel) add(id, 10); else if (nbr(S.sel).has(id)) add(id, 5.5); else if (N.get(S.sel).n.isPos) add(id, 3 - x.hop * 0.4); else if (few && V === 'a') add(id, 1); }
    else if (few && (V === 'a' || x.hop <= 1)) add(id, 3 - x.hop * 0.3);
  }
  for (const g of v.groups) add('g:' + g.layer, 5);
  if (S.hover) add(S.hover, 8);
  camRight.setFromMatrixColumn(camera.matrixWorld, 0);
  const proj = (x) => { tmp.copy(x.pos).project(camera); const sx = (tmp.x * 0.5 + 0.5) * w, sy = (-tmp.y * 0.5 + 0.5) * h, z = tmp.z; tmp2.copy(x.pos).addScaledVector(camRight, x.r * x.s).project(camera); return { sx, sy, z, pr: Math.abs((tmp2.x * 0.5 + 0.5) * w - sx) }; };
  const cx = (tmp.set(0, cam.ty, 0).project(camera).x * 0.5 + 0.5) * w;
  const placed = [], bodies = [], items = [];
  if (wide) { for (const id of ['headline', 'sub', 'ctx', 'legend']) { const el = $(id); if (!el || !el.getClientRects().length) continue; const r = el.getBoundingClientRect(); placed.push({ x: r.left - 12, y: r.top - 8, w: r.width + 24, h: r.height + 16 }); }
    const hd = document.querySelector('header').getBoundingClientRect(); placed.push({ x: 0, y: 0, w, h: hd.bottom + 6 }); }
  for (const [key, x] of [...[...N].map(([id, x]) => [id, x]), ...[...G].map(([t, x]) => ['g:' + t, x])]) {
    if (x.a < 0.3) { if (x.label.style.display !== 'none') x.label.style.display = 'none'; continue; }
    const p = proj(x); if (p.z < 1) bodies.push({ key, x: p.sx, y: p.sy, r: p.pr * 0.95 });
    if (!want.has(key) || p.z >= 1) { if (x.label.style.display !== 'none') x.label.style.display = 'none'; continue; }
    items.push({ key, x, p, pri: want.get(key) - p.z * 0.4 });
  }
  items.sort((a, b) => b.pri - a.pri);
  const tierRects = []; if (wide) for (const t of v.L.tiers) { let sy = 0, k = 0; for (const b of bodies) { const x = b.key.startsWith('g:') ? G.get(b.key.slice(2)) : N.get(b.key); const lay = x.n ? x.n.layer : x.layer; if (lay === t && !(x.n && v.dimPos.has(x.n.id))) { sy += b.y; k++; } } if (k) tierRects.push({ t, y: sy / k }); }
  for (const it of items) {
    const x = it.x, el = x.label, n = x.n, st = x.state;
    const cls = 'lbl' + (n && n.isPos ? ' pos' : '') + (!n ? ' grp' : '') + (it.key === S.sel && !st ? ' sel' : '') + (st ? ' ' + st : '') + (S.mode === 'selected' && S.sel && n && it.key !== S.sel && !nbr(S.sel).has(it.key) && !n.isPos && !N.get(S.sel).n.isPos ? ' dimmed' : '');
    const meta = st === 'failed' ? 'fails' : st === 'stressed' ? Math.round((S.casc.strength.get(it.key) || 0) * 100) + '%' : '';
    const short = n && n.isPos && v.overview && S.hover !== it.key && /^\S+\s/.test(n.label) ? n.label.split(' ')[0] : null;
    const html = esc(n ? (short || n.label) : el.textContent.split(' · ').slice(0, 2).join(' · ')) + (meta ? `<small>${meta}</small>` : '');
    if (el.className !== cls || el.dataset.h !== html) { el.className = cls; el.innerHTML = html; el.dataset.h = html; x.w = 0; }
    if (el.style.display === 'none') el.style.display = '';
    if (!x.w) x.w = el.offsetWidth; const lw = x.w, lh = 28, off = it.p.pr * 1.15 + 12;
    const right = it.p.sx >= cx, ys = [it.p.sy - lh / 2, it.p.sy - it.p.pr - lh - 6, it.p.sy + it.p.pr + 6];
    const cand = []; for (const y of ys) { const xs = y === ys[0] ? (right ? [it.p.sx + off, it.p.sx - off - lw] : [it.p.sx - off - lw, it.p.sx + off]) : [it.p.sx - lw / 2]; for (const xx of xs) cand.push([xx, y]); }
    const free = ([xx, y]) => xx >= 8 && xx + lw <= w - 8 && y >= 4 && y + lh <= h - 4 && !placed.some((r) => xx < r.x + r.w + 6 && xx + lw + 6 > r.x && y < r.y + r.h + 3 && y + lh + 3 > r.y)
      && !bodies.some((b) => b.key !== it.key && xx < b.x + b.r && xx + lw > b.x - b.r && y < b.y + b.r && y + lh > b.y - b.r);
    let c0 = cand.find(free);
    if (!c0) { if (it.pri < 5) { el.style.display = 'none'; continue; } // important label: may sit on a body, never on the text panels
      const clear = ([xx, y]) => xx >= 8 && xx + lw <= w - 8 && y >= 4 && y + lh <= h - 4 && !placed.some((r) => xx < r.x + r.w + 6 && xx + lw + 6 > r.x && y < r.y + r.h + 3 && y + lh + 3 > r.y);
      c0 = cand.find(clear) || [[it.p.sx + off, it.p.sy + it.p.pr + 8], [it.p.sx + off, it.p.sy - it.p.pr - lh - 8], [it.p.sx + off + 40, it.p.sy - lh / 2]].find(clear);
      if (!c0) { el.style.display = 'none'; continue; } }
    placed.push({ x: c0[0], y: c0[1], w: lw, h: lh }); el.style.transform = `translate(${c0[0].toFixed(1)}px,${c0[1].toFixed(1)}px)`;
  }
  tierRects.sort((p, q) => p.y - q.y); for (let i = 1; i < tierRects.length; i++) if (tierRects[i].y - tierRects[i - 1].y < 26) tierRects[i].y = tierRects[i - 1].y + 26; // legend rows never collide
  for (const [t, el] of tierEls) { const r = tierRects.find((q) => q.t === t); if (!r) { el.style.display = 'none'; continue; }
    const clash = placed.some((p) => p.x + p.w > w - 200 && r.y - 12 < p.y + p.h && r.y + 12 > p.y); el.style.display = clash ? 'none' : ''; el.style.transform = `translateY(${(r.y - 10).toFixed(1)}px)`; }
  if (failing) { const steps = $('steps'); if (steps) for (const li of steps.children) li.classList.toggle('on', T >= +li.dataset.d); }
}
function placeCamera() { const s = Math.sin(cam.pol); camera.position.set(cam.dist * s * Math.sin(cam.az), cam.ty + cam.dist * Math.cos(cam.pol), cam.dist * s * Math.cos(cam.az)); camera.lookAt(0, cam.ty, 0); camera.updateMatrixWorld(); }

const perf = { warm: 0, dts: [], done: false, last: 0 };
let prev = 0;
function frame(now) {
  requestAnimationFrame(frame);
  if (!S.m || S.flat) return;
  const dt = prev ? Math.min(64, now - prev) : 16; prev = now;
  const k = REDUCED ? 1 : 1 - Math.pow(0.001, dt / 620); let moving = false;
  for (const key of ['az', 'pol', 'dist', 'ty']) { const d = goal[key] - cam[key]; if (Math.abs(d) > 1e-4) { cam[key] += d * k; moving = true; } else cam[key] = goal[key]; }
  if (Q.has('perf') && !perf.done) { goal.az += 0.004; moving = true; }
  const busy = S.mode === 'failure' && S.freezeAt == null && !REDUCED && failT() < failEnd();
  if (moving || dirty || busy) lastActive = now;
  if (!(moving || dirty || busy || now - lastActive < 700)) { perf.last = 0; return; } // on demand: an idle scene costs nothing
  dirty = false; placeCamera(); if (paint(dt)) lastActive = now; renderer.render(scene, camera); labels();
  if (Q.has('perf') && !perf.done && perf.last) { if (perf.warm++ > 45) perf.dts.push(now - perf.last); if (perf.dts.length >= 240) report(); }
  perf.last = now;
}
function report() {
  perf.done = true; const a = [...perf.dts].sort((x, y) => x - y), avg = a.reduce((s, x) => s + x, 0) / a.length, gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info'), inf = renderer.info;
  const out = { variant: V, dataset: S.which, state: S.mode, shown: S.view.ids.size + S.view.groups.length, viewport: `${innerWidth}x${innerHeight}@${renderer.getPixelRatio()}`, frames: a.length, avg_ms: +avg.toFixed(2), median_ms: +a[a.length >> 1].toFixed(2), p95_ms: +a[Math.floor(a.length * 0.95)].toFixed(2), max_ms: +a[a.length - 1].toFixed(2), draw_calls: inf.render.calls, triangles: inf.render.triangles, gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown' };
  $('perf').textContent = JSON.stringify(out, null, 1); fetch('/__perf', { method: 'POST', body: JSON.stringify(out) }).catch(() => {});
}

// ---------------------------------------------------------------- input
function bind() {
  const c = $('stage'); let down = null;
  const pick = (ev) => { const r = c.getBoundingClientRect(); raycaster.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), camera);
    const hit = raycaster.intersectObjects([...N.values(), ...G.values()].filter((x) => x.a > 0.2).map((x) => x.mesh), false)[0]; return hit ? (hit.object.userData.id || 'g:' + hit.object.userData.group) : null; };
  c.addEventListener('pointerdown', (ev) => { down = { x: ev.clientX, y: ev.clientY, moved: 0 }; c.setPointerCapture(ev.pointerId); });
  c.addEventListener('pointermove', (ev) => {
    if (down) { const dx = ev.clientX - down.x, dy = ev.clientY - down.y; down.moved += Math.abs(dx) + Math.abs(dy); down.x = ev.clientX; down.y = ev.clientY; if (down.moved > 5) { c.classList.add('drag'); goal.az -= dx * 0.006; goal.pol = clamp(goal.pol - dy * 0.004, 0.8, 1.62); } return; }
    const id = pick(ev); if (id !== S.hover) { S.hover = id; c.classList.toggle('hot', !!id); dirty = true; }
  });
  c.addEventListener('pointerup', (ev) => { const was = down; down = null; c.classList.remove('drag'); if (was && was.moved <= 5) { const id = pick(ev); if (id && id.startsWith('g:')) selectGroup(id.slice(2)); else if (id) select(id); else if (S.mode !== 'normal') clearSel(); } });
  c.addEventListener('pointerleave', () => { if (S.hover) { S.hover = null; dirty = true; } });
  c.addEventListener('wheel', (ev) => { ev.preventDefault(); goal.dist = clamp(goal.dist * Math.exp(ev.deltaY * 0.001), cam.fit * 0.6, cam.fit * 1.45); }, { passive: false });
  c.addEventListener('keydown', (ev) => { const key = ev.key; if (key === 'ArrowLeft') goal.az -= 0.2; else if (key === 'ArrowRight') goal.az += 0.2; else if (key === 'ArrowUp') goal.pol = clamp(goal.pol - 0.1, 0.8, 1.62); else if (key === 'ArrowDown') goal.pol = clamp(goal.pol + 0.1, 0.8, 1.62); else if (key === '+' || key === '=') goal.dist = Math.max(cam.fit * 0.6, goal.dist * 0.9); else if (key === '-') goal.dist = Math.min(cam.fit * 1.45, goal.dist * 1.1); else return; ev.preventDefault(); });
  addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && S.mode !== 'normal') clearSel(); if ((ev.key === 'r' || ev.key === 'R') && !ev.metaKey && !ev.ctrlKey && document.activeElement.tagName !== 'INPUT') resetView(); });
  $('reset').onclick = resetView;
  $('viewList').onclick = () => { const l = $('list'); l.hidden = !l.hidden; $('viewList').setAttribute('aria-expanded', String(!l.hidden)); };
  $('list').addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) select(b.dataset.id); });
  $('d11').onclick = () => load('sample'); $('d44').onclick = () => load('large');
}
function resetView() { goal.az = TH.az; goal.pol = TH.pol; goal.dist = cam.fit; goal.ty = 0; dirty = true; }

async function load(which) {
  const r = await fetch(`../../../../public/data/${which === 'large' ? 'sample-large' : 'sample'}.json`, { cache: 'no-store' }); if (!r.ok) throw new Error('HTTP ' + r.status);
  const payload = await r.json(), m = buildIndex(normalize(payload));
  Object.assign(S, { payload, m, which, mode: 'normal', sel: null, selGroup: null, focus: null, expanded: null, casc: null, hover: null });
  $('d11').setAttribute('aria-pressed', String(which !== 'large')); $('d44').setAttribute('aria-pressed', String(which === 'large'));
  const deps = m.nodes.filter((n) => !n.isPos).length, np = m.positions.length, word = (k) => WORDS[k] || String(k);
  $('headline').textContent = V === 'b' ? `${word(deps)} ${deps === 1 ? 'thing holds' : 'things hold'} ${np > 1 ? `these ${word(np).toLowerCase()} positions` : 'this position'} up.` : (np > 1 ? `What these ${word(np).toLowerCase()} positions stand on` : 'What this position stands on');
  $('sub').textContent = `${deps} dependencies, ${m.edges.length} links. ${payload.source ? 'Saved run of the real pipeline.' : (m.position.meta && m.position.meta.synthetic ? 'Synthetic demo book.' : 'Bundled example.')}`;
  buildList(); if (!S.flat) { build(m); resetView(); Object.assign(cam, goal); } else { S.view = computeView(); }
  panel();
}

(async function main() {
  try { if (S.flat) throw new Error('flat'); initScene(); }
  catch (e) { S.flat = true; document.body.classList.add('no3d'); $('list').hidden = false; $('status').textContent = '3D view unavailable here. The list gives the same dependencies and the same simulation.'; }
  bind();
  try { await load(Q.get('data') === 'large' ? 'large' : 'sample'); }
  catch (e) { $('headline').textContent = 'The example data did not load.'; $('sub').textContent = 'Serve the repository root over HTTP and open this page from there (see README). ' + e.message; return; }
  if (Q.get('at') != null) S.freezeAt = clamp(+Q.get('at'), 0, 1);
  if (Q.get('select')) { select(Q.get('select'), { snap: true }); if (!S.flat) { cam.az = goal.az; } }
  if (Q.has('expand') && S.sel) { S.expanded = S.sel; applyView(true); panel(); }
  if (Q.get('group')) selectGroup(Q.get('group'));
  if (Q.get('fail')) { select(Q.get('fail'), { snap: true }); if (!S.flat) cam.az = goal.az; fail(Q.get('fail'), { snap: true }); }
  if (Q.has('list')) $('list').hidden = false;
  if (Q.get('az')) cam.az = goal.az = +Q.get('az');
  requestAnimationFrame(frame);
})();
