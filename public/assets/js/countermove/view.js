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

export const fmtAmt = (n, sym, d = 4) => (n == null || !Number.isFinite(Number(n)) ? '—'
  : `${Number(n).toLocaleString('en-US', { maximumFractionDigits: d })}${sym ? ' ' + sym : ''}`);

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
    reason: (c.reasons || [])[0] || '', capital: c.capital_committed, ltvAfter: c.ltv_after, worstBuffer: c.worst_buffer_after,
    exposure: c.exposure_added_value, principal: c.principal_repaid, cls: c.status === 'eligible' ? 'stay' : 'exit',
  }));
}

export function envText(env) {
  if (!env) return 'environment unknown';
  return `${env.kind} · fork block ${Number(env.fork_block).toLocaleString('en-US')} · chain id ${env.chain_id}`;
}
