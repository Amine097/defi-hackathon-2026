// Formatting only. No financial computation lives in the browser.
export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ok = (n) => n != null && n !== '' && Number.isFinite(Number(n));

/** Compact USD for headlines: $761, $5.2k, $270.5k, $1.00M. Negative values keep their sign. */
export function usd(n, { dash = '—' } = {}) {
  if (!ok(n)) return dash;
  n = Number(n);
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e5) return `${s}$${(a / 1e3).toFixed(0)}k`;
  if (a >= 1e4) return `${s}$${(a / 1e3).toFixed(1)}k`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}k`;
  if (a >= 1) return `${s}$${a.toFixed(0)}`;
  if (a === 0) return '$0';
  return `${s}$${a.toFixed(2)}`;
}
/** Full USD to the dollar ($5,178), or to the cent below $100. */
export function usdFull(n, { dash = '—' } = {}) {
  if (!ok(n)) return dash;
  n = Number(n);
  const a = Math.abs(n), s = n < 0 ? '−' : '';
  return s + '$' + a.toLocaleString('en-US', { minimumFractionDigits: a < 100 ? 2 : 0, maximumFractionDigits: a < 100 ? 2 : 0 });
}
export const pct = (n, d = 1, { dash = '—' } = {}) => (ok(n) ? `${(Number(n) * 100).toFixed(d)}%` : dash);
export const num = (n, d = 0, { dash = '—' } = {}) => (ok(n) ? Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) : dash);
export const mult = (n, d = 1) => (ok(n) ? `×${Number(n).toFixed(d)}` : '—');
export const short = (a, l = 6, r = 4) => (a && a.length > l + r + 2 ? `${a.slice(0, l)}…${a.slice(-r)}` : a || '');

export function ago(seconds) {
  if (!ok(seconds)) return '';
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
export function duration(seconds) {
  if (!ok(seconds)) return '—';
  const s = Number(seconds);
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 86400 * 2) return `${(s / 3600).toFixed(1)} h`;
  return `${Math.round(s / 86400)} days`;
}
export function dateTime(ts) {
  if (!ok(ts)) return '—';
  return new Date(Number(ts) * 1000).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' });
}
export const verdictClass = (v) => ({ EXIT: 'exit', STAY: 'stay', REVIEW: 'review', HOLD_TO_MATURITY: 'hold' }[v] || 'neutral');
export const verdictWord = (v) => ({ HOLD_TO_MATURITY: 'Hold to maturity', EXIT: 'Exit', STAY: 'Stay', REVIEW: 'Review' }[v] || v || '—');
export function tag(v, extra = '') {
  return `<span class="tag tag--${verdictClass(v)}${extra ? ' ' + extra : ''}">${esc(verdictWord(v))}</span>`;
}
