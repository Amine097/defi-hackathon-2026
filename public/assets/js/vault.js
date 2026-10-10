// Vault Risk Analyzer page (Phase 1). Renders the faultline.vault/1 payload of GET /api/vault.
// Single source of truth: every USD figure, band, margin and verdict is read from the backend payload.
import {
  buildQuery, verdictView, modeBadge, errorText, shockOptions, layoutGraph, sharedDependencies, routeRows, EXECUTABLE,
  fmtUsd, fmtPct, fmtNum, esc, short,
} from './vault/view.js';

const BELEM = '0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec';
const $ = (id) => document.getElementById(id);
const ROLE_COLOR = {
  vault: '#ff8a3d', adapter: '#b05cf0', market: '#b05cf0', morpho_blue: '#b05cf0', lending: '#b05cf0',
  collateral: '#2ecc71', stablecoin: '#2ecc71', oracle: '#f1c40f', fx: '#f1c40f', chain: '#7f8c9a',
};
let current = null;
let busy = false;

function setStatus(text) { const s = $('status'); s.hidden = !text; s.textContent = text || ''; }
function setError(text) { const e = $('error'); e.hidden = !text; e.textContent = text || ''; }
function badge(cls, label, tip) { return `<span class="badge badge-${esc(cls)}" title="${esc(tip || '')}">${esc(label)}</span>`; }

async function run(params) {
  const b = buildQuery(params);
  if (b.error) { setError(b.error); return; }
  if (busy) return;
  busy = true;
  $('fSubmit').disabled = true;
  setError('');
  const t0 = performance.now();
  setStatus('Reading the vault on-chain, its markets, oracles and prices, and simulating a redemption… (about 10–20 s)');
  history.replaceState(null, '', '?' + b.query);
  let status = 0, body = null;
  try {
    const r = await fetch('/api/vault?' + b.query, { cache: 'no-store' });
    status = r.status;
    body = await r.json().catch(() => null);
  } catch (_) { status = 0; }
  busy = false;
  $('fSubmit').disabled = false;
  if (status !== 200 || !body || body.schema !== 'faultline.vault/1') {
    setStatus('');
    $('result').hidden = true;
    current = null;
    setError(errorText(status, body));
    return;
  }
  setStatus(`Analysis done in ${((performance.now() - t0) / 1000).toFixed(1)} s.`);
  current = body;
  render(body);
}

function render(p) {
  $('result').hidden = false;
  renderSummary(p);
  renderAllocations(p);
  renderGraph(p);
  renderRisk(p);
  renderScenarios(p);
  renderSensitivity(p);
  renderExit(p);
  $('assumptions').innerHTML = (p.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join('');
  const pv = p.provenance || {};
  $('provBox').innerHTML = [
    `mode ${esc(p.mode)} · block ${esc(p.as_of_block)} · ${esc(new Date(p.timestamp * 1000).toISOString())} · age ${fmtNum(p.age_s, 0)} s`,
    `RPC: ${esc(pv.rpc)} · indexer: ${esc(pv.indexer)} · prices: ${esc(pv.prices)} · simulation: ${esc(pv.simulation)}`,
    `HTTP calls live ${esc(pv.live)} / cached ${esc(pv.cached)}`,
  ].map((l) => `<div>${l}</div>`).join('');
}

function renderSummary(p) {
  const v = p.vault, d = p.decision, al = p.allocations, ex = p.exit;
  $('sumTitle').textContent = `${v.name} (${v.version.toUpperCase()})`;
  $('sumMeta').textContent = `${v.address} · ${v.chain} · asset ${v.asset.symbol} @ ${fmtNum(v.asset.price_usd, 4)} USD · block ${p.as_of_block} · ${new Date(p.timestamp * 1000).toUTCString()}`;
  const mb = modeBadge(p.mode);
  const fr = d.freshness || {};
  $('sumBadges').innerHTML = [
    badge(mb.cls, mb.label, mb.tip),
    badge(fr.label === 'fresh' ? 'stay' : 'warn', 'data ' + (fr.label || '?'), (d.blockers || []).join('; ')),
    badge(al.coverage >= 0.95 ? 'stay' : 'warn', 'coverage ' + fmtPct(al.coverage, 1), al.displayed),
    badge(EXECUTABLE.has(ex.withdrawal_feasibility) ? 'stay' : 'warn', 'withdrawal ' + ex.withdrawal_feasibility, ex.capacity && ex.capacity.rule),
    badge('', 'quote ' + ex.quote_status, ex.simulation && ex.simulation.method),
  ].join(' ');

  const vv = verdictView(d);
  const vb = $('vBadge');
  vb.className = 'va-verdict va-' + vv.cls;
  vb.textContent = vv.label;
  vb.setAttribute('aria-label', `Decision ${vv.label}` + (vv.lean ? `, ${vv.lean}` : ''));
  $('vLean').textContent = d.verdict === 'REVIEW'
    ? `${d.lean} · confidence ${d.confidence}`
    : `Firm ${d.verdict} (confidence ${d.confidence}): the uncertainty bands do not overlap.`;
  $('vReasons').innerHTML = [...(d.reasons || []), ...(d.blockers || []).map((b) => 'blocker: ' + b)].map((r) => `<li>${esc(r)}</li>`).join('');

  $('kLoss').textContent = fmtUsd(d.expected_loss_usd);
  $('kLossBand').textContent = `band ${fmtUsd(d.loss_band_usd[0])} – ${fmtUsd(d.loss_band_usd[1])} over ${d.horizon_days} d · basis: ${vv.basisText}`;
  $('kExit').textContent = fmtUsd(d.exit_side_usd);
  $('kExitBand').textContent = `band ${fmtUsd(d.exit_band_usd[0])} – ${fmtUsd(d.exit_band_usd[1])} (execution + carry)`;
  const km = $('kMargin');
  km.textContent = vv.marginText;
  km.className = 'value va-txt-' + vv.cls;
  $('kMarginHint').textContent = vv.hint + (d.verdict === 'REVIEW' ? ' (not decisive: bands overlap)' : '');
  $('kBreakeven').textContent = d.breakeven_risk_multiplier == null ? '—' : '×' + fmtNum(d.breakeven_risk_multiplier, 2);

  const conv = ex.usd_conversion || {};
  $('costBreakdown').innerHTML = `<table class="table"><tbody>
    <tr><td>Gas (simulated ${esc(ex.executable_route || 'redeem')})</td><td class="num">${fmtUsd(ex.gas_usd)}</td><td class="muted">${esc(ex.gas_why)}</td></tr>
    <tr><td>Withdrawal friction</td><td class="num">${fmtUsd(ex.withdrawal_friction_usd)}</td><td class="muted">assets requested − assets out of the simulated route (incl. forceDeallocate penalty ${fmtUsd(ex.force_deallocate_penalty_usd)})</td></tr>
    <tr><td>Exit fee</td><td class="num">${fmtUsd(ex.exit_fee_usd)}</td><td class="muted">${esc(ex.exit_fee_note)}</td></tr>
    <tr class="va-sub"><td>= Execution cost</td><td class="num">${fmtUsd(d.execution_cost_usd)}</td><td></td></tr>
    <tr><td>+ Carry forgone (${d.horizon_days} d)</td><td class="num">${fmtUsd(d.carry_usd)}</td><td class="muted">${esc(ex.carry.formula)}</td></tr>
    <tr class="va-sub"><td>= Exit side</td><td class="num">${fmtUsd(d.exit_side_usd)}</td><td class="muted">compared with the expected loss ${fmtUsd(d.expected_loss_usd)} (${esc(vv.basisText)})</td></tr>
    <tr><td>Optional ${esc(v.asset.symbol)} → USD conversion</td><td class="num">${conv.status === 'indicative' ? fmtUsd(conv.cost_usd) : '—'}</td>
      <td class="muted">${esc(conv.status)}: not counted in the decision (${esc(conv.why || '')})</td></tr>
  </tbody></table>`;
  $('vExplain').textContent = d.explanation;
  $('consistency').innerHTML = vv.consistent
    ? `<span class="badge badge-stay">figures consistent</span> <span class="muted">margin = loss − (execution + carry); colour, lean and explanation agree with the backend decision.</span>`
    : `<span class="badge badge-exit">inconsistent payload</span> ${esc(vv.issues.join('; '))}: do not act on this result.`;
  const warns = [...(p.warnings || [])];
  if (!EXECUTABLE.has(ex.withdrawal_feasibility)) warns.unshift(`Only ${fmtUsd(ex.immediately_withdrawable_usd)} of ${fmtUsd(ex.theoretical_value_usd)} can be withdrawn now by a simulated route; ${fmtUsd(ex.blocked_or_deferred_usd)} is blocked or deferred.`);
  else if (ex.withdrawal_feasibility === 'full_via_force_deallocate') warns.unshift(`The full ${fmtUsd(ex.theoretical_value_usd)} is withdrawable now only through forceDeallocate (multicall simulated); ordinary capacity alone is ${fmtUsd(ex.capacity.ordinary_usd)}. Liquidity is shared: first come, first served.`);
  $('warnings').innerHTML = warns.map((w) => `<li>${esc(w)}</li>`).join('');
}

function renderAllocations(p) {
  const al = p.allocations;
  $('allocNote').textContent = `${al.items.length} markets · total ${fmtNum(al.total_assets, 2)} ${al.unit} (${fmtUsd(al.total_assets_usd)}) · idle ${fmtPct(al.idle_share, 2)} · unattributed ${fmtPct(al.unattributed_share, 2)} · coverage ${fmtPct(al.coverage, 1)} · ${al.displayed}`;
  const rows = al.items.map((i) => `<tr>
    <td><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.collateral_symbol || 'idle')}</a><div class="muted mono">${esc(short(i.market_id))}</div></td>
    <td class="num">${fmtPct(i.share_of_vault, 2)}</td><td class="num">${fmtUsd(i.supply_usd)}</td>
    <td class="num">${fmtPct(i.lltv, 1)}</td><td class="num">${fmtPct(i.utilization, 1)}</td>
    <td class="num">${fmtPct(i.supply_apy, 2)}</td><td class="num">${fmtNum(i.market_liquidity, 0)}</td>
    <td class="num">${fmtPct(i.vault_share_of_market, 1)}</td><td class="mono">${esc(short(i.oracle))}</td></tr>`).join('');
  $('allocTable').innerHTML = `<thead><tr><th>Market (collateral)</th><th class="num">Share</th><th class="num">USD</th><th class="num">LLTV</th>
    <th class="num">Util.</th><th class="num">Supply APY</th><th class="num">Free liquidity</th><th class="num">Vault % of market</th><th>Oracle</th></tr></thead><tbody>${rows}</tbody>`;
}

function renderGraph(p) {
  const nodes = p.dependencies.nodes, edges = p.dependencies.edges;
  const { pos } = layoutGraph(nodes, edges, 900, 420);
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const maxEl = Math.max(1e-9, ...nodes.map((n) => n.expected_loss_usd || 0));
  const svgE = edges.filter((e) => pos[e.src] && pos[e.dst]).map((e) => {
    const a = pos[e.src], b = pos[e.dst];
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="va-edge" stroke-width="${0.6 + 2.4 * (e.transmission || 0)}" marker-end="url(#arr)"><title>${esc(e.src)} → ${esc(e.dst)}: transmission ${fmtNum(e.transmission, 3)} (${esc(e.relation_type || '')}, ${esc(e.confidence || '')})</title></line>`;
  }).join('');
  const svgN = Object.entries(pos).map(([id, q]) => {
    const n = byId[id];
    const r = id === 'pos' ? 12 : 6 + 12 * Math.sqrt((n.expected_loss_usd || 0) / maxEl);
    const col = id === 'pos' ? '#3b82f6' : ROLE_COLOR[n.role] || '#8a94a8';
    const label = id === 'pos' ? 'Your deposit' : (n.label || id);
    return `<g class="va-node" data-id="${esc(id)}" tabindex="0" role="button" aria-label="${esc(label)}">
      <circle cx="${q.x}" cy="${q.y}" r="${r.toFixed(1)}" fill="${col}"/><text x="${q.x}" y="${q.y + r + 12}" text-anchor="middle">${esc(label.length > 22 ? label.slice(0, 21) + '…' : label)}</text></g>`;
  }).join('');
  $('graph').innerHTML = `<defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a94a8"/></marker></defs>${svgE}${svgN}`;
  $('graph').querySelectorAll('.va-node').forEach((g) => {
    const show = () => showNode(byId[g.dataset.id], g.dataset.id);
    g.addEventListener('click', show);
    g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); show(); } });
  });
  const sh = sharedDependencies(nodes);
  $('sharedList').innerHTML = sh.length
    ? sh.map((s) => `<li><b>${esc(s.label)}</b> (${esc(s.role)}) behind ${s.count} allocations: ${fmtUsd(s.usd)} affected if it fails. Counted once.</li>`).join('')
    : '<li class="muted">No dependency is shared by several allocations.</li>';
}

function showNode(n, id) {
  if (!n) { $('nodeInfo').textContent = 'Your deposit: hypothetical vault shares worth the exposure entered above.'; return; }
  $('nodeInfo').innerHTML = `<b>${esc(n.label)}</b> <span class="muted">(${esc(n.role)}, ${esc(id)})</span><br>
    P(fail over horizon) ${fmtPct(n.p_fail_horizon, 3)} · loss given failure ${fmtPct(n.loss_given_failure, 0)} · share of your deposit exposed ${fmtPct(n.affected_fraction, 2)}
    · affected if it fails ${fmtUsd(n.affected_usd_if_fails)} · expected loss ${fmtUsd(n.expected_loss_usd)}<br>
    <span class="muted">P source: ${esc(n.source)}</span><br><span class="muted">LGF source: ${esc(n.lgf_source)}</span>`;
}

function renderRisk(p) {
  const r = p.risk;
  $('riskBox').innerHTML = `<p>Expected loss over ${r.horizon_days} d: <b>${fmtUsd(r.expected_loss_usd)}</b> (${fmtPct(r.expected_loss_pct, 3)}),
    uncertainty band ${fmtUsd(r.band_usd[0])} – ${fmtUsd(r.band_usd[1])}; dependence bounds ${fmtUsd(r.dependence_bounds_usd[0])} – ${fmtUsd(r.dependence_bounds_usd[1])};
    Monte Carlo mean ${fmtUsd(r.mc_mean_usd)}, 95% VaR ${fmtUsd(r.var95_usd)}.</p><p class="muted">${esc(r.label)} · ${esc(r.formula)}</p>`;
  $('driverTable').innerHTML = '<thead><tr><th>Dependency</th><th class="num">Expected loss</th><th class="num">Best-path transmission</th></tr></thead><tbody>' +
    (r.drivers || []).map((x) => `<tr><td>${esc(x.label)}</td><td class="num">${fmtUsd(x.expected_loss_usd)}</td><td class="num">${fmtNum(x.paths && x.paths[0] && x.paths[0].transmission, 3)}</td></tr>`).join('') + '</tbody>';
}

function renderScenarios(p) {
  $('scenTable').innerHTML = '<thead><tr><th>Scenario</th><th class="num">Loss</th><th class="num">% of exposure</th><th class="num">Withdrawable after (ordinary)</th><th class="num">With forceDeallocate</th><th>What happens</th></tr></thead><tbody>' +
    p.scenarios.map((s) => `<tr><td>${esc(s.name)}</td><td class="num">${fmtUsd(s.loss_usd)}</td><td class="num">${fmtPct(s.loss_pct, 2)}</td>
      <td class="num">${fmtUsd(s.immediately_withdrawable_usd)}</td><td class="num" title="${esc(s.force_deallocate_route || '')}">${s.withdrawable_with_force_deallocate_usd == null ? '—' : fmtUsd(s.withdrawable_with_force_deallocate_usd) + (/^confirmed/.test(s.force_deallocate_route || '') ? ' ✓' : ' (theoretical)')}</td><td class="muted">${esc(s.description)}</td></tr>`).join('') + '</tbody>';
  const sel = $('shockNode'), chosen = p.input.shock;
  sel.innerHTML = shockOptions(p.dependencies.nodes).map((o) => `<option value="${esc(o.id)}"${o.id === chosen ? ' selected' : ''}>${esc(o.label)} (${esc(o.role)})</option>`).join('');
  if (p.input.severity != null) $('shockSev').value = p.input.severity;
}

function renderSensitivity(p) {
  const s = p.sensitivity;
  $('sensTable').innerHTML = `<thead><tr><th>Dependency: probability ×0.5 / ×2</th><th class="num">Expected loss low</th><th class="num">High</th></tr></thead><tbody>` +
    (s['tornado_p_x0.5_x2'] || []).map((t) => `<tr><td>${esc(t.label)}</td><td class="num">${fmtUsd(t.low_usd)}</td><td class="num">${fmtUsd(t.high_usd)}</td></tr>`).join('') +
    `</tbody><caption class="muted">base ${fmtUsd(s.base_expected_loss_usd)} · ${esc(s.note)}${s.breakeven_risk_multiplier != null ? ': ×' + fmtNum(s.breakeven_risk_multiplier, 2) : ''}</caption>`;
  const c = s.collateral_crash_curve;
  $('crashCurve').innerHTML = c && c.node
    ? `<p class="muted">Crash curve for ${esc(c.label)} (conditional on the drop): ` + c.points.map((q) => `−${fmtPct(q.drop, 0)} → ${fmtUsd(q.loss_usd)}`).join(' · ') + '</p>'
    : '';
}

function renderExit(p) {
  const e = p.exit, c = e.capacity, f = e.force_deallocate, sim = e.simulation || {};
  const rows = (c.rows || []).map((r) => `<li>${esc(r.collateral || 'idle market (no collateral)')} (${esc(r.path)}): ${fmtNum(r.available, 2)} available</li>`).join('');
  $('exitBox').innerHTML = `
    <p>Feasibility <b>${esc(e.withdrawal_feasibility)}</b>: ${fmtUsd(e.immediately_withdrawable_usd)} withdrawable now, ${fmtUsd(e.blocked_or_deferred_usd)} blocked or deferred
      (exposure ${fmtUsd(e.theoretical_value_usd)}, ${esc(e.basis)}).</p>
    <p>Ordinary capacity ${fmtNum(c.ordinary_assets, 2)} ${esc(p.vault.asset.symbol)} (${fmtUsd(c.ordinary_usd)}), <i>shared with every other depositor</i>. Rule: ${esc(c.rule)}.
      ${c.api_cross_check ? `Cross-check vs ${esc(c.api_cross_check.source)}: ${c.api_cross_check.ok ? 'ok' : 'MISMATCH'} (rel. diff ${Number(c.api_cross_check.rel_diff).toExponential(1)}).` : ''}</p>
    <ul class="va-list">${rows}</ul>
    ${c.contract_max_redeem_note ? `<p class="muted">${esc(c.contract_max_redeem_note)}</p>` : ''}
    <p>Redeem simulation: <b>${esc(sim.status)}</b>${sim.block ? ' at block ' + esc(sim.block) : ''}${sim.gas_estimate ? ', ' + fmtNum(sim.gas_estimate, 0) + ' gas' : ''}. <span class="muted">${esc(sim.method || '')}</span></p>
    ${e.simulation_partial ? `<p>Partial redeem simulation: <b>${esc(e.simulation_partial.status)}</b>.</p>` : ''}
    <table class="table"><thead><tr><th>Exit route</th><th>Status</th><th class="num">Capacity</th><th class="num">Gas</th><th class="num">Penalty</th></tr></thead><tbody>
      ${routeRows(e).map((r) => `<tr><td>${esc(r.name)}</td><td><span class="badge badge-${r.confirmed ? 'stay' : 'warn'}">${esc(r.status)}</span></td>
        <td class="num">${fmtUsd(r.capacity)}</td><td class="num">${r.gas == null ? '—' : fmtUsd(r.gas)}</td><td class="num">${r.penalty == null ? '—' : fmtUsd(r.penalty)}</td></tr>`).join('')}
    </tbody><caption class="muted">A route counts as executable only when its simulation succeeded for the amount (eth_call, no transaction). Executable route: ${esc(e.executable_route || 'none')}.</caption></table>
    ${f.plan ? `<p>forceDeallocate plan: ${f.plan.steps.map((s) => `${esc(s.collateral || 'idle')} ${fmtNum(s.assets, 2)} (penalty ${fmtPct(s.penalty_rate, 2)})`).join(' + ')} to cover ${fmtNum(f.plan.need_assets, 2)} ${esc(p.vault.asset.symbol)} beyond ordinary capacity. <span class="muted">${esc(f.plan.rule)}</span></p>` : ''}
    <p>Force-deallocate path (${esc(f.status)}): ${fmtNum(f.assets, 2)} ${esc(p.vault.asset.symbol)} (${fmtUsd(f.usd)}) of other-market liquidity, penalty ${fmtUsd(f.penalty_cost_usd)}. <span class="muted">${esc(f.note)} ${esc((f.reserves || []).join('; '))}</span></p>
    <p>Carry: net APY on-chain ${fmtPct(e.carry.net_apy_onchain, 2)} (API excl. rewards ${fmtPct(e.carry.net_apy_api, 2)}${e.carry.apy_cross_check ? (e.carry.apy_cross_check.ok ? ', cross-check ok' : ', cross-check MISMATCH') : ''});
      token rewards not counted ${fmtUsd(e.carry.rewards_usd_not_counted)}. <span class="muted">${esc(e.carry.note)}</span></p>`;
}

$('vaultForm').addEventListener('submit', (ev) => {
  ev.preventDefault();
  run({ address: $('fAddress').value, value_usd: $('fValue').value, horizon_days: $('fHorizon').value });
});
$('fBelem').addEventListener('click', () => { $('fAddress').value = BELEM; $('fAddress').focus(); });
$('shockForm').addEventListener('submit', (ev) => {
  ev.preventDefault();
  if (!current) return;
  run({ address: current.input.address, value_usd: current.input.value_usd, horizon_days: current.input.horizon_days, shock: $('shockNode').value, severity: $('shockSev').value });
});

// Deep link: /vault.html?address=0x…&value_usd=…&horizon_days=… runs the analysis live on load (never a cached result).
const qs = new URLSearchParams(location.search);
const qa = qs.get('address') || qs.get('url');
if (qa) {
  $('fAddress').value = qa;
  if (qs.get('value_usd')) $('fValue').value = qs.get('value_usd');
  if (qs.get('horizon_days')) $('fHorizon').value = qs.get('horizon_days');
  run({ address: qa, value_usd: $('fValue').value, horizon_days: $('fHorizon').value, shock: qs.get('shock'), severity: qs.get('severity') });
}
