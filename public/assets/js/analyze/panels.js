// Analysis tools. Each panel renders backend fields; interactive changes call the backend again.
import { getJson, explain } from '../core/api.js';
import { statusChip, analyzeStatus } from '../core/status.js';
import { mountWork, ANALYZE_STEPS } from '../core/work.js';
import { esc, usd, usdFull, pct, num, mult, ago, short, tag, verdictWord } from '../core/format.js';
import { BANDS, ROLE_WORDS, bookRows, maturityView, sensitivityView, isAssumption, CLASS_WORDS } from './view.js';

const $ = (id) => document.getElementById(id);
let S, ctx;
const incident = { node: null, severity: null, ctl: null, last: null };
const book = { mode: 'quoted', ctl: null };

export function renderAll(state, context) {
  S = state; ctx = context;
  renderIncident();
  renderOptions();
  renderBook(S.payload.book, { mode: 'quoted' });
  renderStress();
  renderBorrower();
  renderEvidence();
}

// ================================================================ incident lab
export function prefillIncident(id) {
  incident.node = id;
  const n = S.index.byId.get(id);
  incident.severity = n ? Math.round(n.loss_given_failure * 100) : 50;
  renderIncident();
}

function renderIncident() {
  const el = $('p-incident');
  const deps = S.index.nodes.filter((n) => n.id !== S.index.posId);
  if (!incident.node || !S.index.byId.has(incident.node)) incident.node = (deps.find((n) => n.meta.role === 'issuer') || deps[0]).id;
  const cur = S.index.byId.get(incident.node);
  if (incident.severity == null) incident.severity = Math.round(cur.loss_given_failure * 100);
  const groups = BANDS.filter((b) => b.key !== 'position').map((b) => ({ b, ns: deps.filter((n) => n.band === b.key) })).filter((g) => g.ns.length);
  const oracle = deps.find((n) => n.meta.role === 'oracle');
  const issuer = deps.find((n) => n.meta.role === 'issuer');
  const under = deps.find((n) => n.meta.role === 'underlying');
  el.innerHTML = `
    <p class="lead">Pick a dependency, set how badly it fails, and run the incident on the live backend. The result covers the
      position and every pocket of the book that shares the dependency. Incidents are hypothetical: nothing has failed.</p>
    <form class="inc-form" id="incForm">
      <label class="field"><span>Dependency that fails</span>
        <select class="select" id="incNode">${groups.map((g) => `<optgroup label="${esc(g.b.label)}">${g.ns.map((n) => `<option value="${esc(n.id)}"${n.id === incident.node ? ' selected' : ''}>${esc(n.label)}</option>`).join('')}</optgroup>`).join('')}</select></label>
      <label class="inc-sev"><span class="muted" style="font-size:var(--t-sm)">Severity: share of the value it carries that is lost, <output id="incSevOut">${incident.severity}%</output></span>
        <input type="range" id="incSev" min="0" max="100" step="5" value="${incident.severity}" aria-describedby="incSevHelp"></label>
      <button class="btn btn--fault" type="submit" id="incRun">Run incident</button>
    </form>
    <p class="note" id="incSevHelp" style="margin-top:6px">Default severity = the dependency's calibrated loss if it fails (${pct(cur.loss_given_failure, 1)}). Each run is a full live analysis (about 20–35 s); results are kept for this session.</p>
    <div class="inc-presets" aria-label="Suggested incidents">
      ${oracle ? `<button class="btn btn--sm" data-n="${esc(oracle.id)}" data-s="${Math.round(oracle.loss_given_failure * 100)}">The brief's layer-3 incident: oracle fails</button>` : ''}
      ${issuer ? `<button class="btn btn--sm" data-n="${esc(issuer.id)}" data-s="50">Issuer loses 50%</button>` : ''}
      ${under ? `<button class="btn btn--sm" data-n="${esc(under.id)}" data-s="30">Underlying depegs 30%</button>` : ''}
    </div>
    <div class="inc-result" id="incResult">${incident.last ? '' : '<p class="note">No incident run yet.</p>'}</div>`;
  const sev = $('incSev'), out = $('incSevOut');
  sev.addEventListener('input', () => { out.textContent = `${sev.value}%`; incident.severity = +sev.value; });
  $('incNode').addEventListener('change', (e) => {
    incident.node = e.target.value;
    const n = S.index.byId.get(incident.node);
    incident.severity = Math.round(n.loss_given_failure * 100);
    sev.value = incident.severity; out.textContent = `${incident.severity}%`;
    ctx.select(incident.node, { quiet: true });
  });
  $('incForm').addEventListener('submit', (e) => { e.preventDefault(); runIncident(incident.node, incident.severity); });
  el.querySelectorAll('.inc-presets button').forEach((b) => b.addEventListener('click', () => {
    incident.node = b.dataset.n; incident.severity = +b.dataset.s;
    renderIncident();
    runIncident(incident.node, incident.severity);
  }));
  if (incident.last) showIncident(incident.last.data, incident.last.meta);
}

async function runIncident(id, sevPct) {
  if (incident.ctl) incident.ctl.abort();
  const ctl = new AbortController();
  incident.ctl = ctl;
  ctx.select(id, { quiet: true });
  const box = $('incResult');
  const url = ctx.analyzeUrl({ shock: id, severity: (sevPct / 100).toFixed(2) });
  const work = mountWork(box, { title: `Running the incident: ${S.index.byId.get(id).label} fails at ${sevPct}%`, typical: [20, 35], steps: ANALYZE_STEPS.slice(0, 6), onCancel: () => ctl.abort() });
  $('incRun').disabled = true;
  try {
    const r = await getJson(url, { signal: ctl.signal, useCache: true });
    if (incident.ctl !== ctl) return;
    work.stop(); box.hidden = false;
    incident.last = { data: r.data, meta: r };
    showIncident(r.data, r);
  } catch (err) {
    if (incident.ctl !== ctl) return;
    work.stop(); box.hidden = false;
    const x = explain(err);
    box.innerHTML = `<div class="alert alert--error" role="alert"><p class="alert__title">${esc(err.code === 'aborted' ? 'Incident cancelled' : x.title)}</p><p class="muted">${esc(x.body)}</p>
      <div class="alert__actions"><button class="btn btn--sm" id="incRetry">Retry</button></div></div>`;
    $('incRetry').addEventListener('click', () => runIncident(id, sevPct));
  } finally { if (incident.ctl === ctl) $('incRun').disabled = false; }
}

function showIncident(p, meta) {
  const box = $('incResult');
  const inc = p.incident;
  const st = analyzeStatus(p, { fromCache: meta.fromCache, ageS: meta.ageS });
  if (!inc || inc.error) {
    box.innerHTML = `<div class="alert alert--error"><p class="alert__title">The backend rejected this incident</p><p class="muted">${esc((inc && inc.error) || 'no incident block in the response')}</p></div>`;
    return;
  }
  const pos = inc.position || {};
  const ch = pos.channel;
  const blocked = ch && ch.blocked_by && ch.blocked_by.length && pos.conditional_loss_usd <= pos.exit_total_usd;
  const b = inc.book || {};
  box.innerHTML = `
    <div class="panel"><div class="panel__body">
      <div class="inc-head">${statusChip(st.key, st.meta)}<span class="tag tag--neutral">hypothetical incident</span>
        <span class="faint" style="font-size:var(--t-sm)">${esc(inc.name)} at ${pct(inc.severity, 0)} severity</span></div>
      <p style="margin-top:var(--s4);font-size:var(--t-lg);font-weight:600;max-width:70ch">${blocked
        ? esc(`No effect on this position: ${ch.note}`)
        : `If ${esc(inc.name.replace(/^Shock:\s*/, ''))} loses ${pct(inc.severity, 0)}, staying would cost about ${usd(pos.conditional_loss_usd)}; exiting now costs ${usd(pos.exit_total_usd)}. The backend says ${esc(verdictWord(pos.verdict).toLowerCase())}.`}</p>
      <details class="more" style="margin-top:6px"><summary>Backend headline</summary><p class="note mono" style="margin-top:6px">${esc(inc.headline)}</p></details>
      <dl class="inc-cmp">
        <div><dt>Lost if you stay, given the incident</dt><dd>${usd(pos.conditional_loss_usd)}</dd></div>
        <div><dt>Cost to exit now</dt><dd>${usd(pos.exit_total_usd)}</dd></div>
        <div><dt>Backend call for the position</dt><dd>${tag(pos.verdict)}</dd></div>
      </dl>
      ${ch ? `<p class="note" style="margin-top:var(--s3)">Channel: ${esc(ch.note)}</p>` : ''}
      <p class="note" style="margin-top:var(--s3)">The comparison assumes you can sell before the incident is priced into the PT. After a depeg has hit the market, exit proceeds would be lower too.</p>
      ${b.applied ? `<div class="inc-book"><p class="an-h3" style="margin:0 0 6px">Book of ten pockets</p>
        <p class="muted">${b.pockets_hit && b.pockets_hit.length ? `${b.pockets_hit.length} pocket(s) share this dependency: ${esc(b.pockets_hit.join(', '))}. Exit ${b.pockets_to_exit.length}${b.pockets_to_exit.length ? ': ' + esc(b.pockets_to_exit.join(', ')) : ''}.` : 'No other pocket shares this dependency.'}</p>
        <p class="muted" style="margin-top:4px">Book loss if every pocket stays: <b>${usd(b.book_loss_if_stay_usd)}</b>. With the backend's best action per pocket: <b>${usd(b.book_loss_best_usd)}</b> (${pct(b.pct_of_book, 2)} of the book).</p></div>` : ''}
      ${inc.hold_to_maturity ? `<p class="note" style="margin-top:var(--s3)">Hold to maturity: ${esc(inc.hold_to_maturity)}</p>` : ''}
    </div></div>`;
}

// ================================================================ exit or hold
function renderOptions() {
  const el = $('p-options');
  const v = maturityView(S.payload.maturity);
  if (!v.applicable) {
    el.innerHTML = `<p class="lead">Hold to maturity is not available for this analysis.</p><div class="callout"><p>${esc(v.reason)}</p></div>`;
    return;
  }
  const max = Math.max(v.exit.high_usd || 0, v.hold.high_usd || 0, v.stay.high_usd || 0, 1);
  const X = (x) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`;
  const row = (o, name, sub, color, best) => `
    <div class="opt${best ? ' is-best' : ''}">
      <div class="opt__name">${esc(name)}<small>${esc(sub)}</small></div>
      <div class="opt__bar" role="img" aria-label="${esc(name)}: central ${usd(o.central_usd)}, range ${usd(o.low_usd)} to ${usd(o.high_usd)}">
        <span class="rng" style="left:${X(o.low_usd)};width:calc(${X(o.high_usd)} - ${X(o.low_usd)});background:${color}"></span>
        <span class="ctr" style="left:${X(o.central_usd)}"></span></div>
      <div class="opt__val">${usd(o.central_usd)}<small>${usd(o.low_usd)} to ${usd(o.high_usd)}</small></div>
    </div>`;
  const days = Math.round(v.days);
  el.innerHTML = `
    <p class="lead">Is there something better than exiting? A Pendle PT redeems at par at maturity through Pendle's contracts,
      whatever happens to its AMM pool. Holding avoids the exit cost but keeps the principal risks for ${days} more days.</p>
    <div class="panel"><div class="panel__body">
      <div class="inc-head"><span class="an-h3" style="margin:0">Same window: now to maturity, ${days} days</span>
        ${tag(v.best)}<span class="faint" style="font-size:var(--t-sm)">${esc(v.confidence)} confidence</span></div>
      ${row(v.exit, 'Exit now', 'sell through the Pendle AMM, give up the remaining yield', 'rgba(95,208,196,.45)', v.best === 'EXIT')}
      ${row(v.hold, 'Hold to maturity', 'expected loss to maturity plus redemption gas, no AMM exposure', 'rgba(185,167,240,.5)', v.best === 'HOLD_TO_MATURITY')}
      <div class="opt opt--sep">
        <div class="opt__name">Stay ${S.payload.position.horizon_days} days, then decide again<small>the main verdict's window, shown for reference, not ranked</small></div>
        <div class="opt__bar" role="img" aria-label="Stay ${S.payload.position.horizon_days} days: central ${usd(v.stay.central_usd)}">
          <span class="rng" style="left:${X(v.stay.low_usd || 0)};width:calc(${X(v.stay.high_usd || 0)} - ${X(v.stay.low_usd || 0)});background:rgba(236,233,226,.25)"></span>
          <span class="ctr" style="left:${X(v.stay.central_usd)}"></span></div>
        <div class="opt__val">${usd(v.stay.central_usd)}<small>${tag(v.stay.verdict_vs_exit)}</small></div>
      </div>
      <p class="note" style="margin-top:var(--s4)">${esc(v.ifAmmFails || '')}. If the threat is the issuer or the underlying itself, holding does not avoid that loss.</p>
      <details class="more" style="margin-top:var(--s3)"><summary>How the options are costed</summary>
        <ul class="note" style="padding-left:18px;margin-top:8px"><li>${esc(v.exit.basis)}</li><li>${esc(v.hold.basis)}</li><li>${esc(v.stay.basis)}</li><li>${esc(v.rule)}</li></ul></details>
    </div></div>`;
}

// ================================================================ book of ten
function renderBook(b, { mode, meta } = {}) {
  const el = $('p-book');
  if (!b) { el.innerHTML = '<p class="lead">No book in this response.</p>'; return; }
  book.mode = mode || book.mode;
  const real = b.mode === 'real_book';
  const { rows, yieldGain, yieldRows } = bookRows(b);
  const shared = (b.shared_dependencies || []).slice(0, 8);
  el.innerHTML = `
    <p class="lead">The brief's example: a book split into ten pockets of 10%; one dependency is hit. Here the pockets are the ten
      largest live Morpho markets taking a Pendle PT as collateral, equal weights, ${usdFull(b.book_usd)} in total. It is an
      illustration of the method, not Belem's actual portfolio.</p>
    <div class="inc-head" style="margin-bottom:var(--s4)">
      <div class="seg" role="group" aria-label="Exit cost used for every pocket">
        <button type="button" data-m="quoted" aria-pressed="${book.mode === 'quoted'}">Executable quotes</button>
        <button type="button" data-m="brief" aria-pressed="${book.mode === 'brief'}">Brief's 11% exit cost</button>
      </div>
      ${meta ? statusChip(analyzeStatus(meta.data, { fromCache: meta.fromCache, ageS: meta.ageS }).key, meta.fromCache ? `fetched ${ago(meta.ageS)}` : '') : ''}
      <span class="faint" style="font-size:var(--t-sm)">${esc(b.scenario || '')}</span>
    </div>
    <div id="bookWork" hidden></div>
    ${!real ? `<div class="callout" style="margin-bottom:var(--s4)">${esc(b.note || 'Copies of the analysed position (no real pocket list in this mode).')}</div>` : ''}
    <dl class="inc-cmp" style="margin-top:0">
      <div><dt>Book loss if every pocket stays</dt><dd>${usd(b.total_stay_loss_usd)}</dd></div>
      <div><dt>With the backend's best action per pocket</dt><dd>${usd(b.total_optimal_usd)}</dd></div>
      <div><dt>Share of the book</dt><dd>${pct(b.pct_of_book, 2)}</dd></div>
    </dl>
    ${yieldRows ? `<p class="note" style="margin-top:var(--s3)">${yieldRows} unaffected pocket(s) carry a backend EXIT because their PT yields less than the single reference rate used for every pocket, so exiting “gains” yield. They are marked “yield rebalance, not a risk exit”; the best-action total above includes ${usd(yieldGain)} of such yield gains. Reported unchanged, flagged for the backend owner.</p>` : ''}
    <div class="tablewrap" style="margin-top:var(--s4)"><table class="table">
      <caption class="vh">Pockets of the book with the backend's stay loss, exit side and call</caption>
      <thead><tr><th>Pocket</th><th>Hit by the shock</th><th class="r">Loss if it stays</th><th class="r">Exit side</th><th>Backend call</th></tr></thead>
      <tbody>${rows.map((p) => `<tr${p.affected ? ' class="is-hit"' : ''}>
        <td>${esc(p.label)}${p.is_analysed_position ? ' <span class="tag tag--neutral">analysed</span>' : ''}<br><span class="faint" style="font-size:var(--t-xs)">${usd(p.value_usd)}, ${pct(p.weight, 0)}</span></td>
        <td>${p.affected ? '<span class="tag tag--exit">hit</span>' : '<span class="faint">no</span>'}</td>
        <td class="r">${usd(p.stay_loss_usd)}<br><span class="faint" style="font-size:var(--t-xs)">${esc(p.stay_loss_type)}</span></td>
        <td class="r">${usd(p.exit_total_usd)}<br><span class="faint" style="font-size:var(--t-xs)">${p.exit_method === 'given' ? 'given ' + usd(p.exit_cost_usd) : usd(p.exit_cost_usd) + ' ' + esc(qShort(p.quote_status, p.exit_method))}, carry ${usd(p.carry_usd)}</span></td>
        <td>${p.reason === 'yield' ? '<span class="tag tag--yield" title="The scenario does not reach this pocket; the EXIT comes from yield (negative exit side), not risk">yield rebalance, not a risk exit</span>' : tag(p.verdict)}</td></tr>`).join('')}</tbody></table></div>
    ${shared.length ? `<p class="an-h3" style="margin-top:var(--s6)">Dependencies shared across the book</p>
    <div class="tablewrap"><table class="table"><thead><tr><th>Dependency</th><th class="r">Pockets</th><th class="r">Share of book exposed</th><th class="r">Book loss if it fails</th></tr></thead>
      <tbody>${shared.map((s) => `<tr><td>${esc(s.label)}</td><td class="r">${s.n_pockets} of ${b.n_pockets}</td><td class="r">${pct(s.share_of_book, 0)}</td><td class="r">${usd(s.loss_if_fails_usd)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    <details class="more" style="margin-top:var(--s4)"><summary>Book assumptions</summary><ul class="note" style="padding-left:18px;margin-top:8px">${(b.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>`;
  el.querySelectorAll('[data-m]').forEach((btn) => btn.addEventListener('click', () => switchBook(btn.dataset.m)));
}
const qShort = (s, m) => (m === 'approximation_constant_product' ? 'approximation' : s === 'simulated' ? 'quote, re-executed' : s ? 'quote, ' + s : '');

async function switchBook(mode) {
  if (mode === book.mode) return;
  if (mode === 'quoted') { book.mode = 'quoted'; renderBook(S.payload.book, { mode }); return; }
  if (book.ctl) book.ctl.abort();
  const ctl = new AbortController(); book.ctl = ctl;
  book.mode = mode;
  renderBook(S.payload.book, { mode });
  const wbox = $('bookWork');
  const work = mountWork(wbox, { title: 'Re-running the book with the brief\'s 11% exit cost', typical: [20, 35], onCancel: () => ctl.abort() });
  try {
    const r = await getJson(ctx.analyzeUrl({ exit_cost_pct: '0.11' }), { signal: ctl.signal, useCache: true });
    work.stop();
    if (book.ctl !== ctl) return;
    renderBook(r.data.book, { mode, meta: r });
  } catch (err) {
    work.stop();
    if (book.ctl !== ctl) return;
    book.mode = 'quoted';
    renderBook(S.payload.book, { mode: 'quoted' });
    const x = explain(err);
    $('bookWork').hidden = false;
    $('bookWork').innerHTML = `<div class="alert alert--error" role="alert"><p class="alert__title">${esc(x.title)}</p><p class="muted">${esc(x.body)}</p></div>`;
  }
}

// ================================================================ stress and sensitivity
function renderStress() {
  const el = $('p-stress');
  const rows = S.payload.stress_table || [];
  const max = Math.max(1, ...rows.map((r) => r.conditional_loss_usd));
  const sv = sensitivityView(S.payload.sensitivity);
  el.innerHTML = `
    <p class="lead">Each dependency failing on its own, at its own severity, from the backend's stress run; then how much the verdict
      depends on the model's parameters.</p>
    <div class="an-grid2">
      <div class="panel"><div class="panel__body">
        <p class="an-h3">Which single failure would hurt most</p>
        <div class="bars">${rows.map((r) => {
          const n = S.index.byId.get(r.id) || {};
          const blocked = r.channel && r.channel.blocked_by && r.channel.blocked_by.length;
          return `<div class="bar${blocked ? ' is-blocked' : ''}"><span class="name" title="${esc(r.label)}">${esc(r.label)}</span>
            <span class="track" aria-hidden="true"><i style="width:${blocked ? 100 : (r.conditional_loss_usd / max) * 100}%"></i></span>
            <span class="v">${blocked ? 'no effect' : usd(r.conditional_loss_usd)}</span></div>
            <div class="note" style="margin:-2px 0 6px">${blocked ? esc(r.channel.blocked_by.includes('debt') ? 'acts only through debt' : 'exit cost only') : `${pct(r.severity, 0)} severity, ${r.hops} hop${r.hops > 1 ? 's' : ''}, call ${verdictWord(r.verdict_if_shocked)}`}${isAssumption(n) ? ' <span class="tag tag--review">assumption-driven</span>' : ''}</div>`;
        }).join('')}</div>
        <p class="note" style="margin-top:var(--s3)">Losses are conditional on the failure happening. Rows marked assumption-driven use structural assumptions (e.g. the chain's 30% loss), not calibrated data.</p>
      </div></div>
      <div class="panel"><div class="panel__body">
        <p class="an-h3">Does the verdict survive different parameters?</p>
        ${sv ? `<p class="muted">${sv.stable ? `Every row keeps the point call at ${verdictWord(sv.only)}.` : 'Some parameter settings flip the point call.'} The call flips at about ${mult(sv.breakeven, 1)} the central risk.</p>
        <div class="tablewrap" style="margin-top:var(--s3)"><table class="table"><thead><tr><th>Parameter family</th><th>Setting</th><th class="r">Loss if you stay</th><th>Call</th></tr></thead>
          <tbody>${sv.rows.map((r) => `<tr><td>${esc(r.family)}</td><td>${esc(r.setting)}</td><td class="r">${usd(r.loss)}</td><td>${tag(r.verdict)}</td></tr>`).join('')}</tbody></table></div>
        <p class="note" style="margin-top:var(--s3)">${esc(sv.note || '')}</p>` : '<p class="note">No sensitivity in this response.</p>'}
      </div></div>
    </div>
    <div class="panel" style="margin-top:var(--s5)"><div class="panel__body">
      <p class="an-h3">Predefined scenarios</p>
      <div class="tablewrap"><table class="table"><thead><tr><th>Scenario</th><th>What happens</th><th class="r">Loss if it happens</th><th class="r">Exit side</th><th>Call</th></tr></thead>
        <tbody>${(S.payload.scenarios || []).map((s) => {
          const notes = Object.values(s.channel_notes || {}).map((c) => c.note);
          return `<tr><td>${esc(s.name)}</td><td class="muted">${esc(s.description)}${notes.length ? `<br><span class="faint">${esc(notes.join(' '))}</span>` : ''}</td>
            <td class="r">${usd(s.conditional_loss_usd)}</td><td class="r">${usd(s.exit_total_usd)}</td><td>${tag(s.verdict)}</td></tr>`;
        }).join('')}</tbody></table></div>
    </div></div>`;
}

// ================================================================ borrower and liquidation
function renderBorrower() {
  const el = $('p-borrower');
  const L = S.payload.liquidation || {};
  if (L.mode !== 'borrower_position') {
    el.innerHTML = `<p class="lead">The analysis above treats the PT as collateral with no debt, so nothing can be liquidated and oracle or
      market failures cannot reach it. To see liquidation risk, analyse a real borrower of the same Morpho market.</p>
      <div class="callout"><p>${esc(L.reason || L.liquidation || 'Unlevered exposure: liquidation not applicable.')}</p>
      <div class="alert__actions" style="margin-top:var(--s3)"><button class="btn btn--primary btn--sm" id="toBorrower">Analyse the largest real borrower</button></div>
      <p class="note" style="margin-top:var(--s2)">Reads the borrower's debt and collateral on-chain at the analysis block (about 25–35 s).</p></div>`;
    $('toBorrower').addEventListener('click', () => ctx.reload('borrower'));
    return;
  }
  const g = L.price_grid || [];
  const firstIdx = g.findIndex((x) => x.liquidated);
  const first = firstIdx >= 0 ? g[firstIdx] : null;
  const lastSafe = firstIdx > 0 ? g[firstIdx - 1] : null;
  const d = L.decision || {};
  const sug = L.countermove_suggestion;
  el.innerHTML = `
    <div class="callout callout--hyp" style="margin-bottom:var(--s5)"><p><b>Two different positions on this page.</b> The headline verdict uses the hypothetical
      ${usdFull(S.payload.position.value_usd)} exposure. This tab is the real borrower <span class="mono">${esc(short(L.borrower, 8, 6))}</span>
      (${esc(L.selected_by || 'user supplied')}), read on-chain at block ${num(L.as_of_block)}.</p></div>
    <dl class="inc-cmp" style="margin-top:0">
      <div><dt>Collateral (oracle value)</dt><dd>${usd(L.collateral_value_usd_oracle)}</dd></div>
      <div><dt>Debt</dt><dd>${usd(L.debt_value_usd)}</dd></div>
      <div><dt>Loan to value</dt><dd>${pct(L.ltv, 2)} <span class="faint" style="font-size:var(--t-sm)">liquidation at ${pct(L.lltv, 1)}</span></dd></div>
      <div><dt>Health factor</dt><dd>${num(L.health_factor, 3)}</dd></div>
      <div><dt>Room before liquidation</dt><dd>${pct(L.distance_to_liquidation_pct, 2)} <span class="faint" style="font-size:var(--t-sm)">oracle price drop</span></dd></div>
      <div><dt>Backend call for the borrower</dt><dd>${tag(d.verdict)}</dd></div>
    </dl>
    <div class="an-grid2" style="margin-top:var(--s5)">
      <div class="panel"><div class="panel__body liq-grid"><p class="an-h3">Breaking point: health factor as the oracle price falls</p>${gridSvg(g, L)}
        <p class="note" style="margin-top:6px">Points are the backend's price grid (Morpho liquidation arithmetic). Exact threshold: a ${pct(L.distance_to_liquidation_pct, 2)} oracle drop${lastSafe && first ? `, bracketed by grid points ${pct(lastSafe.oracle_drop, 2)} (safe) and ${pct(first.oracle_drop, 2)} (liquidated)` : ''}.</p></div></div>
      <div class="panel"><div class="panel__body">
        <p class="an-h3">What the backend expects</p>
        <dl class="an-kv"><dt>Chance of liquidation, ${S.payload.position.horizon_days} d</dt><dd>${pct((L.expected || {}).p_liquidation, 2)}</dd>
          <dt>Expected borrower loss</dt><dd>${usd((L.expected || {}).expected_borrower_loss_usd)}</dd>
          <dt>Deleverage cost (sell all collateral)</dt><dd>${usd(d.exit_cost_usd)}</dd>
          <dt>Health factor after ${S.payload.position.horizon_days} d of interest</dt><dd>${num((L.drift || {}).health_factor_at_horizon_constant_price, 3)}</dd></dl>
        ${(d.reasons || []).length ? `<ul class="note" style="padding-left:18px;margin-top:var(--s3)">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
        <div class="tablewrap" style="margin-top:var(--s3)"><table class="table"><thead><tr><th>Scenario</th><th class="r">Oracle drop</th><th>Liquidated</th><th class="r">Borrower loss</th></tr></thead>
          <tbody>${(L.scenarios || []).map((s) => `<tr><td>${esc(s.name)}</td><td class="r">${pct(s.oracle_drop, 1)}</td><td>${s.liquidated ? '<span class="tag tag--exit">yes</span>' : '<span class="tag tag--stay">no</span>'}</td><td class="r">${usd(s.borrower_loss_usd)}</td></tr>`).join('')}</tbody></table></div>
      </div></div>
    </div>
    ${sug ? `<div class="panel" style="margin-top:var(--s5)"><div class="panel__body">
      <p class="an-h3">Suggested protection policy for this borrower</p>
      <p class="muted">${esc(sug.why)}</p>
      <dl class="an-kv"><dt>Act when loan to value reaches</dt><dd>${pct(sug.policy_draft_query.trigger_ltv, 1)}</dd>
        <dt>Never push it below</dt><dd>${pct(sug.policy_draft_query.min_ltv_after, 1)}</dd>
        <dt>Allowed actions</dt><dd>${esc(String(sug.policy_draft_query.strategies).replace(/,/g, ', ').replace('TOP_UP', 'top up').replace('REPAY', 'repay').replace('FULL_REPAY', 'full repay'))}</dd>
        <dt>Reserve to deposit</dt><dd>${num(sug.reserve_to_deposit.loan_token, 2)} loan token, ${num(sug.reserve_to_deposit.collateral_token, 4)} collateral token</dd></dl>
      <p class="note" style="margin-top:var(--s3)">${esc(sug.note)} No RescueVault is deployed on mainnet: this is a preview for the local-fork demonstration.</p>
      <div class="alert__actions"><a class="btn btn--sm" href="/countermove.html">Open the protection lab</a></div>
    </div></div>` : ''}`;
}

function gridSvg(g, L) {
  if (!g.length) return '<p class="note">No price grid.</p>';
  const W = 460, H = 210, l = 40, r = 12, t = 14, b = 34;
  const xs = g.map((p) => p.oracle_drop), ys = g.map((p) => p.health_factor_after);
  const xMax = Math.max(...xs, 0.05), yMax = Math.max(1.1, ...ys), yMin = Math.min(0.4, ...ys);
  const X = (v) => l + (W - l - r) * (v / xMax), Y = (v) => t + (H - t - b) * (1 - (v - yMin) / (yMax - yMin));
  const line = g.map((p, i) => `${i ? 'L' : 'M'}${X(p.oracle_drop).toFixed(1)},${Y(p.health_factor_after).toFixed(1)}`).join(' ');
  const xt = [0, xMax * 0.25, xMax * 0.5, xMax * 0.75, xMax];
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Health factor versus oracle price drop. Liquidation below 1.0, first at ${pct(L.distance_to_liquidation_pct, 1)}.">
    <line class="ax" x1="${l}" x2="${W - r}" y1="${H - b}" y2="${H - b}"></line><line class="ax" x1="${l}" x2="${l}" y1="${t}" y2="${H - b}"></line>
    <line class="thr" x1="${l}" x2="${W - r}" y1="${Y(1)}" y2="${Y(1)}"></line><text class="lbl" x="${W - r}" y="${Y(1) - 5}" text-anchor="end">liquidation, health factor 1.0</text>
    ${xt.map((v) => `<text x="${X(v)}" y="${H - b + 16}" text-anchor="middle">−${(v * 100).toFixed(0)}%</text>`).join('')}
    <text x="${l}" y="${H - 4}">oracle price drop</text>
    ${[yMin, 1, yMax].map((v) => `<text x="${l - 6}" y="${Y(v) + 4}" text-anchor="end">${v.toFixed(2)}</text>`).join('')}
    <path class="ln" d="${line}"></path>
    ${g.map((p) => `<circle class="pt${p.liquidated ? ' is-liq' : ''}" cx="${X(p.oracle_drop)}" cy="${Y(p.health_factor_after)}" r="3.5"><title>−${pct(p.oracle_drop, 2)}: health factor ${num(p.health_factor_after, 3)}${p.liquidated ? ', liquidated' : ''}</title></circle>`).join('')}
  </svg>`;
}

// ================================================================ evidence
function renderEvidence() {
  const el = $('p-evidence');
  const p = S.payload;
  const d = p.decision || {};
  const fr = (d.freshness && d.freshness.items) || [];
  const dec = (p.exit && p.exit.decomposition) || null;
  const prov = p.provenance || {};
  const kinds = { exit_quote: 'Exit quote', onchain_state: 'On-chain state', market_data: 'Market data', priors: 'Failure priors' };
  el.innerHTML = `
    <p class="lead">Where every number comes from, how fresh it is, and which parts are assumptions.</p>
    <div class="an-grid2">
      <div class="panel"><div class="panel__body">
        <p class="an-h3">Data freshness</p>
        <p class="muted">${S.snapshot ? `Saved snapshot: ${esc(S.snapshot.label)}. Not current data.` : `Source: ${esc(p.source)}; ${num(prov.live)} live calls, ${num(prov.cached)} replayed from the server cache.`}</p>
        <div class="tablewrap" style="margin-top:var(--s3)"><table class="table"><thead><tr><th>Input</th><th>Source</th><th class="r">Age at analysis</th><th class="r">Limit</th><th>Decisive</th></tr></thead>
          <tbody>${fr.map((i) => `<tr><td>${esc(kinds[i.kind] || i.kind)}</td><td class="muted">${esc(i.source)}</td><td class="r">${i.age_seconds == null ? '—' : `${num(i.age_seconds, 0)} s`}${i.stale ? ' <span class="tag tag--review">stale</span>' : ''}</td><td class="r">${num(i.max_age_seconds)} s</td><td>${i.decisive ? 'yes' : 'context'}</td></tr>`).join('')}</tbody></table></div>
        ${dec ? `<p class="an-h3" style="margin-top:var(--s5)">Exit quote, decomposed</p>
        <dl class="an-kv"><dt>Value at Pendle mid</dt><dd>${usdFull(dec.value_at_mid_usd)}</dd><dt>Proceeds from the router</dt><dd>${usdFull(dec.proceeds_usd)}</dd>
          <dt>Of which Pendle fee</dt><dd>${usdFull(dec.of_which_pendle_fee_usd)}</dd><dt>Of which exit token off peg</dt><dd>${usdFull(dec.of_which_out_token_off_peg_usd)}</dd>
          <dt>Of which price impact and route</dt><dd>${usdFull(dec.of_which_price_impact_and_route_usd)}</dd><dt>Gas</dt><dd>${usdFull(dec.gas_usd)}</dd>
          <dt>Total execution cost</dt><dd>${usdFull(dec.total_exit_cost_usd)}</dd></dl>
        <p class="note" style="margin-top:6px">${esc(p.exit.basis || '')}</p>` : ''}
      </div></div>
      <div class="panel"><div class="panel__body">
        <p class="an-h3">Parameters and their basis</p>
        <div class="tablewrap"><table class="table"><thead><tr><th>Dependency</th><th>Failure odds</th><th>Loss if it fails</th></tr></thead>
          <tbody>${((p.uncertainty && p.uncertainty.nodes) || []).map((n) => `<tr><td>${esc(n.label)}</td>
            <td>${pct(n.p_fail_horizon.central, 3)} <span class="faint">${esc(CLASS_WORDS[n.p_fail_horizon.class] || n.p_fail_horizon.class)}</span></td>
            <td>${pct(n.loss_given_failure.central, 1)} <span class="faint">${esc(CLASS_WORDS[n.loss_given_failure.class] || n.loss_given_failure.class)}</span></td></tr>`).join('')}</tbody></table></div>
        <details class="more" style="margin-top:var(--s4)"><summary>Model assumptions (${(p.assumptions || []).length})</summary>
          <ul class="note" style="padding-left:18px;margin-top:8px">${(p.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>
      </div></div>
    </div>`;
}
