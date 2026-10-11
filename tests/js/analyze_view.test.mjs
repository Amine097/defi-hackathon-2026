// Regression tests for /analyze.html: every figure the view-model exposes is a payload field, and the old
// client-side loss propagation (which showed $154k / EXIT for an oracle failure on a no-debt position) is gone.
// Fixtures: real /api/analyze responses recorded on 11 Oct 2026 (collateral-only and borrower=auto).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { headline, bandLayout, indexPayload, nodeImpact, bookRows, maturityView, sensitivityView, bandOf, strataLayout } from '../../public/assets/js/analyze/view.js';
import * as legacy from '../../public/assets/js/xray/model.js';

const live = JSON.parse(readFileSync(new URL('./fixtures/analyze_live.json', import.meta.url), 'utf8'));
const borrower = JSON.parse(readFileSync(new URL('./fixtures/analyze_borrower.json', import.meta.url), 'utf8'));

test('headline numbers are the decision fields, unchanged', () => {
  const h = headline(live);
  const d = live.decision;
  assert.equal(h.verdict, d.verdict);
  assert.equal(h.stay.central, d.expected_loss_usd);
  assert.equal(h.stay.low, d.loss_band.low_usd);
  assert.equal(h.stay.high, d.loss_band.high_usd);
  assert.equal(h.exit.total, d.exit_total_usd);
  assert.equal(h.exit.execution, d.exit_cost_usd);
  assert.equal(h.exit.carry, d.carry_usd);
  assert.equal(h.breakeven, d.breakeven_risk_multiplier);
  assert.equal(h.lean, d.verdict === 'REVIEW' ? d.point_verdict : null);
  assert.equal(h.firm, d.verdict !== 'REVIEW');
});

test('band chart shows an overlap exactly when the verdict is REVIEW for overlapping bands', () => {
  const L = bandLayout(headline(live));
  const d = live.decision;
  const overlap = d.loss_band.high_usd > d.exit_band.low_usd && d.exit_band.high_usd > d.loss_band.low_usd;
  assert.equal(!!L.overlap, overlap);
  if (d.verdict === 'REVIEW' && !(d.freshness.blockers || []).length) assert.ok(L.overlap);
});

test('REGRESSION: a failing oracle on a no-debt position shows the backend result (no effect), not a client estimate', () => {
  const idx = indexPayload(live);
  const oracle = idx.nodes.find((n) => n.meta.role === 'oracle');
  const imp = nodeImpact(oracle, live);
  const row = live.stress_table.find((r) => r.id === oracle.id);
  assert.equal(imp.kind, 'blocked');
  assert.deepEqual(imp.blockedBy, row.channel.blocked_by);
  assert.ok(imp.blockedBy.includes('debt'));
  assert.equal(imp.loss, row.conditional_loss_usd);
  // the backend's conditional loss for the oracle equals the baseline expected loss: the oracle adds nothing
  assert.ok(Math.abs(row.conditional_loss_usd - live.decision.expected_loss_usd) < 1);
  assert.ok(imp.loss < 2000, 'must never show the old six-figure client estimate');
});

test('REGRESSION: AMM and Morpho market are blocked channels for collateral without debt', () => {
  const idx = indexPayload(live);
  for (const role of ['amm', 'lending', 'feed_provider']) {
    const n = idx.nodes.find((x) => x.meta.role === role);
    const imp = nodeImpact(n, live);
    assert.equal(imp.kind, 'blocked', role);
    assert.equal(imp.loss, live.stress_table.find((r) => r.id === n.id).conditional_loss_usd, role);
  }
});

test('reachable dependencies show the stress-table loss and verdict verbatim, with the server path', () => {
  const idx = indexPayload(live);
  const issuer = idx.nodes.find((n) => n.meta.role === 'issuer');
  const row = live.stress_table.find((r) => r.id === issuer.id);
  const imp = nodeImpact(issuer, live);
  assert.equal(imp.kind, 'reaches');
  assert.equal(imp.loss, row.conditional_loss_usd);
  assert.equal(imp.verdict, row.verdict_if_shocked);
  assert.equal(imp.exitSide, row.exit_total_usd);
  assert.deepEqual(imp.path, row.path);
});

test('the client-side loss engine is gone', () => {
  for (const fn of ['positionLosses', 'cascade', 'breakEven', 'concentration']) assert.equal(legacy[fn], undefined, fn);
  assert.equal(typeof legacy.decisionView, 'function');
});

test('edges keep their channel and the backend reach flag', () => {
  const idx = indexPayload(live);
  const debt = idx.edges.find((e) => e.channel === 'debt');
  const exit = idx.edges.find((e) => e.channel === 'exit');
  assert.ok(debt && exit);
  assert.equal(debt.reaches, false);
  assert.equal(exit.reaches, false);
  assert.ok(idx.edges.filter((e) => e.channel === 'principal').every((e) => e.reaches === true));
});

test('book rows: unaffected EXIT pockets are flagged as yield rebalances, numbers untouched', () => {
  const { rows, yieldRows } = bookRows(live.book);
  rows.forEach((r, i) => {
    const p = live.book.pockets[i];
    assert.equal(r.stay_loss_usd, p.stay_loss_usd);
    assert.equal(r.exit_total_usd, p.exit_total_usd);
    assert.equal(r.verdict, p.verdict);
    if (p.verdict === 'EXIT' && !p.affected) assert.equal(r.reason, 'yield');
    if (p.affected) assert.equal(r.reason, 'risk');
  });
  assert.equal(yieldRows, live.book.pockets.filter((p) => p.verdict === 'EXIT' && !p.affected).length);
});

test('hold to maturity mirrors the backend options and hides itself when not applicable', () => {
  const v = maturityView(live.maturity);
  assert.equal(v.applicable, live.maturity.status === 'ok');
  if (v.applicable) {
    assert.equal(v.best, live.maturity.best_over_window);
    assert.equal(v.hold.central_usd, live.maturity.options.find((o) => o.option === 'HOLD_TO_MATURITY').central_usd);
    assert.equal(v.exit.central_usd, live.maturity.options.find((o) => o.option === 'EXIT').central_usd);
  }
  const b = maturityView(borrower.maturity);
  assert.equal(b.applicable, false);
  assert.equal(b.reason, borrower.maturity.reason);
});

test('sensitivity rows are the backend rows', () => {
  const s = sensitivityView(live.sensitivity);
  const n = live.sensitivity.rows.length + live.sensitivity.lgf_rows.length + live.sensitivity.transmission_rows.length;
  assert.equal(s.rows.length, n);
  assert.equal(s.breakeven, live.sensitivity.breakeven_risk_multiplier);
});

test('every node lands in one of the five Belem layers (or the position) and the layout places all of them', () => {
  const idx = indexPayload(live);
  const keys = new Set(idx.nodes.map((n) => bandOf(n)));
  for (const k of keys) assert.ok(['position', 'lending', 'amm', 'oracle', 'yield', 'chain'].includes(k));
  const lay = strataLayout(idx, { width: 900 });
  assert.equal(lay.pos.size, idx.nodes.length);
});

test('borrower payload: liquidation section is a real borrower, distinct from the hypothetical headline', () => {
  const L = borrower.liquidation;
  assert.equal(L.mode, 'borrower_position');
  assert.ok(L.collateral_value_usd_oracle > borrower.position.value_usd, 'real borrower is larger than the hypothetical exposure');
  assert.ok(Array.isArray(L.price_grid) && L.price_grid.some((g) => g.liquidated));
  assert.ok(L.countermove_suggestion && L.countermove_suggestion.policy_draft_query);
});
