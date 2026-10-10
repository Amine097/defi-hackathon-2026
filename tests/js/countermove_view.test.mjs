// Phase 2 Autonomous Countermove UI logic, run against the real backend payload of the recorded fork run
// (tests/js/fixtures/countermove.json, kept in sync by tests/test_countermove_api.py). Run: node --test tests/js/countermove_view.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  statusView, executionIssues, timelineView, candidateRows, envText, fmtAmt, STATUS, fmtTok, fmtDuration, fmtDate,
  STRATEGY_LABEL, outcomeKey, labelParts, shortReason, whyHead, dependencyRows, heroView, gaugeLayout,
} from '../../public/assets/js/countermove/view.js';

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

test('amount, duration and date formatting for people', () => {
  assert.equal(fmtTok(1086.5, 'USDC', 'USDC'), '1,086.50 USDC');
  assert.equal(fmtTok(3913.4986, 'USDC', 'USDC'), '3,913.50 USDC');
  assert.equal(fmtTok(0.01672998, 'cbBTC', 'USDC'), '0.01673 cbBTC');
  assert.equal(fmtTok(1.23456789, 'weETH', 'USDC'), '1.2346 weETH');
  assert.equal(fmtDuration(3600), '1 h');
  assert.equal(fmtDuration(30 * 86400), '30 d');
  assert.equal(fmtDuration(1260), '21 min');
  assert.equal(fmtDuration(3.66), '3.7 s');
  assert.equal(fmtDate(0), '—');
  assert.match(fmtDate(1794254002), /^\d{1,2} \w{3} 2026, \d\d:\d\d UTC$/);
});

test('scenario labels and strategy names are human-readable', () => {
  const lp = labelParts(by.S1.label);
  assert.equal(lp.user, 'user A');
  assert.equal(lp.market, 'weETH/USDC');
  assert.equal(STRATEGY_LABEL[outcomeKey(by.S1)], 'Auto-repay');
  assert.equal(STRATEGY_LABEL[outcomeKey(by.S2)], 'Auto top-up');
  assert.equal(STRATEGY_LABEL[outcomeKey(by.S3)], 'No action');
  assert.equal(STRATEGY_LABEL[outcomeKey(by.S4)], 'Emergency full repay');
});

test('hero summarises crisis, decision and result from the payload', () => {
  for (const p of P.positions) {
    const h = heroView(p);
    assert.match(h.crisis, /crossed your \d+% trigger/);
    assert.ok(h.reaction_s > 0 && h.reaction_s < 60, `${p.scenario} reaction ${h.reaction_s}`);
    assert.equal(h.user_signed, false);
  }
  assert.match(heroView(by.S1).decision, /^Auto-repay [\d,]+\.\d\d USDC/);
  assert.equal(heroView(by.S1).tone, 'stay');
  assert.match(heroView(by.S4).result, /→ 0/);
  const h3 = heroView(by.S3);
  assert.equal(h3.tone, 'warn');
  assert.match(h3.result, /nothing sent/);
  assert.equal(h3.gauge.marks.length, 2);
});

test('gauge geometry keeps every marker on the bar and the zones ordered', () => {
  for (const p of P.positions) {
    const L = gaugeLayout(heroView(p).gauge);
    assert.ok(L.lo < L.hi && L.trigger < L.lltv);
    for (const m of L.marks) assert.ok(m.x >= 0 && m.x <= 100);
  }
  const s4 = gaugeLayout(heroView(by.S4).gauge);
  const after = s4.marks.find((m) => m.id === 'after');
  assert.equal(after.x, 0);
  assert.match(after.text, /debt repaid/);
});

test('rejection reasons are shortened, the full text is kept', () => {
  const rep = candidateRows(by.S2.decision).find((r) => r.strategy === 'REPAY');
  assert.equal(rep.verdict, 'not feasible');
  assert.doesNotMatch(shortReason(rep.reason), /pre-deposited/);
  assert.match(shortReason(rep.reason), /^reserve has .+, needs .+/);
  assert.equal(shortReason('TOP_UP is not among the strategies the owner authorized'), 'not allowed by your policy');
  const s3 = candidateRows(by.S3.decision);
  assert.ok(s3.every((r) => r.reasons.length >= 1));
  assert.doesNotMatch(whyHead('Chose REPAY. Rejected: TOP_UP (x)'), /Rejected/);
});

test('dependency list drops constant placeholder feeds and explains freshness', () => {
  const rows = dependencyRows(by.S1.before.dependencies);
  assert.ok(rows.length >= 1);
  assert.ok(rows.every((r) => !/dummy feed/i.test(r.name)));
  assert.ok(rows.some((r) => /no update time/.test(r.state)));
  assert.ok(rows.every((r) => /BASE_FEED|QUOTE_FEED/.test(r.tip)));
});