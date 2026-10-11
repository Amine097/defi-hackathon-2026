// Vault intelligence page controller. Renders GET /api/vault (faultline.vault/1) result-first.
// Every figure, band, route status and verdict is read from the backend payload; the browser only formats it.
import { mountShell, setShellEnd } from './core/shell.js';
import { statusChip } from './core/status.js';
import { esc, usd, pct, num, short, dateTime, ago, duration } from './core/format.js';
import { getJson, explain, ApiError } from './core/api.js';
import { mountWork, VAULT_STEPS } from './core/work.js';
import { buildQuery, verdictView, shockOptions, sharedDependencies, EXECUTABLE } from './vault/view.js';
import * as V from './vault/present.js';

mountShell({ active: 'vault' });

const $ = (id) => document.getElementById(id);
const els = {
  intro: $('intro'), form: $('vaultForm'), addr: $('fAddress'), value: $('fValue'), horizon: $('fHorizon'),
  submit: $('fSubmit'), ferr: $('fAddressErr'), examples: $('examples'), work: $('work'), notice: $('notice'),
  result: $('result'), bar: $('bar'), decision: $('decision'), exit: $('exit'), fx: $('fx'), tabs: $('tabs'),
};
const TABS = ['alloc', 'deps', 'stress', 'sens', 'assum'];
const state = { p: null, ctrl: null, last: null, selected: null, model: null, tab: 'alloc', shockCtrl: null, widths: {} };
const money = V.money;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const extLink = (href, text, cls = '') => `<a href="${esc(href)}" target="_blank" rel="noopener"${cls ? ` class="${cls}"` : ''}>${text}<span class="vh"> (opens in a new tab)</span></a>`;
const addrLink = (a, text) => (a ? extLink(V.etherscan(a), `<span class="mono">${esc(text || short(a))}</span>`) : '—');
const tagHtml = (label, tone, title = '') => `<span class="tag tag--${tone}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</span>`;
const mark = (tone) => `<span class="vi-mark is-${tone}" aria-hidden="true"></span>`;

// ---------- input ----------
els.examples.innerHTML = V.EXAMPLES.map((x, i) => `<li><button class="vi-ex" type="button" data-i="${i}"
    aria-label="Analyse ${esc(x.name)}, ${esc(x.version)} vault ${esc(x.address)}">
    <span class="vi-ex__name">${esc(x.name)}</span>
    <span class="vi-ex__meta">${esc(x.version)}, ${esc(x.asset)}${x.note ? ` <span class="tag tag--neutral">${esc(x.note)}</span>` : ''}</span>
    <span class="vi-ex__addr mono">${esc(x.address)}</span></button></li>`).join('');

els.examples.addEventListener('click', (ev) => {
  const b = ev.target.closest('.vi-ex');
  if (!b || b.disabled) return;
  const x = V.EXAMPLES[Number(b.dataset.i)];
  els.addr.value = x.address;
  run({ address: x.address, value_usd: els.value.value, horizon_days: els.horizon.value }, x.name);
});
els.form.addEventListener('submit', (ev) => {
  ev.preventDefault();
  const a = els.addr.value.trim();
  const ex = V.EXAMPLES.find((x) => x.address.toLowerCase() === a.toLowerCase());
  run({ address: a, value_usd: els.value.value, horizon_days: els.horizon.value }, ex && ex.name);
});
els.addr.addEventListener('input', () => fieldError(''));

function fieldError(msg) {
  els.ferr.hidden = !msg;
  els.ferr.textContent = msg || '';
  if (msg) els.addr.setAttribute('aria-invalid', 'true'); else els.addr.removeAttribute('aria-invalid');
}

function localCheck(params) {
  const v = Number(params.value_usd), h = Number(params.horizon_days);
  if (params.value_usd !== '' && !(v >= 1000 && v <= 1e8)) return 'Exposure must be between $1,000 and $100,000,000.';
  if (params.horizon_days !== '' && !(Number.isInteger(h) && h >= 1 && h <= 365)) return 'Horizon must be a whole number of days from 1 to 365.';
  return '';
}

function setBusy(on) {
  els.submit.disabled = on;
  els.form.setAttribute('aria-busy', String(on));
  els.examples.querySelectorAll('button').forEach((b) => { b.disabled = on; });
}

function collapse(on) {
  els.intro.classList.toggle('is-collapsed', on);
  const edit = els.bar.querySelector('[data-act="edit"]');
  if (edit) {
    edit.setAttribute('aria-expanded', String(!on));
    edit.textContent = on ? 'Edit inputs' : 'Hide inputs';
  }
}

function deepQuery(params) {
  const b = buildQuery({ address: params.address, value_usd: params.value_usd, horizon_days: params.horizon_days });
  return b.query || '';
}

async function run(params, label) {
  const b = buildQuery(params);
  const err = b.error || localCheck(params);
  if (err) { fieldError(err); collapse(false); els.addr.focus(); return; }
  fieldError('');
  if (state.ctrl) state.ctrl.abort();
  const ctrl = new AbortController();
  state.ctrl = ctrl;
  state.last = { params, label };
  hideNotice();
  setBusy(true);
  els.result.hidden = true;
  setShellEnd(statusChip('loading'));
  const name = label || short(String(params.address).trim(), 6, 4);
  const work = mountWork(els.work, { title: `Analysing ${name}`, typical: [15, 25], steps: VAULT_STEPS, onCancel: () => ctrl.abort() });
  els.work.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  const q = deepQuery(params);
  if (q) history.replaceState(null, '', `?${q}`);
  try {
    const { data } = await getJson('/api/vault?' + b.query, { timeout: 90000, signal: ctrl.signal, store: false });
    if (!data || data.schema !== 'faultline.vault/1') {
      throw new ApiError({ status: 200, code: 'invalid_payload', message: 'the server answered with an unexpected format' });
    }
    if (ctrl !== state.ctrl) return;
    work.stop();
    state.p = data;
    els.result.hidden = false;
    render(data);
    collapse(true);
    window.scrollTo({ top: 0, behavior: 'auto' });
    const h = $('decTitle');
    if (h) h.focus({ preventScroll: true });
  } catch (e) {
    if (ctrl !== state.ctrl) return;
    work.stop();
    if (e.code === 'aborted') showCancelled();
    else showError(e);
  } finally {
    if (ctrl === state.ctrl) { state.ctrl = null; setBusy(false); }
  }
}

// ---------- errors and notices ----------
function nextStep(e) {
  switch (e.code) {
    case 'unsupported_contract': return {
      title: 'Not a Morpho vault: check the address',
      body: 'FAULTLINE reads Morpho V1 (MetaMorpho) and V2 vaults on Ethereum mainnet. A token, market or wallet address will not work: paste the vault address or its Morpho link.' };
    case 'not_found': return {
      title: 'No contract at this address on Ethereum',
      body: 'Check that you copied the full vault address and that the vault lives on Ethereum mainnet, not another chain.' };
    case 'invalid_input': return {
      title: 'The input was rejected',
      body: 'Check the address or link. Exposure must be $1,000 to $100,000,000 and the horizon 1 to 365 days.' };
    case 'invalid_scenario': return { title: 'That shock is not a dependency of this vault', body: 'Pick a dependency from the list and retry.' };
    case 'timeout': case 'network_error': return { title: '', body: 'Nothing is shown rather than stale figures.' };
    case 'invalid_payload': return { title: 'The answer could not be read', body: 'No figures are shown rather than unverified ones. Retry in a moment.' };
    default: return (e.status >= 500 || !e.status)
      ? { title: 'The analysis failed on the server', body: 'No figures are shown rather than unverified ones. Public data sources can fail briefly: retry in a moment.' }
      : { title: '', body: '' };
  }
}

function errorBox(e, actions) {
  const x = explain(e), n = nextStep(e);
  return `<div class="alert alert--error" role="alert">
      <p class="alert__title">${mark('exit')}${esc(n.title || x.title)}</p>
      ${x.body ? `<p>${esc(x.body.charAt(0).toUpperCase() + x.body.slice(1))}${/[.!?]$/.test(x.body) ? '' : '.'}</p>` : ''}
      ${n.body ? `<p class="muted">${esc(n.body)}</p>` : ''}
      <p class="note mono">${esc(e.code || 'error')}${e.status ? ` (HTTP ${esc(e.status)})` : ''}</p>
      <div class="alert__actions">${actions}</div></div>`;
}

function showError(e) {
  const input = ['unsupported_contract', 'not_found', 'invalid_input'].includes(e.code);
  const actions = input
    ? ['<button class="btn btn--primary btn--sm" type="button" data-act="edit-addr">Edit the address</button>',
      '<button class="btn btn--sm" type="button" data-act="retry">Retry</button>']
    : ['<button class="btn btn--primary btn--sm" type="button" data-act="retry">Retry</button>'];
  actions.push('<button class="btn btn--quiet btn--sm" type="button" data-act="belem">Try the Belem vault</button>');
  els.notice.hidden = false;
  els.notice.innerHTML = errorBox(e, actions.join(''));
  setShellEnd(statusChip('unavailable'));
  collapse(false);
  els.notice.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
}

function showCancelled() {
  els.notice.hidden = false;
  els.notice.innerHTML = `<div class="alert" role="status"><p class="alert__title">Analysis cancelled</p>
    <p class="muted">Nothing was analysed.${state.p ? ' The previous result is shown again.' : ''}</p>
    <div class="alert__actions"><button class="btn btn--sm" type="button" data-act="retry">Run it again</button></div></div>`;
  if (state.p) {
    els.result.hidden = false;
    const st = V.statusOf(state.p);
    setShellEnd(statusChip(st.key, st.meta));
    collapse(true);
  } else setShellEnd('');
}

function hideNotice() { els.notice.hidden = true; els.notice.innerHTML = ''; }

els.notice.addEventListener('click', (ev) => {
  const act = ev.target.closest('[data-act]');
  if (!act) return;
  if (act.dataset.act === 'retry' && state.last) run(state.last.params, state.last.label);
  if (act.dataset.act === 'edit-addr') { hideNotice(); collapse(false); els.addr.focus(); els.addr.select(); }
  if (act.dataset.act === 'belem') {
    const x = V.EXAMPLES[0];
    els.addr.value = x.address;
    run({ address: x.address, value_usd: els.value.value, horizon_days: els.horizon.value }, x.name);
  }
});

// ---------- result ----------
function render(p) {
  const vv = verdictView(p.decision);
  renderBar(p);
  renderDecision(p, vv);
  renderExit(p);
  renderFx(p);
  renderAlloc(p);
  renderDeps(p);
  renderStress(p);
  renderSens(p);
  renderAssum(p);
  const st = V.statusOf(p);
  setShellEnd(statusChip(st.key, st.meta));
  document.title = `${p.vault.name}: ${p.decision.verdict} — Vault intelligence — FAULTLINE`;
  state.widths = {};
  selectTab(TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : state.tab);
}

function renderBar(p) {
  const v = p.vault, inp = p.input;
  els.bar.innerHTML = `
    <div class="vi-bar__id">
      <h2 class="vi-bar__name" id="vName">${v.url ? extLink(v.url, esc(v.name)) : esc(v.name)}</h2>
      <span class="tag tag--neutral" title="${esc(v.factory_name || '')}">Morpho ${esc(String(v.version || '').toUpperCase())}</span>
      <span class="vi-bar__addr" title="${esc(v.address)}">${addrLink(v.address, short(v.address, 6, 4))}</span>
    </div>
    <dl class="vi-bar__facts">
      <div><dt>Exposure</dt><dd class="num">${esc(V.money(inp.value_usd))}</dd></div>
      <div><dt>Horizon</dt><dd class="num">${esc(inp.horizon_days)} days</dd></div>
      <div><dt>Asset</dt><dd>${esc(v.asset && v.asset.symbol)}</dd></div>
    </dl>
    <button class="btn btn--sm vi-bar__edit" type="button" data-act="edit" aria-controls="intro" aria-expanded="false">Edit inputs</button>`;
  els.value.value = inp.value_usd;
  els.horizon.value = inp.horizon_days;
  if (!els.addr.value) els.addr.value = inp.address;
}

els.bar.addEventListener('click', (ev) => {
  if (!ev.target.closest('[data-act="edit"]')) return;
  const open = els.intro.classList.contains('is-collapsed');
  collapse(!open);
  if (open) { window.scrollTo({ top: 0, behavior: 'auto' }); els.addr.focus(); }
});

function renderDecision(p, vv) {
  const d = p.decision, tone = V.verdictTone(d.verdict);
  const st = V.statusOf(p);
  const reasons = (d.reasons || []).map(V.plainReason);
  if (!reasons.length && d.verdict !== 'REVIEW') reasons.push(V.firmWhy(d));
  const basis = V.basisSentence(d);
  const warns = p.warnings || [];
  const ex = p.exit || {}, conv = ex.usd_conversion || {}, risk = p.risk || {};
  els.decision.innerHTML = `
    <div class="vi-dec">
      <div class="vi-dec__main">
        <div class="vi-dec__top">
          <h2 class="vi-h3" id="decTitle" tabindex="-1">Decision for this exposure</h2>
          ${statusChip(st.key, st.meta)}
        </div>
        <p class="vi-verdict v-${tone}" aria-label="Verdict ${esc(d.verdict)}">${mark(tone)}<span class="vword">${esc(d.verdict)}</span></p>
        <p class="vi-lean">${esc(V.leanText(d))}</p>
        <p class="vi-story">${V.decisionStory(d).map((s) => `<span>${esc(s)}</span>`).join(' ')}</p>
        ${basis ? `<p class="note vi-basis">${esc(basis)}</p>` : ''}
      </div>
      <div class="vi-dec__side">
        <figure class="vi-fig">
          <figcaption class="vi-figcap">Staying against exiting, over ${esc(d.horizon_days)} days</figcaption>
          <div class="vi-chartbox" id="bandsChart"></div>
        </figure>
        <h3 class="vi-h4">Why</h3>
        <ul class="vi-reasons">${reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
      </div>
    </div>
    ${(d.blockers || []).length ? `<div class="alert vi-blockers" role="status"><p class="alert__title">${mark('review')}Before acting</p>
      <ul class="vi-list">${d.blockers.map((b) => `<li>${esc(V.plainReason(b))}</li>`).join('')}</ul></div>` : ''}
    ${warns.length ? `<ul class="vi-warns" aria-label="Warnings">${warns.map((w) => `<li>${mark('review')}<span><b>Check:</b> ${esc(w)}</span></li>`).join('')}</ul>` : ''}
    ${vv.consistent ? '' : `<div class="alert alert--error" role="alert"><p class="alert__title">${mark('exit')}These figures contradict each other: do not act on them</p>
      <p class="muted">${esc(vv.issues.join('; '))}.</p></div>`}
    <details class="more vi-detail">
      <summary>Full explanation and cost breakdown</summary>
      <div class="vi-detail__body">
        <p class="vi-explain">${esc(d.explanation)}</p>
        <div class="tablewrap"><table class="table vi-costs">
          <caption class="vh">How the cost of exiting is built</caption>
          <tbody>
            <tr><th scope="row">Gas of the simulated route</th><td class="r num">${esc(money(ex.gas_usd))}</td><td class="faint">${esc(ex.gas_why || '')}</td></tr>
            <tr><th scope="row">Withdrawal friction</th><td class="r num">${esc(money(ex.withdrawal_friction_usd))}</td><td class="faint">Assets requested minus assets received in the simulation, including any forceDeallocate penalty (${esc(money(ex.force_deallocate_penalty_usd))}).</td></tr>
            <tr><th scope="row">Exit fee</th><td class="r num">${esc(money(ex.exit_fee_usd))}</td><td class="faint">${esc(ex.exit_fee_note || '')}</td></tr>
            <tr class="vi-sum"><th scope="row">Execution cost</th><td class="r num">${esc(money(d.execution_cost_usd))}</td><td></td></tr>
            <tr><th scope="row">Carry forgone over ${esc(d.horizon_days)} days</th><td class="r num">${esc(money(d.carry_usd))}</td><td class="faint">Yield given up by leaving. ${esc((ex.carry && ex.carry.formula) || '')}</td></tr>
            <tr class="vi-sum"><th scope="row">Cost of exiting</th><td class="r num">${esc(money(d.exit_side_usd))}</td><td class="faint">Range ${esc(money(d.exit_band_usd[0]))}–${esc(money(d.exit_band_usd[1]))}, compared with an expected loss of ${esc(money(d.expected_loss_usd))}.</td></tr>
            <tr><th scope="row">Converting ${esc(p.vault.asset.symbol)} to USD</th><td class="r num">${conv.status === 'indicative' ? esc(money(conv.cost_usd)) : '—'}</td>
              <td class="faint">${conv.status === 'indicative' ? 'Indicative quote, not simulated. ' : ''}Not counted in the decision: ${esc(conv.why || conv.reason || conv.status || '')}.</td></tr>
          </tbody></table></div>
        <p class="note">Expected loss ${esc(money(risk.expected_loss_usd))} (${esc(pct(risk.expected_loss_pct, 3))} of the exposure), ${esc(risk.label || '')}.
          Range ${esc(money(risk.band_usd && risk.band_usd[0]))}–${esc(money(risk.band_usd && risk.band_usd[1]))};
          without any assumption on correlation it lies between ${esc(money(risk.dependence_bounds_usd && risk.dependence_bounds_usd[0]))} and ${esc(money(risk.dependence_bounds_usd && risk.dependence_bounds_usd[1]))}.
          Monte Carlo mean ${esc(money(risk.mc_mean_usd))}; 95% value at risk ${esc(money(risk.var95_usd))}.</p>
        <p class="note mono">${esc(risk.formula || '')}</p>
        <p class="note mono">${esc(d.rule || '')}</p>
        ${(d.reasons || []).length ? `<p class="note">Reasons as sent by the backend:</p><ul class="vi-list note mono">${d.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
        <p class="note">${vv.consistent ? `${mark('stay')}Figures checked: cost of exiting = execution + carry, and the margin (${esc(vv.marginText)}) has the sign the verdict needs.` : ''}</p>
      </div>
    </details>`;
}

const ROUTE_WHAT = {
  ordinary: (v) => (v === 'v1' ? "Withdraws along the vault's withdraw queue: a plain redeem." : "Idle cash plus the vault's liquidity market: a plain redeem."),
  force_deallocate: (v) => (v === 'v1' ? 'forceDeallocate exists only on Morpho V2 vaults.'
    : "One transaction pulls liquidity from the vault's other markets into idle cash, then redeems. Anyone can call it; the curator can set a penalty."),
};

function routeCard(key, r, p, scale) {
  const ex = p.exit, v = p.vault;
  const st = V.routeStatus(r.status);
  const usedKey = String(ex.executable_route || '').startsWith('force') ? 'force_deallocate' : ex.executable_route ? 'ordinary' : '';
  const used = usedKey === key;
  const na = r.status === 'not_applicable';
  const paper = !na && !/^simulated/.test(r.status || '');
  const cap = r.capacity_usd;
  const w = na || !(scale > 0) ? 0 : Math.min(100, (100 * (cap || 0)) / scale);
  const posAt = Math.min(100, (100 * ex.theoretical_value_usd) / scale);
  return `<li class="vi-route${used ? ' is-used' : ''}${na ? ' is-na' : ''}${paper ? ' is-paper' : ''}">
      <div class="vi-route__head">
        <h3 class="vi-h4">${key === 'ordinary' ? 'Ordinary withdrawal' : 'With forceDeallocate'}</h3>
        ${used ? tagHtml('Used for the decision', 'stay') : ''}
      </div>
      <p class="vi-route__what">${esc(ROUTE_WHAT[key](v.version))}</p>
      <p class="vi-route__status" title="status: ${esc(st.raw)}">${mark(st.tone)}${esc(st.label)}</p>
      ${na ? '' : `<div class="vi-cap" aria-hidden="true"><span class="vi-cap__fill" style="width:${w.toFixed(1)}%"></span><span class="vi-cap__you" style="left:${posAt.toFixed(1)}%"></span></div>`}
      <dl class="vi-route__facts">
        <div><dt>Capacity now</dt><dd class="num">${na ? '—' : esc(money(cap))}</dd></div>
        <div><dt>Penalty</dt><dd class="num">${na ? '—' : esc(money(key === 'ordinary' ? 0 : r.penalty_usd))}</dd></div>
        <div><dt>Gas</dt><dd class="num">${r.gas && r.gas.gas_usd != null ? `${esc(money(r.gas.gas_usd))}<span class="faint"> ${esc(num(r.gas.gas_units))} gas</span>` : '—'}</dd></div>
      </dl>
    </li>`;
}

function renderExit(p) {
  const ex = p.exit, d = p.decision, routes = ex.routes || {};
  const f = V.feasibility(ex.withdrawal_feasibility);
  const blocked = ex.blocked_or_deferred_usd || 0;
  const scale = Math.max(ex.theoretical_value_usd || 0, (routes.ordinary && routes.ordinary.capacity_usd) || 0,
    (routes.force_deallocate && routes.force_deallocate.status !== 'not_applicable' && routes.force_deallocate.capacity_usd) || 0);
  const block = (ex.simulation && ex.simulation.block) || p.as_of_block;
  const unconf = routes.unconfirmed || [];
  els.exit.innerHTML = `
    <h2 class="vi-h2" id="exitTitle">What you could withdraw now</h2>
    <p class="vi-feas is-${f.tone}" title="withdrawal_feasibility: ${esc(f.raw)}">${mark(f.tone)}<span>${esc(f.label)}</span></p>
    <p class="vi-feas__sub">${esc(money(ex.immediately_withdrawable_usd))} of your ${esc(money(ex.theoretical_value_usd))} could leave now through a simulated route.
      ${blocked > 0 ? `${esc(money(blocked))} is blocked or deferred: not lost, but it has to wait for liquidity.` : 'Nothing is blocked or deferred.'}</p>
    <ul class="vi-routes" aria-label="Withdrawal routes compared">
      ${routes.ordinary ? routeCard('ordinary', routes.ordinary, p, scale) : ''}
      ${routes.force_deallocate ? routeCard('force_deallocate', routes.force_deallocate, p, scale) : ''}
    </ul>
    <p class="vi-cap-legend note" aria-hidden="true"><span class="vi-cap-key"></span>Capacity, hatched when not simulated <span class="vi-you-key"></span>Your exposure</p>
    ${unconf.map((u) => `<p class="note">${mark('neutral')}${esc(u.route)} could add ${esc(money(u.usd))} on paper, but no simulation confirmed it for this amount, so it is never counted as withdrawable.</p>`).join('')}
    <div class="vi-exit__grid">
      <div class="vi-lossvwait">
        <h3 class="vi-h4">Losing money is not the same as waiting for it</h3>
        <dl>
          <div><dt>${mark('exit')}Loss</dt><dd>Value that is gone. Expected over ${esc(d.horizon_days)} days: ${esc(money(d.expected_loss_usd))}.</dd></div>
          <div><dt>${mark('review')}Cannot withdraw yet</dt><dd>The money is still there but has to wait for liquidity. Now: ${esc(money(blocked))} blocked or deferred.</dd></div>
        </dl>
        <button class="btn btn--quiet btn--sm" type="button" data-goto="stress">See both for each stress scenario</button>
      </div>
      <p class="vi-shared">Liquidity is shared: every depositor draws on the same pool, first come first served, and it can change every block.
        Routes were simulated with a read-only eth_call at block ${extLink(V.etherscanBlock(block), esc(num(block)))}; nothing was sent.</p>
    </div>
    ${exitDetails(p)}`;
}

function exitDetails(p) {
  const ex = p.exit, c = ex.capacity || {}, fd = ex.force_deallocate || {}, sym = p.vault.asset.symbol;
  const plan = fd.plan, carry = ex.carry || {}, x = c.api_cross_check;
  const sims = [['Ordinary redeem, full amount', ex.simulation], ['Ordinary redeem, part', ex.simulation_partial], ['forceDeallocate multicall', ex.simulation_force_deallocate]]
    .filter(([, s]) => s && s.status);
  return `<details class="more vi-detail">
      <summary>Route details for technical users</summary>
      <div class="vi-detail__body">
        <dl class="vi-kv">
          <div><dt>withdrawal_feasibility</dt><dd class="mono">${esc(ex.withdrawal_feasibility)}</dd></div>
          <div><dt>executable_route</dt><dd class="mono">${esc(ex.executable_route || 'null')}<span class="faint"> (${esc(V.routeLabel(ex.executable_route))})</span></dd></div>
          <div><dt>Route statuses</dt><dd class="mono">ordinary ${esc((ex.routes.ordinary || {}).status)}, force_deallocate ${esc((ex.routes.force_deallocate || {}).status)}</dd></div>
          <div><dt>Capacity rule</dt><dd>${esc(c.rule || '')}</dd></div>
          ${x ? `<div><dt>Cross-check</dt><dd>${x.ok ? 'Agrees' : 'Disagrees'} with ${esc(x.source)} (relative difference ${esc(Number(x.rel_diff).toExponential(1))}).</dd></div>` : ''}
          ${c.contract_max_redeem_note ? `<div><dt>maxRedeem</dt><dd>${esc(c.contract_max_redeem_note)}</dd></div>` : ''}
          ${(c.rows || []).length ? `<div><dt>Ordinary liquidity</dt><dd>${c.rows.map((r) => `${esc(r.collateral || 'idle market')} via ${esc(r.path)}: ${esc(num(r.available))} ${esc(sym)}`).join('; ')}</dd></div>` : ''}
          ${plan ? `<div><dt>forceDeallocate plan</dt><dd>${plan.steps.map((s) => `${esc(s.collateral || 'idle')} ${esc(num(s.assets))} ${esc(sym)} (penalty ${esc(pct(s.penalty_rate, 2))})`).join(', ')} to cover ${esc(num(plan.need_assets))} ${esc(sym)} beyond ordinary capacity. <span class="faint">${esc(plan.rule)}</span></dd></div>` : ''}
          ${sims.map(([k, s]) => `<div><dt>${esc(k)}</dt><dd>${esc(s.status)}${s.gas_estimate ? `, ${esc(num(s.gas_estimate))} gas` : ''}${s.block ? ` at block ${esc(num(s.block))}` : ''}. <span class="faint">${esc(s.method || s.reason || '')}</span></dd></div>`).join('')}
          <div><dt>Carry</dt><dd>Net APY on-chain ${esc(pct(carry.net_apy_onchain, 2))}, Morpho API ${esc(pct(carry.net_apy_api, 2))}${carry.apy_cross_check ? (carry.apy_cross_check.ok ? ' (agree)' : ' (disagree)') : ''}; rewards not counted ${esc(money(carry.rewards_usd_not_counted))}. <span class="faint">${esc(carry.note || '')}</span></dd></div>
          ${fd.note ? `<div><dt>forceDeallocate</dt><dd>${esc(fd.note)}</dd></div>` : ''}
        </dl>
        ${(fd.reserves || []).length ? `<p class="note">Reserves:</p><ul class="vi-list note">${fd.reserves.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
      </div>
    </details>`;
}

els.result.addEventListener('click', (ev) => {
  const g = ev.target.closest('[data-goto]');
  if (!g) return;
  selectTab(g.dataset.goto, true);
  els.tabs.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' });
});

// ---------- FX and peg ----------
function renderFx(p) {
  const f = V.fxView(p);
  els.fx.hidden = !f;
  if (!f) { els.fx.innerHTML = ''; return; }
  const [base] = String(f.pair || '').split('/');
  const neutralFx = f.fxNode && f.fxNode.decision_neutral, neutralAsset = f.assetNode && f.assetNode.decision_neutral;
  const conv = f.conversion || {};
  const dep = f.depeg;
  els.fx.innerHTML = `
    <h2 class="vi-h2" id="fxTitle">Priced in ${esc(f.currency)}, reported in USD</h2>
    <p class="vi-fx__eq" aria-label="USD price ${esc(num(f.price, 5))} equals ${esc(f.pair)} ${esc(num(f.rate, 5))} times ${esc(f.symbol)} per ${esc(base)} ${esc(num(f.peg, 5))}">
      <span class="vi-fx__row"><span class="vi-fx__term"><b class="num">${esc(num(f.price, 5))}</b><small>USD price of ${esc(f.symbol)}</small></span></span>
      <span class="vi-fx__row"><span class="vi-fx__op" aria-hidden="true">=</span>
        <span class="vi-fx__term"><b class="num">${esc(num(f.rate, 5))}</b><small>${esc(f.pair)} exchange rate</small></span></span>
      <span class="vi-fx__row"><span class="vi-fx__op" aria-hidden="true">×</span>
        <span class="vi-fx__term"><b class="num">${f.peg == null ? '—' : esc(num(f.peg, 5))}</b><small>${esc(f.symbol)} per ${esc(base)}: the peg</small></span></span>
    </p>
    <div class="vi-fx__grid">
      <div>
        <h3 class="vi-h4">Exchange-rate moves</h3>
        <p>${esc(f.pair)} changes your USD value whether you stay or exit: you get ${esc(f.symbol)} back either way.${neutralFx ? ' It does not change the decision.' : ''}</p>
      </div>
      <div>
        <h3 class="vi-h4">Token depeg</h3>
        <p>If ${esc(f.symbol)} loses its peg to the ${esc(base)}, the token itself is worth less.${neutralAsset ? ' Redeeming returns the same token, so staying and exiting lose alike.' : ''}
          ${dep ? `In the ${esc(dep.name)} scenario: ${esc(money(dep.stay_loss_usd != null ? dep.stay_loss_usd : dep.loss_usd))} if you stay, ${esc(money(dep.exit_to_asset_loss_usd != null ? dep.exit_to_asset_loss_usd : dep.loss_usd))} if you exit to ${esc(f.symbol)}.` : ''}</p>
      </div>
      ${conv.status === 'indicative' ? `<div>
        <h3 class="vi-h4">Leaving ${esc(base)} for USD</h3>
        <p>Swapping the redeemed ${esc(f.symbol)} to USDC now would cost about ${esc(money(conv.cost_usd))}. That is a separate treasury choice, not counted in the decision.</p>
      </div>` : ''}
    </div>
    <details class="more vi-detail"><summary>Sources</summary>
      <dl class="vi-kv vi-detail__body">
        <div><dt>Exchange rate</dt><dd>${esc(f.fxSource || '—')}${f.fxUpdated ? `, updated ${esc(dateTime(f.fxUpdated))}` : ''}</dd></div>
        <div><dt>Token price</dt><dd>${esc(f.priceSource || '—')}${f.priceAge != null ? `, ${esc(ago(f.priceAge))}` : ''}</dd></div>
        ${conv.status === 'indicative' ? `<div><dt>Swap quote</dt><dd>${esc(conv.source || '')}</dd></div>` : ''}
        ${f.decomposition ? `<div><dt>Backend formula</dt><dd class="mono">${esc(f.decomposition)}</dd></div>` : ''}
      </dl>
    </details>`;
}

// ---------- allocations ----------
const SEG_TONES = 5;
function renderAlloc(p) {
  const al = p.allocations, sym = p.vault.asset.symbol;
  const segs = V.allocationSegments(al);
  const items = al.items.slice().sort((a, b) => (b.share_of_vault || 0) - (a.share_of_vault || 0));
  const segLabel = (s) => (s.kind === 'market' ? `${s.label}, LLTV ${V.lltvText(s.lltv)}` : s.label);
  const segShare = (s) => (s.kind === 'small' ? `under 1% each (${s.names.join(', ')})` : pct(s.share, s.share < 0.1 ? 2 : 1));
  $('tp-alloc').innerHTML = `
    <div class="vi-tp__head">
      <h3 class="vi-h2">Where the vault's money is</h3>
      <p class="note">${esc(items.length)} market${items.length === 1 ? '' : 's'} holding ${esc(num(al.total_assets, 0))} ${esc(al.unit || sym)} (${esc(money(al.total_assets_usd))}) at block ${esc(num(p.as_of_block))}.
        Idle cash ${esc(pct(al.idle_share, 2))}, coverage ${esc(pct(al.coverage, 1))}: ${esc(al.displayed || '')}.</p>
    </div>
    <div class="vi-stack" aria-hidden="true">${segs.map((s, i) => `<span class="vi-seg t${i % SEG_TONES}${s.kind !== 'market' ? ' is-' + s.kind : ''}" style="flex-basis:${(100 * s.share).toFixed(3)}%" title="${esc(segLabel(s))}: ${esc(segShare(s))}">
        ${s.share >= 0.09 ? `<span class="vi-seg__txt${s.share < 0.25 ? ' is-narrow' : ''}">${esc(s.label)} <span class="vi-seg__sub">${esc(V.lltvText(s.lltv))} LLTV</span></span>` : ''}</span>`).join('')}</div>
    <ul class="vi-legend" aria-label="Share of the vault by market">${segs.map((s, i) => `<li><span class="vi-swatch t${i % SEG_TONES}${s.kind !== 'market' ? ' is-' + s.kind : ''}" aria-hidden="true"></span>
        <span>${esc(segLabel(s))}</span> <b class="num">${esc(segShare(s))}</b></li>`).join('')}</ul>
    <div class="tablewrap" role="region" aria-label="Allocations table" tabindex="0"><table class="table vi-alloc">
      <thead><tr><th scope="col">Market</th><th scope="col" class="r">LLTV</th><th scope="col" class="r">Share</th><th scope="col" class="r">Supplied</th>
        <th scope="col" class="r">Utilisation</th><th scope="col" class="r">Supply APY</th><th scope="col" class="r">Free liquidity</th><th scope="col">Oracle</th></tr></thead>
      <tbody>${items.map((i) => `<tr>
        <td><b>${i.url ? extLink(i.url, esc(i.collateral_symbol || 'Idle market')) : esc(i.collateral_symbol || 'Idle market')}</b><span class="faint"> / ${esc(sym)}</span>
          <div class="faint mono vi-mid" title="${esc(i.market_id)}">${esc(short(i.market_id, 8, 4))}</div></td>
        <td class="r num">${esc(pct(i.lltv, 1))}</td><td class="r num">${esc(pct(i.share_of_vault, 2))}</td><td class="r num">${esc(money(i.supply_usd))}</td>
        <td class="r num">${esc(pct(i.utilization, 1))}</td><td class="r num">${esc(pct(i.supply_apy, 2))}</td>
        <td class="r num">${esc(num(i.market_liquidity, 0))} <span class="faint">${esc(sym)}</span></td>
        <td>${i.oracle ? addrLink(i.oracle, V.oracleText(i.oracle)) : '—'}</td></tr>`).join('')}</tbody></table></div>
    <p class="note">LLTV is the loan-to-value at which borrowers get liquidated. Utilisation is the share of a market's supply that is borrowed: the higher it is, the less can be withdrawn at once.</p>`;
}

// ---------- dependencies ----------
function renderDeps(p) {
  const { nodes, edges } = p.dependencies;
  state.model = V.graphModel(nodes, edges);
  const drivers = (p.risk && p.risk.drivers) || [];
  state.selected = (drivers[0] && state.model.at[drivers[0].id]) ? drivers[0].id : (nodes.find((n) => n.id !== 'pos') || {}).id || 'pos';
  const shared = sharedDependencies(nodes);
  const roles = [...new Set(['pos', ...nodes.map((n) => n.role)])];
  const H = p.decision.horizon_days;
  $('tp-deps').innerHTML = `
    <div class="vi-tp__head">
      <h3 class="vi-h2">What your deposit depends on</h3>
      <p class="note">Each line points from a component to what it depends on; thicker lines carry more of the loss. The bar under a component is its share of the expected loss, against the largest. Select a component, or use the arrow keys, to see its parameters.</p>
    </div>
    <div class="vi-deps">
      <div class="vi-graphwrap" id="graphWrap" role="region" aria-label="Dependency map"></div>
      <div class="vi-layers" id="graphLayers" role="group" aria-label="Dependencies by layer, from your deposit outwards"></div>
      <aside class="vi-node" id="nodeInfo" aria-live="polite" aria-label="Selected component"></aside>
    </div>
    <ul class="vi-glegend" aria-label="Legend">${roles.map((r) => `<li>${V.glyphIcon(r)}${esc(V.roleLabel(r))}</li>`).join('')}
      <li><span class="vi-dash" aria-hidden="true"></span>Dashed: hits staying and exiting alike</li></ul>
    <h4 class="vi-h4">Shared dependencies</h4>
    <ul class="vi-list vi-shared-list">${shared.length ? shared.map((s) => `<li><b>${esc(s.label)}</b> sits behind ${esc(s.count)} allocations: ${esc(money(s.usd))} affected if it fails, counted once.</li>`).join('')
      : '<li class="muted">No dependency is shared by several allocations.</li>'}</ul>
    <details class="more vi-detail"><summary>Main drivers of the expected loss</summary>
      <div class="tablewrap"><table class="table"><thead><tr><th scope="col">Dependency</th><th scope="col" class="r">Expected loss</th><th scope="col" class="r">Strongest path transmission</th></tr></thead>
      <tbody>${drivers.map((x) => `<tr><td>${esc(x.label)}</td><td class="r num">${esc(money(x.expected_loss_usd))}</td><td class="r num">${esc(num(x.paths && x.paths[0] && x.paths[0].transmission, 3))}</td></tr>`).join('')}</tbody></table></div>
    </details>
    <details class="more vi-detail"><summary>All dependencies as a table</summary>
      <div class="tablewrap"><table class="table"><thead><tr><th scope="col">Component</th><th scope="col">Role</th><th scope="col" class="r">Fails within ${esc(H)} days</th>
        <th scope="col" class="r">Loss if it fails</th><th scope="col" class="r">Affected if it fails</th><th scope="col" class="r">Expected loss</th></tr></thead>
      <tbody>${nodes.filter((n) => n.id !== 'pos').map((n) => `<tr><td>${esc(n.label)}${n.decision_neutral ? ' <span class="faint">(same either way)</span>' : ''}</td><td>${esc(V.roleLabel(n.role))}</td>
        <td class="r num">${esc(pct(n.p_fail_horizon, 3))}</td><td class="r num">${esc(pct(n.loss_given_failure, 0))}</td>
        <td class="r num">${esc(money(n.affected_usd_if_fails))}</td><td class="r num">${esc(money(n.expected_loss_usd))}</td></tr>`).join('')}</tbody></table></div>
    </details>`;
  drawGraph(false);
}

function drawGraph(focus) {
  const p = state.p;
  $('graphWrap').innerHTML = V.graphSvg(state.model, p.dependencies.edges, { selected: state.selected });
  $('graphLayers').innerHTML = V.layersHtml(state.model, { selected: state.selected });
  $('nodeInfo').innerHTML = nodeInfo(state.selected);
  if (focus) {
    const host = $('graphWrap').offsetParent ? $('graphWrap') : $('graphLayers');
    const g = host.querySelector(`[data-id="${CSS.escape(state.selected)}"]`);
    if (g) g.focus({ preventScroll: host === $('graphLayers') });
  }
}

function nodeInfo(id) {
  const p = state.p, n = state.model.byId.get(id);
  const edges = p.dependencies.edges || [];
  const name = (x) => V.nodeShort(state.model.byId.get(x), x);
  const dependsOn = edges.filter((e) => e.src === id).map((e) => name(e.dst));
  const usedBy = edges.filter((e) => e.dst === id).map((e) => name(e.src));
  const links = `${dependsOn.length ? `<div><dt>Depends on</dt><dd>${esc(dependsOn.join('; '))}</dd></div>` : ''}${usedBy.length ? `<div><dt>Used by</dt><dd>${esc(usedBy.join('; '))}</dd></div>` : ''}`;
  if (!n) {
    return `<h4 class="vi-h4">${V.glyphIcon('pos')}Your deposit</h4>
      <p class="muted">Hypothetical vault shares worth ${esc(money(p.input.value_usd))}, converted at the share price of block ${esc(num(p.as_of_block))}.</p>
      <dl class="vi-kv vi-kv--tight vi-kv--links">${links}</dl>`;
  }
  const H = p.decision.horizon_days;
  const markets = new Map(p.allocations.items.map((i) => [`market:${i.market_id}`, i]));
  const exposed = (n.exposed_allocations || []).map((m) => markets.get(m)).filter(Boolean)
    .map((i) => `${i.collateral_symbol || 'idle'} (${pct(i.share_of_vault, 1)})`);
  const addr = n.address || (String(n.id).match(/0x[0-9a-fA-F]{40}/) || [])[0];
  const rows = [
    [`Chance it fails within ${H} days`, pct(n.p_fail_horizon, 3)],
    ['Share of exposed value lost if it fails', pct(n.loss_given_failure, 0)],
    ['Share of your deposit exposed', pct(n.affected_fraction, 2)],
    ['Affected if it fails', money(n.affected_usd_if_fails)],
    ['Expected loss it adds', money(n.expected_loss_usd)],
  ];
  return `<h4 class="vi-h4">${V.glyphIcon(n.role)}${esc(n.label)}</h4>
    <p class="faint">${esc(V.roleLabel(n.role))}${n.decision_neutral ? ', hits staying and exiting alike' : ''}</p>
    <dl class="vi-kv vi-kv--tight">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd class="num">${esc(v)}</dd></div>`).join('')}
      <div><dt>Allocations exposed</dt><dd>${exposed.length ? esc(exposed.join('; ')) : (n.exposed_allocations || []).length ? esc(n.exposed_allocations.length) : 'All of the vault'}</dd></div>
      ${addr ? `<div><dt>Contract</dt><dd>${addrLink(addr, short(addr, 6, 4))}</dd></div>` : ''}</dl>
    <dl class="vi-kv vi-kv--tight vi-kv--links">${links}</dl>
    <details class="more"><summary>Sources</summary>
      <p class="note"><b>Probability:</b> ${esc(n.source || '—')}</p>
      <p class="note"><b>Loss if it fails:</b> ${esc(n.lgf_source || '—')}</p></details>`;
}

function moveSel(id, key) {
  const { at, cols } = state.model;
  const q = at[id];
  if (!q) return null;
  if (key === 'ArrowDown') return cols[q.col][q.row + 1] || null;
  if (key === 'ArrowUp') return q.row > 0 ? cols[q.col][q.row - 1] : null;
  const c = cols[q.col + (key === 'ArrowRight' ? 1 : -1)];
  if (!c) return null;
  return c.reduce((best, k) => (Math.abs(at[k].y - q.y) < Math.abs(at[best].y - q.y) ? k : best), c[0]);
}

$('tp-deps').addEventListener('click', (ev) => {
  const g = ev.target.closest('.vi-g-node, .vi-chip');
  if (!g) return;
  state.selected = g.dataset.id;
  drawGraph(true);
  if (g.classList.contains('vi-chip') && matchMedia('(max-width: 760px)').matches) {
    $('nodeInfo').scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  }
});
$('tp-deps').addEventListener('keydown', (ev) => {
  const g = ev.target.closest && ev.target.closest('.vi-g-node');
  if (!g) return;
  if (['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(ev.key)) {
    ev.preventDefault();
    const nx = moveSel(g.dataset.id, ev.key);
    if (nx) { state.selected = nx; drawGraph(true); }
  } else if (ev.key === 'Enter' || ev.key === ' ') {
    ev.preventDefault();
    state.selected = g.dataset.id;
    drawGraph(true);
  }
});

// ---------- stress ----------
const FEAS_WORD = { full: 'all of it', partial: 'part of it', zero: 'none of it', unknown: 'unconfirmed' };

function withdrawCell(s) {
  if (s.decision_neutral) return '<span class="faint">Not a liquidity event</span>';
  if (s.immediately_withdrawable_usd == null) return '—';
  return `${esc(money(s.immediately_withdrawable_usd))}<div class="faint">${esc(FEAS_WORD[s.withdrawal_feasibility] || s.withdrawal_feasibility || '')}</div>`;
}
function forceCell(s) {
  if (s.decision_neutral || s.withdrawable_with_force_deallocate_usd == null) return '—';
  const t = V.forceRouteTag(s);
  return `${esc(money(s.withdrawable_with_force_deallocate_usd))}<div>${t.label ? tagHtml(t.label, t.tone, s.force_deallocate_route) : ''}</div>`;
}

function renderStress(p) {
  const rows = (p.scenarios || []).filter((s) => !s.custom);
  $('stressBody').innerHTML = `
    <div class="vi-tp__head">
      <h3 class="vi-h2">Stress scenarios</h3>
      <p class="note">Each row assumes the shock happens: losses are not weighted by probability. Loss is value that is gone.
        Withdrawable now is what could leave the vault at once; money that cannot leave yet is delayed, not lost.</p>
    </div>
    <div class="tablewrap" role="region" aria-label="Stress scenarios table" tabindex="0"><table class="table vi-scen">
      <thead><tr><th scope="col">Scenario</th><th scope="col" class="r">Loss if it happens</th><th scope="col" class="r">Of the exposure</th>
        <th scope="col" class="r">Withdrawable now</th><th scope="col" class="r">With forceDeallocate</th></tr></thead>
      <tbody>${rows.map((s) => `<tr>
        <td class="vi-scen__name"><b>${esc(s.name)}</b><div class="faint vi-scen__desc">${esc(s.description)}${s.decision_neutral && s.note ? `. ${esc(s.note)}` : ''}</div></td>
        <td class="r num" data-label="Loss if it happens"><b>${esc(money(s.loss_usd))}</b></td><td class="r num" data-label="Of the exposure">${esc(pct(s.loss_pct, 2))}</td>
        <td class="r num" data-label="Withdrawable now">${withdrawCell(s)}</td><td class="r num" data-label="With forceDeallocate">${forceCell(s)}</td></tr>`).join('')}</tbody></table></div>`;
  const sel = $('shockNode');
  const opts = shockOptions(p.dependencies.nodes);
  const groups = new Map();
  for (const o of opts) { const g = V.roleLabel(o.role); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(o); }
  const drivers = (p.risk && p.risk.drivers) || [];
  const chosen = p.input.shock || (drivers[0] && drivers[0].id) || (opts[0] && opts[0].id);
  sel.innerHTML = [...groups].map(([g, list]) => `<optgroup label="${esc(g)}">${list.map((o) => `<option value="${esc(o.id)}"${o.id === chosen ? ' selected' : ''}>${esc(o.label)}</option>`).join('')}</optgroup>`).join('');
  setSeverity(p.input.severity != null ? p.input.severity : defaultSeverity(chosen));
  const custom = (p.scenarios || []).find((s) => s.custom);
  $('shockOut').innerHTML = custom ? shockResult(custom, p) : '';
}

function defaultSeverity(id) {
  const n = state.p && state.p.dependencies.nodes.find((x) => x.id === id);
  return n && n.loss_given_failure > 0 ? n.loss_given_failure : 0.5;
}
function setSeverity(v) {
  const r = $('shockSev');
  r.value = String(Math.round(Number(v) * 20) / 20);
  $('shockSevOut').textContent = pct(r.value, 0);
}
$('shockSev').addEventListener('input', () => { $('shockSevOut').textContent = pct($('shockSev').value, 0); });
$('shockNode').addEventListener('change', () => setSeverity(defaultSeverity($('shockNode').value)));

function shockResult(s, run) {
  const st = V.statusOf(run);
  const t = V.forceRouteTag(s);
  return `<article class="vi-shockres">
      <p class="vi-shockres__head"><span class="tag tag--neutral vi-hyp">Hypothetical</span><b>${esc(s.name)}</b></p>
      <p class="note">${esc(s.description)}.</p>
      <dl class="vi-figs">
        <div><dt>Loss if it happens</dt><dd class="num">${esc(money(s.loss_usd))}</dd><dd class="faint">${esc(pct(s.loss_pct, 2))} of the exposure</dd></div>
        <div><dt>Withdrawable now</dt><dd class="num">${esc(money(s.immediately_withdrawable_usd))}</dd><dd class="faint">${esc(FEAS_WORD[s.withdrawal_feasibility] || s.withdrawal_feasibility || '')}</dd></div>
        <div><dt>With forceDeallocate</dt><dd class="num">${esc(money(s.withdrawable_with_force_deallocate_usd))}</dd><dd>${t.label ? tagHtml(t.label, t.tone, s.force_deallocate_route) : ''}</dd></div>
        <div><dt>Expected loss with background risk</dt><dd class="num">${esc(money(s.loss_incl_background_risk_usd))}</dd><dd class="faint">other dependencies at their usual odds</dd></div>
      </dl>
      <p class="note vi-shockres__src">From a separate live run. ${statusChip(st.key, st.meta)}</p>
    </article>`;
}

$('shockForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const p = state.p;
  if (!p) return;
  const node = $('shockNode').value, sev = $('shockSev').value;
  const b = buildQuery({ address: p.input.address, value_usd: p.input.value_usd, horizon_days: p.input.horizon_days, shock: node, severity: sev });
  if (b.error) return;
  if (state.shockCtrl) state.shockCtrl.abort();
  const ctrl = new AbortController();
  state.shockCtrl = ctrl;
  const btn = $('shockSubmit');
  btn.disabled = true;
  $('shockOut').innerHTML = '';
  const label = ($('shockNode').selectedOptions[0] || {}).textContent || node;
  const work = mountWork($('shockWork'), { title: `Shocking ${label} at ${pct(sev, 0)}`, typical: [15, 25], steps: VAULT_STEPS, onCancel: () => ctrl.abort() });
  try {
    const { data } = await getJson('/api/vault?' + b.query, { timeout: 90000, signal: ctrl.signal, store: false });
    if (ctrl !== state.shockCtrl) return;
    const s = data && (data.scenarios || []).find((x) => x.custom);
    if (!s) throw new ApiError({ status: 200, code: 'invalid_payload', message: 'the answer contained no custom scenario' });
    $('shockOut').innerHTML = shockResult(s, data);
  } catch (e) {
    if (ctrl !== state.shockCtrl) return;
    $('shockOut').innerHTML = e.code === 'aborted'
      ? '<p class="note" role="status">Shock cancelled. Nothing was run.</p>'
      : errorBox(e, '<button class="btn btn--sm" type="submit">Retry</button>');
  } finally {
    work.stop();
    if (ctrl === state.shockCtrl) { state.shockCtrl = null; btn.disabled = false; }
  }
});

// ---------- sensitivity ----------
function renderSens(p) {
  const s = p.sensitivity || {}, d = p.decision;
  const curve = s.collateral_crash_curve;
  const m = s.breakeven_risk_multiplier != null ? s.breakeven_risk_multiplier : d.breakeven_risk_multiplier;
  const be = m == null ? '' : d.point_verdict === 'EXIT'
    ? `Exiting pays for itself unless the risk is below ${V.multiple(m)} the central estimate.`
    : `The risk would have to be ${V.multiple(m)} the central estimate before exiting pays for itself.`;
  $('tp-sens').innerHTML = `
    <div class="vi-tp__head">
      <h3 class="vi-h2">How sensitive is the result?</h3>
      ${m != null ? `<p class="vi-breakeven"><b class="num">${esc(V.multiple(m))}</b><span>${esc(be)}</span></p>` : ''}
    </div>
    <div class="vi-sens">
      <figure class="vi-fig">
        <figcaption class="vi-figcap"><b>Failure probability halved or doubled</b>
          <span class="note">Expected loss when one dependency's chance of failing is halved (darker bar, left of the line) or doubled (lighter bar, right). Central estimate ${esc(money(s.base_expected_loss_usd))}.</span></figcaption>
        <div class="vi-chartbox" id="tornado"></div>
      </figure>
      ${curve && curve.points ? `<figure class="vi-fig">
        <figcaption class="vi-figcap"><b>Collateral crash: ${esc(curve.label)}</b>
          <span class="note">Loss of your position if its price drops this far, assuming the drop happens (not weighted by probability).</span></figcaption>
        <div class="vi-chartbox" id="crash"></div>
        <details class="more"><summary>Crash curve as a table</summary>
          <div class="tablewrap"><table class="table"><thead><tr><th scope="col">Price drop</th><th scope="col" class="r">Loss if it happens</th></tr></thead>
          <tbody>${curve.points.map((q) => `<tr><td class="num">${esc(pct(q.drop, 0))}</td><td class="r num">${esc(money(q.loss_usd))}</td></tr>`).join('')}</tbody></table></div>
        </details>
      </figure>` : ''}
    </div>`;
}

/** Tornado rows with the same short names as the map (oracles are only known by address). */
function tornadoRows(p) {
  const byId = new Map(p.dependencies.nodes.map((n) => [n.id, n]));
  return ((p.sensitivity || {})['tornado_p_x0.5_x2'] || []).map((r) => {
    const n = byId.get(r.id);
    return n && n.role === 'oracle' ? { ...r, label: V.nodeShort(n, r.id) } : r;
  });
}

// ---------- assumptions and provenance ----------
function renderAssum(p) {
  const pv = p.provenance || {}, snap = p.snapshot || {}, v = p.vault, st = V.statusOf(p);
  const fr = (p.decision.freshness && p.decision.freshness.items) || [];
  const xc = snap.cross_checks || [];
  const fees = v.fees || {}, gates = v.gates || {};
  $('tp-assum').innerHTML = `
    <div class="vi-tp__head"><h3 class="vi-h2">Assumptions and sources</h3>
      <p class="note">What the model assumes, where every input comes from, and how fresh it is.</p></div>
    <details class="more vi-detail" open><summary>Assumptions (${esc((p.assumptions || []).length)})</summary>
      <ol class="vi-list vi-assum">${(p.assumptions || []).map((a) => `<li>${esc(/^[a-z]+_/.test(a) ? a : a.charAt(0).toUpperCase() + a.slice(1))}.</li>`).join('')}</ol></details>
    <details class="more vi-detail"><summary>Data sources and provenance</summary>
      <dl class="vi-kv">
        <div><dt>Data status</dt><dd>${statusChip(st.key, st.meta)}</dd></div>
        <div><dt>Pinned block</dt><dd>${extLink(V.etherscanBlock(p.as_of_block), esc(num(p.as_of_block)))}${snap.block_timestamp ? `, mined ${esc(dateTime(snap.block_timestamp))}` : ''}</dd></div>
        <div><dt>Analysed</dt><dd>${esc(dateTime(p.timestamp))}, data age ${esc(duration(p.age_s))} at the time</dd></div>
        <div><dt>On-chain reads</dt><dd>${esc(pv.rpc || '—')}</dd></div>
        <div><dt>Indexer</dt><dd class="mono">${esc(pv.indexer || '—')}</dd></div>
        <div><dt>Prices</dt><dd>${esc(pv.prices || '—')}</dd></div>
        <div><dt>Simulation</dt><dd>${esc(pv.simulation || '—')}</dd></div>
        <div><dt>HTTP calls</dt><dd>${esc(num(pv.live))} live, ${esc(num(pv.cached))} from cache</dd></div>
        <div><dt>Vault check</dt><dd>${esc(v.detection || '—')}</dd></div>
        <div><dt>Exposure</dt><dd>${esc(p.input.value_semantics || '')}</dd></div>
      </dl>
      ${xc.length ? `<h4 class="vi-h4">Cross-checks</h4><div class="tablewrap"><table class="table"><thead><tr><th scope="col">Field</th><th scope="col">Result</th><th scope="col" class="r">Difference</th><th scope="col">Against</th></tr></thead>
        <tbody>${xc.map((c) => `<tr><td class="mono">${esc(c.field)}</td><td>${c.ok ? tagHtml('Agrees', 'stay') : tagHtml('Disagrees', 'review')}</td>
          <td class="r num">${c.rel_diff != null ? esc(Number(c.rel_diff).toExponential(1)) : c.abs_diff != null ? esc(Number(c.abs_diff).toExponential(1)) : '—'}</td><td>${esc(c.source || '')}</td></tr>`).join('')}</tbody></table></div>` : ''}
      ${fr.length ? `<h4 class="vi-h4">Freshness</h4><div class="tablewrap"><table class="table"><thead><tr><th scope="col">Input</th><th scope="col" class="r">Age</th><th scope="col" class="r">Limit</th><th scope="col">State</th><th scope="col">Source</th></tr></thead>
        <tbody>${fr.map((i) => `<tr><td>${esc(String(i.kind).replace(/_/g, ' '))}</td><td class="r num">${esc(duration(i.age_seconds))}</td><td class="r num">${esc(duration(i.max_age_seconds))}</td>
          <td>${i.stale ? tagHtml('Stale', 'review') : tagHtml('Fresh', 'stay')}${i.decisive ? '' : ' <span class="faint">(context)</span>'}</td><td class="faint">${esc(i.source || '')}</td></tr>`).join('')}</tbody></table></div>` : ''}
    </details>
    <details class="more vi-detail"><summary>Vault settings</summary>
      <dl class="vi-kv">
        <div><dt>Contract</dt><dd>${addrLink(v.address, v.address)}</dd></div>
        <div><dt>Factory</dt><dd>${esc(v.factory_name || '—')}${v.factory ? ` ${addrLink(v.factory, short(v.factory, 6, 4))}` : ''}</dd></div>
        <div><dt>Fees</dt><dd>Performance ${esc(pct(fees.performance, 1))}, management ${esc(pct(fees.management_annual, 2))} a year. <span class="faint">${esc(fees.source || '')}</span></dd></div>
        <div><dt>Withdrawals</dt><dd>${gates.withdraw_open === false ? `${mark('exit')}Closed by a gate` : gates.withdraw_open ? `${mark('stay')}Open: no gate blocks withdrawals` : '—'}</dd></div>
        ${(v.adapters || []).length ? `<div><dt>Adapters</dt><dd>${v.adapters.map((a) => `${esc(a.type)} ${addrLink(a.address, short(a.address, 6, 4))}`).join(', ')}</dd></div>` : ''}
        <div><dt>Share price</dt><dd class="num">${esc(num(v.share_price, 6))} ${esc(v.asset.symbol)}</dd></div>
      </dl>
    </details>`;
}

// ---------- tabs ----------
function selectTab(key, focus = false) {
  if (!TABS.includes(key)) key = 'alloc';
  state.tab = key;
  for (const k of TABS) {
    const t = $(`tab-${k}`), on = k === key;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    $(`tp-${k}`).hidden = !on;
  }
  if (focus) $(`tab-${key}`).focus();
  drawCharts();
}
els.tabs.addEventListener('click', (ev) => {
  const t = ev.target.closest('[role="tab"]');
  if (t) selectTab(t.id.slice(4));
});
els.tabs.addEventListener('keydown', (ev) => {
  const i = TABS.indexOf(state.tab);
  const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[ev.key];
  if (to == null) return;
  ev.preventDefault();
  selectTab(TABS[(to + TABS.length) % TABS.length], true);
});

// ---------- charts: drawn at the real pixel width so text stays legible on phones ----------
function drawChart(id, fn) {
  const el = $(id);
  if (!el || el.offsetParent === null) return;
  const w = Math.floor(el.clientWidth);
  if (!w || state.widths[id] === w) return;
  state.widths[id] = w;
  el.innerHTML = fn(w);
}
function drawCharts() {
  const p = state.p;
  if (!p) return;
  const s = p.sensitivity || {};
  drawChart('bandsChart', (w) => V.bandsSvg(p.decision, w));
  drawChart('tornado', (w) => V.tornadoSvg(tornadoRows(p), s.base_expected_loss_usd, w, p.decision.horizon_days));
  drawChart('crash', (w) => V.crashSvg(s.collateral_crash_curve, w));
}
let rz = 0;
window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(drawCharts, 120); });

// ---------- deep link: /vault.html?address=0x…&value_usd=…&horizon_days=… runs live on load ----------
const qs = new URLSearchParams(location.search);
const qa = qs.get('address') || qs.get('url');
if (qa) {
  els.addr.value = qa;
  if (qs.get('value_usd')) els.value.value = qs.get('value_usd');
  if (qs.get('horizon_days')) els.horizon.value = qs.get('horizon_days');
  const ex = V.EXAMPLES.find((x) => x.address.toLowerCase() === qa.toLowerCase());
  run({ address: qa, value_usd: els.value.value, horizon_days: els.horizon.value, shock: qs.get('shock'), severity: qs.get('severity') }, ex && ex.name);
}
