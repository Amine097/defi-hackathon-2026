import { loadPayload, normalize } from './xray/data.js';
import { buildIndex, cascade, positionLosses, concentration, breakEven, closure, pathTo, exitCostOf } from './xray/model.js';
import { createGraph, LAYERS, layerColors } from './xray/graph.js';
import { renderBreakEven } from './xray/chart.js';
import { $, esc, usd, pct, clamp, countUp, reducedMotion } from './xray/util.js';

const HOP_MS = 650;
const COL = layerColors();
const LAYER_NAME = Object.fromEntries(LAYERS.map((l) => [l.key, l.name]));
const S = { m: null, g: null, failed: new Map(), scenario: null, selected: null, clickMode: 'fail', exitOverride: null, beNode: null, beP: null, timers: [], verdict: null, conc: null };

const hop = () => (reducedMotion() ? 0 : HOP_MS);
const later = (fn, ms) => { if (ms <= 0) fn(); else S.timers.push(setTimeout(fn, ms)); };
const clearTimers = () => { S.timers.forEach(clearTimeout); S.timers = []; };
const dot = (n) => `<i class="xr-dot" style="--c:${COL[n.layer] || COL.protocol}"></i>`;
const nodeName = (n) => `<b>${esc(n.label)}</b>`;
const pluralPos = (k) => (k === 1 ? 'position' : 'positions');

// ---------- boot
init();

async function init() {
  const qs = new URLSearchParams(location.search);
  $('srcSelect').value = ['sample', 'large'].includes(qs.get('data')) ? qs.get('data') : '';
  $('srcSelect').addEventListener('change', (e) => {
    const q = new URLSearchParams(location.search);
    if (e.target.value) q.set('data', e.target.value); else q.delete('data');
    location.search = q.toString();
  });
  let res;
  try {
    res = await loadPayload();
  } catch (err) {
    showError(err);
    return;
  }
  try {
    start(res);
  } catch (err) {
    console.error(err);
    showError(err);
  }
}

function showError(err) {
  $('loading').hidden = true;
  const box = $('errorBox');
  box.hidden = false;
  box.innerHTML = `<h3>Could not load the dependency graph</h3><p>${esc(err && err.message || err)}</p><button class="xr-btn" onclick="location.reload()">Retry</button>`;
  $('dataBadge').textContent = 'no data';
  $('dataBadge').className = 'xr-badge xr-badge-err';
}

function start({ payload, kind, url }) {
  const m = buildIndex(normalize(payload));
  S.m = m;
  const badge = $('dataBadge');
  const LBL = {
    live: ['Live on-chain data', 'xr-badge-live', `Fetched now from ${url}`],
    cache: ['Real data (cached)', 'xr-badge-demo', 'Real API responses replayed from data/cache'],
    mixed: ['Real data (part cached)', 'xr-badge-demo', 'Some API calls served from data/cache'],
    mock: ['MOCK data', 'xr-badge-err', 'Demo graph requested explicitly: numbers are not real'],
    'mock-fallback': ['MOCK · live discovery failed', 'xr-badge-err', `Live discovery failed: ${payload.discovery_error || ''}`],
    demo: ['MOCK · demo data', 'xr-badge-err', `API unavailable or demo selected: showing ${url}`],
  };
  const [txt, cls, tip] = LBL[kind] || ['Unknown source', 'xr-badge-err', url];
  badge.textContent = txt;
  badge.className = `xr-badge ${cls}`;
  badge.title = tip + (payload.data_as_of && kind !== 'live' ? ` (as of ${new Date(payload.data_as_of * 1000).toISOString()})` : '');
  const wantedLive = !new URLSearchParams(location.search).get('data');
  const note = $('guideNote');
  note.textContent = (kind === 'demo' || kind === 'mock-fallback') && wantedLive
    ? 'Note: the live /api/analyze backend did not deliver real data, so you are seeing built-in MOCK data (same model, sample inputs).'
    : '';
  if (kind === 'demo' && wantedLive) badge.textContent = 'MOCK · API offline';
  const guide = $('guide');
  const closeGuide = () => { guide.hidden = true; try { localStorage.setItem('fl-guide', '1'); } catch (e) {} };
  $('helpBtn').addEventListener('click', () => { guide.hidden = false; });
  $('guideGo').addEventListener('click', closeGuide);
  guide.addEventListener('click', (e) => { if (e.target === guide) closeGuide(); });
  let seen = false;
  try { seen = !!localStorage.getItem('fl-guide'); } catch (e) {}
  guide.hidden = seen;

  renderHeader(m);
  renderLegend(m);
  S.g = createGraph($('graph'), m, {
    tipEl: $('tip'),
    tipHtml,
    onNodeClick,
    onBackgroundClick: () => deselect(),
    leftInset: () => { const d = $('drawer'); return !d.hidden && window.innerWidth > 900 ? d.offsetWidth + 24 : 0; },
  });
  $('loading').hidden = true;
  document.body.classList.add('xr-ready');

  renderScenarios(m);
  renderFailPicker(m);
  S.conc = concentration(m);
  renderConcentration(m);
  renderBook(m);
  const top = topRiskNode(m);
  S.beNode = top;
  $('exitSlider').value = (exitTotalAll() / (m.totalValue || 1) * 100).toFixed(1);
  baselineVerdict();
  renderBE();
  wireControls();
}

// ---------- header + legend
function renderHeader(m) {
  const p = m.position;
  $('posInfo').innerHTML = `<strong title="${esc(p.label)}">${esc(p.label)}</strong>
    <span class="xr-chip">${esc(p.chain || 'chain n/a')}</span>
    <span class="xr-chip">${usd(m.totalValue)}</span>
    <span class="xr-chip">${m.horizon}d horizon</span>
    <span class="xr-chip xr-chip-dim">${m.nodes.length} nodes · ${m.edges.length} links</span>`;
  document.title = `FaultLine · X-Ray · ${p.label}`;
}

function renderLegend(m) {
  const present = new Set(m.nodes.map((n) => n.layer));
  $('legend').innerHTML = LAYERS.filter((l) => present.has(l.key))
    .map((l) => `<span><img class="xr-layer-icon" src="/assets/layers/${l.key}.svg" alt="">${esc(l.name)}</span>`).join('')
    + `<span class="xr-leg-sep"></span><span><i class="xr-line"></i>A → B: A depends on B</span><span><i class="xr-line xr-line-dash"></i>weak link (&lt;50%)</span><span><i class="xr-line xr-line-red"></i>failure path</span>`;
}

// ---------- tooltip
function tipHtml(item) {
  if (item.type === 'edge') {
    const e = item.e;
    return `<div class="xr-tip-h">${dot(e.src)}${esc(e.src.label)} <span class="xr-arrow">→</span> ${dot(e.dst)}${esc(e.dst.label)}</div>
      <div class="xr-tip-r"><span>depends on</span><b>${esc(e.reason || 'dependency')}</b></div>
      <div class="xr-tip-r"><span>transmission</span><b>${pct(e.t)}</b></div>
      <div class="xr-tip-f">If ${esc(e.dst.label)} fails, ${pct(e.t)} of the shock reaches ${esc(e.src.label)}.</div>`;
  }
  const n = item.n;
  let rows = n.isPos
    ? `<div class="xr-tip-r"><span>value</span><b>${usd(n.value)}</b></div><div class="xr-tip-r"><span>exit cost</span><b>${usd(exitCostOf(S.m, n, S.exitOverride))}</b></div>`
    : `<div class="xr-tip-r"><span>P(fail) ${S.m.horizon}d</span><b>${pct(n.p_fail)}</b></div>
       <div class="xr-tip-r"><span>loss if fails</span><b>${pct(n.lgf)}</b></div>
       <div class="xr-tip-r"><span>expected loss</span><b>${usd(n.contrib)}</b></div>`;
  if (item.hit) rows += `<div class="xr-tip-r xr-tip-hit"><span>shock received</span><b>${pct(item.hit)}</b></div>`;
  return `<div class="xr-tip-h">${dot(n)}${esc(n.label)}</div><div class="xr-tip-l">${esc(LAYER_NAME[n.layer] || n.layerRaw)}</div>${rows}
    <div class="xr-tip-f">${n.isPos ? 'Your position' : S.clickMode === 'fail' ? 'Click to simulate failure · Shift+click to add' : 'Click to inspect'}</div>`;
}

// ---------- controls
function wireControls() {
  $('layoutSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    setSeg('layoutSeg', b.dataset.v); S.g.setLayout(b.dataset.v);
  });
  $('clickSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    setSeg('clickSeg', b.dataset.v); S.clickMode = b.dataset.v;
  });
  $('fitBtn').onclick = () => S.g.fit();
  $('resetBtn').onclick = reset;
  $('resetBtn2').onclick = reset;
  $('failBtn').onclick = () => { const id = $('failSelect').value; if (id) failNodes([id], false); };
  $('addFailBtn').onclick = () => { const id = $('failSelect').value; if (id) failNodes([id], true); };
  $('beSlider').addEventListener('input', (e) => { S.beP = +e.target.value / 100; renderBE(); });
  $('exitSlider').addEventListener('input', (e) => {
    S.exitOverride = +e.target.value / 100;
    refreshVerdict();
    renderBE();
  });
  $('sheetHandle').onclick = () => $('panel').classList.toggle('xr-collapsed');
  document.addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('input, select, textarea')) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'r') reset();
    else if (k === 'escape') deselect();
    else if (k === 'f') S.g.fit();
    else if (k === 'l') { const v = S.g.layout === 'force' ? 'layers' : 'force'; setSeg('layoutSeg', v); S.g.setLayout(v); }
    else if (/^[1-9]$/.test(k) && S.m.scenarios[+k - 1]) runScenario(+k - 1);
  });
}

function setSeg(id, v) {
  for (const b of $(id).querySelectorAll('button')) b.classList.toggle('on', b.dataset.v === v);
}

// ---------- selection / focus
function onNodeClick(n, { shift }) {
  if (n.isPos || S.clickMode === 'inspect') { select(n.id); return; }
  select(n.id, { keepFocus: true });
  failNodes([n.id], shift);
}

function select(id, { keepFocus = false, focusSet = null } = {}) {
  const n = S.m.byId.get(id);
  if (!n) return;
  S.selected = id;
  S.g.select(id);
  if (!keepFocus || focusSet) {
    const f = focusSet || new Set([...closure(S.m, id, 'up'), ...closure(S.m, id, 'down')]);
    S.g.setFocus(S.failed.size && !focusSet ? null : f);
  }
  if (!n.isPos) { S.beNode = n; S.beP = null; renderBE(); }
  renderDrawer(n);
}

function deselect() {
  S.selected = null;
  S.g.select(null);
  S.g.setFocus(null);
  $('drawer').hidden = true;
  for (const el of document.querySelectorAll('.xr-conc li.on, .xr-insights li.on')) el.classList.remove('on');
}

// ---------- simulation
function failNodes(ids, add) {
  const failed = add && !S.scenario ? new Map(S.failed) : new Map();
  for (const id of ids) { const n = S.m.byId.get(id); if (n && !n.isPos) failed.set(id, n.lgf); }
  if (!failed.size) return;
  S.scenario = null;
  markScenario(null);
  runFailure(failed);
}

function runScenario(i) {
  const sc = S.m.scenarios[i];
  if (!sc) return;
  const failed = new Map();
  for (const [id, ov] of Object.entries(sc.overrides || {})) {
    const n = S.m.byId.get(id);
    if (!n) continue;
    failed.set(id, ov && Number.isFinite(+ov.loss_given_failure) ? +ov.loss_given_failure : n.lgf);
  }
  S.scenario = sc;
  markScenario(i);
  if (!failed.size) { scenarioVerdict(sc, null); return; }
  const first = S.m.byId.get(failed.keys().next().value);
  S.beNode = first; S.beP = null;
  runFailure(failed, sc);
}

function markScenario(i) {
  [...$('scenarioBtns').children].forEach((b, j) => b.classList.toggle('on', j === i));
}

function runFailure(failed, sc = null) {
  clearTimers();
  const m = S.m;
  S.failed = failed;
  S.g.setFocus(null);
  const c = cascade(m, failed);
  const h = hop();
  const res = positionLosses(m, failed, S.exitOverride);
  S.g.playCascade(c, h, new Map(res.rows.filter((r) => r.exposed).map((r) => [r.p.id, r.loss / Math.max(1e-9, r.p.value)])));
  const roots = [...failed.keys()].map((id) => m.byId.get(id));
  const rootNames = roots.map((n) => n.label).join(' + ');

  $('simState').textContent = 'cascading…';
  $('simState').className = 'xr-chip xr-chip-red';
  const tl = $('timeline');
  tl.innerHTML = '';
  const byDepth = new Map();
  for (const ev of c.events) { if (!byDepth.has(ev.depth)) byDepth.set(ev.depth, []); byDepth.get(ev.depth).push(ev); }
  const depths = [...byDepth.keys()].sort((a, b) => a - b);
  const banner = $('banner');
  for (const d of depths) {
    later(() => {
      const evs = byDepth.get(d);
      for (const ev of evs) tl.insertAdjacentHTML('beforeend', timelineItem(ev, failed, res));
      tl.scrollTop = tl.scrollHeight;
      const hitPos = evs.filter((e) => e.node.isPos).length;
      banner.innerHTML = `<b>${d === 0 ? '⚠' : `T+${d}`}</b> ${d === 0 ? esc(sc ? sc.name : `${rootNames} ${failed.size > 1 ? 'fail' : 'fails'}`) : `${evs.length} more node${evs.length > 1 ? 's' : ''} hit${hitPos ? ` · ${hitPos} ${pluralPos(hitPos)} reached` : ''}`}`;
      banner.classList.add('show');
    }, d * h);
  }
  const posDepths = res.exposed.map((r) => c.depth.get(r.p.id)).filter(Number.isFinite);
  const verdictAt = (posDepths.length ? Math.min(...posDepths) : c.maxDepth) * h;
  later(() => (sc ? scenarioVerdict(sc, res) : failureVerdict(roots, res, c)), verdictAt);
  later(() => {
    const exposedVal = res.exposed.reduce((a, r) => a + r.p.value, 0);
    tl.insertAdjacentHTML('beforeend', `<li class="xr-tl-result"><span class="xr-t">Result</span><div>${res.exposed.length}/${m.positions.length} ${pluralPos(m.positions.length)} exposed (${pct(exposedVal / (m.totalValue || 1))} of book) in ${c.maxDepth} hop${c.maxDepth === 1 ? '' : 's'}. Loss if it happens <b class="xr-red">${usd(res.stay)}</b> vs exit <b>${usd(res.exit)}</b>.</div></li>`);
    tl.scrollTop = tl.scrollHeight;
    $('simState').textContent = `${c.events.length - failed.size} hit · ${c.maxDepth} hops`;
    later(() => banner.classList.remove('show'), 2200);
    renderSimPositions(res);
  }, (c.maxDepth + 0.6) * h);
  renderBE();
}

function timelineItem(ev, failed, res) {
  const n = ev.node;
  if (ev.root) return `<li class="xr-tl-root"><span class="xr-t">T+0</span><div>${dot(n)}${nodeName(n)} fails <span class="xr-muted">(loses ${pct(failed.get(n.id))} of value)</span></div></li>`;
  const via = ev.via ? ` <span class="xr-muted">via ${esc(ev.via.dst.label)}${ev.via.reason ? ` · ${esc(ev.via.reason)}` : ''}</span>` : '';
  if (n.isPos) {
    const r = res.rows.find((x) => x.p === n);
    return `<li class="xr-tl-pos"><span class="xr-t">T+${ev.depth}</span><div>${dot(n)}${nodeName(n)} hit: <b class="xr-red">−${usd(r ? r.loss : 0)}</b> <span class="xr-muted">(${pct(r ? r.loss / n.value : 0)} of position)</span>${via}</div></li>`;
  }
  return `<li><span class="xr-t">T+${ev.depth}</span><div>${dot(n)}${nodeName(n)} hit, ${pct(ev.strength)} transmitted${via}</div></li>`;
}

function renderSimPositions(res) {
  const box = $('simPositions');
  if (S.m.positions.length < 2 || !res) { box.innerHTML = ''; return; }
  const rows = res.rows.filter((r) => r.exposed).sort((a, b) => b.loss - a.loss);
  const safe = res.rows.filter((r) => !r.exposed).map((r) => esc(r.p.label.split(' ')[0]));
  box.innerHTML = `<h4>Positions hit by this failure</h4><div class="xr-tablewrap"><table class="xr-table"><thead><tr><th>Position</th><th>Loss if hit</th><th>Exit</th><th>Call</th></tr></thead><tbody>
    ${rows.map((r) => `<tr data-id="${esc(r.p.id)}"><td>${dot(r.p)}${esc(r.p.label)}</td><td class="num xr-red">${usd(r.loss)}</td><td class="num">${usd(r.exit)}</td><td><span class="xr-vb xr-vb-${r.verdict.toLowerCase()}">${r.verdict}</span></td></tr>`).join('')}
    </tbody></table></div>${safe.length ? `<p class="xr-note">Not exposed: ${safe.join(', ')}</p>` : ''}`;
  box.querySelectorAll('tr[data-id]').forEach((tr) => tr.addEventListener('click', () => { select(tr.dataset.id); S.g.centerOn(tr.dataset.id); }));
}

function reset() {
  clearTimers();
  S.failed = new Map();
  S.scenario = null;
  markScenario(null);
  S.g.clearCascade();
  $('timeline').innerHTML = '<li class="xr-empty">Pick a scenario or click a node on the graph to watch the failure cascade hop by hop.</li>';
  $('simPositions').innerHTML = '';
  $('simState').textContent = 'idle';
  $('simState').className = 'xr-chip';
  $('banner').classList.remove('show');
  baselineVerdict();
  renderBE();
}

// ---------- verdict
function exitTotalAll() { return S.m.positions.reduce((a, p) => a + exitCostOf(S.m, p, S.exitOverride), 0); }

function topRiskNode(m) {
  return m.nodes.filter((n) => !n.isPos).sort((a, b) => b.contrib - a.contrib)[0] || m.nodes[0];
}

function refreshVerdict() {
  if (S.scenario) scenarioVerdict(S.scenario, S.failed.size ? positionLosses(S.m, S.failed, S.exitOverride) : null);
  else if (S.failed.size) {
    const roots = [...S.failed.keys()].map((id) => S.m.byId.get(id));
    const res = positionLosses(S.m, S.failed, S.exitOverride);
    failureVerdict(roots, res, cascade(S.m, S.failed));
    renderSimPositions(res);
  } else baselineVerdict();
}

function baselineVerdict() {
  const m = S.m, d = m.decision;
  const overridden = S.exitOverride != null;
  const stay = d.expected_loss_usd || m.nodes.reduce((a, n) => a + n.contrib, 0);
  const exit = overridden || !d.exit_cost_usd ? exitTotalAll() : d.exit_cost_usd;
  const verdict = !overridden && d.verdict ? d.verdict : stay > exit ? 'EXIT' : 'STAY';
  const top = topRiskNode(m);
  const share = top && S.conc ? top.contrib / S.conc.sumContrib : 0;
  const ratio = stay > 0 ? exit / stay : Infinity;
  const why = `Exiting costs <b>${usd(exit)}</b> for sure; staying loses <b>${usd(stay)}</b> in expectation over ${m.horizon} days (${pct(stay / (m.totalValue || 1))} of value).`
    + (top && top.contrib > 0 ? ` ${dot(top)}${nodeName(top)} drives <b>${pct(share)}</b> of that risk.` : '')
    + (verdict === 'STAY'
      ? ` The certain exit cost is <b>${ratio.toFixed(1)}×</b> the expected loss, so <b class="xr-green">stay</b>, but watch the top driver.`
      : ` Expected loss exceeds the exit cost by <b>${usd(stay - exit)}</b>: <b class="xr-red">exit</b>.`);
  setVerdict({ mode: overridden ? 'baseline · custom exit cost' : 'baseline', title: 'Decision', verdict, stay, exit, why,
    sub: `${m.horizon}-day horizon · all ${m.nodes.length - m.positions.length} dependencies at their base failure odds`,
    server: d.explanation && !overridden ? `Model: ${esc(d.explanation)}` : '' });
}

function failureVerdict(roots, res, c) {
  const m = S.m;
  const names = roots.map((n) => n.label).join(' + ');
  const fails = roots.length > 1 ? 'fail' : 'fails';
  const multi = m.positions.length > 1;
  let verdict, sub;
  if (!res.exposed.length) { verdict = 'STAY'; sub = 'No position depends on it'; }
  else if (multi) {
    verdict = res.exits.length ? 'EXIT' : 'STAY';
    sub = res.exits.length ? `exit ${res.exits.length} of ${res.exposed.length} exposed pockets` : `all ${res.exposed.length} exposed pockets: stay`;
  } else { verdict = res.rows[0].verdict; sub = `if ${names} ${fails}`; }
  const exposedVal = res.exposed.reduce((a, r) => a + r.p.value, 0);
  const minHops = Math.min(...res.exposed.map((r) => r.hops));
  let why;
  if (!res.exposed.length) why = `${esc(names)} ${fails}, but no position depends on it: nothing to do.`;
  else {
    why = `If ${nodeName({ label: names })} ${fails}, the shock reaches ${res.exposed.length} ${pluralPos(res.exposed.length)} (${pct(exposedVal / (m.totalValue || 1))} of book) in ${minHops} hop${minHops === 1 ? '' : 's'}. Staying loses <b class="xr-red">${usd(res.stay)}</b> if it happens; exiting costs <b>${usd(res.exit)}</b> for sure.`;
    if (multi && res.exits.length) why += ` Best action: exit ${res.exits.map((r) => esc(r.p.label.split(' ')[0])).join(', ')}, stay elsewhere (total ${usd(res.optimal)}).`;
    if (roots.length === 1) {
      const be = breakEven(m, roots[0], S.failed.get(roots[0].id), res.exit);
      if (Number.isFinite(be.pStar)) {
        why += be.pStar <= 0 ? ' Exit is cheaper than staying even at today\'s odds.'
          : be.pStar >= 1 ? ' Even a certain failure costs less than exiting.'
            : ` Today's odds of this failure are ${pct(roots[0].p_fail)} over ${m.horizon}d; exiting only pays if they exceed <b>${pct(be.pStar)}</b>.`;
      }
    }
  }
  setVerdict({ mode: 'simulated failure', title: 'If it happens', verdict, stay: res.stay, exit: res.exit, why, sub, stayLabel: ['Loss if STAY', 'if it happens'],
    server: `Client-side propagation: loss = value × loss-if-fails × path transmission (best path), failure assumed certain.` });
}

function scenarioVerdict(sc, res) {
  const m = S.m;
  const exit = S.exitOverride != null || !(sc.exit_cost_usd || m.decision.exit_cost_usd) ? exitTotalAll() : (+sc.exit_cost_usd || m.decision.exit_cost_usd);
  const stay = +(sc.conditional_loss_usd != null ? sc.conditional_loss_usd : sc.expected_loss_usd) || 0;
  const verdict = S.exitOverride != null ? (stay > exit ? 'EXIT' : 'STAY') : sc.verdict || (stay > exit ? 'EXIT' : 'STAY');
  const why = `${esc(sc.description || sc.name)}. If this shock happens, staying loses <b class="xr-red">${usd(stay)}</b> over ${m.horizon} days vs a certain exit cost of <b>${usd(exit)}</b>${sc.exit && sc.exit.liquidity_factor < 1 ? ' (stressed exit liquidity)' : ''}`
    + (verdict === 'EXIT' ? `: <b class="xr-red">exit</b> saves ${usd(stay - exit)}.` : `: <b class="xr-green">stay</b>, exiting would waste ${usd(exit - stay)}.`);
  setVerdict({ mode: 'scenario · server model', title: sc.name, verdict, stay, exit, why, sub: `${pct(stay / (m.totalValue || 1))} of value at risk`,
    stayLabel: ['Loss if STAY', 'if the shock happens'],
    server: res ? `Client propagation check: ${usd(res.stay)} lost across ${res.exposed.length} ${pluralPos(res.exposed.length)} if the failure is certain.` : '' });
}

function setVerdict({ mode, title, verdict, stay, exit, why, sub, server, stayLabel = ['Expected loss if STAY', 'uncertain'] }) {
  $('kStayL').textContent = stayLabel[0];
  $('kStayS').textContent = stayLabel[1];
  $('vTitle').textContent = title;
  $('vMode').textContent = mode;
  const b = $('vBadge');
  const changed = S.verdict !== verdict;
  b.textContent = verdict || '—';
  b.className = `xr-vbadge ${verdict === 'EXIT' ? 'exit' : verdict === 'STAY' ? 'stay' : ''}`;
  if (changed && !reducedMotion()) { void b.offsetWidth; b.classList.add('pop'); }
  S.verdict = verdict;
  $('verdictCard').classList.toggle('is-exit', verdict === 'EXIT');
  $('verdictCard').classList.toggle('is-stay', verdict === 'STAY');
  $('vSub').innerHTML = `<span>${esc(sub || '')}</span>`;
  countUp($('kStay'), stay, (v) => usd(v));
  countUp($('kExit'), exit, (v) => usd(v));
  const margin = stay - exit;
  countUp($('kMargin'), margin, (v) => usd(v, { sign: true }));
  $('kMargin').className = margin > 0 ? 'xr-red' : 'xr-green';
  $('kMarginHint').textContent = margin > 0 ? 'stay costs more' : 'exit costs more';
  const mx = Math.max(stay, exit, 1);
  $('barStay').style.width = `${clamp(stay / mx * 100, 1, 100)}%`;
  $('barExit').style.width = `${clamp(exit / mx * 100, 1, 100)}%`;
  $('vWhy').innerHTML = why;
  $('vServer').hidden = !server;
  $('vServer').innerHTML = server || '';
}

// ---------- scenarios + picker
function renderScenarios(m) {
  const box = $('scenarioBtns');
  if (!m.scenarios.length) { box.innerHTML = '<p class="xr-note">No predefined scenarios in this payload: click any node to fail it.</p>'; return; }
  box.innerHTML = m.scenarios.map((s, i) => `<button class="xr-scbtn" title="${esc(s.description || '')} (key ${i + 1})">
    <span>${esc(s.name)}</span><small class="${s.verdict === 'EXIT' ? 'xr-red' : 'xr-green'}">${usd(+(s.conditional_loss_usd != null ? s.conditional_loss_usd : s.expected_loss_usd))} if it happens · ${esc(s.verdict || '')}</small></button>`).join('');
  [...box.children].forEach((b, i) => b.addEventListener('click', () => runScenario(i)));
}

function renderFailPicker(m) {
  const groups = LAYERS.filter((l) => l.key !== 'position').map((l) => {
    const ns = m.nodes.filter((n) => n.layer === l.key).sort((a, b) => b.contrib - a.contrib);
    return ns.length ? `<optgroup label="${esc(l.name)}">${ns.map((n) => `<option value="${esc(n.id)}">${esc(n.label)}</option>`).join('')}</optgroup>` : '';
  }).join('');
  $('failSelect').innerHTML = `<option value="">Fail a node…</option>${groups}`;
}

// ---------- break-even
function renderBE() {
  const m = S.m;
  const node = S.beNode;
  if (!node || node.isPos) { $('beCard').hidden = true; return; }
  $('beCard').hidden = false;
  const lgf = S.failed.has(node.id) ? S.failed.get(node.id) : node.lgf;
  const exposedRes = positionLosses(m, new Map([[node.id, lgf]]), S.exitOverride);
  const exitTotal = exposedRes.exposed.length ? exposedRes.exit : exitTotalAll();
  const be = breakEven(m, node, lgf, exitTotal);
  $('beNode').innerHTML = `${dot(node)}${esc(node.label)}`;
  const finite = Number.isFinite(be.pStar);
  const pMax = finite && be.pStar > 0.08 ? Math.min(1, Math.max(0.1, be.pStar * 1.6)) : 0.1;
  const slider = $('beSlider');
  slider.max = (pMax * 100).toFixed(2);
  slider.step = pMax > 0.2 ? '0.25' : '0.05';
  const p = S.beP ?? clamp(node.p_fail, 0, pMax);
  slider.value = (p * 100).toFixed(2);
  $('beP').textContent = pct(p, p < 0.01 ? 2 : 1);
  $('beX').textContent = `${pct(exitTotal / (m.totalValue || 1), 1)} · ${usd(exitTotal)}`;
  const v = renderBreakEven($('beChart'), be, p, pMax, node.label);
  let msg;
  if (!(be.L > 0)) msg = `No position depends on ${esc(node.label)}: its failure costs nothing here.`;
  else if (be.pStar <= 0) msg = `<b class="xr-red">EXIT at any probability</b>: other risks already exceed the exit cost.`;
  else if (be.pStar >= 1) msg = `<b class="xr-green">STAY</b>: even a certain failure of ${esc(node.label)} (−${usd(be.L)}) costs less than exiting.`;
  else msg = `<b class="${v === 'EXIT' ? 'xr-red' : 'xr-green'}">${v}</b> at ${pct(p, 1)}. Exit if P(${esc(node.label)} fails) &gt; <b>${pct(be.pStar, 1)}</b> over ${m.horizon}d · model estimate ${pct(node.p_fail, 1)} · loss if it happens ${usd(be.L)} vs exit ${usd(be.exit)}${m.positions.length > 1 ? ` (${exposedRes.exposed.length} exposed ${pluralPos(exposedRes.exposed.length)})` : ''}.`;
  $('beOut').innerHTML = msg;
}

// ---------- book
function renderBook(m) {
  const b = m.book;
  if (!b || !b.pockets.length) { $('bookCard').hidden = true; return; }
  const P = b.pockets;
  const exitAll = P.reduce((a, p) => a + (+p.exit_cost_usd || 0), 0);
  const affected = P.filter((p) => p.affected);
  const opts = [
    { k: 'Stay everywhere', v: +b.total_stay_loss_usd, d: 'expected loss, uncertain' },
    { k: 'Best action per pocket', v: +b.total_optimal_usd, d: `${pct(+b.pct_of_book, 2)} of book` },
    { k: 'Exit whole book', v: exitAll, d: 'certain cost' },
  ];
  const best = Math.min(...opts.map((o) => o.v));
  $('bookPct').textContent = `${P.length} pockets`;
  $('bookNote').innerHTML = `${esc(b.scenario || `Stress test: ${affected.length} of ${P.length} pockets hit by ${S.m.scenarios[0] ? `“${S.m.scenarios[0].name}”` : 'the stress scenario'}`)}. Exit is expensive but certain; staying is cheaper on average but uncertain.`;
  $('bookTotals').innerHTML = opts.map((o) => `<div class="xr-total ${o.v === best ? 'best' : ''}"><span>${o.k}</span><b>${usd(o.v)}</b><small>${o.d}</small></div>`).join('');
  $('bookTable').innerHTML = `<thead><tr><th>Pocket</th><th class="num">Value</th><th class="num">Stay loss</th><th class="num">Exit cost</th><th>Call</th></tr></thead><tbody>
    ${P.map((p) => {
      const node = S.m.positions.find((n) => n.label === p.label || n.id === p.label || n.label.split(' ')[0] === p.label);
      return `<tr class="${p.affected ? 'hit' : ''}" ${node ? `data-id="${esc(node.id)}"` : ''}><td>${p.affected ? '<i class="xr-hitdot" title="hit by the stress scenario"></i>' : '<i class="xr-hitdot off"></i>'}${esc(p.label)}</td>
      <td class="num">${usd(+p.value_usd)}</td><td class="num ${p.affected ? 'xr-red' : ''}">${usd(+p.stay_loss_usd)}</td><td class="num">${usd(+p.exit_cost_usd)}</td>
      <td><span class="xr-vb xr-vb-${String(p.verdict).toLowerCase()}">${esc(p.verdict)}</span></td></tr>`;
    }).join('')}</tbody>`;
  $('bookTable').querySelectorAll('tr[data-id]').forEach((tr) => tr.addEventListener('click', () => { select(tr.dataset.id); S.g.centerOn(tr.dataset.id); }));
}

// ---------- concentration
function renderConcentration(m) {
  const { list, insights } = S.conc;
  const multi = m.positions.length > 1;
  $('concChip').textContent = multi ? `${m.positions.length} positions` : 'single position';
  const top = list.slice(0, multi ? 8 : 7);
  $('concList').innerHTML = top.map((c, i) => {
    const bar = multi ? c.share : c.elShare;
    const text = multi
      ? `${c.deps.length}/${m.positions.length} · <b>${pct(c.share)}</b> of book`
      : `<b>${pct(c.elShare)}</b> of risk · ${c.minHops} hop${c.minHops === 1 ? '' : 's'}`;
    const tag = multi
      ? (c.indirect.length ? `<em title="${c.indirect.length} position(s) reach it only through other protocols">${c.indirect.length} hidden</em>` : '')
      : (c.minHops >= 2 ? '<em title="Not a direct dependency">indirect</em>' : '');
    const hot = multi ? c.share >= 0.5 : c.elShare >= 0.3;
    return `<li data-i="${i}" class="${hot ? 'hot' : ''}" tabindex="0"><div class="xr-conc-h">${dot(c.n)}<span>${esc(c.n.label)}</span>${tag}</div>
      <div class="xr-conc-bar"><i style="width:${clamp(bar * 100, 2, 100)}%;--c:${COL[c.n.layer] || COL.protocol}"></i></div><div class="xr-conc-t">${text}</div></li>`;
  }).join('') || '<li class="xr-empty">No shared dependencies found.</li>';
  const items = [...$('concList').querySelectorAll('li[data-i]')];
  items.forEach((li) => {
    const go = () => {
      const c = top[+li.dataset.i];
      const f = closure(m, c.n.id, 'down');
      for (const el of document.querySelectorAll('.xr-conc li.on, .xr-insights li.on')) el.classList.remove('on');
      li.classList.add('on');
      select(c.n.id, { focusSet: f });
      S.g.centerOn(c.n.id);
    };
    li.addEventListener('click', go);
    li.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  });
  $('concInsights').innerHTML = insights.map((x, i) => `<li data-i="${i}" tabindex="0"><span class="xr-eye">◎</span><div>${nodeName(x.p)} never touches ${nodeName(x.c.n)} directly, but depends on it via ${x.via.map((v) => esc(v.label)).join(' → ')} <span class="xr-muted">(${x.hops} hops)</span>.</div></li>`).join('');
  [...$('concInsights').children].forEach((li) => li.addEventListener('click', () => {
    const x = insights[+li.dataset.i];
    const path = pathTo(m, x.p.id, x.c.n.id);
    for (const el of document.querySelectorAll('.xr-conc li.on, .xr-insights li.on')) el.classList.remove('on');
    li.classList.add('on');
    select(x.c.n.id, { focusSet: new Set(path.map((n) => n.id)) });
    S.g.centerOn(x.c.n.id);
  }));
}

// ---------- drawer
const ORACLE_CHIPS = [
  ['twap_window', (v) => `TWAP ${v}`],
  ['twap_minutes', (v) => `TWAP ${v}m`],
  ['provider', (v) => `${v}`],
  ['single_feed', (v) => (v ? 'single feed' : 'multi-feed')],
  ['sources', (v) => (+v === 1 ? 'single source' : `${v} sources`)],
  ['deviation_threshold', (v) => `deviation ${+v < 1 ? pct(+v, 1) : `${v}%`}`],
  ['deviation', (v) => `deviation ${+v < 1 ? pct(+v, 1) : `${v}%`}`],
  ['heartbeat', (v) => `heartbeat ${v}`],
  ['provider', (v) => String(v)],
];

function metaHtml(meta) {
  const chips = [];
  const rows = [];
  const used = new Set();
  for (const [k, f] of ORACLE_CHIPS) {
    if (meta[k] == null || meta[k] === '') continue;
    const warn = (k === 'single_feed' && meta[k]) || (k === 'sources' && +meta[k] === 1);
    chips.push(`<span class="xr-qchip ${warn ? 'warn' : ''}">${esc(f(meta[k]))}</span>`);
    used.add(k);
  }
  for (const [k, v] of Object.entries(meta)) {
    if (used.has(k) || v == null || v === '' || k === 'placeholder') continue;
    const label = k.replace(/_/g, ' ');
    let val;
    if (typeof v === 'string' && /^0x[a-fA-F0-9]{40}$/.test(v)) {
      val = `<code title="${esc(v)}">${esc(v.slice(0, 6))}…${esc(v.slice(-4))}</code><button class="xr-copy" data-copy="${esc(v)}" title="Copy address">copy</button>`;
    } else if (typeof v === 'string' && /^https?:\/\//.test(v)) {
      val = `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v.replace(/^https?:\/\//, '').slice(0, 32))}</a>`;
    } else if (typeof v === 'number' && /usd|tvl|liquidity/.test(k)) val = usd(v);
    else if (typeof v === 'number' && /ltv|rate|pct|share/.test(k) && v <= 1) val = pct(v, 1);
    else if (typeof v === 'object') val = `<code>${esc(JSON.stringify(v).slice(0, 80))}</code>`;
    else val = esc(String(v));
    rows.push(`<div class="xr-kv"><span>${esc(label)}</span><b>${val}</b></div>`);
  }
  return { chips: chips.join(''), rows: rows.join('') };
}

function renderDrawer(n) {
  const m = S.m;
  const d = $('drawer');
  const deps = m.out.get(n.id);
  const dependents = m.inc.get(n.id);
  const reachers = m.positions.filter((p) => p !== n && m.reach.get(p.id).has(n.id));
  const bestT = reachers.length ? Math.max(...reachers.map((p) => m.reach.get(p.id).get(n.id).t)) : 0;
  const { chips, rows } = metaHtml(n.meta);
  const linkList = (arr, side) => arr.length
    ? arr.sort((a, b) => b.t - a.t).map((e) => { const o = e[side]; return `<li data-id="${esc(o.id)}">${dot(o)}<span>${esc(o.label)}</span><em>${pct(e.t)}</em>${e.reason ? `<small>${esc(e.reason)}</small>` : ''}</li>`; }).join('')
    : '<li class="xr-empty">none</li>';
  const stats = n.isPos
    ? `<div><span>Value</span><b>${usd(n.value)}</b></div><div><span>Exit cost</span><b>${usd(exitCostOf(m, n, S.exitOverride))}</b></div><div><span>Dependencies</span><b>${m.reach.get(n.id).size - 1}</b></div>`
    : `<div><span>P(fail) ${m.horizon}d</span><b>${pct(n.p_fail, n.p_fail < 0.01 ? 2 : 1)}</b></div><div><span>Loss if fails</span><b>${pct(n.lgf)}</b></div>
       <div><span>Expected loss</span><b>${usd(n.contrib)}</b></div><div><span>Max transmission</span><b>${reachers.length ? pct(bestT) : '—'}</b></div>
       <div><span>Positions exposed</span><b>${reachers.length}/${m.positions.length}</b></div><div><span>Dependents</span><b>${dependents.length}</b></div>`;
  d.innerHTML = `<div class="xr-drawer-h">${dot(n)}<div><h3>${esc(n.label)}</h3><span class="xr-chip" style="--c:${COL[n.layer]}">${esc(LAYER_NAME[n.layer] || n.layerRaw)}</span> <code class="xr-id">${esc(n.id)}</code></div>
      <button class="xr-x" id="drawerClose" aria-label="Close details">×</button></div>
    <div class="xr-stats">${stats}</div>
    ${chips ? `<div class="xr-qchips">${chips}</div>` : ''}
    ${!n.isPos ? `<div class="xr-drawer-actions"><button class="xr-btn xr-btn-red" id="dFail">Simulate failure</button><button class="xr-btn" id="dAdd">+ Add to failure</button></div>` : ''}
    <h4>Depends on (${deps.length})</h4><ul class="xr-links-list">${linkList([...deps], 'dst')}</ul>
    <h4>Dependents (${dependents.length})</h4><ul class="xr-links-list">${linkList([...dependents], 'src')}</ul>
    ${rows ? `<h4>Details</h4><div class="xr-meta">${rows}</div>` : ''}`;
  d.hidden = false;
  $('drawerClose').onclick = deselect;
  if (!n.isPos) {
    $('dFail').onclick = () => failNodes([n.id], false);
    $('dAdd').onclick = () => failNodes([n.id], true);
  }
  d.querySelectorAll('li[data-id]').forEach((li) => li.addEventListener('click', () => { select(li.dataset.id); S.g.centerOn(li.dataset.id); }));
  d.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'copied'; } catch { b.textContent = 'failed'; }
    setTimeout(() => { b.textContent = 'copy'; }, 1200);
  }));
}
