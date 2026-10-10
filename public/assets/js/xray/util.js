export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function usd(v, { sign = false, exact = false } = {}) {
  if (!Number.isFinite(v)) return '—';
  const s = v < 0 ? '−' : sign && v > 0 ? '+' : '';
  const a = Math.abs(v);
  if (exact) return `${s}$${Math.round(a).toLocaleString('en-US')}`;
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(a >= 1e10 ? 1 : 2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(a >= 1e7 ? 1 : 2)}M`;
  if (a >= 1e4) return `${s}$${(a / 1e3).toFixed(0)}k`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}k`;
  return `${s}$${a.toFixed(0)}`;
}

export function pct(v, digits) {
  if (!Number.isFinite(v)) return '—';
  const x = v * 100;
  const d = digits ?? (Math.abs(x) >= 10 || x === 0 ? 0 : Math.abs(x) >= 1 ? 1 : 2);
  return `${x.toFixed(d)}%`;
}

export const $ = (id) => document.getElementById(id);
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function countUp(el, to, fmt, ms = 650) {
  const from = Number.isFinite(+el.dataset.v) ? +el.dataset.v : 0;
  el.dataset.v = to;
  if (reducedMotion() || !Number.isFinite(to) || from === to) { el.textContent = fmt(to); return; }
  const t0 = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - t0) / ms);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (to - from) * e);
    if (k < 1 && el.dataset.v == to) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
