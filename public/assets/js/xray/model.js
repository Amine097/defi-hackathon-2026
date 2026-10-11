// Pure decision presentation helpers kept for tests/js/decision_view.test.mjs.
// The former client-side loss propagation (positionLosses / cascade / breakEven) was removed: it ignored the backend's
// role-aware channels and showed losses the model does not produce. All losses now come from the server.

/** Exit side of the STAY/EXIT comparison = execution cost + carry forgone (same basis as the backend verdict).
 *  exitOverride = what-if execution rate (fraction of value); carry is still added. */
export function exitCostOf(m, p, exitOverride) {
  const carry = p.value * (m.carryRate || 0);
  if (exitOverride != null) return p.value * exitOverride + carry;
  if (p.exitCostMeta != null) return p.exitCostMeta + carry;
  if (p.id === m.position.id && m.decision.exit_total_usd > 0) return m.decision.exit_total_usd;
  if (p.id === m.position.id && m.decision.exit_cost_usd > 0) return m.decision.exit_cost_usd + carry;
  return p.value * m.exitRate + carry;
}

/** Pure presentation of the headline signal, so numbers, colour and wording always agree with the verdict.
 *  margin = central loss - exit side (incl. carry); > 0 = staying costs more. REVIEW is never shown as a firm call. */
export function decisionView(d) {
  const verdict = d.verdict || '';
  const stay = +d.expected_loss_usd || 0;
  const exec = +d.exit_cost_usd || 0;
  const carry = d.carry_usd != null ? +d.carry_usd : 0;
  const exit = d.exit_total_usd != null ? +d.exit_total_usd : exec + carry;
  const margin = stay - exit;
  const point = d.point_verdict || (margin > 0 ? 'EXIT' : 'STAY');
  const side = margin > 0 ? 'stay costs more' : 'exit costs more';
  let cls, hint;
  if (verdict === 'REVIEW') {
    cls = 'warn';
    hint = `central values only · bands overlap or inputs not firm · lean ${point}`;
  } else {
    cls = verdict === 'EXIT' ? 'bad' : 'good';
    hint = side;
  }
  const consistent = point === (margin > 0 ? 'EXIT' : 'STAY') && (verdict === 'REVIEW' || verdict === point);
  return { verdict, point, stay, exec, carry, exit, margin, cls, hint, consistent };
}
