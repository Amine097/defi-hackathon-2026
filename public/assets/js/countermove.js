// Autonomous Countermove page (Phase 2). Renders faultline.countermove/1 from GET /api/countermove.
// No financial computation here: amounts, LTVs, buffers, decisions and checks are all read from the backend payload.
import {
  statusView, executionIssues, timelineView, candidateRows, envText, fmtAmt, fmtPct, fmtNum, esc, short, STATUS,
} from './countermove/view.js';

const $ = (id) => document.getElementById(id);
let data = null;
let current = 0;

const badge = (st, txt, tip) => `<span class="badge badge-${esc(st)}" title="${esc(tip || '')}">${esc(txt)}</span>`;
const kv = (rows) => rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('');
const pct = (x, d = 2) => fmtPct(x, d);
const ts = (t) => (t ? new Date(Number(t) * 1000).toISOString().replace('.000Z', 'Z') : '—');

async function load() {
  try {
    const r = await fetch('/api/countermove', { cache: 'no-store' });
    const body = await r.json();
    if (!r.ok || body.status !== 'ok') throw new Error((body.error && body.error.message) || body.message || `HTTP ${r.status}`);
    if (body.schema !== 'faultline.countermove/1') throw new Error('unexpected payload schema');
    data = body;
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
  $('envText').textContent = envText(data.environment);
  $('envNotes').textContent = (data.environment.notes || []).join(' · ');
  $('tabs').innerHTML = data.positions.map((p, i) => {
    const sv = statusView(p);
    return `<button class="cm-tab" role="tab" aria-selected="${i === current}" data-i="${i}">
      <span>${badge(sv.cls, sv.label, sv.tip)} ${badge('sim', 'SIMULATED', STATUS.SIMULATED.tip)}</span>
      <strong>${esc(p.scenario)} · ${esc((p.execution && p.execution.strategy) || (p.decision && p.decision.decision) || '')}</strong>
      <small>${esc(p.label)}</small></button>`;
  }).join('');
  document.querySelectorAll('.cm-tab').forEach((b) => b.addEventListener('click', () => { current = Number(b.dataset.i); render(); }));
  renderPosition(data.positions[current]);
  renderRuns();
  $('result').hidden = false;
}

function renderPosition(p) {
  const sv = statusView(p);
  const b = p.before || {};
  const loan = (b.loan || {}).symbol || '', coll = (b.collateral || {}).symbol || '';
  $('pTitle').textContent = p.label;
  $('pMeta').textContent = `borrower ${p.user} · RescueVault ${p.rescue_vault} · market ${short(p.market_id)}`;
  $('pBadges').innerHTML = [badge(sv.cls, sv.label, sv.tip), badge('sim', 'SIMULATED', STATUS.SIMULATED.tip),
    badge(p.user_signed_during_crisis ? 'exit' : 'stay', p.user_signed_during_crisis ? 'user signed' : 'no user signature',
      `user nonce ${p.user_nonce.after_arming} after arming → ${p.user_nonce.at_end} at the end`)].join(' ');
  $('steps').innerHTML = timelineView(p.timeline).map((s) => `<li class="${esc(s.cls)}">${esc(s.state)}</li>`).join('');
  const d = p.decision || {};
  $('pWhy').textContent = p.no_action ? `NO ACTION — ${p.no_action.reason}` : (d.why || '');
  const issues = [...sv.issues, ...executionIssues(p)];
  $('pIssues').innerHTML = issues.map((i) => `<li>${esc(i)}: do not rely on this result</li>`).join('');

  const pol = (b.vault || {}).policy || {};
  $('before').innerHTML = kv([
    ['Collateral', fmtAmt(b.collateral_amount, coll)], ['Collateral value (oracle)', fmtAmt(b.collateral_value, loan, 2)],
    ['Debt (interest accrued)', fmtAmt(b.debt, loan, 2)], ['LTV / LLTV', `${pct(b.ltv)} / ${pct(b.lltv, 1)}`],
    ['Liquidation buffer', fmtAmt(b.buffer, loan, 2)], ['On-chain borrow APR', pct(b.borrow_apr_onchain)],
    ['Block', fmtNum(b.block, 0)]]);
  const deps = b.dependencies || {};
  $('deps').innerHTML = (deps.feeds || []).map((f) => `<li>${esc(f.original_description || f.description || f.role)}
      <span class="muted">(${esc(f.role)}, ${esc(f.side)}, ${esc(f.freshness)})</span></li>`).join('')
    + (deps.assumptions || []).map((a) => `<li class="muted">assumption: ${esc(a)}</li>`).join('');
  $('policy').innerHTML = kv([
    ['Strategies allowed', esc((pol.strategies || []).join(', ') || '—')], ['Trigger LTV', pct(pol.trigger_ltv_pct)],
    ['LTV floor after action', pct(pol.min_ltv_after_pct)], ['Max repay / action', fmtAmt(pol.max_repay_per_action_h, loan, 2)],
    ['Max top-up / action', fmtAmt(pol.max_top_up_per_action_h, coll)], ['Max full repay', fmtAmt(pol.max_full_repay_h, loan, 2)],
    ['Repay budget', fmtAmt(pol.max_repay_total_h, loan, 2)], ['Top-up budget', fmtAmt(pol.max_top_up_total_h, coll)],
    ['Reserve funded', `${fmtAmt((b.vault || {}).loan_reserve, loan, 2)} + ${fmtAmt((b.vault || {}).collateral_reserve, coll)}`],
    ['Reserve floors', `${fmtAmt(pol.min_loan_reserve_h, loan, 2)} / ${fmtAmt(pol.min_collateral_reserve_h, coll)}`],
    ['Valid until', ts(pol.valid_until)], ['Cooldown', `${fmtNum(pol.cooldown, 0)} s`],
    ['Keeper', `<span class="cm-mono">${esc(short((b.vault || {}).keeper))}</span>`],
    ['Monitoring', (b.vault || {}).revoked ? 'revoked' : (b.vault || {}).paused ? 'paused' : 'armed']]);
  $('reserves').innerHTML = '<thead><tr><th>First hit</th><th class="num">LTV</th><th class="num">Min repay</th><th class="num">or min top-up</th></tr></thead><tbody>'
    + (p.reserve_requirements || []).map((r) => `<tr><td>−${fmtPct(r.first_hit, 0)}</td><td class="num">${pct(r.ltv_after_hit)}${r.liquidatable_after_hit ? ' ⚠' : ''}</td>
      <td class="num">${r.repay_possible ? fmtAmt(r.min_repay, loan, 2) : 'full repay'}</td>
      <td class="num">${fmtAmt(r.min_top_up, coll)} <span class="muted">(${fmtAmt(r.min_top_up_value, loan, 0)})</span></td></tr>`).join('') + '</tbody>';

  const c = p.crisis || {};
  $('crisis').innerHTML = kv([
    ['On-chain LTV at detection', `<b>${pct(c.ltv)}</b>`], ['Trigger set by the owner', pct(c.trigger_ltv)],
    ['Threshold crossed', c.trigger_met ? '<span class="va-txt-exit">yes</span>' : 'no'],
    ['Oracle price change', c.oracle_change == null ? '—' : pct(c.oracle_change)],
    ['Scenario margin', `${fmtAmt(d.safety_margin, loan, 2)} · horizon ${fmtNum((d.interest_horizon_s || 0) / 3600, 0)} h`],
    ['Scenarios', esc((d.scenarios || []).map((s) => `${s.label} (×${fmtNum(s.price_factor, 4)})`).join('; '))]]);
  $('movers').innerHTML = (c.movers || []).map((m) => `<li><b>${esc(m.label)}</b> ${pct(m.change)} ${m.simulated ? badge('sim', 'SIMULATED') : ''}
    <span class="muted">(${esc(m.role)})</span></li>`).join('') || '<li class="muted">no dependency move recorded</li>';
  if (p.shock) $('movers').innerHTML += `<li class="muted">${esc(p.shock.label)}</li>`;
  $('cands').innerHTML = '<thead><tr><th>Action</th><th class="num">Required</th><th>Outcome</th><th class="num">Reserve value used</th><th class="num">LTV after</th><th class="num">Worst buffer after</th></tr></thead><tbody>'
    + candidateRows(d).map((r) => `<tr class="${r.chosen ? 'cm-chosen' : ''}"><td><b>${esc(r.strategy)}</b>${r.chosen ? ' ' + badge('stay', 'CHOSEN') : ''}</td>
      <td class="num">${fmtAmt(r.required, r.token)}</td>
      <td>${badge(r.cls, r.stage)}<br><small class="muted">${esc(r.reason)}</small></td>
      <td class="num">${fmtAmt(r.capital, loan, 2)}</td><td class="num">${r.ltvAfter == null ? '—' : pct(r.ltvAfter)}</td>
      <td class="num">${fmtAmt(r.worstBuffer, loan, 2)}</td></tr>`).join('') + '</tbody>';
  $('rule').textContent = d.rule ? `Rule: ${d.rule}. Repaid principal and added collateral stay your wealth; only gas is a cost lost; a hypothetical liquidation penalty is shown apart, never summed.` : '';
  const v = p.validation || {};
  $('validation').innerHTML = (v.checks || []).map((k) => `<li class="${k.ok ? '' : 'bad'}">${esc(k.check)}</li>`).join('')
    || `<li class="bad">${esc((p.no_action && 'not reached: no action was planned') || 'not reached')}</li>`;

  const e = p.execution;
  if (e) {
    const tok = e.token || '';
    $('after').innerHTML = `<p>${badge(sv.cls, sv.label, sv.tip)} <span class="cm-big">${esc(e.strategy)} ${fmtAmt(e.amount, tok)}</span></p>
      <dl class="cm-kv">${kv([
        ['Transaction', `<span class="cm-mono">${esc(e.tx_hash)}</span>`], ['Block (fork)', fmtNum(e.block, 0)],
        ['Signed by', `keeper <span class="cm-mono">${esc(short(e.signed_by))}</span>`],
        ['Gas used', `${fmtNum(e.gas_used, 0)} @ ${fmtNum(e.effective_gas_price_gwei, 3)} gwei`],
        ['Debt', `${fmtAmt(e.before.debt, loan, 2)} → <b>${fmtAmt(e.after.debt, loan, 2)}</b>`],
        ['Collateral', `${fmtAmt(e.before.collateral, coll)} → <b>${fmtAmt(e.after.collateral, coll)}</b>`],
        ['LTV', `${pct(e.before.ltv)} → <b>${pct(e.after.ltv)}</b>`],
        ['Liquidation buffer', `${fmtAmt(e.before.buffer, loan, 2)} → <b>${fmtAmt(e.after.buffer, loan, 2)}</b>`],
        ['Reserve', `${fmtAmt(e.before.reserve, tok)} → ${fmtAmt(e.after.reserve, tok)}`]])}</dl>`;
    $('checks').innerHTML = (e.checks || []).map((k) => `<li class="${k.ok ? '' : 'bad'}">${esc(k.check)}</li>`).join('');
  } else {
    $('after').innerHTML = `<p>${badge(sv.cls, sv.label, sv.tip)} <b>No transaction was sent.</b></p><p class="muted">${esc((p.no_action || {}).reason || '')}</p>`;
    $('checks').innerHTML = '<li class="muted">nothing to verify: reserves and position untouched by the keeper</li>';
  }
  const pr = p.protections || {}, lm = p.remaining_limits || {};
  $('protections').innerHTML = p.protections ? kv([
    ['Strategies', esc((pr.strategies || []).join(', '))], ['Trigger LTV', pct(pr.trigger_ltv)], ['LTV floor', pct(pr.min_ltv_after)],
    ['Cooldown', `${fmtNum(pr.cooldown_s, 0)} s`], ['Valid until', ts(pr.valid_until)],
    ['Paused / revoked', `${pr.paused ? 'paused' : 'active'} / ${pr.revoked ? 'revoked' : 'not revoked'}`],
    ['Actions executed', fmtNum(pr.actions_executed, 0)]]) : kv([['Policy', 'unchanged (no action)']]);
  $('limits').innerHTML = p.remaining_limits ? kv([
    ['Repay budget left', fmtAmt(lm.repay_budget_left, loan, 2)], ['Top-up budget left', fmtAmt(lm.top_up_budget_left, coll)],
    ['Loan reserve left', fmtAmt(lm.loan_reserve_left, loan, 2)], ['Collateral reserve left', fmtAmt(lm.collateral_reserve_left, coll)],
    ['Reserve floors', `${fmtAmt(lm.min_loan_reserve, loan, 2)} / ${fmtAmt(lm.min_collateral_reserve, coll)}`]]) : kv([['Reserves', 'untouched']]);
}

function renderRuns() {
  $('runs').innerHTML = '<thead><tr><th>Run</th><th class="num">Seconds</th><th>Result per position</th></tr></thead><tbody>'
    + (data.keeper_runs || []).map((r) => `<tr><td><b>${esc(r.tag)}</b><br><span class="cm-mono muted">${esc(r.command)}</span></td>
      <td class="num">${fmtNum(r.seconds, 1)}</td><td>${(r.results || []).map((x) => `${esc(x.position)}: ${badge((STATUS[x.state] || {}).cls || 'muted', x.state)}`).join('<br>')}</td></tr>`).join('') + '</tbody>';
}

$('liveBtn').addEventListener('click', async () => {
  $('live').textContent = 'Reading mainnet…';
  try {
    const r = await fetch('/api/countermove?live=1', { cache: 'no-store' });
    const body = await r.json();
    const lv = body.live || {};
    if (lv.status !== 'LIVE') { $('live').textContent = `LIVE read unavailable (${lv.error || 'no answer'}): nothing shown.`; return; }
    $('live').innerHTML = `<p>${badge('live', 'LIVE', STATUS.LIVE.tip)} block ${fmtNum(lv.block, 0)} · ${ts(lv.timestamp)}</p>`
      + Object.entries(lv.markets).map(([name, m]) => `<h4>${esc(name)}</h4><ul class="va-list">${(m.feeds || []).map((f) =>
        `<li>${esc(f.description || f.role)}: ${fmtNum(f.value, 6)} <span class="muted">(${esc(f.freshness)}${f.age_s != null ? ', ' + fmtNum(f.age_s, 0) + ' s old' : ''})</span></li>`).join('')}
        ${(m.assumptions || []).map((a) => `<li class="muted">assumption: ${esc(a)}</li>`).join('')}</ul>`).join('');
  } catch (e) {
    $('live').textContent = `LIVE read failed: ${e.message}`;
  }
});

$('draft').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const q = new URLSearchParams(new FormData(ev.target));
  const r = await fetch('/api/countermove/policy-draft?' + q.toString(), { cache: 'no-store' });
  const body = await r.json();
  $('draftOut').innerHTML = body.valid
    ? `<p>${badge('stay', 'VALID')} Sign this <b>setPolicy</b> call with your wallet (target: your RescueVault). ${esc(body.signer)}.</p>
       <p class="cm-mono">${esc(body.calldata)}</p><p class="muted">Pause monitoring: <span class="cm-mono">${esc(body.pause_calldata)}</span> · revoke forever: <span class="cm-mono">${esc(body.revoke_calldata)}</span></p>`
    : `<p>${badge('exit', 'INVALID')}</p><ul class="va-warnings">${(body.errors || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
});

load();
