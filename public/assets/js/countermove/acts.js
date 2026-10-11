// Countermove lab (ARM, DEFEND, PROVE + live dry run). Pure helpers, no DOM, no financial computation: every amount,
// LTV, decision and check comes from the backend payload. This module only orders, labels and shortens it for people.
import {
  statusView, outcomeKey, labelParts, candidateRows, shortReason, fmtTok, fmtDuration, STRATEGY_LABEL,
} from './view.js';
import { pct, ago, duration } from '../core/format.js';

export const DEFAULT_SCENARIO = 'S5';

export const ACTS = [
  { id: 'arm', n: 1, name: 'Arm', gist: 'Policy, limits, reserves', q: 'What did the owner authorise before the crisis?' },
  { id: 'defend', n: 2, name: 'Defend', gist: 'Shock, timeline, choice', q: 'What happened and why this action?' },
  { id: 'prove', n: 3, name: 'Prove', gist: 'Receipt and checks', q: 'What is verified, and where?' },
];

export const OUTCOME_SHORT = { REPAY: 'Repay', TOP_UP: 'Top-up', FULL_REPAY: 'Full repay', NO_ACTION: 'No action' };
const STRATS = ['REPAY', 'TOP_UP', 'FULL_REPAY'];

// Status words for a recorded position. CONFIRMED is only ever shown after statusView's proof check and always with
// the environment ("on fork" / "on the local fork") next to it.
export function proofStatus(p) {
  const sv = statusView(p);
  if (sv.status === 'CONFIRMED') {
    return { key: 'confirmed', tone: 'ok', tag: 'stay', short: 'Confirmed on fork', long: 'Confirmed on the local fork',
      tip: 'Mined on the local Anvil fork and every verification check passed. Not an Ethereum mainnet transaction.', issues: [] };
  }
  if (sv.status === 'NO_ACTION' && sv.consistent) {
    return { key: 'no_action', tone: 'none', tag: 'review', short: 'Nothing sent', long: 'No action, nothing sent',
      tip: 'No authorised action could restore the margin: no transaction was sent, the reason is shown.', issues: [] };
  }
  return { key: 'failed', tone: 'fail', tag: 'exit', short: 'Failed on fork', long: 'Failed or unverified on the local fork',
    tip: 'Reverted, unverified or inconsistent: do not rely on this result.', issues: sv.issues };
}

export function scenarioItems(positions) {
  return (positions || []).map((p) => {
    const key = outcomeKey(p);
    const lp = labelParts(p.label);
    return {
      scenario: p.scenario, key, outcome: STRATEGY_LABEL[key] || key, outcomeShort: OUTCOME_SHORT[key] || key,
      market: lp.market, user: lp.user, setup: lp.setup, status: proofStatus(p),
    };
  });
}

export function pickScenario(positions, want) {
  const list = positions || [];
  const i = list.findIndex((p) => p.scenario === want);
  if (i >= 0) return i;
  const d = list.findIndex((p) => p.scenario === DEFAULT_SCENARIO);
  return d >= 0 ? d : 0;
}

// "#S3-prove" -> { scenario: 'S3', act: 'prove' }
export function parseHash(h) {
  const m = /^#?(S\d+)(?:-(arm|defend|prove))?$/i.exec(String(h || ''));
  return m ? { scenario: m[1].toUpperCase(), act: m[2] ? m[2].toLowerCase() : null } : { scenario: null, act: null };
}

// The policy the owner set before the crisis (RescueVault state read at arming), in human units.
export function policyOf(p) {
  const b = (p && p.before) || {}, v = b.vault || {}, pol = v.policy || {}, pr = (p && p.protections) || null;
  const allowed = new Set(pol.strategies || (pr && pr.strategies) || []);
  return {
    loan: (b.loan || {}).symbol || '', coll: (b.collateral || {}).symbol || '',
    loanDecimals: (b.loan || {}).decimals, collDecimals: (b.collateral || {}).decimals,
    strategies: STRATS.map((s) => ({ key: s, label: STRATEGY_LABEL[s], allowed: allowed.has(s) })),
    allowed,
    trigger: pol.trigger_ltv_pct, floor: pol.min_ltv_after_pct, lltv: b.lltv,
    repayPer: pol.max_repay_per_action_h, repayTotal: pol.max_repay_total_h, fullRepay: pol.max_full_repay_h,
    topUpPer: pol.max_top_up_per_action_h, topUpTotal: pol.max_top_up_total_h,
    loanReserve: v.loan_reserve, collReserve: v.collateral_reserve,
    loanFloor: pol.min_loan_reserve_h, collFloor: pol.min_collateral_reserve_h,
    cooldown: pol.cooldown, validUntil: pol.valid_until,
    state: v.revoked ? 'revoked' : v.paused ? 'paused' : 'armed', block: b.block, armedAt: b.timestamp, vault: v.address,
  };
}

// What the RescueVault can and cannot do (contracts/src/RescueVault.sol: no other code path exists). The limits
// themselves are listed in the policy, so these lines stay short.
export function vaultPowers(pol) {
  const trig = pctTidy(pol.trigger);
  const can = [];
  if (pol.allowed.has('REPAY')) can.push(`Repay part of this borrower's ${pol.loan} debt, within the repay limits`);
  if (pol.allowed.has('TOP_UP')) can.push(`Add ${pol.coll} collateral to this borrower's position, within the top-up limits`);
  if (pol.allowed.has('FULL_REPAY') && Number(pol.fullRepay) > 0) can.push(`Repay the whole debt, up to ${fmtTok(pol.fullRepay, pol.loan, pol.loan)}`);
  can.push(`Act only while the on-chain LTV is at or above ${trig}, at most once per ${fmtDuration(pol.cooldown)}`);
  const cannot = [
    'Borrow, or withdraw collateral',
    'Send funds anywhere other than this borrower\'s Morpho position',
    `Act below the ${trig} trigger, even when a stress scenario predicts a breach`,
    'Dip under the reserve it must always keep',
    'Change its policy: only the owner can, and can pause or revoke it',
  ];
  for (const s of pol.strategies) if (!s.allowed) cannot.push(`${s.label}: not allowed by this policy`);
  if (pol.allowed.has('FULL_REPAY') && !(Number(pol.fullRepay) > 0)) cannot.push(`${STRATEGY_LABEL.FULL_REPAY}: cap set to 0`);
  return { can, cannot };
}

// Labels under the LTV bar: one lane per mark in story order (before, crisis, after). Each label starts (or, past 60%
// of the bar, ends) on its pin so its shape sits exactly under the mark and the text never leaves the bar.
export function markLabels(layout) {
  if (!layout) return [];
  return layout.marks.map((m, i) => ({ ...m, lane: i, anchor: m.x < 60 ? 'start' : 'end' }));
}

// Whole percentages print without decimals (88%), others keep one (91.5%).
export const pctTidy = (x) => {
  const v = Number(x) * 100;
  return Number.isFinite(v) && Math.abs(v - Math.round(v)) < 1e-6 ? pct(x, 0) : pct(x, 1);
};

// Trigger and liquidation ticks above the bar: the trigger label grows left, the liquidation label right; a second
// lane is used when either has no room on its side.
export function tickLabels(layout, trigger, lltv, { triggerLabel = 'Trigger', lltvLabel = 'Liquidation' } = {}) {
  if (!layout) return [];
  const t = { id: 'trigger', x: layout.trigger, text: `${triggerLabel} ${pctTidy(trigger)}`, lane: 0, anchor: layout.trigger < 30 ? 'start' : 'end' };
  const l = { id: 'lltv', x: layout.lltv, text: `${lltvLabel} ${pctTidy(lltv)}`, lane: 0, anchor: layout.lltv > 72 ? 'end' : 'start' };
  if (t.anchor === 'start' || l.anchor === 'end') l.lane = 1;
  return [t, l];
}

const TERMINAL = new Set(['CONFIRMED', 'FAILED', 'NO_ACTION']);
export const STATE_WORD = {
  WATCHING: 'Watching', DETECTED: 'Detected', PLANNING: 'Planning', VALIDATING: 'Validating', EXECUTING: 'Executing',
  CONFIRMED: 'Confirmed on fork', FAILED: 'Failed', NO_ACTION: 'No action',
};
const STATE_HINT = {
  WATCHING: 'Position read at every block', DETECTED: 'Risk seen at this block', PLANNING: 'Engine ranked the allowed actions',
  VALIDATING: 'Pre-send checks: eth_call simulation, gas and fee caps', EXECUTING: 'Keeper sent the vault call',
  CONFIRMED: 'Mined on the local fork', FAILED: 'Reverted or unverified', NO_ACTION: 'No transaction sent',
};
const STATE_TONE = { CONFIRMED: 'ok', FAILED: 'fail', NO_ACTION: 'none', EXECUTING: 'act', VALIDATING: 'act', DETECTED: 'alert' };

// First clause of a keeper note, without the parenthesised detail; the full note stays available.
export function noteHead(note) {
  if (!note) return '';
  let s = String(note).replace(/\s*\([^)]*\)/g, '');
  const alertOnly = /:\s*ALERT only\s*$/i.test(s);
  s = s.replace(/:\s*ALERT only\s*$/i, '').split(/;\s|:\s/)[0].trim();
  s = s.charAt(0).toUpperCase() + s.slice(1);
  return alertOnly ? `${s}. Alert only` : s;
}

// Every keeper state in order, with time since the first state. A new check after a terminal state starts a new cycle.
export function timelineSteps(timeline) {
  const list = timeline || [];
  const t0 = list.length ? Number(list[0].ts) : 0;
  let cycle = 0, prevTerminal = false, prevTs = t0;
  return list.map((t, i) => {
    if (prevTerminal) cycle += 1;
    const head = noteHead(t.note);
    const row = {
      i, state: t.state, word: STATE_WORD[t.state] || t.state, tone: STATE_TONE[t.state] || 'neutral',
      rel: Number.isFinite(Number(t.ts)) ? Number(t.ts) - t0 : null,
      dt: Number.isFinite(Number(t.ts)) ? Number(t.ts) - prevTs : null,
      block: t.block, tx: t.tx_hash, head: head || STATE_HINT[t.state] || '', note: t.note || '',
      hasMore: Boolean(t.note) && head !== String(t.note), cycle, newCycle: prevTerminal, terminal: TERMINAL.has(t.state),
    };
    prevTerminal = row.terminal;
    if (Number.isFinite(Number(t.ts))) prevTs = Number(t.ts);
    return row;
  });
}

export const relTime = (s) => (s == null ? '' : `+${Number(s).toFixed(s < 10 ? 2 : 1)} s`);

// One plain-words verdict per candidate action: chosen, also eligible, or why it was rejected.
export function candidateVerdicts(decision) {
  const minCap = decision && decision.ranking === 'min_capital';
  const rows0 = candidateRows(decision);
  const sole = rows0.filter((r) => r.status === 'eligible').length === 1;
  return rows0.map((r) => {
    let tone, text, detail = '';
    if (r.chosen) {
      tone = 'ok'; text = 'Chosen';
      detail = sole ? 'the only action that meets every constraint'
        : minCap ? 'meets every constraint and commits the least reserve value' : 'meets every constraint, first in the preference order';
    } else if (r.status === 'eligible') {
      tone = 'none'; text = `Also possible, ranked ${r.rank}`;
      detail = minCap ? 'meets every constraint but commits more reserve value' : 'meets every constraint, later in the preference order';
    } else {
      tone = 'fail'; text = r.verdict.charAt(0).toUpperCase() + r.verdict.slice(1);
      detail = shortReason(r.reason).replace(/your policy/g, 'the owner\'s policy');
    }
    const more = r.reasons.length > 1 && !r.chosen ? r.reasons.length - 1 : 0;
    return { ...r, label: STRATEGY_LABEL[r.strategy] || r.strategy, tone, text, detail, more };
  });
}

// Oracle feeds a person should read (constant placeholder feeds are dropped), with freshness in words.
export function feedRows(deps) {
  return ((deps && deps.feeds) || [])
    .filter((f) => !/^dummy feed/i.test(f.original_description || f.description || ''))
    .map((f) => {
      let tone = 'none', state;
      if (f.freshness === 'fresh') { tone = 'ok'; state = f.age_s != null ? `Fresh, updated ${ago(f.age_s)}` : 'Fresh'; }
      else if (f.freshness === 'stale') { tone = 'fail'; state = f.age_s != null ? `Stale, last update ${ago(f.age_s)}` : 'Stale'; }
      else if (f.freshness === 'no_timestamp') state = 'Exchange rate, no update time to check';
      else state = f.freshness ? String(f.freshness) : 'Freshness unknown';
      return {
        name: f.original_description || f.description || f.role, role: f.role, side: f.side, address: f.address,
        value: f.value, tone, state, limit: f.max_age_s ? `limit ${duration(f.max_age_s)}` : '', simulated: Boolean(f.simulated),
      };
    });
}

export const DECISION_WORD = {
  HOLD: { text: 'Hold', detail: 'no action needed now', tone: 'ok' },
  EXECUTE: { text: 'Would act', detail: 'the engine found an authorised action', tone: 'act' },
  NO_ACTION: { text: 'No action possible', detail: 'no authorised action restores the margin', tone: 'fail' },
};
export const WATCH_WORD = { WATCHING: 'Watching', DETECTED: 'Detected', PLANNING: 'Planning', NO_ACTION: 'No action', EXECUTING: 'Executing' };

// The live dry run (faultline.countermove.dryrun/1) in the order a person reads it.
export function dryRunView(d) {
  const env = d.environment || {}, m = d.market || {}, b = d.borrower || {}, pos = d.position || {};
  const hyp = d.hypothetical || {}, hp = hyp.policy || {}, w = d.watcher || {}, dec = d.decision || {};
  const loan = pos.debt_symbol || (m.loan || {}).symbol || '', coll = pos.collateral_symbol || (m.collateral || {}).symbol || '';
  const chosen = dec.decision === 'EXECUTE' ? candidateRows(dec).find((r) => r.chosen) : null;
  const dw = DECISION_WORD[dec.decision] || { text: dec.decision || '—', detail: '', tone: 'none' };
  return {
    block: env.block, network: env.network, chainId: env.chain_id, rpcHost: env.rpc_host, blockTs: env.block_timestamp,
    readOnly: env.read_only === true && env.signed === false && env.broadcast === false,
    market: m.name, marketId: m.id, lltv: pos.lltv != null ? pos.lltv : m.lltv, loan, coll,
    borrower: { address: b.address || pos.borrower, rank: b.rank, source: b.source, how: b.how },
    position: {
      hasDebt: pos.has_debt !== false, ltv: pos.ltv, debt: pos.debt, collateral: pos.collateral, collateralValue: pos.collateral_value,
      healthFactor: pos.health_factor, dropToLiquidation: pos.drop_to_liquidation, healthy: pos.healthy,
    },
    trigger: (w.trigger || {}).trigger_ltv != null ? w.trigger.trigger_ltv : hp.trigger_ltv,
    triggerMet: (w.trigger || {}).trigger_met === true,
    watcher: { state: w.state, word: WATCH_WORD[w.state] || w.state, outcome: w.outcome, head: noteHead(w.reason), reason: w.reason || '', path: w.path || [] },
    decision: {
      key: dec.decision, text: dw.text, tone: dw.tone, alert: Boolean(dec.alert),
      detail: chosen ? `${STRATEGY_LABEL[chosen.strategy] || chosen.strategy} ${fmtTok(chosen.required, chosen.token, loan)}, nothing sent` : dw.detail,
      head: noteHead(dec.why), why: dec.why || '',
    },
    reserves: (d.reserve_requirements || []).map((r) => {
      const kw = r.keeper_would || {};
      const would = kw.decision === 'EXECUTE' && kw.strategy
        ? `${STRATEGY_LABEL[kw.strategy] || kw.strategy} ${fmtTok(kw.amount, kw.token, loan)}`
        : (DECISION_WORD[kw.decision] || {}).text || kw.decision || '—';
      return { ...r, would, wouldTone: kw.decision === 'EXECUTE' ? 'act' : kw.decision === 'NO_ACTION' ? 'fail' : 'ok' };
    }),
    policy: hp, reservesHyp: hyp.reserves || {}, defaultsUsed: hyp.defaults_used || [], defaultRules: hyp.default_rules || {},
    notDone: d.not_done || [], elapsed: d.elapsed_s,
  };
}

export const RANKS = [1, 2, 3, 4, 5];
export const rankLabel = (r) => (r === 1 ? 'Largest borrower' : `${r}${({ 2: 'nd', 3: 'rd' })[r] || 'th'} largest borrower`);

// Policy preview query: the form takes percentages, the API (and the contract) take fractions. No other change.
export function draftParams(fields) {
  const f = { ...fields };
  for (const k of ['trigger_ltv', 'min_ltv_after', 'lltv']) {
    if (f[k] !== '' && f[k] != null && Number.isFinite(Number(f[k]))) f[k] = String(+(Number(f[k]) / 100).toFixed(6));
  }
  return { action: 'policy-draft', ...f };
}

// Value for a percentage input (0.88 -> "88"), without floating-point noise.
export const pctInput = (x) => (x == null || !Number.isFinite(Number(x)) ? '' : String(+(Number(x) * 100).toFixed(2)));
