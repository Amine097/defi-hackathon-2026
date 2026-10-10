// Autonomous Countermove view model (Phase 2). Pure functions, no DOM, no financial computation: every amount, LTV,
// buffer and decision comes from the backend payload (faultline.countermove/1). This module only formats it and REFUSES
// to display a confirmation that is not backed by a transaction hash AND a passed on-chain verification.
import { fmtUsd, fmtPct, fmtNum, esc, short } from '../vault/view.js';

export { fmtUsd, fmtPct, fmtNum, esc, short };

export const STATUS = {
  LIVE: { label: 'LIVE', cls: 'live', tip: 'Read now from Ethereum mainnet (read-only)' },
  SIMULATED: { label: 'SIMULATED', cls: 'sim', tip: 'Local Anvil fork of mainnet at a pinned block, test funds, controlled shock' },
  CONFIRMED: { label: 'CONFIRMED', cls: 'stay', tip: 'Mined on the local fork and every verification check passed' },
  FAILED: { label: 'FAILED', cls: 'exit', tip: 'Reverted, unverified or did not execute' },
  NO_ACTION: { label: 'NO ACTION', cls: 'warn', tip: 'No transaction was sent; the reason is shown' },
  WATCHING: { label: 'WATCHING', cls: 'muted', tip: 'Monitoring' },
  EXECUTING: { label: 'EXECUTING', cls: 'warn', tip: 'Transaction signed and sent, awaiting proof' },
};

export const STATES = ['WATCHING', 'DETECTED', 'PLANNING', 'VALIDATING', 'EXECUTING'];

export const fmtAmt = (n, sym, d = 4, minD = 0) => (n == null || !Number.isFinite(Number(n)) ? '—'
  : `${Number(n).toLocaleString('en-US', { minimumFractionDigits: Math.min(minD, d), maximumFractionDigits: d })}${sym ? ' ' + sym : ''}`);

// Amounts in the loan token (a stablecoin here) always show cents; other tokens keep enough precision for small sizes.
export function fmtTok(n, sym, loanSym) {
  if (sym && sym === loanSym) return fmtAmt(n, sym, 2, 2);
  return fmtAmt(n, sym, Math.abs(Number(n)) < 1 ? 6 : 4);
}

export function fmtDuration(s) {
  const n = Number(s);
  if (!Number.isFinite(n)) return '—';
  if (n >= 86400 && n % 86400 === 0) return `${n / 86400} d`;
  if (n >= 3600 && n % 3600 === 0) return `${n / 3600} h`;
  if (n >= 60 && n % 60 === 0) return `${n / 60} min`;
  return `${fmtNum(n, n < 10 ? 1 : 0)} s`;
}

export function fmtDate(ts) {
  if (!ts) return '—';
  const d = new Date(Number(ts) * 1000);
  return `${d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`;
}

export const STRATEGY_LABEL = {
  REPAY: 'Auto-repay', TOP_UP: 'Auto top-up', FULL_REPAY: 'Emergency full repay', NO_ACTION: 'No action',
};

// What the keeper ended up doing for this position (the executed strategy, or NO_ACTION).
export function outcomeKey(p) {
  if (p && p.execution && p.execution.strategy) return p.execution.strategy;
  if (p && (p.no_action || (p.decision && p.decision.decision === 'NO_ACTION'))) return 'NO_ACTION';
  return (p && p.decision && p.decision.decision) || '—';
}

// "S1 | user A | weETH/USDC | USDC reserve" -> parts (the backend label stays the source of truth).
export function labelParts(label) {
  const [scenario = '', user = '', market = '', ...setup] = String(label || '').split('|').map((x) => x.trim());
  return { scenario, user, market, setup: setup.join(' · ') };
}

const STAGE_LABEL = { security: 'not authorized', feasibility: 'not feasible', target: 'misses the target' };

// Backend reasons are exhaustive; the table shows a short form and keeps the full text as a tooltip.
export function shortReason(reason) {
  return String(reason || '')
    .replace(/\s*\(funds must be pre-deposited in the RescueVault\)/g, '')
    .replace(/^reserve holds (.+?) < required (.+)$/, 'reserve has $1, needs $2')
    .replace(/^(\w+) is not among the strategies the owner authorized$/, 'not allowed by your policy')
    .replace(/^needs (.+?) > per-action cap (.+)$/, 'needs $1, cap is $2')
    .replace(/^needs (.+?) > cumulative budget left (.+)$/, 'needs $1, budget left $2')
    .replace(/^full repay disabled by the owner \(cap 0\)$/, 'disabled in your policy');
}

// First sentence of the backend explanation (the rejected alternatives are shown in the comparison table).
export function whyHead(why) {
  return String(why || '').split(/\s+Rejected:\s+/)[0];
}

// Oracle inputs a person should read: constant placeholder feeds (e.g. a quote feed fixed at 1) are not dependencies.
export function dependencyRows(deps) {
  return ((deps && deps.feeds) || [])
    .filter((f) => !/^dummy feed/i.test(f.original_description || f.description || ''))
    .map((f) => {
      const name = f.original_description || f.description || f.role;
      let state = f.freshness, cls = 'muted';
      if (f.freshness === 'fresh') { state = f.age_s != null ? `fresh · updated ${fmtDuration(Math.max(60, Math.round(f.age_s / 60) * 60))} ago` : 'fresh'; cls = 'stay'; }
      else if (f.freshness === 'no_timestamp') state = 'exchange rate · no update time to check';
      else if (f.freshness === 'stale') { state = 'STALE'; cls = 'exit'; }
      return { name, state, cls, value: f.value, tip: `${f.role} (${f.side})${f.freshness_note ? ' · ' + f.freshness_note : ''}` };
    });
}

// The headline of a position: crisis -> decision -> result, with the LTV markers of the gauge.
export function heroView(p) {
  const b = p.before || {}, c = p.crisis || {}, e = p.execution, d = p.decision || {};
  const loan = (b.loan || {}).symbol || '';
  const key = outcomeKey(p);
  const mover = (c.movers || [])[0];
  const seen = (p.timeline || []);
  const t0 = (seen.find((t) => t.state === 'DETECTED') || {}).ts;
  const t1 = (seen.find((t) => ['CONFIRMED', 'FAILED', 'NO_ACTION'].includes(t.state)) || {}).ts;
  const crisis = `${mover ? `${String(mover.label).replace(/\s*\(SIMULATED SHOCK\)/, '')} ${fmtPct(mover.change, 1)}` : 'oracle price move'}`
    + ` → LTV ${fmtPct(c.ltv)} crossed your ${fmtPct(c.trigger_ltv, 0)} trigger`;
  let decision, result, tone;
  if (e) {
    decision = `${STRATEGY_LABEL[e.strategy] || e.strategy} ${fmtTok(e.amount, e.token, loan)}`
      + (e.strategy === 'FULL_REPAY' ? ' (whole debt)' : ' (smallest amount that restores the margin)');
    const after = e.after || {}, before = e.before || {};
    result = e.strategy === 'FULL_REPAY'
      ? `debt ${fmtTok(before.debt, loan, loan)} → 0 · collateral kept`
      : `LTV ${fmtPct(before.ltv)} → ${fmtPct(after.ltv)} · room before liquidation ${fmtTok(before.buffer, loan, loan)} → ${fmtTok(after.buffer, loan, loan)}`;
    tone = 'stay';
  } else {
    const best = candidateRows(d).filter((r) => r.reason)[0];
    decision = 'No authorized action can restore the margin';
    result = `nothing sent · reserves untouched${best ? ` · ${STRATEGY_LABEL[best.strategy] || best.strategy}: ${shortReason(best.reason)}` : ''}`;
    tone = 'warn';
  }
  const gauge = {
    trigger: c.trigger_ltv, lltv: b.lltv,
    marks: [{ id: 'before', label: 'before', ltv: b.ltv }, { id: 'crisis', label: 'crisis', ltv: c.ltv }]
      .concat(e ? [{ id: 'after', label: 'after', ltv: (e.after || {}).ltv }] : []),
  };
  return { key, title: STRATEGY_LABEL[key] || key, crisis, decision, result, tone, gauge,
    reaction_s: t0 && t1 ? t1 - t0 : null, user_signed: Boolean(p.user_signed_during_crisis) };
}

// Horizontal LTV scale for the gauge: positions in % of the bar width (display geometry only, no finance).
export function gaugeLayout(g) {
  const vals = [g.trigger, g.lltv, ...g.marks.map((m) => m.ltv)].map(Number).filter(Number.isFinite);
  if (!vals.length || !Number.isFinite(Number(g.lltv))) return null;
  const nonZero = g.marks.map((m) => Number(m.ltv)).filter((x) => Number.isFinite(x) && x > 0);
  const lo = Math.max(0, Math.floor((Math.min(...nonZero, Number(g.trigger)) - 0.05) * 20) / 20);
  const hi = Math.min(1, Math.ceil((Number(g.lltv) + 0.05) * 20) / 20);
  const pos = (x) => Math.max(0, Math.min(100, ((Number(x) - lo) / (hi - lo)) * 100));
  return {
    lo, hi, trigger: pos(g.trigger), lltv: pos(g.lltv),
    marks: g.marks.filter((m) => Number.isFinite(Number(m.ltv))).map((m) => ({
      ...m, x: pos(m.ltv), clamped: Number(m.ltv) < lo,
      text: Number(m.ltv) === 0 ? `${m.label}: 0% (debt repaid)` : `${m.label}: ${fmtPct(m.ltv)}`,
    })),
  };
}

// Proof-checked status: CONFIRMED only with a tx hash, verified = true and every check ok.
export function statusView(p) {
  const issues = [];
  let s = (p && p.status) || 'UNKNOWN';
  if (s === 'CONFIRMED') {
    const e = p.execution || {};
    if (!/^0x[0-9a-f]{64}$/i.test(e.tx_hash || '')) issues.push('no transaction hash');
    if (e.verified !== true) issues.push('verification not passed');
    if (!Array.isArray(e.checks) || !e.checks.length || e.checks.some((c) => !c.ok)) issues.push('a verification check failed or is missing');
    if (issues.length) s = 'FAILED';
  }
  if (s === 'NO_ACTION' && p.execution && p.execution.tx_hash) issues.push('NO ACTION but a transaction is attached');
  const st = STATUS[s] || { label: s, cls: 'warn', tip: '' };
  return { ...st, status: s, issues, consistent: issues.length === 0 };
}

// Identity checks on what the backend says happened (never recomputes the decision).
export function executionIssues(p) {
  const out = [];
  const e = p && p.execution;
  if (p && p.user_signed_during_crisis) out.push('the user signed during the crisis');
  if (!e) return out;
  const b = e.before || {}, a = e.after || {};
  if (e.strategy === 'REPAY' && !(a.debt < b.debt)) out.push('repay did not reduce the debt');
  if (e.strategy === 'REPAY' && a.collateral !== b.collateral) out.push('repay changed the collateral');
  if (e.strategy === 'TOP_UP' && !(a.collateral > b.collateral)) out.push('top-up did not add collateral');
  if (e.strategy === 'FULL_REPAY' && a.debt !== 0) out.push('full repay left debt');
  if (e.status === 'CONFIRMED' && !(a.ltv < b.ltv)) out.push('LTV did not improve');
  if (e.status === 'CONFIRMED' && !(a.buffer > b.buffer)) out.push('buffer did not increase');
  return out;
}

// The state machine as reached by this position; the last cell is the terminal state.
export function timelineView(timeline) {
  const seen = (timeline || []).map((t) => t.state);
  const steps = STATES.map((s) => ({ state: s, reached: seen.includes(s), cls: seen.includes(s) ? 'reached' : 'muted' }));
  const term = seen.find((x) => ['CONFIRMED', 'FAILED', 'NO_ACTION'].includes(x));
  steps.push({ state: term || '—', reached: Boolean(term), cls: term ? (STATUS[term] || {}).cls : 'muted', terminal: true });
  return steps;
}

export function candidateRows(decision) {
  return ((decision && decision.candidates) || []).map((c) => ({
    strategy: c.strategy, token: c.token, required: c.required, status: c.status, rank: c.rank,
    chosen: c.status === 'eligible' && c.rank === 1 && decision.decision === 'EXECUTE',
    stage: c.rejected_at ? `rejected at ${c.rejected_at}` : (c.status === 'eligible' ? 'meets every constraint' : c.status),
    verdict: c.rejected_at ? (STAGE_LABEL[c.rejected_at] || `rejected (${c.rejected_at})`) : (c.status === 'eligible' ? 'meets every constraint' : c.status),
    reason: (c.reasons || [])[0] || '', reasons: c.reasons || [], capital: c.capital_committed, ltvAfter: c.ltv_after, worstBuffer: c.worst_buffer_after,
    exposure: c.exposure_added_value, principal: c.principal_repaid, cls: c.status === 'eligible' ? 'stay' : 'exit',
  }));
}

export function envText(env) {
  if (!env) return 'environment unknown';
  return `${env.kind} · fork block ${Number(env.fork_block).toLocaleString('en-US')} · chain id ${env.chain_id}`;
}
