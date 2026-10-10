// Frontend coherence: the margin, colour and hint shown next to a verdict follow the backend decision basis
// (central loss vs execution + carry). Run: node --test tests/js/decision_view.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decisionView, exitCostOf } from '../../public/assets/js/xray/model.js';

test('REVIEW / lean STAY with carry: negative margin, amber, never "stay costs more" (prod +$371 bug)', () => {
  // live values reported on production (block 26162693)
  const v = decisionView({ verdict: 'REVIEW', point_verdict: 'STAY', expected_loss_usd: 1657, exit_cost_usd: 1286, carry_usd: 3680, exit_total_usd: 4966 });
  assert.equal(v.exit, 4966);
  assert.ok(v.margin < 0);
  assert.equal(Math.round(v.margin), -3309);
  assert.equal(v.cls, 'warn');
  assert.match(v.hint, /lean STAY/);
  assert.doesNotMatch(v.hint, /stay costs more/);
  assert.ok(v.consistent);
});

test('REVIEW without exit_total_usd still adds carry (older payloads)', () => {
  const v = decisionView({ verdict: 'REVIEW', point_verdict: 'STAY', expected_loss_usd: 1657, exit_cost_usd: 1286, carry_usd: 3680 });
  assert.equal(v.exit, 4966);
  assert.ok(v.margin < 0 && v.consistent);
});

test('firm EXIT: positive margin, red', () => {
  const v = decisionView({ verdict: 'EXIT', point_verdict: 'EXIT', expected_loss_usd: 243000, exit_cost_usd: 1000, carry_usd: 2466, exit_total_usd: 3466 });
  assert.ok(v.margin > 0);
  assert.equal(v.cls, 'bad');
  assert.equal(v.hint, 'stay costs more');
  assert.ok(v.consistent);
});

test('firm STAY: negative margin, green', () => {
  const v = decisionView({ verdict: 'STAY', point_verdict: 'STAY', expected_loss_usd: 8100, exit_cost_usd: 50000, carry_usd: 2466, exit_total_usd: 52466 });
  assert.ok(v.margin < 0);
  assert.equal(v.cls, 'good');
  assert.equal(v.hint, 'exit costs more');
  assert.ok(v.consistent);
});

test('REVIEW / lean EXIT: positive margin, amber with lean EXIT', () => {
  const v = decisionView({ verdict: 'REVIEW', point_verdict: 'EXIT', expected_loss_usd: 243000, exit_cost_usd: 60000, carry_usd: 2466, exit_total_usd: 62466 });
  assert.ok(v.margin > 0);
  assert.equal(v.cls, 'warn');
  assert.match(v.hint, /lean EXIT/);
  assert.ok(v.consistent);
});

test('inconsistent input is detected (margin sign vs point verdict)', () => {
  const v = decisionView({ verdict: 'REVIEW', point_verdict: 'STAY', expected_loss_usd: 1657, exit_cost_usd: 1286 });
  assert.equal(v.consistent, false); // execution-only basis would contradict lean STAY
});

test('exitCostOf: main position uses exit_total_usd; what-if override keeps carry', () => {
  const pos = { id: 'pos', value: 1_000_000, exitCostMeta: null };
  const m = { position: { id: 'pos' }, decision: { exit_cost_usd: 1286, exit_total_usd: 4966 }, exitRate: 0.001286, carryRate: 0.00368 };
  assert.equal(exitCostOf(m, pos, null), 4966);
  assert.equal(Math.round(exitCostOf(m, pos, 0.01)), 10000 + 3680);
  const other = { id: 'p2', value: 500_000, exitCostMeta: null };
  assert.equal(Math.round(exitCostOf(m, other, null)), 643 + 1840);
  const noCarry = { ...m, carryRate: 0, decision: { exit_cost_usd: 1286 } };
  assert.equal(exitCostOf(noCarry, pos, null), 1286);
});
