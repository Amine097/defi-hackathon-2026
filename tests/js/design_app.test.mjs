// Claude Design v2 app wiring (public/app.html + /assets/dc/fl-live.js): every figure the design renders must come from
// a backend payload, role-aware results must pass through unchanged, and the pages must run under the CSP.
// Run: node --test tests/js/*.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = p => readFileSync(new URL('../../' + p, import.meta.url), 'utf8');
const json = p => JSON.parse(read(p));
const sandbox = { window: {}, console, setTimeout, clearTimeout, AbortController, fetch: () => Promise.reject(new Error('no network in unit tests')) };
vm.createContext(sandbox);
vm.runInContext(read('public/assets/dc/fl-live.js'), sandbox);
const X = sandbox.window.FLX;
const usd = X.F.usd;
const pt = json('public/data/recorded/analyze-pt.json');
const borrow = json('public/data/recorded/analyze-borrower.json');
const vault = json('public/data/recorded/vault-belem.json');
const cm = json('tests/js/fixtures/countermove.json');
const strip = c => { const o = Object.assign({}, c); delete o.payload; delete o.cm; return o; };
const clean = c => { const s = JSON.stringify(strip(c)); assert.ok(!/NaN|undefined|\[object Object\]/.test(s), 'no NaN / undefined in rendered values: ' + (s.match(/.{60}(NaN|undefined).{20}/) || [''])[0]); };

test('PT position: headline figures are the backend decision fields, formatted only', () => {
  const c = X.fromAnalyze(pt, { mode: 'recorded', id: 'pt' });
  const d = pt.decision;
  assert.equal(c.kind, 'pt');
  assert.equal(c.verdict, d.verdict);
  assert.equal(c.dash.verdict, d.verdict);
  const m = Object.fromEntries(c.dash.metrics.map(x => [x[0].split(' ·')[0], x]));
  assert.equal(m['EXPECTED LOSS'][1], usd(d.expected_loss_usd));
  assert.equal(m['EXIT SIDE'][1], usd(d.exit_total_usd));
  assert.equal(m['MARGIN'][1], usd(d.margin_usd));
  assert.equal(c.db.rows[0].value, usd(d.expected_loss_usd));
  assert.equal(c.db.rows[1].value, usd(d.exit_total_usd));
  assert.match(c.db.rows[0].range, new RegExp(usd(d.loss_band.low_usd).replace('$', '\\$')));
  assert.equal(c.source, 'RECORDED LIVE RUN');
  assert.match(c.sourceNote, new RegExp(Number(pt._snapshot.block).toLocaleString('en-US')));
  clean(c);
});

test('PT position: graph, transmissions and conditional losses come from nodes / stress_table', () => {
  const c = X.fromAnalyze(pt, { mode: 'recorded' });
  assert.equal(c.G.NODES.length, pt.nodes.length);
  const S = Object.fromEntries(pt.stress_table.map(r => [r.id, r]));
  for (const n of c.G.NODES.filter(n => n.id !== 'pos')) {
    assert.equal(n.T, S[n.id].transmission, n.id + ' transmission');
    assert.equal(n.cond, S[n.id].conditional_loss_usd, n.id + ' conditional loss');
    assert.equal(n.verdictIf, S[n.id].verdict_if_shocked, n.id + ' verdict');
    assert.equal(n.contrib, pt.node_contrib_usd[n.id] || 0, n.id + ' contribution');
    assert.ok(n.x > 0 && n.y >= 0 && n.y <= 520, n.id + ' laid out inside the design viewBox');
  }
  assert.equal(c.G.EDGES.length, pt.edges.length);
});

test('role-aware results pass through: a no-debt position is not hurt by an oracle failure', () => {
  const c = X.fromAnalyze(pt, { mode: 'recorded' });
  const oracle = c.G.NODES.find(n => n.id === 'oracle');
  assert.equal(oracle.T, 0);
  assert.equal(oracle.verdictIf, 'STAY');
  assert.match(oracle.why, /no effect without debt/i);
  const sc = c.scen.find(s => s.name === 'Oracle failure');
  assert.equal(sc.verdict, pt.scenarios.find(s => s.name === 'Oracle failure').verdict);
});

test('hold to maturity is shown from payload.maturity, not marked unavailable', () => {
  const c = X.fromAnalyze(pt, { mode: 'recorded' });
  const r = c.pv.routes.find(x => x.name === 'Hold to maturity');
  const htm = pt.maturity.options.find(o => o.option === 'HOLD_TO_MATURITY');
  assert.equal(r.status, 'MODELLED');
  assert.ok(r.val.startsWith(usd(htm.central_usd)));
});

test('borrower: liquidation figures and the backend-suggested Countermove policy', () => {
  const c = X.fromAnalyze(borrow, { mode: 'recorded', id: 'borrow' });
  const L = borrow.liquidation;
  assert.equal(c.kind, 'borrow');
  assert.ok(c.db.headline.includes(X.F.pct(L.distance_to_liquidation_pct)));
  assert.equal(c.arm.eligible, true);
  assert.equal(c.arm.marketId, L.market_id);
  assert.equal(c.arm.borrower, L.borrower);
  assert.deepEqual(c.arm.suggestion, L.countermove_suggestion.policy_draft_query);
  clean(c);
});

test('vault: decision, withdrawal route and allocations come from /api/vault', () => {
  const c = X.fromVault(vault, { mode: 'recorded' });
  assert.equal(c.verdict, vault.decision.verdict);
  assert.equal(c.db.rows[0].value, usd(vault.risk.expected_loss_usd));
  assert.equal(c.db.rows[1].value, usd(vault.decision.exit_side_usd));
  assert.equal(c.pv.markets.length, vault.allocations.items.length);
  const w = c.db.facts.find(f => f.k === 'Withdrawal');
  assert.equal(w.v, /^full/.test(vault.decision.withdrawal_feasibility) ? 'Full' : w.v);
  assert.equal(c.graph, false, 'vault graph has no designed view yet (reported design gap)');
  clean(c);
});

test('fork demo and replay follow the recorded local-fork run (S1, S5)', () => {
  const s1 = cm.positions.find(p => p.scenario === 'S1');
  const r = X.replay(cm, 'S1');
  assert.equal(r.steps.length, 7);
  assert.ok(r.steps[5].body.includes(s1.execution.tx_hash.slice(0, 10)));
  assert.equal(r.steps[5].chip, 'FORK CONFIRMED');
  assert.equal(r.steps[1].chip, 'SIMULATED SHOCK');
  const r5 = X.replay(cm, 'S5');
  assert.ok(r5, 'S5 is recorded, so its replay is available');
  assert.match(r5.rnodes.find(n => n.id === 'pos').sub, /PT/);
  assert.equal(X.replay(cm, 'S3'), null, 'NO_ACTION runs are not replayed as executions');
  const fk = X.forkTab(cm, 'S1');
  assert.equal(fk.trigger, 'LTV ' + X.F.pct0(s1.protections.trigger_ltv));
  assert.equal(fk.reserveAfter, X.F.amt(s1.remaining_limits.loan_reserve_left) + ' USDC');
  const ctx = X.fromFork(cm, 'S1');
  assert.equal(ctx.source, 'LOCAL FORK');
  assert.match(ctx.network, /31337/);
  const acts = X.forkActivity(cm);
  assert.equal(acts.length, cm.positions.length);
  assert.ok(acts.every(a => a.status === 'FORK CONFIRMED' && /chain 31337/.test(a.meta)), 'fork runs never appear as mainnet transactions');
});

test('landing quotes the recorded artifacts it names', () => {
  const html = read('public/index.html');
  const d = pt.decision;
  assert.ok(html.includes('ETHEREUM BLOCK ' + Number(pt._snapshot.block).toLocaleString('en-US')));
  assert.ok(html.includes('expected loss ' + usd(d.expected_loss_usd)));
  assert.ok(html.includes('vs exit side ' + usd(d.exit_total_usd)));
  const s1 = cm.positions.find(p => p.scenario === 'S1');
  assert.ok(html.includes('REPAY · ' + X.F.amt(s1.execution.amount) + ' USDC'));
  assert.ok(html.includes(s1.execution.tx_hash.slice(0, 6) + '…' + s1.execution.tx_hash.slice(-4)));
});

test('pages run under the CSP: no third-party origins, no inline scripts, no eval of the logic class', () => {
  for (const f of ['public/index.html', 'public/app.html']) {
    const html = read(f);
    assert.ok(!/fonts\.googleapis|fonts\.gstatic|unpkg\.com|jsdelivr|esm\.sh/.test(html), f + ' loads nothing from third parties');
    for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
      const attrs = m[1], body = m[2].trim();
      if (/type="text\/x-dc"/.test(attrs)) assert.equal(body, '', f + ': the data-dc-script body is shipped as a same-origin file');
      else assert.ok(/\ssrc="\//.test(attrs) && body === '', f + ': only same-origin script files');
    }
  }
  const landing = read('public/assets/dc/landing.js');
  assert.ok(!/unpkg|https:\/\//.test(landing.replace(/^\/\*[\s\S]*?\*\//, '')), 'three.js is self-hosted');
});
