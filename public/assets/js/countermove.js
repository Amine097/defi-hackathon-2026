// Autonomous Countermove page (Phase 2). Renders faultline.countermove/1 from GET /api/countermove.
// No financial computation here: amounts, LTVs, buffers, decisions and checks are all read from the backend payload.
import {
  statusView, executionIssues, timelineView, candidateRows, envText, fmtTok, fmtPct, fmtNum, fmtDate, fmtDuration,
  esc, short, STATUS, STRATEGY_LABEL, labelParts, outcomeKey, shortReason, whyHead, dependencyRows, heroView, gaugeLayout,
} from './countermove/view.js';

const $ = (id) => document.getElementById(id);
let data = null;
let current = 0;

const badge = (st, txt, tip) => `<span class="badge badge-${esc(st)}" title="${esc(tip || '')}">${esc(txt)}</span>`;
const kv = (rows) => rows.filter(Boolean).map(([k, v, tip]) => `<dt${tip ? ` title="${esc(tip)}"` : ''}>${esc(k)}</dt><dd>${v}</dd>`).join('');
const pct = (x, d = 1) => fmtPct(x, d);
const strat = (s) => STRATEGY_LABEL[s] || s;
const arrow = (a, b) => `${a} → <b>${b}</b>`;

async function load() {
  try {
    const r = await fetch('/api/countermove', { cache: 'no-store' });
    const body = await r.json();
    if (!r.ok || body.status !== 'ok') throw new Error((body.error && body.error.message) || body.message || `HTTP ${r.status}`);
    if (body.schema !== 'faultline.countermove/1') throw new Error('unexpected payload schema');
    data = body;
    const want = (location.hash || '').slice(1).toUpperCase();
    current = Math.max(0, data.positions.findIndex((p) => p.scenario === want));
    $('status').hidden = true;
    render();
  } catch (e) {
    $('status').hidden = true;
    $('error').hidden = false;
    $('error').textContent = `No Countermove data: ${e.message}. Nothing is shown rather than unverified figures.`;
  }
}

function render() {
  $('env').hidden = false;
  $('envText').textContent = `Recorded demo run on a ${envText(data.environment)}.`;
  $('envNotes').textContent = (data.environment.notes || []).join(' · ');
  $('tabs').innerHTML = data.positions.map((p, i) => {
    const sv = statusView(p), lp = labelParts(p.label);
    return `<button class="cm-tab" role="tab" aria-selected="${i === current}" data-i="${i}" title="${esc(p.label)}">
      <span class="cm-tab-top"><b>${esc(p.scenario)}</b> ${badge(sv.cls, sv.label, sv.tip)}</span>
      <strong>${esc(strat(outcomeKey(p)))}</strong>
      <small>${esc([lp.user, lp.market].filter(Boolean).join(' · '))}</small></button>`;
  }).join('');
  document.querySelectorAll('.cm-tab').forEach((b) => b.addEventListener('click', () => {
    current = Number(b.dataset.i);
    history.replaceState(null, '', `#${data.positions[current].scenario}`);
    render();
  }));
  renderPosition(data.positions[current]);
  renderRuns();
  $('result').hidden = false;
}

function renderGauge(g) {
  const L = gaugeLayout(g);
  if (!L) { $('gauge').innerHTML = ''; return; }
  const marks = L.marks.map((m) => `<span class="cm-mark cm-mark-${esc(m.id)}${m.x < 12 ? ' cm-edge' : ''}" style="left:${m.x.toFixed(2)}%"
      title="${esc(m.text)}"><i></i><em>${esc(m.text)}</em></span>`).join('');
  $('gauge').innerHTML = `<div class="cm-bar" style="--t:${L.trigger.toFixed(2)}%;--l:${L.lltv.toFixed(2)}%">
      <span class="cm-tick" style="left:${L.trigger.toFixed(2)}%"><em>your trigger ${pct(g.trigger, 0)}</em></span>
      <span class="cm-tick cm-tick-l" style="left:${L.lltv.toFixed(2)}%"><em>liquidation ${pct(g.lltv, 0)}</em></span>
      ${marks}</div>
    <figcaption class="muted"><span><span class="cm-key cm-key-ok"></span>safe</span> <span><span class="cm-key cm-key-warn"></span>keeper acts</span>
      <span><span class="cm-key cm-key-bad"></span>liquidatable</span> <span>· scale ${pct(L.lo, 0)}–${pct(L.hi, 0)} LTV</span></figcaption>`;
}

function renderPosition(p) {
  const sv = statusView(p), h = heroView(p), lp = labelParts(p.label);
  const b = p.before || {}, vault = b.vault || {}, d = p.decision || {};
  const loan = (b.loan || {}).symbol || '', coll = (b.collateral || {}).symbol || '';
  const T = (n, sym) => fmtTok(n, sym, loan);

  // Hero: the outcome first.
  $('hEyebrow').textContent = `${p.scenario} · ${[lp.user, lp.market, lp.setup].filter(Boolean).join(' · ')}`;
  $('hBadge').innerHTML = badge(sv.cls, sv.label, sv.tip);
  $('hTitle').textContent = h.title;
  $('hero').dataset.tone = sv.consistent ? h.tone : 'exit';
  $('hFacts').innerHTML = [
    h.reaction_s != null ? badge('muted', `${p.execution ? 'reacted' : 'decided'} in ${fmtNum(h.reaction_s, 1)} s`, 'From detection to the final state, measured by the keeper') : '',
    badge(h.user_signed ? 'exit' : 'stay', h.user_signed ? 'user signed' : 'no user signature',
      `user nonce ${p.user_nonce.after_arming} after arming → ${p.user_nonce.at_end} at the end`),
    badge('sim', 'SIMULATED', STATUS.SIMULATED.tip)].join(' ');
  $('hCrisis').textContent = h.crisis;
  $('hDecision').textContent = h.decision;
  $('hResult').textContent = h.result;
  renderGauge(h.gauge);
  const issues = [...sv.issues, ...executionIssues(p)];
  $('pIssues').innerHTML = issues.map((i) => `<li>${esc(i)}: do not rely on this result</li>`).join('');
  $('pMeta').innerHTML = `borrower ${esc(p.user)}<br>RescueVault ${esc(p.rescue_vault)}<br>market ${esc(p.market_id)}`;
  $('steps').innerHTML = timelineView(p.timeline).map((s) => `<li class="${esc(s.cls)}">${esc(s.state)}</li>`).join('');

  // 1 · Before.
  const pol = vault.policy || {};
  $('before').innerHTML = kv([
    ['Collateral', `${T(b.collateral_amount, coll)} <span class="muted">≈ ${T(b.collateral_value, loan)}</span>`, 'valued at the market oracle price'],
    ['Debt', T(b.debt, loan), 'interest accrued'],
    ['LTV', `<b>${pct(b.ltv)}</b> <span class="muted">liquidation at ${pct(b.lltv, 0)}</span>`],
    ['Room before liquidation', T(b.buffer, loan), 'debt can grow by this much (or collateral value fall by the equivalent) before liquidation'],
    ['Borrow APR', pct(b.borrow_apr_onchain, 2)],
  ]);
  const deps = b.dependencies || {};
  $('deps').innerHTML = dependencyRows(deps).map((r) => `<li title="${esc(r.tip)}">${esc(r.name)} <span class="va-txt-${esc(r.cls)} cm-dep-state">${esc(r.state)}</span></li>`).join('')
    || '<li class="muted">no oracle feed recorded</li>';
  $('assume').innerHTML = (deps.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join('');
  const allowed = new Set(pol.strategies || []);
  $('policy').innerHTML = kv([
    ['Allowed actions', esc(['REPAY', 'TOP_UP', 'FULL_REPAY'].filter((s) => allowed.has(s)).map(strat).join(', ') || 'none')],
    ['Act when LTV reaches', `<b>${pct(pol.trigger_ltv_pct, 0)}</b>`],
    ['Never push LTV below', pct(pol.min_ltv_after_pct, 0)],
    allowed.has('REPAY') && ['Repay', `up to ${T(pol.max_repay_per_action_h, loan)} per action · ${T(pol.max_repay_total_h, loan)} total`],
    allowed.has('TOP_UP') && ['Top-up', `up to ${T(pol.max_top_up_per_action_h, coll)} per action · ${T(pol.max_top_up_total_h, coll)} total`],
    allowed.has('FULL_REPAY') && ['Full repay', Number(pol.max_full_repay_h) > 0 ? `up to ${T(pol.max_full_repay_h, loan)}` : 'disabled (cap 0)'],
    ['Reserve deposited', `${T(vault.loan_reserve, loan)} + ${T(vault.collateral_reserve, coll)}`],
    ['Always keep', `${T(pol.min_loan_reserve_h, loan)} + ${T(pol.min_collateral_reserve_h, coll)}`, 'reserve floors the keeper can never go below'],
    ['Wait between actions', fmtDuration(pol.cooldown)],
    ['Valid until', fmtDate(pol.valid_until)],
    ['Monitoring', vault.revoked ? 'revoked' : vault.paused ? 'paused' : '<span class="va-txt-stay">armed</span>'],
  ]);
  const reqs = p.reserve_requirements || [];
  $('reserves').innerHTML = '<thead><tr><th>If collateral price falls</th><th class="num">LTV becomes</th><th class="num">Repay at least</th><th class="num">or top up at least</th></tr></thead><tbody>'
    + reqs.map((r) => `<tr class="${r.liquidatable_after_hit ? 'cm-row-bad' : ''}"><td>−${fmtPct(r.first_hit, 0)}</td>
      <td class="num">${pct(r.ltv_after_hit)}${r.liquidatable_after_hit ? ' <span class="va-txt-exit" title="above the liquidation LTV">⚠</span>' : ''}</td>
      <td class="num">${r.repay_possible ? T(r.min_repay, loan) : 'full repay only'}</td>
      <td class="num">${T(r.min_top_up, coll)} <span class="muted">≈ ${fmtNum(r.min_top_up_value, 0)} ${esc(loan)}</span></td></tr>`).join('') + '</tbody>';
  $('reservesNote').textContent = reqs.some((r) => r.liquidatable_after_hit)
    ? '⚠ = liquidatable immediately after this first hit: a keeper reacting after the move would be too late, the reserve only helps for smaller hits.' : '';

  // 2 · During.
  const c = p.crisis || {};
  $('crisis').innerHTML = kv([
    ['LTV when detected', `<b class="va-txt-exit">${pct(c.ltv)}</b> <span class="muted">trigger ${pct(c.trigger_ltv, 0)}</span>`],
    ['Collateral price change', c.oracle_change == null ? '—' : pct(c.oracle_change)],
    ['Safety margin required', T(d.safety_margin, loan), `kept in every scenario below, including ${fmtDuration(d.interest_horizon_s)} of interest`],
    ['Stress scenarios tested', esc((d.scenarios || []).map((s) => s.label).join(' · '))],
  ]);
  $('movers').innerHTML = (c.movers || []).map((m) => `<li title="${esc(m.role)} (${esc(m.side || '')})"><b>${esc(String(m.label).replace(/\s*\(SIMULATED SHOCK\)/, ''))}</b>
      <span class="va-txt-exit">${pct(m.change)}</span> ${m.simulated ? '<small class="muted">simulated shock</small>' : ''}</li>`).join('')
    || '<li class="muted">no dependency move recorded</li>';
  if (p.shock) $('movers').innerHTML += `<li class="muted cm-note">${esc(p.shock.label)}</li>`;
  const noActionHead = p.no_action ? String(p.no_action.reason || '').split(/:\s/)[0] : '';
  $('pWhy').textContent = p.no_action ? `${noActionHead.charAt(0).toUpperCase()}${noActionHead.slice(1)}. Each action's blocking reason is in the table (hover for the full list).` : whyHead(d.why);
  $('cands').innerHTML = '<thead><tr><th>Action</th><th class="num">Needs</th><th>Verdict</th><th class="num">LTV after</th><th class="num">Worst-case room</th></tr></thead><tbody>'
    + candidateRows(d).map((r) => `<tr class="${r.chosen ? 'cm-chosen' : ''}">
      <td><b>${esc(strat(r.strategy))}</b>${r.chosen ? ' ' + badge('stay', 'CHOSEN') : ''}</td>
      <td class="num">${T(r.required, r.token)}${r.token !== loan && r.capital != null ? `<br><small class="muted">≈ ${fmtNum(r.capital, 0)} ${esc(loan)}</small>` : ''}</td>
      <td title="${esc(r.reasons.join('\n'))}"><span class="va-txt-${esc(r.cls)}">${r.cls === 'stay' ? '✓' : '✗'} ${esc(r.verdict)}</span>
        ${r.reason ? `<br><small class="muted">${esc(shortReason(r.reason))}${r.reasons.length > 1 ? ` (+${r.reasons.length - 1} more)` : ''}</small>` : ''}</td>
      <td class="num">${r.ltvAfter == null ? '—' : r.ltvAfter === 0 ? '0% (no debt)' : pct(r.ltvAfter)}</td>
      <td class="num">${T(r.worstBuffer, loan)}</td></tr>`).join('') + '</tbody>';
  $('rule').textContent = d.rule ? `Ranking rule: ${d.rule}. Repaid debt and added collateral remain your wealth; only gas is lost. A hypothetical liquidation penalty is shown apart, never summed.` : '';
  const v = p.validation || {}, vc = v.checks || [];
  $('validationSum').innerHTML = vc.length
    ? `Pre-send checks: <span class="va-txt-${vc.every((k) => k.ok) ? 'stay' : 'exit'}">${vc.filter((k) => k.ok).length}/${vc.length} passed</span>`
    : 'Pre-send checks: <span class="muted">not reached (no action planned)</span>';
  $('validation').innerHTML = vc.map((k) => `<li class="${k.ok ? '' : 'bad'}">${esc(k.check)}</li>`).join('') || '<li class="muted">not reached</li>';

  // 3 · After.
  const e = p.execution;
  if (e) {
    const tok = e.token || '';
    $('after').innerHTML = `<p class="cm-big">${badge(sv.cls, sv.label, sv.tip)} ${esc(strat(e.strategy))} ${T(e.amount, tok)}</p>
      <dl class="cm-kv cm-kv-wide">${kv([
        ['Debt', arrow(T(e.before.debt, loan), T(e.after.debt, loan))],
        ['Collateral', arrow(T(e.before.collateral, coll), T(e.after.collateral, coll))],
        ['LTV', arrow(pct(e.before.ltv), e.after.ltv === 0 ? '0%' : pct(e.after.ltv))],
        ['Room before liquidation', arrow(T(e.before.buffer, loan), T(e.after.buffer, loan))],
        [`Reserve (${tok})`, arrow(T(e.before.reserve, tok), T(e.after.reserve, tok))],
        ['Transaction', `<span class="cm-mono" title="${esc(e.tx_hash)}">${esc(short(e.tx_hash))}</span> <span class="muted">block ${fmtNum(e.block, 0)} (fork)</span>`],
        ['Signed by', `keeper <span class="cm-mono" title="${esc(e.signed_by)}">${esc(short(e.signed_by))}</span>, not you`],
        ['Gas', `${fmtNum(e.gas_used, 0)} <span class="muted">@ ${fmtNum(e.effective_gas_price_gwei, 3)} gwei</span>`],
      ])}</dl>`;
    const ec = e.checks || [];
    $('checksSum').innerHTML = `On-chain verification: <span class="va-txt-${ec.length && ec.every((k) => k.ok) ? 'stay' : 'exit'}">${ec.filter((k) => k.ok).length}/${ec.length} checks passed</span>`;
    $('checks').innerHTML = ec.map((k) => `<li class="${k.ok ? '' : 'bad'}">${esc(k.check)}</li>`).join('');
  } else {
    $('after').innerHTML = `<p class="cm-big">${badge(sv.cls, sv.label, sv.tip)} No transaction was sent.</p>
      <p class="muted">Your position and reserves are exactly as they were. Top up the RescueVault or widen your policy to make an action possible.</p>`;
    $('checksSum').innerHTML = 'On-chain verification: <span class="muted">nothing to verify</span>';
    $('checks').innerHTML = '<li class="muted">reserves and position untouched by the keeper</li>';
  }
  const pr = p.protections || {}, lm = p.remaining_limits || {};
  const prAllowed = new Set(pr.strategies || []);
  $('protections').innerHTML = p.protections ? kv([
    ['Allowed actions', esc(['REPAY', 'TOP_UP', 'FULL_REPAY'].filter((s) => prAllowed.has(s)).map(strat).join(', '))],
    ['Act when LTV reaches', pct(pr.trigger_ltv, 0)], ['Never push LTV below', pct(pr.min_ltv_after, 0)],
    ['Wait between actions', fmtDuration(pr.cooldown_s)], ['Valid until', fmtDate(pr.valid_until)],
    ['Status', pr.revoked ? '<span class="va-txt-exit">revoked</span>' : pr.paused ? 'paused' : '<span class="va-txt-stay">armed</span>'],
    ['Actions executed', fmtNum(pr.actions_executed, 0)]]) : kv([['Policy', 'unchanged (no action)']]);
  $('limits').innerHTML = p.remaining_limits ? kv([
    ['Repay budget left', T(lm.repay_budget_left, loan)], ['Top-up budget left', T(lm.top_up_budget_left, coll)],
    ['Reserve left', `${T(lm.loan_reserve_left, loan)} + ${T(lm.collateral_reserve_left, coll)}`],
    ['Always keep', `${T(lm.min_loan_reserve, loan)} + ${T(lm.min_collateral_reserve, coll)}`]]) : kv([['Reserves', 'untouched']]);

  syncDraftForm(b);
}

// The policy form uses the selected scenario's market: token units, decimals and the market LLTV are not user inputs.
function syncDraftForm(b) {
  const f = $('draft');
  const loan = b.loan || {}, coll = b.collateral || {};
  f.elements.lltv.value = Number.isFinite(Number(b.lltv)) ? +(Number(b.lltv) * 100).toFixed(2) : 86;
  if (loan.decimals != null) f.elements.loan_decimals.value = loan.decimals;
  if (coll.decimals != null) f.elements.collateral_decimals.value = coll.decimals;
  f.querySelectorAll('[data-unit="loan"]').forEach((x) => { x.textContent = loan.symbol || ''; });
  f.querySelectorAll('[data-unit="coll"]').forEach((x) => { x.textContent = coll.symbol || ''; });
  $('draftMarket').textContent = `${coll.symbol || '?'}/${loan.symbol || '?'}, liquidation at ${pct(b.lltv, 0)}`;
}

function renderRuns() {
  $('runs').innerHTML = '<thead><tr><th>Run</th><th class="num">Duration</th><th>Result per scenario</th></tr></thead><tbody>'
    + (data.keeper_runs || []).map((r) => `<tr><td><b>${esc(r.tag)}</b><br><code class="cm-mono muted">${esc(r.command)}</code></td>
      <td class="num">${fmtNum(r.seconds, 1)} s</td><td>${(r.results || []).map((x) => `${esc(x.position)}: ${badge((STATUS[x.state] || {}).cls || 'muted', (STATUS[x.state] || {}).label || x.state)}`).join('<br>')}</td></tr>`).join('') + '</tbody>';
}

$('liveBtn').addEventListener('click', async () => {
  $('live').textContent = 'Reading mainnet…';
  try {
    const r = await fetch('/api/countermove?live=1', { cache: 'no-store' });
    const body = await r.json();
    const lv = body.live || {};
    if (lv.status !== 'LIVE') { $('live').textContent = `LIVE read unavailable (${lv.error || 'no answer'}): nothing shown.`; return; }
    $('live').innerHTML = `<p>${badge('live', 'LIVE', STATUS.LIVE.tip)} block ${fmtNum(lv.block, 0)} · ${fmtDate(lv.timestamp)}</p>`
      + Object.entries(lv.markets).map(([name, m]) => `<h4>${esc(name)}</h4><ul class="cm-deps">${dependencyRows(m).map((x) =>
        `<li title="${esc(x.tip)}">${esc(x.name)}: <b>${fmtNum(x.value, 6)}</b> <span class="va-txt-${esc(x.cls)} cm-dep-state">${esc(x.state)}</span></li>`).join('')}</ul>`
        + `<ul class="cm-assume">${(m.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join('')}</ul>`).join('');
  } catch (e) {
    $('live').textContent = `LIVE read failed: ${e.message}`;
  }
});

$('draft').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const q = new URLSearchParams(new FormData(ev.target));
  // The form shows percentages; the API (and the contract) take fractions.
  for (const k of ['trigger_ltv', 'min_ltv_after', 'lltv']) q.set(k, String(Number(q.get(k)) / 100));
  q.set('action', 'policy-draft');
  $('draftOut').textContent = 'Checking…';
  try {
    // Query-string action (not a sub-path): Vercel only routes /api/countermove itself to the function.
    const r = await fetch('/api/countermove?' + q.toString(), { cache: 'no-store' });
    const isJson = (r.headers.get('content-type') || '').includes('application/json');
    if (!isJson) throw new Error(`the policy check service did not answer (HTTP ${r.status})`);
    const body = await r.json();
    if (!r.ok) throw new Error((body.error && body.error.message) || `HTTP ${r.status}`);
    const warn = (body.warnings || []).length
      ? `<ul class="va-warnings">${body.warnings.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
    $('draftOut').innerHTML = body.valid
      ? `<p>${badge('stay', 'VALID')} Sign this <b>setPolicy</b> call, sent to your RescueVault. <span class="muted">Signer: ${esc(body.signer)}.</span></p>${warn}
         <p class="cm-mono cm-calldata">${esc(body.calldata)}</p>
         <details class="cm-more"><summary>Pause or revoke later</summary>
           <p class="muted">Pause monitoring:</p><p class="cm-mono cm-calldata">${esc(body.pause_calldata)}</p>
           <p class="muted">Revoke forever:</p><p class="cm-mono cm-calldata">${esc(body.revoke_calldata)}</p></details>`
      : `<p>${badge('exit', 'INVALID')} Fix the following before signing:</p><ul class="va-warnings">${(body.errors || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
  } catch (e) {
    $('draftOut').textContent = `Policy check failed: ${e.message}`;
  }
});

// A printout should not hide the evidence behind collapsed sections.
window.addEventListener('beforeprint', () => document.querySelectorAll('details').forEach((x) => { x.dataset.wasOpen = x.open ? '1' : ''; x.open = true; }));
window.addEventListener('afterprint', () => document.querySelectorAll('details').forEach((x) => { if (x.dataset.wasOpen !== undefined) { x.open = x.dataset.wasOpen === '1'; delete x.dataset.wasOpen; } }));

load();
