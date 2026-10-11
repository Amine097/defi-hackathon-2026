// Honest long-wait indicator: elapsed time, typical duration, the real pipeline steps (not ticked off: the
// backend does not stream progress), a seismograph trace, and Cancel. No fabricated percentages.
import { esc } from './format.js';

export function mountWork(el, { title, typical = [20, 35], steps = [], onCancel } = {}) {
  const t0 = performance.now();
  el.hidden = false;
  el.innerHTML = `<div class="work" role="status" aria-live="polite">
      <div class="work__head"><span class="work__title">${esc(title)}</span>
        <span class="work__clock"><b class="num" data-k="el">0 s</b> elapsed, usually ${typical[0]}–${typical[1]} s</span>
        ${onCancel ? '<button class="btn btn--quiet btn--sm" type="button" data-k="cancel">Cancel</button>' : ''}</div>
      <canvas class="work__trace" aria-hidden="true"></canvas>
      ${steps.length ? `<ol class="work__steps" aria-label="What the backend does">${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` : ''}
      <p class="note" data-k="slow" hidden>Taking longer than usual: public RPC endpoints can be slow. Keep waiting, or cancel and retry.</p>
    </div>`;
  const box = el.firstElementChild;
  const elT = box.querySelector('[data-k="el"]');
  const slow = box.querySelector('[data-k="slow"]');
  const cv = box.querySelector('canvas');
  if (onCancel) box.querySelector('[data-k="cancel"]').addEventListener('click', onCancel);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ctx = cv.getContext('2d');
  let raf = 0, alive = true, lastSec = -1;
  function frame(t) {
    if (!alive) return;
    const s = (t - t0) / 1000;
    const sec = Math.floor(s);
    if (sec !== lastSec) {
      lastSec = sec;
      elT.textContent = `${sec} s`;
      if (sec > typical[1] + 5) { slow.hidden = false; box.classList.add('is-slow'); }
    }
    const w = cv.clientWidth, h = cv.clientHeight, dpr = Math.min(devicePixelRatio || 1, 2);
    if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(236,233,226,.55)';
    ctx.beginPath();
    for (let x = 0; x <= w; x += 2) {
      const ph = x / w * 18 - s * 3.2;
      const burst = Math.exp(-Math.pow(((x / w) - ((s * 0.11) % 1.2)) * 9, 2));
      const y = h / 2 + Math.sin(ph) * 1.4 + Math.sin(ph * 3.7) * burst * h * 0.32;
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
    if (!reduce) raf = requestAnimationFrame(frame);
    else setTimeout(() => frame(performance.now()), 1000);
  }
  raf = requestAnimationFrame(frame);
  return { stop() { alive = false; cancelAnimationFrame(raf); el.hidden = true; el.innerHTML = ''; }, elapsed: () => (performance.now() - t0) / 1000 };
}

export const ANALYZE_STEPS = [
  'Pendle market and its SY / underlying',
  'Morpho market, LLTV and liquidity',
  'Every oracle feed, read on-chain',
  'Token look-through to base assets',
  'Failure priors from DefiLlama history',
  'Executable exit quote, re-run with eth_call',
  'Ten-pocket book quotes',
];
export const VAULT_STEPS = [
  'Vault version and factory check',
  'Allocations at one pinned block',
  'Markets, collateral and oracles',
  'Borrowers and bad-debt band',
  'Withdrawal routes simulated by multicall',
];
