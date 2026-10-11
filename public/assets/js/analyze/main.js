// /analyze.html controller. Loads /api/analyze, renders the decision, the strata X-Ray and the analysis tools.
// Contract: every financial number on screen is a payload field. Interactive shocks call the server.
import { mountShell, setShellEnd } from '../core/shell.js';
import { getJson, apiUrl, explain } from '../core/api.js';
import { analyzeStatus, statusChip } from '../core/status.js';
import { mountWork, ANALYZE_STEPS } from '../core/work.js';
import { esc, usd, usdFull, pct, mult, ago, num, short, verdictClass, verdictWord, tag } from '../core/format.js';
import { headline, bandLayout, indexPayload, nodeImpact, ROLE_WORDS, BANDS, isAssumption, CLASS_WORDS } from './view.js';
import { renderGraph, highlight, legendHtml, shortLabel } from './graph.js';
import * as P from './panels.js';

mountShell({ active: 'analyze' });

const qs = new URLSearchParams(location.search);
const BASE = { ref: qs.get('ref') || 'auto', value_usd: qs.get('value_usd') || undefined };
const S = {
  role: qs.get('borrower') ? 'borrower' : 'collateral',
  payload: null, index: null, meta: null, sel: null, ctl: null, fetchedAt: 0, snapshot: null,
};
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- loading
function paramsFor(role = S.role, extra = {}) {
  return { ...BASE, ...(role === 'borrower' ? { borrower: 'auto' } : {}), ...extra };
}

async function load({ role = S.role } = {}) {
  if (S.ctl) S.ctl.abort();
  const ctl = new AbortController();
  S.ctl = ctl;
  S.snapshot = null;
  const url = apiUrl('/api/analyze', paramsFor(role));
  $('rerun').disabled = true;
  setShellEnd(statusChip('loading', 'live request', { live: true }));
  const work = mountWork($('loadState'), {
    title: role === 'borrower' ? 'Reading the largest real borrower and its liquidation math' : 'Running the live dependency analysis',
    typical: [20, 35], steps: ANALYZE_STEPS, onCancel: () => ctl.abort(),
  });
  document.body.classList.add('is-loading');
  try {
    const r = await getJson(url, { signal: ctl.signal });
    if (S.ctl !== ctl) return;
    work.stop();
    S.role = role;
    apply(r.data, { fromCache: r.fromCache, ageS: r.ageS });
  } catch (err) {
    if (S.ctl !== ctl) return;
    work.stop();
    if (err.code === 'aborted') { showError(err, { cancelled: true }); return; }
    showError(err);
  } finally {
    if (S.ctl === ctl) { $('rerun').disabled = false; document.body.classList.remove('is-loading'); }
  }
}

function showError(err, { cancelled = false } = {}) {
  const x = explain(err);
  setShellEnd(statusChip('unavailable', cancelled ? 'cancelled' : (err.code || '')));
  const box = $('loadState');
  box.hidden = false;
  box.innerHTML = `<div class="alert alert--error" role="alert">
      <p class="alert__title">${esc(cancelled ? 'Analysis cancelled' : x.title)}</p>
      <p class="muted">${esc(cancelled ? 'No figures are shown for a cancelled run.' : x.body)}</p>
      <p class="note">No numbers are substituted. You can retry the live analysis, or open the saved snapshot on purpose: it is a real backend response recorded earlier and is labelled as such everywhere.</p>
      <div class="alert__actions"><button class="btn btn--primary btn--sm" data-a="retry">Retry live analysis</button>
        <button class="btn btn--sm" data-a="snap">Open saved snapshot</button></div></div>`;
  box.querySelector('[data-a="retry"]').addEventListener('click', () => load());
  box.querySelector('[data-a="snap"]').addEventListener('click', openSnapshot);
}

async function openSnapshot() {
  try {
    const r = await getJson('/data/snapshot-analyze.json', { timeout: 15000, store: false });
    const snap = r.data._snapshot || {};
    const created = snap.created_at ? new Date(snap.created_at).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'unknown date';
    S.role = 'collateral';
    apply(r.data, { snapshot: { ...snap, label: `block ${num(snap.block)}, recorded ${created}` } });
    $('rerun').disabled = false;
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- apply payload
function apply(payload, meta) {
  S.payload = payload;
  S.meta = meta;
  S.snapshot = meta.snapshot || null;
  S.fetchedAt = Date.now() - (meta.ageS || 0) * 1000;
  S.index = indexPayload(payload);
  S.index.posLabel = (payload.position.label || '').split(' on ')[0];
  S.index.posSub = `${usd(payload.position.value_usd)}, ${payload.position.meta && payload.position.meta.exposure_role === 'borrower' ? 'borrower view' : 'collateral, no debt'}`;
  $('loadState').hidden = true;
  $('loadState').innerHTML = '';
  renderPosition();
  renderStatus();
  renderDecision();
  renderXray();
  P.renderAll(S, ctx);
  syncRoleSeg();
  if (S.sel) select(S.sel, { quiet: true });
}

function renderStatus() {
  const st = analyzeStatus(S.payload, { fromCache: S.meta.fromCache, ageS: S.meta.ageS, snapshot: S.snapshot });
  const age = (Date.now() - S.fetchedAt) / 1000;
  let { key, meta } = st;
  if (key === 'live' && age > 60) { key = 'stale'; meta = `fetched ${ago(age)}; the exit quote expires after 60 s`; }
  else if (key === 'live') meta = `${meta}, ${ago(age)}`;
  setShellEnd(statusChip(key, meta, { live: false }));
  return key;
}
setInterval(() => { if (S.payload && !S.snapshot) renderStatus(); }, 5000);

function renderPosition() {
  const p = S.payload.position;
  const m = p.meta || {};
  $('posTitle').textContent = p.label;
  const role = m.exposure_role === 'borrower' ? 'analysed as a real borrower (debt and liquidation)' : 'collateral without debt';
  const sub = [`${usdFull(p.value_usd)} hypothetical exposure`, `${p.horizon_days}-day horizon`, `${p.chain}`, role];
  if (m.block_number) sub.push(`block ${num(m.block_number)}`);
  $('posSub').textContent = sub.join(', ');
  document.title = `FAULTLINE — ${p.label}`;
}

// ---------------------------------------------------------------- decision
function renderDecision() {
  const h = headline(S.payload);
  const cls = verdictClass(h.verdict);
  $('decision').dataset.v = cls;
  const H = h.horizon;
  const sentence = h.firm
    ? `${h.verdict === 'EXIT' ? 'Even the lowest estimate of the staying loss is above the highest cost of exiting.' : 'Even the highest estimate of the staying loss is below the lowest cost of exiting.'}`
    : `The estimates overlap, so the model will not make a firm call.`;
  $('verdict').innerHTML = `
    <span class="vword an-verdict__word v-${cls}">${esc(verdictWord(h.verdict))}</span>
    <div class="an-verdict__lean">${h.lean ? `<span>leans ${tag(h.lean)}</span>` : ''}<span class="an-verdict__conf">${esc(h.confidence || '')} confidence</span></div>
    <p class="an-verdict__sentence">Staying has an estimated loss of <b>${usd(h.stay.central)}</b> over ${H} days (range ${usd(h.stay.low)} to ${usd(h.stay.high)}).
      Exiting now costs <b>${usd(h.exit.total)}</b>: ${usd(h.exit.execution)} to sell${h.exit.carry != null ? ` plus ${usd(h.exit.carry)} of yield given up` : ''}.
      ${h.breakeven ? `The answer changes only if the true risk is about <b>${mult(h.breakeven, 1)}</b> the estimate.` : ''} ${sentence}</p>`;
  renderBands(h);
  $('facts').innerHTML = `
    <div><dt>Loss if you stay, ${H} days</dt><dd>${usdFull(h.stay.central)}<small>range ${usd(h.stay.low)} to ${usd(h.stay.high)}</small></dd></div>
    <div><dt>Cost to exit now</dt><dd>${usdFull(h.exit.total)}<small>${usd(h.exit.execution)} execution, ${h.exit.carry != null ? usd(h.exit.carry) + ' carry' : 'carry unknown'}</small></dd></div>
    <div><dt>Risk multiple to flip the call</dt><dd>${mult(h.breakeven, 2)}<small>${h.lean === 'STAY' || h.verdict === 'STAY' ? 'stay holds below this' : 'exit holds above this'}</small></dd></div>
    <div><dt>Exit quote</dt><dd>${esc(qWord(h.quoteStatus))}<small>${esc(S.payload.exit && S.payload.exit.aggregator ? 'Pendle router via ' + S.payload.exit.aggregator : (S.payload.exit && S.payload.exit.method) || '')}</small></dd></div>`;
  const d = S.payload.decision;
  const reasons = [...h.blockers, ...h.reasons.filter((r) => !h.blockers.includes(r))];
  $('why').innerHTML = `
    ${h.firm ? '' : `<p class="an-h3" style="margin:0">Why it is not a firm decision</p>`}
    ${reasons.length ? `<ul>${reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
    <details class="more"><summary>Full model explanation</summary><p class="long">${esc(d.explanation)}</p><p class="long">${esc(d.rule)}</p></details>`;
}
const qWord = (s) => ({ simulated: 'Re-executed on-chain', indicative: 'Indicative', stale: 'Stale', replayed_cache: 'Replayed', simulation_mismatch: 'Mismatch', approximation: 'Approximation' }[s] || s || '—');

function renderBands(h) {
  const L = bandLayout(h);
  const fig = $('bands');
  if (!L) { fig.innerHTML = ''; return; }
  const W = Math.max(300, Math.min(620, Math.round(fig.clientWidth || 520))), x0 = W < 420 ? 44 : 64, x1 = W - 12, X = (t) => x0 + (x1 - x0) * t;
  const row = (y, b, cls, label, vals) => `
    <text class="lbl" x="0" y="${y + 5}">${label}</text>
    <rect class="b-${cls}" x="${X(b.a)}" y="${y - 9}" width="${Math.max(2, X(b.b) - X(b.a))}" height="18" rx="2"></rect>
    <line class="c c-${cls}" x1="${X(b.c)}" x2="${X(b.c)}" y1="${y - 13}" y2="${y + 13}"></line>
    <text class="val" x="${Math.min(X(b.c) + 6, x1 - 40)}" y="${y - 16}">${vals}</text>`;
  fig.innerHTML = `<svg viewBox="0 0 ${W} 132" role="img" aria-label="Loss if you stay ${usd(h.stay.low)} to ${usd(h.stay.high)}, central ${usd(h.stay.central)}; cost to exit ${usd(h.exit.low)} to ${usd(h.exit.high)}, central ${usd(h.exit.total)}.${L.overlap ? ' The ranges overlap.' : ''}">
      <defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="rgba(242,180,65,.10)"/><line x1="0" y1="0" x2="0" y2="6" stroke="rgba(242,180,65,.55)" stroke-width="2"/></pattern></defs>
      ${L.ticks.map((t) => `<line class="gl" x1="${X(t.x)}" x2="${X(t.x)}" y1="14" y2="104"></line><text class="tick" x="${X(t.x)}" y="122" text-anchor="middle">${usd(t.v)}</text>`).join('')}
      ${L.overlap ? `<rect class="ov" x="${X(L.overlap[0])}" y="14" width="${X(L.overlap[1]) - X(L.overlap[0])}" height="90"></rect>` : ''}
      ${row(42, L.stay, 'stay', 'Stay', usd(h.stay.central))}
      ${row(84, L.exit, 'exit', 'Exit', usd(h.exit.total))}
    </svg>
    <figcaption class="note">${L.overlap ? 'The hatched zone is where the two ranges overlap: that overlap is why the verdict is Review.' : 'The ranges do not overlap.'} Log scale. Ranges and central values from the backend.</figcaption>`;
}

// ---------------------------------------------------------------- x-ray
function renderXray() {
  renderGraph($('graph'), S.index, { onSelect: (id) => select(id), width: $('graphBox').clientWidth });
  $('legend').innerHTML = legendHtml();
  renderList();
}

function renderList() {
  const rows = S.index.nodes.filter((n) => n.id !== S.index.posId).sort((a, b) => BANDS.findIndex((x) => x.key === a.band) - BANDS.findIndex((x) => x.key === b.band));
  $('listBox').innerHTML = `<div class="tablewrap"><table class="table"><caption class="vh">Dependencies of the position, with the backend's single-failure result</caption>
    <thead><tr><th>Dependency</th><th>Layer</th><th>Channel to you</th><th class="r">If it fails alone</th><th>Call</th></tr></thead><tbody>
    ${rows.map((n) => {
      const ch = n.stress && n.stress.channel;
      const blocked = ch && ch.blocked_by && ch.blocked_by.length;
      return `<tr data-id="${esc(n.id)}"${S.sel === n.id ? ' class="sel"' : ''}><td><button class="link" data-id="${esc(n.id)}">${esc(n.label)}</button>${n.hidden ? ' <span class="tag tag--neutral">hidden</span>' : ''}</td>
        <td>${esc((BANDS.find((b) => b.key === n.band) || {}).label || '')}</td>
        <td>${blocked ? esc(ch.blocked_by.includes('debt') ? 'debt only' : 'exit cost only') : n.stress ? 'reaches you' : 'not reachable'}</td>
        <td class="r">${n.stress ? (blocked ? 'no effect' : usd(n.stress.conditional_loss_usd)) : '—'}</td>
        <td>${n.stress ? tag(blocked ? 'STAY' : n.stress.verdict_if_shocked) : ''}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  $('listBox').querySelectorAll('button.link').forEach((b) => b.addEventListener('click', () => select(b.dataset.id)));
}

document.querySelectorAll('.an-xray__view button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
function setView(v) {
  const list = v === 'list';
  document.querySelectorAll('.an-xray__view button').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.view === v)));
  $('graphBox').hidden = list; $('legend').hidden = list; $('listBox').hidden = !list;
  if (!list && S.index) { renderXray(); if (S.sel) select(S.sel, { quiet: true }); }
}
if (innerWidth <= 760) setView('list');

function select(id, { quiet = false } = {}) {
  const n = S.index && S.index.byId.get(id);
  if (!n) return;
  S.sel = id;
  const imp = nodeImpact(n, S.payload);
  highlight($('graph'), imp.path, { blocked: imp.kind === 'blocked', selected: id });
  $('listBox').querySelectorAll('tr[data-id]').forEach((tr) => tr.classList.toggle('sel', tr.dataset.id === id));
  renderNode(n, imp);
  if (!quiet) $('nodePanel').scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

function renderNode(n, imp) {
  const box = $('nodePanel');
  box.hidden = false;
  const lastEdge = imp.path && imp.path.length > 1 ? S.payload.edges.find((e) => e.src === imp.path[imp.path.length - 2] && e.dst === n.id) : null;
  const labels = new Map(S.index.nodes.map((x) => [x.id, x.label]));
  const u = n.unc || {};
  const pf = u.p_fail_horizon || {}, lg = u.loss_given_failure || {};
  const m = n.meta || {};
  const extra = [];
  if (m.feeds && m.feeds.length) extra.push(['Feeds read on-chain', `${m.feeds.length}${m.single_feed ? ', single feed' : ''}${m.providers && m.providers.length ? ', ' + m.providers.join(', ') : ''}`]);
  if (m.computed_on_read != null && m.role === 'oracle') extra.push(['Updated', m.computed_on_read ? 'computed on read (no heartbeat)' : 'pushed updates']);
  if (m.liquidity_usd) extra.push(['Pool liquidity', usd(m.liquidity_usd)]);
  if (m.implied_apy != null) extra.push(['PT implied yield', pct(m.implied_apy, 2)]);
  if (m.expiry) extra.push(['Maturity', String(m.expiry).slice(0, 10)]);
  if (m.tvl_usd) extra.push(['TVL', usd(m.tvl_usd)]);
  const impact = imp.kind === 'blocked'
    ? `<div class="an-node__impact is-blocked"><p class="faint">Backend stress run, this dependency failing alone</p>
        <p class="big">No effect on this position</p><p class="muted" style="margin-top:6px">${esc(imp.note || '')}</p>
        <p class="note" style="margin-top:6px">The staying loss stays at the baseline ${usd(imp.loss)}; the call stays ${tag('STAY')}.</p></div>`
    : imp.kind === 'reaches'
      ? `<div class="an-node__impact"><p class="faint">Backend stress run: if it fails at ${pct(imp.severity, 0)} severity</p>
          <p class="big">${usd(imp.loss)} <span class="faint" style="font-size:var(--t-md);font-weight:450">lost if you stay</span></p>
          <p class="muted" style="margin-top:4px">vs ${usd(imp.exitSide)} to exit now: ${tag(imp.verdict)}</p>
          <p class="note" style="margin-top:6px">Conditional on the failure happening. Today's modelled odds are ${pct(n.p_fail, 3)} over the horizon.</p></div>`
      : `<div class="an-node__impact is-blocked"><p class="muted">${esc(imp.text)}</p></div>`;
  box.innerHTML = `
    <div>
      <h3>${esc(n.label)}</h3>
      <p class="an-node__role">${esc(ROLE_WORDS[m.role] || n.layer)}${n.hidden ? ', hidden: not visible from the position itself' : ''}</p>
      ${lastEdge ? `<p class="an-node__why">${esc(lastEdge.reason)}</p>` : ''}
      ${imp.path && imp.path.length > 1 ? `<div class="an-node__path" aria-label="Failure path reported by the backend">${imp.path.slice().reverse().map((id) => `<span>${esc(shortLabel(id === S.index.posId ? 'Your position' : labels.get(id)))}</span>`).join('<em>to</em>')}</div>` : ''}
      <dl class="an-kv">
        <dt>Failure odds, ${S.payload.position.horizon_days} d</dt><dd>${pct(n.p_fail, 3)} <span class="faint">${esc(CLASS_WORDS[pf.class] || '')}</span></dd>
        <dt>Loss if it fails</dt><dd>${pct(n.loss_given_failure, 1)} of what it carries <span class="faint">${esc(CLASS_WORDS[lg.class] || '')}</span></dd>
        ${extra.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
        ${m.address ? `<dt>Contract</dt><dd><a class="mono" href="https://etherscan.io/address/${esc(m.address)}" target="_blank" rel="noopener">${esc(short(m.address, 8, 6))}</a></dd>` : ''}
      </dl>
      <details class="more" style="margin-top:8px"><summary>Where these numbers come from</summary><p class="note" style="margin-top:6px">${esc(m.source || pf.why || '')}</p><p class="note" style="margin-top:6px">${esc(m.lgf_source || lg.why || '')}</p></details>
    </div>
    <div>${impact}
      <div class="an-node__actions"><button class="btn btn--sm" data-a="shock">Simulate a different severity</button>
      <button class="btn btn--quiet btn--sm" data-a="clear">Clear selection</button></div></div>`;
  box.querySelector('[data-a="shock"]').addEventListener('click', () => { P.prefillIncident(n.id); openTab('t-incident', true); });
  box.querySelector('[data-a="clear"]').addEventListener('click', clearSel);
}

function clearSel() {
  S.sel = null;
  highlight($('graph'), [], {});
  $('nodePanel').hidden = true;
  $('listBox').querySelectorAll('tr.sel').forEach((tr) => tr.classList.remove('sel'));
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.sel) clearSel(); });

let rsz = 0;
window.addEventListener('resize', () => { clearTimeout(rsz); rsz = setTimeout(() => { if (!S.index) return; renderXray(); if (S.sel) select(S.sel, { quiet: true }); }, 180); });

// ---------------------------------------------------------------- role, rerun, tabs
function syncRoleSeg() {
  document.querySelectorAll('#roleSeg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.role === S.role)));
}
document.querySelectorAll('#roleSeg button').forEach((b) => b.addEventListener('click', () => {
  if (b.dataset.role === S.role && S.payload) return;
  document.querySelectorAll('#roleSeg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  const u = new URL(location.href);
  if (b.dataset.role === 'borrower') u.searchParams.set('borrower', 'auto'); else u.searchParams.delete('borrower');
  history.replaceState(null, '', u);
  load({ role: b.dataset.role });
}));
$('rerun').addEventListener('click', () => load());

const tabs = [...document.querySelectorAll('#tabs [role="tab"]')];
function openTab(id, focusPanel = false) {
  tabs.forEach((t) => {
    const on = t.id === id;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute('aria-controls')).hidden = !on;
  });
  const t = $(id);
  if (focusPanel) { $(t.getAttribute('aria-controls')).scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  const u = new URL(location.href); u.hash = id.slice(2); history.replaceState(null, '', u);
}
tabs.forEach((t, i) => {
  t.addEventListener('click', () => openTab(t.id));
  t.addEventListener('keydown', (e) => {
    const k = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!k) return;
    e.preventDefault();
    const nt = tabs[(i + k + tabs.length) % tabs.length];
    openTab(nt.id); nt.focus();
  });
});
if (location.hash && $('t-' + location.hash.slice(1))) openTab('t-' + location.hash.slice(1));

// context handed to panels
const ctx = {
  analyzeUrl: (extra) => apiUrl('/api/analyze', paramsFor(S.role, extra)),
  select, openTab, reload: (role) => load({ role }),
  get snapshot() { return S.snapshot; },
};

if (qs.get('snapshot') === '1') openSnapshot(); else load();
