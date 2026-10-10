// Phase 1 Vault Risk Analyzer UI logic, run against real backend payloads for the three verdicts
// (tests/js/fixtures/vault_*.json, kept in sync with the backend by tests/test_vault.py::test_v19_ui_fixtures_in_sync).
// Run: node --test tests/js/vault_view.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildQuery, verdictView, modeBadge, errorText, shockOptions, layoutGraph, sharedDependencies, fmtUsd, esc,
} from '../../public/assets/js/vault/view.js';

const load = (k) => JSON.parse(readFileSync(new URL(`./fixtures/vault_${k}.json`, import.meta.url), 'utf8'));
const P = { stay: load('stay'), exit: load('exit'), review: load('review') };
const BELEM = '0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec';

for (const [k, cls, sign] of [['stay', 'stay', -1], ['exit', 'exit', 1], ['review', 'warn', 0]]) {
  test(`${k.toUpperCase()} payload: consistent, colour ${cls}, margin sign agrees`, () => {
    const d = P[k].decision;
    const v = verdictView(d);
    assert.equal(v.label, k.toUpperCase());
    assert.equal(v.cls, cls);
    assert.deepEqual(v.issues, []);
    assert.ok(v.consistent);
    if (sign) assert.equal(Math.sign(d.margin_usd), sign);
    if (k === 'review') {
      assert.match(v.lean, new RegExp(`lean ${d.point_verdict}`));
      assert.match(v.hint, d.margin_usd < 0 ? /exiting costs more/ : /staying costs more/);
    } else {
      assert.equal(v.lean, null);
    }
    assert.equal(v.marginText, (d.margin_usd > 0 ? '+' : '') + fmtUsd(d.margin_usd));
  });
}

test('contradictions are reported, never hidden', () => {
  const d = structuredClone(P.review.decision);
  assert.ok(!verdictView({ ...d, colour: 'green' }).consistent);
  assert.ok(!verdictView({ ...d, margin_usd: d.margin_usd + 50 }).consistent);
  assert.ok(!verdictView({ ...d, carry_usd: 0 }).consistent);
  assert.ok(!verdictView({ ...d, point_verdict: d.margin_usd < 0 ? 'EXIT' : 'STAY' }).consistent);
  assert.ok(!verdictView({ ...d, confidence: 'high' }).consistent);
  const e = structuredClone(P.exit.decision);
  assert.ok(!verdictView({ ...e, withdrawal_feasibility: 'partial' }).consistent);
  const s = structuredClone(P.stay.decision);
  assert.ok(!verdictView({ ...s, loss_band_usd: [0, s.exit_band_usd[0] + 1] }).consistent);
  assert.ok(!verdictView({}).consistent);
});

test('buildQuery: address, link, bad input', () => {
  assert.equal(buildQuery({ address: ` ${BELEM} `, value_usd: 100000, horizon_days: 30 }).query,
    `address=${BELEM}&chain_id=1&value_usd=100000&horizon_days=30`);
  const u = buildQuery({ address: `https://app.morpho.org/ethereum/vault/${BELEM}/x` });
  assert.match(u.query, /^url=https/);
  assert.ok(buildQuery({ address: '' }).error);
  assert.ok(buildQuery({ address: '0x123' }).error);
  assert.match(buildQuery({ address: BELEM, shock: 'oracle:0xab', severity: 0.4 }).query, /shock=oracle%3A0xab&severity=0.4/);
});

test('mode badges: live is green, replay amber, mock red', () => {
  assert.equal(modeBadge('live').cls, 'stay');
  assert.equal(modeBadge('offline').cls, 'warn');
  assert.equal(modeBadge('cache').cls, 'warn');
  assert.equal(modeBadge('mock').cls, 'exit');
  assert.equal(modeBadge(undefined).cls, 'exit');
  assert.equal(modeBadge(P.review.mode).label, 'live on-chain');
});

test('errors: structured backend message, network failure, no figures', () => {
  assert.equal(errorText(404, { error: { code: 'not_a_vault', message: 'no contract' } }), 'not_a_vault (404): no contract');
  assert.match(errorText(0, null), /unreachable/);
  assert.match(errorText(502, null), /No figures are shown/);
});

test('graph layout: every node placed, depositor at depth 0, all reachable', () => {
  const { nodes, edges } = P.review.dependencies;
  const { pos, unreachable } = layoutGraph(nodes, edges);
  assert.equal(pos.pos.depth, 0);
  for (const n of nodes) assert.ok(pos[n.id], n.id);
  assert.deepEqual(unreachable, []);
  for (const e of edges) assert.ok(pos[e.dst].depth <= pos[e.src].depth + 1);
});

test('shock options = backend dependency ids; shared dependencies counted once', () => {
  const nodes = P.review.dependencies.nodes;
  const opts = shockOptions(nodes);
  assert.equal(opts.length, nodes.filter((n) => n.id !== 'pos').length);
  assert.equal(new Set(opts.map((o) => o.id)).size, opts.length);
  const sh = sharedDependencies(nodes);
  for (const s of sh) assert.ok(s.count > 1);
  assert.ok(sh.some((s) => s.role === 'chain' || s.role === 'morpho_blue'));
});

test('esc neutralises HTML from on-chain strings', () => {
  assert.equal(esc('<img src=x onerror=alert(1)>"\''), '&lt;img src=x onerror=alert(1)&gt;&quot;&#39;');
});
