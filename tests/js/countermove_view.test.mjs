// Phase 2 Autonomous Countermove UI logic, run against the real backend payload of the recorded fork run
// (tests/js/fixtures/countermove.json, kept in sync by tests/test_countermove_api.py). Run: node --test tests/js/countermove_view.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { statusView, executionIssues, timelineView, candidateRows, envText, fmtAmt, STATUS } from '../../public/assets/js/countermove/view.js';

const P = JSON.parse(readFileSync(new URL('./fixtures/countermove.json', import.meta.url), 'utf8'));
const by = Object.fromEntries(P.positions.map((p) => [p.scenario, p]));

test('every recorded position renders with its proof-checked status', () => {
  assert.equal(statusView(by.S1).status, 'CONFIRMED');
  assert.equal(statusView(by.S2).status, 'CONFIRMED');
  assert.equal(statusView(by.S3).status, 'NO_ACTION');
  assert.equal(statusView(by.S4).status, 'CONFIRMED');
  for (const p of P.positions) {
    assert.deepEqual(statusView(p).issues, []);
    assert.deepEqual(executionIssues(p), []);
  }
});

test('a confirmation without proof is never displayed as CONFIRMED', () => {
  const noHash = structuredClone(by.S1); noHash.execution.tx_hash = null;
  assert.equal(statusView(noHash).status, 'FAILED');
  const unverified = structuredClone(by.S1); unverified.execution.verified = false;
  assert.equal(statusView(unverified).label, 'FAILED');
  const badCheck = structuredClone(by.S2); badCheck.execution.checks[0].ok = false;
  assert.equal(statusView(badCheck).status, 'FAILED');
  const noChecks = structuredClone(by.S4); noChecks.execution.checks = [];
  assert.equal(statusView(noChecks).status, 'FAILED');
});

test('identity checks flag a payload that contradicts the action', () => {
  const r = structuredClone(by.S1); r.execution.after.debt = r.execution.before.debt + 1;
  assert.ok(executionIssues(r).some((x) => /did not reduce the debt/.test(x)));
  const t = structuredClone(by.S2); t.execution.after.collateral = t.execution.before.collateral;
  assert.ok(executionIssues(t).some((x) => /did not add collateral/.test(x)));
  const u = structuredClone(by.S3); u.user_signed_during_crisis = true;
  assert.ok(executionIssues(u).some((x) => /user signed/.test(x)));
});

test('state machine timeline ends in the terminal state', () => {
  const tl = timelineView(by.S1.timeline);
  assert.deepEqual(tl.map((s) => s.state), ['WATCHING', 'DETECTED', 'PLANNING', 'VALIDATING', 'EXECUTING', 'CONFIRMED']);
  assert.ok(tl.every((s) => s.reached));
  const t3 = timelineView(by.S3.timeline);
  assert.equal(t3.at(-1).state, 'NO_ACTION');
  assert.equal(t3.find((s) => s.state === 'EXECUTING').reached, false);
});

test('comparison table: one chosen action, rejections carry their stage and reason', () => {
  const rows = candidateRows(by.S2.decision);
  assert.equal(rows.filter((r) => r.chosen).length, 1);
  assert.equal(rows.find((r) => r.chosen).strategy, 'TOP_UP');
  const rep = rows.find((r) => r.strategy === 'REPAY');
  assert.match(rep.stage, /rejected at feasibility/);
  assert.match(rep.reason, /reserve holds/);
  assert.equal(candidateRows(by.S3.decision).filter((r) => r.chosen).length, 0);
});

test('labels and environment banner', () => {
  assert.match(envText(P.environment), /fork block 26,164,248/);
  for (const k of ['LIVE', 'SIMULATED', 'CONFIRMED', 'FAILED', 'NO_ACTION']) assert.ok(STATUS[k] && STATUS[k].label);
  assert.equal(fmtAmt(1086.5, 'USDC', 2), '1,086.5 USDC');
  assert.equal(fmtAmt(null, 'USDC'), '—');
});
