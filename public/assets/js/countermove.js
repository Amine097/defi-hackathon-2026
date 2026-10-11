// Countermove page controller: the autonomous protection lab. ARM, DEFEND and PROVE replay the recorded run on a local
// mainnet fork (faultline.countermove/1); the dry run and the oracle reads are live and read-only. Renders backend
// payloads only: every amount, LTV, decision and check comes from the API, nothing financial is computed here.
import { mountShell, setShellEnd } from './core/shell.js';
import { statusChip } from './core/status.js';
import { esc, num, pct, short, dateTime } from './core/format.js';
import { getJson, explain, apiUrl, ApiError } from './core/api.js';
import { mountWork } from './core/work.js';
import {
  heroView, gaugeLayout, executionIssues, fmtTok, fmtDuration, fmtDate, STRATEGY_LABEL, labelParts, whyHead,
} from './countermove/view.js';
import {
  ACTS, scenarioItems, pickScenario, parseHash, proofStatus, policyOf, vaultPowers, markLabels, tickLabels,
  timelineSteps, relTime, candidateVerdicts, feedRows, dryRunView, RANKS, rankLabel, draftParams, pctInput, pctTidy,
  noteHead, STATE_WORD,
} from './countermove/acts.js';

const $ = (id) => document.getElementById(id);
const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
let data = null;
let cur = 0;
let act = 'arm';

// ---------- small view helpers (markup only) ----------
const ICONS = {
  ok: '<path d="M3.2 8.6l3 3 6.6-7.4"/>',
  fail: '<path d="M4.2 4.2l7.6 7.6M11.8 4.2l-7.6 7.6"/>',
  none: '<path d="M3.6 8h8.8"/>',
  alert: '<path d="M8 2.6l5.8 10.4H2.2z"/>',
  act: '<circle cx="8" cy="8" r="3.4"/>',
  neutral: '<circle cx="8" cy="8" r="3.4"/>',
};
const icon = (tone) => `<svg class="ic ic--${tone}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">${ICONS[tone] || ICONS.neutral}</svg>`;
const TONE_TAG = { ok: 'stay', fail: 'exit', none: 'review', alert: 'review', act: 'neutral', neutral: 'neutral' };
const tagOf = (tone, text, tip = '') => `<span class="tag tag--${TONE_TAG[tone] || 'neutral'} cm-tag"${tip ? ` title="${esc(tip)}"` : ''}>${icon(tone)}<span>${esc(text)}</span></span>`;
const simChip = (block) => statusChip('simulated', block ? `fork block ${num(block)}` : 'local fork');
const signedPct = (x, d = 1) => { const s = pct(x, d); return s.charAt(0) === '-' ? `−${s.slice(1)}` : s; };
// Sentence case, except when the text starts with a code identifier (eth_call, repaidTotal, 0x...).
const cap = (s) => { const t = String(s || ''); return /^([a-z]+_\w+|[a-z]+[A-Z]\w*|0x)/.test(t) ? t : t.charAt(0).toUpperCase() + t.slice(1); };
const kv = (rows, cls = '') => `<dl class="cm-kv${cls ? ' ' + cls : ''}">${rows.filter(Boolean).map(([k, v, rc]) => `<div${rc ? ` class="${rc}"` : ''}><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
// Amount with its token: the number never breaks and the symbol stays whole (long PT symbols wrap as one piece).
const amt = (n, sym, loan) => {
  const s = fmtTok(n, sym, loan);
  if (sym && s.endsWith(` ${sym}`)) return `<span class="amt"><span class="num">${esc(s.slice(0, -sym.length - 1))}</span> <span class="amt__sym">${esc(sym)}</span></span>`;
  return `<span class="num">${esc(s)}</span>`;
};
const shortSym = (s) => String(s || '').replace(/-\d{1,2}[A-Z]{3}\d{4}$/, '');
const errText = (x) => sentence(x.body ? `${x.title}: ${x.body}` : x.title);
const sentence = (s) => { const t = cap(String(s || '').trim()); return t && !/[.!?]$/.test(t) ? `${t}.` : t; };
const copyBtn = (text, label) => `<button type="button" class="btn btn--quiet btn--sm cm-copy" data-copy="${esc(text)}" aria-label="${esc(label)}">Copy</button>`;
const code = (a, l = 6, r = 4) => (a ? `<code class="mono cm-code" title="${esc(a)}">${esc(short(a, l, r))}</code>` : '—');
const list = (items, tone, cls = '') => `<ul class="cm-list${cls ? ' ' + cls : ''}">${items.map((x) => `<li>${icon(tone)}<span>${x}</span></li>`).join('')}</ul>`;
const unavailable = (title, body, retryId) => `<div class="alert alert--error" role="alert">
    <p class="alert__title">${esc(title)}</p>${body ? `<p class="note">${esc(body)}</p>` : ''}
    <div class="alert__actions">${statusChip('unavailable', 'no figures shown')}${retryId ? `<button type="button" class="btn btn--sm" id="${retryId}">Retry</button>` : ''}</div></div>`;

// ---------- boot ----------
mountShell({ active: 'countermove' });
setShellEnd(statusChip('loading', 'recorded run'));

async function load() {
  $('cm-boot').hidden = false;
  $('cm-lab').hidden = true;
  $('cm-boot').innerHTML = `<div class="cm-skel" aria-hidden="true"><div class="skel cm-skel__row"></div><div class="skel cm-skel__head"></div>
    <div class="skel cm-skel__steps"></div><div class="skel cm-skel__panel"></div></div><p class="vh">Loading the recorded keeper run.</p>`;
  $('cm-env-chip').innerHTML = statusChip('loading', 'recorded run');
  try {
    const { data: body } = await getJson('/api/countermove', { timeout: 20000, store: false });
    if (body.schema !== 'faultline.countermove/1' || body.status !== 'ok' || !Array.isArray(body.positions) || !body.positions.length) {
      throw new ApiError({ code: 'invalid_payload', message: 'the server answered with an unexpected payload' });
    }
    data = body;
    const h = parseHash(location.hash);
    cur = pickScenario(data.positions, h.scenario);
    if (h.act) act = h.act;
    renderEnv();
    renderScenarios();
    renderTabs();
    renderPosition();
    $('cm-boot').hidden = true;
    $('cm-lab').hidden = false;
  } catch (e) {
    const x = explain(e);
    $('cm-env-chip').innerHTML = statusChip('unavailable', 'recorded run');
    setShellEnd(statusChip('unavailable', 'recorded run'));
    $('cm-boot').innerHTML = unavailable('The recorded run is unavailable', `${errText(x)} Nothing is shown rather than unverified figures.`, 'boot-retry');
    $('boot-retry').addEventListener('click', load);
  }
}

function renderEnv() {
  const env = data.environment || {};
  $('cm-env-chip').innerHTML = statusChip('simulated', `chain ${env.chain_id}, fork block ${num(env.fork_block)}`);
  setShellEnd(statusChip('simulated', `fork block ${num(env.fork_block)}`));
  const notes = (env.notes || []).map((n) => esc(cap(n)));
  notes.push(`Recorded ${esc(fmtDate(data.generated_at))}, Morpho Blue ${code(env.morpho_blue)}, keeper ${code(env.keeper)}`);
  $('cm-env-list').innerHTML = notes.map((n) => `<li>${n}</li>`).join('');
  $('cm-env-notes').hidden = false;
}

// ---------- scenario selector ----------
function renderScenarios() {
  const items = scenarioItems(data.positions);
  $('cm-scen').innerHTML = items.map((it, i) => `<button type="button" class="cm-scen__item" data-i="${i}" aria-pressed="${i === cur}"
      aria-label="${esc(`${it.scenario}, ${it.outcome}, ${it.market}, ${it.status.long}`)}">
      <span class="cm-scen__top"><b class="cm-scen__id">${esc(it.scenario)}</b>
        <span class="tag tag--${it.status.tag} cm-tag cm-scen__tag" title="${esc(it.status.tip)}">${icon(it.status.tone)}<span class="cm-scen__tagtext">${esc(it.status.short)}</span></span></span>
      <span class="cm-scen__out"><span class="cm-scen__long">${esc(it.outcome)}</span><span class="cm-scen__short">${esc(it.outcomeShort)}</span></span>
      <span class="cm-scen__mkt">${esc(it.market)}</span></button>`).join('');
  $('cm-scen').querySelectorAll('.cm-scen__item').forEach((b) => b.addEventListener('click', () => setScenario(Number(b.dataset.i))));
}

function setScenario(i) {
  if (i === cur) return;
  cur = i;
  $('cm-scen').querySelectorAll('.cm-scen__item').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.i) === cur)));
  stopReplay();
  renderPosition();
  writeHash();
}

function writeHash() {
  history.replaceState(null, '', `#${data.positions[cur].scenario}-${act}`);
}

// ---------- headline of the selected scenario ----------
function crisisLine(p) {
  const c = p.crisis || {}, mover = (c.movers || [])[0];
  const what = mover ? `${String(mover.label).replace(/\s*\(SIMULATED SHOCK\)/, '')} ${signedPct(mover.change)}` : 'An oracle price move';
  return `${what} on the fork pushed the LTV to ${pct(c.ltv)}, past the ${pctTidy(c.trigger_ltv)} trigger`;
}

function renderHead(p) {
  const st = proofStatus(p), lp = labelParts(p.label), h = heroView(p), e = p.execution;
  const loan = ((p.before || {}).loan || {}).symbol || '';
  const word = STRATEGY_LABEL[h.key] || h.key;
  const amount = e ? fmtTok(e.amount, e.token, loan) : '';
  const tone = st.key === 'confirmed' ? 'v-stay' : st.key === 'no_action' ? 'v-review' : 'v-exit';
  const issues = [...st.issues, ...executionIssues(p)];
  const reacted = h.reaction_s != null ? `${num(h.reaction_s, 1)} s from detection to ${e ? 'fork confirmation' : 'decision'}` : '';
  $('cm-head').innerHTML = `<div class="cm-head__main">
      <p class="cm-head__who"><b class="cm-head__id">${esc(p.scenario)}</b><span class="cm-head__mkt">${esc(lp.market)}</span>
        <span class="faint">${esc([lp.user, lp.setup].filter(Boolean).join(', '))}</span></p>
      <p class="cm-head__verdict"><span class="vword ${tone}">${esc(word)}</span>${amount ? ` <span class="cm-head__amt num">${esc(amount)}</span>` : ' <span class="cm-head__amt">nothing sent</span>'}</p>
      <p class="cm-head__crisis">${esc(crisisLine(p))}</p>
    </div>
    <ul class="cm-head__facts">
      <li>${tagOf(st.tone, st.long, st.tip)}</li>
      ${reacted ? `<li>${icon('neutral')}<span>${esc(reacted)}</span></li>` : ''}
      <li>${icon(p.user_signed_during_crisis ? 'fail' : 'ok')}<span>${p.user_signed_during_crisis ? 'The user signed during the crisis' : 'No user signature during the crisis'}</span></li>
      <li class="cm-head__chip">${simChip((e && e.block) || ((p.crisis || {}).snapshot || {}).block)}</li>
    </ul>
    ${issues.length ? `<div class="alert alert--error cm-head__issues" role="alert"><p class="alert__title">Inconsistent proof: do not rely on this result</p>${list(issues.map(esc), 'fail')}</div>` : ''}`;
}

// ---------- acts as tabs ----------
function renderTabs() {
  $('cm-steps').innerHTML = ACTS.map((a) => `<button type="button" role="tab" class="cm-step" id="tab-${a.id}" aria-controls="panel-${a.id}"
      aria-selected="${a.id === act}" tabindex="${a.id === act ? 0 : -1}">
      <span class="cm-step__n" aria-hidden="true">${a.n}</span>
      <span class="cm-step__txt"><span class="cm-step__name">${esc(a.name)}</span><span class="cm-step__gist">${esc(a.gist)}</span></span></button>`).join('');
  $('cm-steps').querySelectorAll('[role="tab"]').forEach((t) => {
    t.addEventListener('click', () => setAct(t.id.slice(4), { write: true }));
    t.addEventListener('keydown', onTabKey);
  });
  showAct();
}

function onTabKey(e) {
  const i = ACTS.findIndex((a) => a.id === act);
  const j = { ArrowRight: (i + 1) % ACTS.length, ArrowLeft: (i + ACTS.length - 1) % ACTS.length, Home: 0, End: ACTS.length - 1 }[e.key];
  if (j == null) return;
  e.preventDefault();
  setAct(ACTS[j].id, { focus: true, write: true });
}

function setAct(id, { focus = false, write = false } = {}) {
  if (!ACTS.some((a) => a.id === id)) return;
  if (id !== act) stopReplay();
  act = id;
  showAct();
  if (focus) $(`tab-${id}`).focus();
  if (write) writeHash();
}

function showAct() {
  for (const a of ACTS) {
    const on = a.id === act;
    const t = $(`tab-${a.id}`);
    if (t) { t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; }
    $(`panel-${a.id}`).hidden = !on;
  }
}

function renderPosition() {
  const p = data.positions[cur];
  renderHead(p);
  renderArm(p);
  renderDefend(p);
  renderProve(p);
}

const panelHead = (a, chip) => `<div class="cm-panel__head"><h2 class="cm-panel__q">${esc(ACTS.find((x) => x.id === a).q)}</h2>${chip}</div>`;

// ---------- ARM: what the owner authorised before the crisis ----------
function renderArm(p) {
  const pol = policyOf(p), b = p.before || {};
  const T = (n, sym) => amt(n, sym, pol.loan);
  const powers = vaultPowers(pol);
  const stateTone = pol.state === 'armed' ? 'ok' : pol.state === 'paused' ? 'none' : 'fail';
  const policy = kv([
    ['Allowed actions', `<span class="cm-strats">${pol.strategies.map((s) => `<span class="cm-strat${s.allowed ? '' : ' is-off'}">${icon(s.allowed ? 'ok' : 'none')}${esc(s.label)}${s.allowed ? '' : '<span class="vh"> not allowed</span>'}</span>`).join('')}</span>`],
    ['Acts when LTV reaches', `<b class="num">${pctTidy(pol.trigger)}</b>`],
    ['Never pushes LTV below', `<span class="num">${pctTidy(pol.floor)}</span>`],
    ['Market liquidation LTV', `<span class="num">${pctTidy(pol.lltv)}</span>`],
    pol.allowed.has('REPAY') && ['Repay limits', `<span class="num">${T(pol.repayPer, pol.loan)}</span> per action<br><span class="num">${T(pol.repayTotal, pol.loan)}</span> in total`],
    pol.allowed.has('TOP_UP') && ['Top-up limits', `<span class="num">${T(pol.topUpPer, pol.coll)}</span> per action<br><span class="num">${T(pol.topUpTotal, pol.coll)}</span> in total`],
    pol.allowed.has('FULL_REPAY') && ['Full repay limit', Number(pol.fullRepay) > 0 ? `<span class="num">${T(pol.fullRepay, pol.loan)}</span>` : 'Off (cap 0)'],
    ['Wait between actions', fmtDuration(pol.cooldown)],
    ['Valid until', esc(fmtDate(pol.validUntil))],
    ['State at arming', tagOf(stateTone, cap(pol.state))],
  ]);
  const position = kv([
    ['Reserve deposited', `<span class="num">${T(pol.loanReserve, pol.loan)}</span><br><span class="num">${T(pol.collReserve, pol.coll)}</span>`],
    ['Always kept in reserve', `<span class="num">${T(pol.loanFloor, pol.loan)}</span><br><span class="num">${T(pol.collFloor, pol.coll)}</span>`],
    ['Collateral', `<span class="num">${T(b.collateral_amount, pol.coll)}</span><br><span class="faint num">worth ${T(b.collateral_value, pol.loan)}</span>`],
    ['Debt', `<span class="num">${T(b.debt, pol.loan)}</span>`],
    ['LTV', `<b class="num">${pct(b.ltv)}</b>`],
    ['Room before liquidation', `<span class="num">${T(b.buffer, pol.loan)}</span>`],
  ]);
  const reqs = p.reserve_requirements || [];
  const nLiq = reqs.filter((r) => r.liquidatable_after_hit).length;
  const reqSummary = reqs.length ? `${reqs.length} first price drops, ${nLiq ? `${nLiq} liquidatable before any keeper can react` : 'none liquidatable at once'}` : '';
  const reserveTable = reqs.length ? `<details class="more cm-fold" data-wide-open><summary>${esc(reqSummary)}</summary><div class="tablewrap"><table class="table cm-stack">
      <caption class="vh">Smallest reserve that restores the margin after a first collateral price drop</caption>
      <thead><tr><th scope="col">First price drop</th><th scope="col" class="r">LTV after the drop</th><th scope="col" class="r">Repay at least</th><th scope="col" class="r">Or top up at least</th></tr></thead>
      <tbody>${reqs.map((r) => `<tr class="${r.liquidatable_after_hit ? 'is-hit' : ''}">
        <th scope="row" data-label="First price drop">${signedPct(-r.first_hit, 0)}</th>
        <td class="r cm-wide" data-label="LTV after the drop"><span class="num">${pct(r.ltv_after_hit)}</span>${r.liquidatable_after_hit ? ` ${tagOf('fail', 'Liquidatable')}` : ''}</td>
        <td class="r" data-label="Repay at least">${r.repay_possible ? T(r.min_repay, pol.loan) : 'Full repay only'}</td>
        <td class="r" data-label="Or top up at least">${T(r.min_top_up, pol.coll)}<br><span class="faint">worth ${T(r.min_top_up_value, pol.loan)}</span></td></tr>`).join('')}</tbody></table></div>
      ${nLiq ? `<p class="note cm-foot">${icon('fail')} Liquidatable: that drop alone crosses the ${pctTidy(pol.lltv)} liquidation LTV before any keeper can react.</p>` : ''}</details>`
    : '<p class="note">No reserve requirements recorded for this position.</p>';

  $('panel-arm').innerHTML = `${panelHead('arm', simChip(b.block))}
    <div class="cm-grid cm-grid--3">
      <article class="cm-card"><h3 class="cm-card__title">Policy set by the owner</h3>${policy}</article>
      <article class="cm-card"><h3 class="cm-card__title">Reserve and position at arming</h3>${position}</article>
      <article class="cm-card cm-powers"><h3 class="cm-card__title">What the vault can and cannot do</h3>
        <h4 class="cm-sub">Can</h4>${list(powers.can.map(esc), 'ok', 'cm-list--can')}
        <h4 class="cm-sub">Cannot</h4>${list(powers.cannot.map(esc), 'fail', 'cm-list--cannot')}</article>
    </div>
    <div class="cm-grid cm-grid--2">
      <article class="cm-card"><h3 class="cm-card__title">Reserve needed if the collateral price drops</h3>${reserveTable}</article>
      <article class="cm-card cm-pv">${previewForm(pol)}</article>
    </div>`;
  openOnWide($('panel-arm'));
  $('pv-form').addEventListener('submit', (ev) => { ev.preventDefault(); submitDraft(ev.target); });
}

// Secondary detail is open on wide screens and folded on phones, so the acts stay short there.
function openOnWide(root) {
  const wide = matchMedia('(min-width: 900px)').matches;
  root.querySelectorAll('details[data-wide-open]').forEach((d) => { d.open = wide; });
}

const COOLDOWNS = [[0, 'None'], [900, '15 min'], [3600, '1 h'], [21600, '6 h'], [86400, '24 h']];

function previewForm(pol) {
  const numIn = (name, label, value, unit, extra = '', type = 'number') => `<label class="field"><span>${esc(label)}</span>
      <span class="cm-unit"><input class="input num" type="${type}" name="${name}" value="${esc(value)}" inputmode="decimal" ${extra}><i title="${esc(unit)}">${esc(shortSym(unit))}</i></span></label>`;
  const h = (x) => (x == null || !Number.isFinite(Number(x)) ? '' : String(+Number(x).toFixed(8)));
  const cds = COOLDOWNS.some(([s]) => s === Number(pol.cooldown)) ? COOLDOWNS : [...COOLDOWNS, [Number(pol.cooldown), fmtDuration(pol.cooldown)]];
  const days = pol.validUntil && pol.armedAt ? Math.max(1, Math.round((pol.validUntil - pol.armedAt) / 86400)) : 30;
  return `<h3 class="cm-card__title">Policy preview</h3>
    <p class="cm-pv__copy">${icon('none')}<span>Policy preview — validated for the local-fork protection demonstration. No mainnet RescueVault is deployed.</span></p>
    <details class="more cm-pv__more" id="pv-details" data-wide-open><summary>Change the limits and check them</summary>
    <form class="cm-pv__form" id="pv-form" novalidate>
      <fieldset class="cm-pv__set cm-pv__set--wide"><legend>Allowed actions</legend>
        <div class="cm-checks-row">${pol.strategies.map((s) => `<label class="cm-check"><input type="checkbox" name="strategy" value="${s.key}"${s.allowed ? ' checked' : ''}><span>${esc(s.label)}</span></label>`).join('')}</div>
      </fieldset>
      ${numIn('trigger_ltv', 'Acts when LTV reaches', pctInput(pol.trigger), '%', 'step="0.5" min="1" max="99"')}
      ${numIn('min_ltv_after', 'Never pushes LTV below', pctInput(pol.floor), '%', 'step="1" min="0" max="99"')}
      ${numIn('lltv', 'Market liquidation LTV', pctInput(pol.lltv), '%', 'readonly aria-readonly="true" title="Read from the market"', 'text')}
      ${numIn('max_repay_per_action', 'Repay per action', h(pol.repayPer), pol.loan, 'min="0" step="any"')}
      ${numIn('max_repay_total', 'Repay in total', h(pol.repayTotal), pol.loan, 'min="0" step="any"')}
      ${numIn('max_full_repay', 'Full repay cap (0 is off)', h(pol.fullRepay), pol.loan, 'min="0" step="any"')}
      ${numIn('max_top_up_per_action', 'Top-up per action', h(pol.topUpPer), pol.coll, 'min="0" step="any"')}
      ${numIn('max_top_up_total', 'Top-up in total', h(pol.topUpTotal), pol.coll, 'min="0" step="any"')}
      ${numIn('min_loan_reserve', 'Always keep', h(pol.loanFloor), pol.loan, 'min="0" step="any"')}
      ${numIn('min_collateral_reserve', 'Always keep', h(pol.collFloor), pol.coll, 'min="0" step="any"')}
      ${numIn('valid_days', 'Valid for', days, 'days', 'min="1" step="1"')}
      <label class="field"><span>Wait between actions</span><select class="select" name="cooldown_s">${cds.map(([s, l]) => `<option value="${s}"${s === Number(pol.cooldown) ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
      <input type="hidden" name="loan_decimals" value="${esc(pol.loanDecimals ?? 6)}"><input type="hidden" name="collateral_decimals" value="${esc(pol.collDecimals ?? 18)}">
      <div class="cm-pv__actions"><button class="btn btn--primary" type="submit">Check this policy</button></div>
    </form>
    <div class="cm-pv__out" id="pv-out" aria-live="polite"></div>
    </details>`;
}

let draftCtl = null;
async function submitDraft(form) {
  const out = $('pv-out');
  const fd = new FormData(form);
  const strategies = fd.getAll('strategy');
  if (!strategies.length) {
    out.innerHTML = `<div class="cm-pv__res is-bad">${list(['Choose at least one allowed action.'], 'fail')}</div>`;
    return;
  }
  const fields = {};
  for (const [k, v] of fd.entries()) if (k !== 'strategy') fields[k] = String(v).trim();
  fields.strategies = strategies.join(',');
  if (draftCtl) draftCtl.abort();
  const ctl = new AbortController();
  draftCtl = ctl;
  const btn = form.querySelector('[type="submit"]');
  btn.disabled = true;
  out.innerHTML = `<p class="note">${statusChip('loading', 'checking the policy')}</p>`;
  try {
    const { data: d } = await getJson(apiUrl('/api/countermove', draftParams(fields)), { timeout: 20000, signal: ctl.signal, store: false });
    out.innerHTML = draftResult(d);
  } catch (e) {
    if (e.code === 'aborted') return;
    const x = explain(e);
    out.innerHTML = unavailable('The policy could not be checked', errText(x), 'pv-retry');
    $('pv-retry').addEventListener('click', () => form.requestSubmit());
  } finally {
    btn.disabled = false;
    if (draftCtl === ctl) draftCtl = null;
  }
}

function draftResult(d) {
  const errs = d.errors || [], warns = d.warnings || [];
  const head = d.valid
    ? `<p class="cm-pv__verdict">${tagOf('ok', 'Valid')}<span>for the local-fork demonstration, valid until ${esc(fmtDate((d.policy || {}).valid_until))}</span></p>`
    : `<p class="cm-pv__verdict">${tagOf('fail', 'Not valid')}<span>${errs.length} ${errs.length === 1 ? 'problem' : 'problems'} to fix</span></p>`;
  const calls = [['Policy call (setPolicy)', d.calldata, 'pv-call'], ['Pause call', d.pause_calldata, 'pv-pause'], ['Revoke call', d.revoke_calldata, 'pv-revoke']]
    .filter(([, c]) => c);
  return `<div class="cm-pv__res ${d.valid ? 'is-ok' : 'is-bad'}">${head}
    ${errs.length ? list(errs.map((x) => esc(cap(x))), 'fail') : ''}
    ${warns.length ? list(warns.map((x) => esc(cap(x))), 'alert') : ''}
    ${calls.length ? `<details class="more cm-pv__calls"><summary>Encoded calls for the local-fork RescueVault</summary>
      ${calls.map(([label, c, id]) => `<div class="cm-calldata"><div class="cm-calldata__head"><span>${esc(label)}</span>${copyBtn(c, `Copy ${label.toLowerCase()}`)}</div>
        <pre class="mono" id="${id}">${esc(c)}</pre></div>`).join('')}
      <p class="note">For the RescueVault on the local fork only. There is no mainnet contract to send them to.</p></details>` : ''}</div>`;
}

// ---------- LTV instrument (geometry from gaugeLayout; zones in words and patterns, marks in words and shapes) ----------
function gaugeHtml(g, { at = {}, ticks = {}, zones = ['Safe', 'Vault may act', 'Liquidatable'], label = '' } = {}) {
  const L = gaugeLayout(g);
  if (!L) return '<p class="note">LTV scale unavailable for this position.</p>';
  const tk = tickLabels(L, g.trigger, g.lltv, ticks);
  const marks = markLabels(L);
  const x = (v) => `${Number(v).toFixed(2)}%`;
  const atAttr = (id) => (at[id] != null && at[id] >= 0 ? ` data-at="${at[id]}"` : '');
  return `<figure class="ltv" style="--tlanes:${Math.max(...tk.map((t) => t.lane)) + 1};--lanes:${marks.length}"${label ? ` aria-label="${esc(label)}"` : ''}>
    <div class="ltv__ticks">${tk.map((t) => `<span class="ltv__tick ltv__tick--${t.id}" data-anchor="${t.anchor}" style="left:${x(t.x)};--lane:${t.lane}">${esc(t.text)}</span>`).join('')}</div>
    <div class="ltv__bar" style="--t:${x(L.trigger)};--l:${x(L.lltv)}">
      <span class="ltv__zone ltv__zone--safe"></span><span class="ltv__zone ltv__zone--act"></span><span class="ltv__zone ltv__zone--liq"></span>
      <span class="ltv__rule ltv__rule--trigger" style="left:${x(L.trigger)}"></span><span class="ltv__rule ltv__rule--lltv" style="left:${x(L.lltv)}"></span>
      ${marks.map((m) => `<span class="ltv__pin ltv__pin--${esc(m.id)}" style="left:${x(m.x)}"${atAttr(m.id)}></span>`).join('')}
    </div>
    <div class="ltv__labels">${marks.map((m) => `<span class="ltv__lab ltv__lab--${esc(m.id)}" data-anchor="${m.anchor}" style="left:${x(m.x)};--lane:${m.lane}"${atAttr(m.id)}><i class="ltv__shape" aria-hidden="true"></i>${esc(cap(m.text))}</span>`).join('')}</div>
    <figcaption class="ltv__key"><span><i class="ltv__sw ltv__sw--safe"></i>${esc(zones[0])}</span><span><i class="ltv__sw ltv__sw--act"></i>${esc(zones[1])}</span>
      <span><i class="ltv__sw ltv__sw--liq"></i>${esc(zones[2])}</span><span class="faint">Scale ${pct(L.lo, 0)} to ${pct(L.hi, 0)} LTV</span></figcaption>
  </figure>`;
}

const rawAnswer = (raw, dec) => {
  if (raw == null || dec == null) return '—';
  const v = Number(raw) / 10 ** Number(dec);
  return Number.isFinite(v) ? v.toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) >= 1000 ? 2 : 6 }) : '—';
};
const roleWords = (role, side) => `${String(role || 'feed').replace(/_FEED_(\d)/, ' feed $1').replace(/^BASE/, 'Base').replace(/^QUOTE/, 'Quote')}${side === 'base' ? ', prices the collateral' : side === 'quote' ? ', prices the loan token' : ''}`;

// ---------- DEFEND: what happened and why this action ----------
function renderDefend(p) {
  const c = p.crisis || {}, d = p.decision || {}, b = p.before || {}, e = p.execution, s = p.shock || {};
  const loan = (b.loan || {}).symbol || '';
  const mover = (c.movers || [])[0] || {};
  const steps = timelineSteps(p.timeline);
  const at = {
    before: 0, crisis: steps.findIndex((x) => x.state === 'DETECTED'),
    after: steps.findIndex((x) => x.state === 'CONFIRMED'),
  };
  const h = heroView(p);

  const shock = `<article class="cm-card cm-shock"><h3 class="cm-card__title">The shock</h3>
      <p class="cm-shock__move">${icon('alert')}<span class="num">${esc(signedPct(mover.change != null ? mover.change : c.oracle_change))}</span></p>
      <p class="cm-shock__feed">${esc(s.original_description || String(mover.label || '').replace(/\s*\(SIMULATED SHOCK\)/, '') || 'Oracle feed')}</p>
      <details class="more cm-fold" data-wide-open><summary>Feed details</summary>${kv([
        ['Feed answer', `<span class="num">${rawAnswer(s.pre_shock_answer, s.decimals)}</span> to <span class="num">${rawAnswer(s.shocked_answer, s.decimals)}</span>`],
        ['Collateral price', `<span class="num">${esc(signedPct(mover.effect_on_collateral_price != null ? mover.effect_on_collateral_price : c.oracle_change))}</span>`],
        mover.role && ['Role', esc(roleWords(mover.role, mover.side))],
        s.feed && ['Feed', code(s.feed)],
      ], 'cm-kv--tight')}</details>
      <p class="cm-shock__src">${statusChip('simulated', 'controlled shock')}<span class="note">Injected on the local fork, not a mainnet event</span></p></article>`;

  const stats = [
    { id: 'before', k: 'Before', ltv: b.ltv, room: b.buffer },
    { id: 'crisis', k: 'Crisis', ltv: c.ltv, room: (c.snapshot || {}).buffer },
    e && { id: 'after', k: 'After', ltv: (e.after || {}).ltv, room: (e.after || {}).buffer },
  ].filter(Boolean);
  const ltv = `<article class="cm-card cm-ltvcard"><h3 class="cm-card__title">Loan-to-value on one scale</h3>
      ${gaugeHtml(h.gauge, { at, label: 'Loan-to-value before, at and after the crisis, with the trigger and the liquidation LTV' })}
      <ul class="ltv-stats">${stats.map((x) => `<li class="ltv-stat ltv-stat--${x.id}"${at[x.id] != null && at[x.id] >= 0 ? ` data-at="${at[x.id]}"` : ''}>
        <span class="ltv-stat__k"><i class="ltv__shape" aria-hidden="true"></i>${esc(x.k)}</span>
        <b class="num ltv-stat__v">${x.ltv === 0 ? '0%' : pct(x.ltv)}</b>
        <span class="ltv-stat__room">${x.room == null ? '' : `${amt(x.room, loan, loan)} of room`}</span></li>`).join('')}</ul></article>`;

  const tl = `<article class="cm-card cm-tl"><div class="cm-card__head"><h3 class="cm-card__title">Keeper timeline</h3>
        <button type="button" class="btn btn--sm cm-tl__replay" id="tl-replay"${reduceMotion() ? ' hidden' : ''}>Replay the run</button></div>
      <ol class="cm-tl__list">${steps.map((t) => `<li class="cm-tl__item tone-${t.tone}${t.newCycle ? ' is-cycle' : ''}" data-word="${esc(t.word)}" data-t="${esc(relTime(t.rel))}">
        ${t.newCycle ? '<span class="cm-tl__cyc">Next check</span>' : ''}
        <span class="cm-tl__mark">${icon(t.tone)}</span>
        <div class="cm-tl__body"><p class="cm-tl__top"><b class="cm-tl__state">${esc(t.word)}</b><span class="cm-tl__t num">${esc(relTime(t.rel))}</span>
          ${t.block ? `<span class="faint cm-tl__blk">fork block ${num(t.block)}</span>` : ''}</p>
          <p class="cm-tl__head">${esc(t.head)}</p>
          ${t.tx && t.state === 'CONFIRMED' ? `<p class="cm-tl__tx faint">Fork transaction ${code(t.tx, 8, 6)}</p>` : ''}
          ${t.hasMore ? `<details class="more cm-tl__more"><summary>Keeper note</summary><p class="note">${esc(cap(t.note))}</p></details>` : ''}</div></li>`).join('')}</ol>
      <p class="vh" id="tl-live" aria-live="polite"></p></article>`;

  const rows = candidateVerdicts(d);
  const chosen = rows.find((r) => r.chosen);
  const needs = (r) => `${amt(r.required, r.token, loan)}${r.token !== loan && r.capital != null ? `<br><span class="faint">worth ${amt(r.capital, loan, loan)}</span>` : ''}`;
  let lead;
  if (chosen) {
    const why = chosen.strategy === 'FULL_REPAY' ? 'closes the whole debt, the collateral is not sold or withdrawn'
      : `the smallest amount that keeps ${fmtTok(d.safety_margin, loan, loan)} of room before liquidation in every tested scenario`;
    lead = `${tagOf('ok', 'Chosen')}<span><b>${esc(chosen.label)} ${fmtTok(chosen.required, chosen.token, loan)}</b>: ${esc(why)}</span>`;
  } else {
    lead = `${tagOf('none', 'No action')}<span>${esc(noteHead((p.no_action || {}).reason || d.why) || 'No authorised action can restore the margin')}</span>`;
  }
  const holdBad = ((d.hold || {}).scenarios || []).filter((x) => x.liquidatable);
  const hold = holdBad.length ? `<p class="cm-cmp__hold">${icon('fail')}<span>Doing nothing: ${holdBad.map((x) => `${esc(x.label)} leaves ${fmtTok(x.buffer, loan, loan)} of room, liquidatable`).join('; ')}</span></p>` : '';
  const table = `<div class="tablewrap"><table class="table cm-stack cm-cands"><caption class="vh">Every strategy the engine compared</caption>
      <thead><tr><th scope="col">Action</th><th scope="col" class="r">Needs</th><th scope="col">Verdict</th><th scope="col" class="r">LTV after</th>
        <th scope="col" class="r" title="Room before liquidation in the worst tested scenario">Worst-case room</th></tr></thead>
      <tbody>${rows.map((r) => `<tr class="${r.chosen ? 'is-chosen' : ''}">
        <th scope="row" data-label="Action">${esc(r.label)}</th>
        <td class="r" data-label="Needs">${needs(r)}</td>
        <td data-label="Verdict" class="cm-wide cm-last" title="${esc(r.reasons.join('\n'))}"><span class="cm-verdict">${tagOf(r.tone, r.text)}<span class="cm-verdict__why">${esc(r.detail)}${r.more ? ` (+${r.more} more)` : ''}</span></span></td>
        <td class="r num" data-label="LTV after">${r.ltvAfter == null ? '—' : r.ltvAfter === 0 ? '0%, no debt' : pct(r.ltvAfter)}</td>
        <td class="r" data-label="Worst-case room">${r.worstBuffer == null ? '—' : amt(r.worstBuffer, loan, loan)}</td></tr>`).join('')}</tbody></table></div>`;
  const why = `<details class="more cm-why"><summary>Why this action, in full</summary>
      ${kv([
        ['Engine explanation', esc(cap(whyHead(d.why) || (p.no_action || {}).reason || '—'))],
        ['Order of checks', esc(cap(d.rule || '—'))],
        ['Scenarios tested', esc((d.scenarios || []).map((x) => cap(x.label)).join('; ') || '—')],
        ['Room kept in every scenario', `${fmtTok(d.safety_margin, loan, loan)}, including ${fmtDuration(d.interest_horizon_s)} of interest`],
        (d.hold || {}).hypothetical_penalty != null && ['Liquidation penalty at risk', `${fmtTok(d.hold.hypothetical_penalty, loan, loan)} if nothing was done (hypothetical, shown apart)`],
      ], 'cm-kv--wide')}</details>`;
  const cmp = `<article class="cm-card cm-cmp"><h3 class="cm-card__title">Actions compared</h3><p class="cm-cmp__lead">${lead}</p>${hold}${table}${why}</article>`;

  $('panel-defend').innerHTML = `${panelHead('defend', simChip(((c.snapshot || {}).block) || (e && e.block)))}
    <div class="cm-grid cm-grid--defend">${shock}${ltv}${tl}${cmp}</div>`;
  const rb = $('tl-replay');
  if (rb) rb.addEventListener('click', () => (replayTimer ? stopReplay() : startReplay()));
  openOnWide($('panel-defend'));
}

// ---------- replay: reveals the recorded states in order (explanatory motion only; off with reduced motion) ----------
let replayTimer = 0;
function stopReplay() {
  clearTimeout(replayTimer);
  replayTimer = 0;
  const panel = $('panel-defend');
  if (!panel) return;
  panel.classList.remove('is-replaying');
  panel.querySelectorAll('.is-pending, .is-now').forEach((el) => el.classList.remove('is-pending', 'is-now'));
  const b = $('tl-replay');
  if (b) b.textContent = 'Replay the run';
}

function startReplay() {
  if (reduceMotion()) return;
  stopReplay();
  const panel = $('panel-defend');
  const items = [...panel.querySelectorAll('.cm-tl__item')];
  const marks = [...panel.querySelectorAll('[data-at]')];
  if (!items.length) return;
  panel.classList.add('is-replaying');
  items.forEach((li) => li.classList.add('is-pending'));
  marks.forEach((m) => m.classList.add('is-pending'));
  $('tl-replay').textContent = 'Show all steps';
  let i = 0;
  const tick = () => {
    if (i > 0) items[i - 1].classList.remove('is-now');
    if (i >= items.length) { stopReplay(); $('tl-live').textContent = 'Replay finished, all steps shown.'; return; }
    items[i].classList.remove('is-pending');
    items[i].classList.add('is-now');
    marks.forEach((m) => { if (Number(m.dataset.at) <= i) m.classList.remove('is-pending'); });
    $('tl-live').textContent = `Step ${i + 1} of ${items.length}: ${items[i].dataset.word}, ${items[i].dataset.t}`;
    i += 1;
    replayTimer = setTimeout(tick, 800);
  };
  tick();
}

// ---------- PROVE: what is verified, and where ----------
function checkList(checks) {
  return `<ul class="cm-list cm-checklist">${checks.map((k) => `<li class="${k.ok ? 'is-ok' : 'is-bad'}">${icon(k.ok ? 'ok' : 'fail')}<span>${esc(cap(k.check))}<span class="vh">: ${k.ok ? 'passed' : 'failed'}</span></span></li>`).join('')}</ul>`;
}
const passed = (checks) => `${checks.filter((k) => k.ok).length} of ${checks.length} passed`;

function renderProve(p) {
  const st = proofStatus(p), e = p.execution, b = p.before || {}, v = p.validation || {}, env = data.environment || {};
  const loan = (b.loan || {}).symbol || '', coll = (b.collateral || {}).symbol || '';
  const T = (n, sym) => amt(n, sym, loan);
  const nonce = p.user_nonce || {};
  const nonceSame = nonce.after_arming != null && nonce.after_arming === nonce.at_end;
  const keeperSent = e && env.keeper && String(e.signed_by || '').toLowerCase() === String(env.keeper).toLowerCase();
  const vChecks = v.checks || [], eChecks = (e && e.checks) || [];
  const issues = [...st.issues, ...executionIssues(p)];

  const receipt = e ? `<article class="cm-card cm-receipt"><h3 class="cm-card__title">Receipt on the local fork</h3>
      <p class="cm-receipt__status">${tagOf(st.tone, st.long, st.tip)}</p>
      ${kv([
        ['Action', `<b>${esc(STRATEGY_LABEL[e.strategy] || e.strategy)} <span class="num">${T(e.amount, e.token)}</span></b>`],
        ['Fork transaction', `<span class="cm-hash"><code class="mono cm-code cm-code--full">${esc(e.tx_hash)}</code>${copyBtn(e.tx_hash, 'Copy the fork transaction hash')}</span><span class="faint cm-hash__note">Exists only on the local fork (chain ${esc(env.chain_id)}), not on Etherscan</span>`, 'cm-kv__block'],
        ['Fork block', `<span class="num">${num(e.block)}</span>`],
        ['Gas used', `<span class="num">${num(e.gas_used)}</span> at <span class="num">${num(e.effective_gas_price_gwei, 3)}</span> gwei (fork gas)`],
        ['Sent by', `${keeperSent ? 'The keeper' : 'Account'} ${code(e.signed_by)}, not the user`],
        ['Action id', code(e.action_id, 8, 6)],
      ])}</article>`
    : `<article class="cm-card cm-receipt"><h3 class="cm-card__title">No transaction on the local fork</h3>
      <p class="cm-receipt__status">${tagOf(st.tone, st.long, st.tip)}</p>
      ${kv([
        ['Reason', esc(noteHead((p.no_action || {}).reason) || 'No authorised action can restore the margin')],
        ['Transactions sent', `<span class="num">${num((p.no_action || {}).transactions_sent ?? 0)}</span> (keeper journal)`],
        ['Reserve and position', 'Left exactly as they were'],
      ])}</article>`;

  const ba = e ? `<div class="tablewrap"><table class="table cm-ba"><caption class="vh">Position before and after the action, on the local fork</caption>
      <thead><tr><th scope="col"></th><th scope="col" class="r">Before</th><th scope="col" class="r">After</th></tr></thead><tbody>
      <tr><th scope="row">Debt</th><td class="r" data-label="Before">${T(e.before.debt, loan)}</td><td class="r" data-label="After">${T(e.after.debt, loan)}</td></tr>
      <tr><th scope="row">Collateral</th><td class="r" data-label="Before">${T(e.before.collateral, coll)}</td><td class="r" data-label="After">${T(e.after.collateral, coll)}</td></tr>
      <tr><th scope="row">LTV</th><td class="r num" data-label="Before">${pct(e.before.ltv)}</td><td class="r num" data-label="After"><b>${e.after.ltv === 0 ? '0%, no debt' : pct(e.after.ltv)}</b></td></tr>
      <tr><th scope="row">Room before liquidation</th><td class="r" data-label="Before">${T(e.before.buffer, loan)}</td><td class="r" data-label="After"><b>${T(e.after.buffer, loan)}</b></td></tr>
      <tr><th scope="row">Reserve in the vault</th><td class="r" data-label="Before">${T(e.before.reserve, e.token)}</td><td class="r" data-label="After">${T(e.after.reserve, e.token)}</td></tr>
      </tbody></table></div>` : `<p class="note">No action, so nothing changed: LTV ${pct((p.crisis || {}).ltv)} at detection, above the ${pctTidy((p.crisis || {}).trigger_ltv)} trigger.</p>`;

  const user = list([
    p.user_signed_during_crisis ? 'The user signed during the crisis' : 'No user signature during the crisis',
    `User nonce ${num(nonce.after_arming)} after arming, ${num(nonce.at_end)} at the end${nonceSame ? ', unchanged' : ', changed'}`,
  ].map(esc), p.user_signed_during_crisis || !nonceSame ? 'fail' : 'ok', 'cm-list--user');

  const checks = `<article class="cm-card cm-checks"><div class="cm-card__head"><h3 class="cm-card__title">Verification checks</h3>
        ${eChecks.length ? tagOf(eChecks.every((k) => k.ok) ? 'ok' : 'fail', `${passed(eChecks)} on the fork`) : tagOf('none', 'Nothing to verify')}</div>
      <details class="more cm-checks__det" id="checks-det" data-wide-open><summary>Every check, before sending and after mining</summary>
      <div class="cm-checks__cols">
        <section><h4 class="cm-sub">Before sending, simulated ${vChecks.length ? `<span class="faint">${passed(vChecks)}</span>` : ''}</h4>
          ${vChecks.length ? checkList(vChecks) : `<p class="note">Not reached: no action was planned.</p>`}</section>
        <section><h4 class="cm-sub">After mining, read on-chain ${eChecks.length ? `<span class="faint">${passed(eChecks)}</span>` : ''}</h4>
          ${eChecks.length ? checkList(eChecks) : `<p class="note">No transaction, so no receipt to verify.</p>`}</section>
      </div></details></article>`;

  const yes = [];
  if (e) {
    yes.push(st.key === 'confirmed' ? `Transaction mined at fork block ${num(e.block)} and not reverted` : 'Transaction recorded, but the proof is incomplete');
    yes.push(`On-chain checks: ${passed(eChecks)}. Pre-send checks: ${vChecks.length ? passed(vChecks) : 'none recorded'}`);
    if (keeperSent) yes.push('Sent by the keeper account, from the pre-funded RescueVault');
  } else {
    yes.push(`Keeper journal: ${num((p.no_action || {}).transactions_sent ?? 0)} transactions sent`);
  }
  yes.push(p.user_signed_during_crisis ? 'The user signed during the crisis' : `No user signature: nonce ${num(nonce.after_arming)} before and ${num(nonce.at_end)} after`);
  yes.push(`Real Morpho Blue, market, oracle and liquidity state at fork block ${num(env.fork_block)}`);
  const no = [
    'No RescueVault is deployed on Ethereum mainnet, and this site has no way to deploy one',
    'No mempool, MEV or gas-price competition: the local fork had no other traffic',
    'No security audit: the RescueVault contract is a hackathon prototype',
    'The price shock was injected on the fork, not observed on mainnet',
    'Test funds written into local storage, not real tokens',
    'Fork transaction hashes do not exist on Etherscan',
  ];
  const scope = `<div class="cm-grid cm-grid--2 cm-scope">
      <article class="cm-card cm-scope__yes"><h3 class="cm-card__title">${icon('ok')}Verified on the local fork</h3>${list(yes.map(esc), 'ok')}</article>
      <article class="cm-card cm-scope__no"><h3 class="cm-card__title">${icon('none')}Not verified on Ethereum mainnet</h3>${list(no.map(esc), 'none')}</article></div>`;

  const pr = p.protections, lm = p.remaining_limits;
  const after = (pr || lm) ? `<details class="more cm-after"><summary>Protection left after the run</summary>${kv([
      pr && ['State', tagOf(pr.revoked ? 'fail' : pr.paused ? 'none' : 'ok', pr.revoked ? 'Revoked' : pr.paused ? 'Paused' : 'Still armed')],
      pr && ['Actions executed', num(pr.actions_executed)],
      lm && ['Repay budget left', T(lm.repay_budget_left, loan)],
      lm && ['Top-up budget left', T(lm.top_up_budget_left, coll)],
      lm && ['Reserve left', `${T(lm.loan_reserve_left, loan)}<br>${T(lm.collateral_reserve_left, coll)}`],
      lm && ['Always kept', `${T(lm.min_loan_reserve, loan)}<br>${T(lm.min_collateral_reserve, coll)}`],
    ], 'cm-kv--wide')}</details>` : '';
  const runs = (data.keeper_runs || []).length ? `<details class="more cm-runs"><summary>Keeper process runs on the fork</summary>
      <div class="tablewrap"><table class="table cm-stack"><thead><tr><th scope="col">Run</th><th scope="col" class="r">Duration</th><th scope="col">Result per position</th></tr></thead><tbody>
      ${data.keeper_runs.map((r) => `<tr><th scope="row" data-label="Run">${esc(cap(String(r.tag).replace(/_/g, ' ')))}</th><td class="r num" data-label="Duration">${num(r.seconds, 1)} s</td>
        <td class="cm-wide" data-label="Result per position"><ul class="cm-runs__res">${(r.results || []).map((x) => `<li><span class="mono">${esc(String(x.position).split('-')[0])}</span> ${esc(STATE_WORD[x.state] || x.state)}</li>`).join('')}</ul></td></tr>`).join('')}
      </tbody></table></div></details>` : '';

  $('panel-prove').innerHTML = `${panelHead('prove', simChip((e && e.block) || ((p.crisis || {}).snapshot || {}).block))}
    ${issues.length ? `<div class="alert alert--error" role="alert"><p class="alert__title">Inconsistent proof: do not rely on this result</p>${list(issues.map(esc), 'fail')}</div>` : ''}
    <div class="cm-grid cm-grid--prove">${receipt}<article class="cm-card"><h3 class="cm-card__title">Before and after</h3>${ba}${user}</article></div>
    ${checks}${scope}<div class="cm-more-row">${after}${runs}</div>`;
  openOnWide($('panel-prove'));
}

// ---------- live dry run: what would FAULTLINE do right now (mainnet read, hypothetical policy, nothing sent) ----------
let dryCtl = null;
function initDry() {
  $('dry-rank').innerHTML = RANKS.map((r) => `<option value="${r}">${esc(rankLabel(r))}</option>`).join('');
  $('dry-chip').innerHTML = statusChip('dryrun', 'nothing sent');
  $('dry-form').addEventListener('submit', (ev) => { ev.preventDefault(); runDry(); });
}

async function runDry() {
  if (dryCtl) dryCtl.abort();
  const ctl = new AbortController();
  dryCtl = ctl;
  const market = $('dry-market').value, rank = Number($('dry-rank').value) || 1;
  const btn = $('dry-run');
  btn.disabled = true;
  $('dry-out').innerHTML = '';
  const work = mountWork($('dry-work'), {
    title: `Dry run on ${market}, ${rankLabel(rank).toLowerCase()}`, typical: [3, 8],
    steps: ['Borrower picked from the Morpho API', 'Position re-read on-chain at one block', 'Oracle and feeds read', 'Keeper engine runs with a hypothetical policy'],
    onCancel: () => ctl.abort(),
  });
  try {
    const { data: d } = await getJson(apiUrl('/api/countermove', { action: 'dry-run', market, borrower: 'auto', rank }), { timeout: 45000, signal: ctl.signal, store: false });
    if (d.schema !== 'faultline.countermove.dryrun/1' || d.status !== 'ok') throw new ApiError({ code: 'invalid_payload', message: 'the server answered with an unexpected payload' });
    $('dry-out').innerHTML = dryHtml(dryRunView(d));
    openOnWide($('dry-out'));
  } catch (e) {
    if (e.code === 'aborted') {
      $('dry-out').innerHTML = '<p class="note">Dry run cancelled. Nothing is shown.</p>';
    } else {
      const x = explain(e);
      $('dry-out').innerHTML = unavailable('The dry run did not complete', `${errText(x)} Nothing is shown.`, 'dry-retry');
      $('dry-retry').addEventListener('click', runDry);
    }
  } finally {
    work.stop();
    btn.disabled = false;
    if (dryCtl === ctl) dryCtl = null;
  }
}

function dryHtml(v) {
  const T = (n, sym) => amt(n, sym, v.loan);
  const wTone = v.watcher.outcome === 'HOLD' ? 'ok' : v.watcher.outcome === 'NO_ACTION' ? 'fail' : 'alert';
  const gauge = v.position.hasDebt && v.position.ltv != null ? gaugeHtml(
    { trigger: v.trigger, lltv: v.lltv, marks: [{ id: 'now', label: 'now', ltv: v.position.ltv }] },
    { ticks: { triggerLabel: 'Hypothetical trigger' }, zones: ['Safe', 'Would act (hypothetical)', 'Liquidatable'], label: 'Borrower LTV now, against the hypothetical trigger and the liquidation LTV' },
  ) : '<p class="note">This borrower has no debt in this market right now.</p>';
  const wouldSet = [...new Set(v.reserves.map((r) => r.would))];
  const drops = v.reserves.map((r) => signedPct(-r.first_hit, 0));
  const dryLiq = v.reserves.filter((r) => r.liquidatable_after_hit).length;
  const reqSummary = wouldSet.length === 1 && drops.length
    ? `Keeper would: ${wouldSet[0].toLowerCase()} at every first drop from ${drops[0]} to ${drops[drops.length - 1]}${dryLiq ? `, ${dryLiq} liquidatable at once` : ''}`
    : `${drops.length} first price drops${dryLiq ? `, ${dryLiq} liquidatable at once` : ''}`;
  const reserves = v.reserves.length ? `<details class="more cm-fold" data-wide-open><summary>${esc(reqSummary)}</summary><div class="tablewrap"><table class="table cm-stack"><caption class="vh">Reserve needed per first price drop, hypothetical policy</caption>
      <thead><tr><th scope="col">First price drop</th><th scope="col" class="r">LTV after the drop</th><th scope="col">Trigger reached</th><th scope="col" class="r">Repay at least</th><th scope="col" class="r">Or top up at least</th><th scope="col">Keeper would</th></tr></thead>
      <tbody>${v.reserves.map((r) => `<tr class="${r.liquidatable_after_hit ? 'is-hit' : ''}"><th scope="row" data-label="First price drop">${signedPct(-r.first_hit, 0)}</th>
        <td class="r" data-label="LTV after the drop"><span class="num">${pct(r.ltv_after_hit)}</span>${r.liquidatable_after_hit ? ` ${tagOf('fail', 'Liquidatable')}` : ''}</td>
        <td data-label="Trigger reached">${r.trigger_met_after_hit ? tagOf('alert', 'Yes') : tagOf('neutral', 'No')}</td>
        <td class="r" data-label="Repay at least">${r.repay_possible === false ? 'Full repay only' : T(r.min_repay, v.loan)}</td>
        <td class="r" data-label="Or top up at least">${T(r.min_top_up, v.coll)}</td>
        <td class="cm-wide" data-label="Keeper would">${tagOf(r.wouldTone, r.would)}</td></tr>`).join('')}</tbody></table></div></details>` : '<p class="note">No reserve requirements returned.</p>';
  const hp = v.policy || {};
  return `<div class="cm-dry__chips">${statusChip('live', `block ${num(v.block)}`)}${statusChip('dryrun', 'nothing sent')}
      <span class="note">${esc(v.network || 'Ethereum mainnet')}, ${v.readOnly ? 'read-only, ' : ''}read ${esc(dateTime(v.blockTs))}${v.elapsed != null ? `, took ${num(v.elapsed, 1)} s` : ''}</span></div>
    <div class="cm-grid cm-grid--dry">
      <article class="cm-card"><h3 class="cm-card__title">Borrower</h3>
        <p class="cm-dry__who">${code(v.borrower.address)}${v.borrower.address ? copyBtn(v.borrower.address, 'Copy the borrower address') : ''}</p>
        <p class="note">${esc(rankLabel(v.borrower.rank || 1))} in ${esc(v.market)}, by borrow shares in the Morpho API, position re-read on-chain</p>
        ${kv([
          ['Debt', `<span class="num">${T(v.position.debt, v.loan)}</span>`],
          ['Collateral', `<span class="num">${T(v.position.collateral, v.coll)}</span><br><span class="faint num">worth ${T(v.position.collateralValue, v.loan)}</span>`],
          v.position.dropToLiquidation != null && ['Price drop to liquidation', `<span class="num">${pct(v.position.dropToLiquidation)}</span>`],
        ], 'cm-kv--tight')}</article>
      <article class="cm-card"><h3 class="cm-card__title">LTV now</h3>${gauge}</article>
      <article class="cm-card cm-dry__engine"><h3 class="cm-card__title">Keeper and engine</h3>
        ${kv([
          ['Watcher', `${tagOf(wTone, v.watcher.word || '—')}<span class="cm-dry__reason">${esc(v.watcher.head)}</span>`],
          ['Trigger reached', v.triggerMet ? tagOf('alert', `Yes, at or above ${pctTidy(v.trigger)}`) : tagOf('ok', `No, below ${pctTidy(v.trigger)}`)],
          ['Engine decision', `${tagOf(v.decision.tone, v.decision.text)}<span class="cm-dry__reason">${esc(cap(v.decision.detail))}</span>`],
        ])}</article>
    </div>
    <article class="cm-card"><h3 class="cm-card__title">Reserve needed if the collateral price drops, hypothetical policy</h3>${reserves}</article>
    <div class="cm-grid cm-grid--2">
      <article class="cm-card cm-dry__notdone"><h3 class="cm-card__title">Not done</h3>${list(v.notDone.map((x) => esc(cap(String(x).replace(/\b(WATCHING|DETECTED|PLANNING|VALIDATING|EXECUTING)\b/g, (m) => STATE_WORD[m].toLowerCase())))), 'none')}</article>
      <details class="more cm-card cm-dry__policy"><summary>Hypothetical policy used</summary>${kv([
        ['Allowed actions', esc((hp.strategies || []).map((s) => STRATEGY_LABEL[s] || s).join(', ') || '—')],
        ['Acts when LTV reaches', `${pctTidy(hp.trigger_ltv)} <span class="faint">(${esc(v.defaultRules.trigger_ltv || '')})</span>`],
        ['Never pushes LTV below', pctTidy(hp.min_ltv_after)],
        ['Reserve assumed', `${T(v.reservesHyp.loan, v.reservesHyp.loan_symbol || v.loan)}<br>${T(v.reservesHyp.collateral, v.reservesHyp.collateral_symbol || v.coll)}`],
        ['Wait between actions', fmtDuration(hp.cooldown_s)],
        ['Defaults used', esc(v.defaultsUsed.map((x) => x.replace(/_/g, ' ')).join(', ') || 'none')],
      ], 'cm-kv--wide')}</details>
    </div>`;
}

// ---------- live oracle dependencies (read on demand) ----------
let liveBusy = false;
function initLive() {
  const box = $('live-box');
  box.addEventListener('toggle', () => { if (box.open && !liveBusy && !$('live-out').dataset.done) loadLive(); });
}

async function loadLive() {
  liveBusy = true;
  const ctl = new AbortController();
  $('live-out').innerHTML = '';
  const work = mountWork($('live-work'), {
    title: 'Reading the oracles on Ethereum mainnet', typical: [6, 18],
    steps: ['Each protected market\'s oracle, read on-chain', 'Every feed behind it, with its last update'], onCancel: () => ctl.abort(),
  });
  try {
    const { data: d } = await getJson('/api/countermove?live=1', { timeout: 60000, signal: ctl.signal, store: false });
    const lv = d.live || {};
    if (lv.status !== 'LIVE') throw new ApiError({ code: 'live_unavailable', message: lv.error || 'no mainnet RPC answered' });
    $('live-out').innerHTML = liveHtml(lv);
    $('live-out').dataset.done = '1';
  } catch (e) {
    if (e.code === 'aborted') $('live-out').innerHTML = '<p class="note">Cancelled. Nothing is shown.</p>';
    else { const x = explain(e); $('live-out').innerHTML = unavailable('The live read did not complete', `${errText(x)} Nothing is shown.`, 'live-retry'); }
    const r = $('live-retry') || null;
    if (r) r.addEventListener('click', loadLive);
  } finally {
    work.stop();
    liveBusy = false;
  }
  const again = $('live-again');
  if (again) again.addEventListener('click', () => { delete $('live-out').dataset.done; loadLive(); });
}

function liveHtml(lv) {
  const markets = Object.entries(lv.markets || {});
  return `<div class="cm-dry__chips">${statusChip('live', `block ${num(lv.block)}`)}<span class="note">Read ${esc(dateTime(lv.timestamp))}, read-only, nothing sent</span>
      <button type="button" class="btn btn--quiet btn--sm" id="live-again">Read again</button></div>
    <div class="cm-grid cm-grid--3">${markets.map(([name, m]) => {
      const feeds = feedRows(m);
      return `<article class="cm-card cm-oracle"><h3 class="cm-card__title">${esc(name)}</h3>
        <p class="faint cm-oracle__type">${esc((m.oracle || {}).type || 'Oracle')} ${code((m.oracle || {}).address)}</p>
        <ul class="cm-feeds">${feeds.map((f) => `<li><div class="cm-feeds__top"><span class="cm-feeds__name">${esc(f.name)}</span><span class="num cm-feeds__val">${f.value != null ? Number(f.value).toLocaleString('en-US', { maximumFractionDigits: Math.abs(Number(f.value)) >= 1000 ? 2 : 6 }) : '—'}</span></div>
          <div class="cm-feeds__meta">${tagOf(f.tone, f.state)}${f.limit ? `<span class="faint">${esc(f.limit)}</span>` : ''}</div></li>`).join('') || '<li class="note">No feed to read</li>'}</ul>
        ${(m.assumptions || []).length ? `<details class="more"><summary>What this oracle does not see</summary>${list(m.assumptions.map((a) => esc(cap(a))), 'none')}</details>` : ''}</article>`;
    }).join('')}</div>`;
}

// ---------- copy buttons ----------
document.addEventListener('click', async (ev) => {
  const b = ev.target.closest('.cm-copy');
  if (!b) return;
  try {
    await navigator.clipboard.writeText(b.dataset.copy);
    b.textContent = 'Copied';
  } catch {
    b.textContent = 'Select and copy';
  }
  setTimeout(() => { b.textContent = 'Copy'; }, 1600);
});

initDry();
initLive();
load();
