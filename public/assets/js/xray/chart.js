import { usd, pct, clamp } from './util.js';

/** Renders expected loss vs P(incident) against the flat exit cost. */
export function renderBreakEven(svg, be, p, pMax, label) {
  const Wd = 340, Ht = 170, L = 46, R = 12, T = 14, B = 28;
  const w = Wd - L - R, h = Ht - T - B;
  const elAt = (q) => be.base + q * be.L;
  const yMax = Math.max(be.exit, elAt(pMax), 1) * 1.15;
  const X = (q) => L + (q / pMax) * w;
  const Y = (v) => T + h - (v / yMax) * h;
  const ticksY = 4;
  let g = '';
  g += `<defs><linearGradient id="beStay" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#4ade80" stop-opacity=".16"/><stop offset="1" stop-color="#4ade80" stop-opacity="0"/></linearGradient>
  <linearGradient id="beExit" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#f87171" stop-opacity=".22"/><stop offset="1" stop-color="#f87171" stop-opacity="0"/></linearGradient></defs>`;
  for (let i = 0; i <= ticksY; i++) {
    const v = (yMax / ticksY) * i, y = Y(v);
    g += `<line x1="${L}" x2="${Wd - R}" y1="${y}" y2="${y}" class="be-grid"/><text x="${L - 6}" y="${y + 3}" class="be-ax" text-anchor="end">${usd(v)}</text>`;
  }
  for (let i = 0; i <= 5; i++) {
    const q = (pMax / 5) * i;
    g += `<text x="${X(q)}" y="${Ht - 10}" class="be-ax" text-anchor="middle">${pct(q, pMax < 0.2 ? 0 : 0)}</text>`;
  }
  const ps = be.pStar;
  if (Number.isFinite(ps) && ps > 0 && ps < pMax) {
    g += `<rect x="${L}" y="${T}" width="${X(ps) - L}" height="${h}" fill="url(#beStay)"/>`;
    g += `<rect x="${X(ps)}" y="${T}" width="${Wd - R - X(ps)}" height="${h}" fill="url(#beExit)"/>`;
    g += `<text x="${(L + X(ps)) / 2}" y="${T + 13}" class="be-zone stay" text-anchor="middle">STAY</text>`;
    g += `<text x="${(X(ps) + Wd - R) / 2}" y="${T + 13}" class="be-zone exit" text-anchor="middle">EXIT</text>`;
  } else {
    const exitAll = Number.isFinite(ps) && ps <= 0;
    g += `<rect x="${L}" y="${T}" width="${w}" height="${h}" fill="url(#${exitAll ? 'beExit' : 'beStay'})"/>`;
    g += `<text x="${L + w / 2}" y="${T + 13}" class="be-zone ${exitAll ? 'exit' : 'stay'}" text-anchor="middle">${exitAll ? 'EXIT' : 'STAY'} across this range</text>`;
  }
  g += `<line x1="${L}" x2="${Wd - R}" y1="${Y(be.exit)}" y2="${Y(be.exit)}" class="be-exit"/>`;
  g += `<text x="${Wd - R}" y="${Y(be.exit) - 5}" class="be-lbl exit" text-anchor="end">exit cost ${usd(be.exit)} (certain)</text>`;
  g += `<line x1="${X(0)}" y1="${Y(elAt(0))}" x2="${X(pMax)}" y2="${Y(elAt(pMax))}" class="be-el"/>`;
  const lblY = clamp(Y(elAt(pMax * 0.55)) + 16, T + 26, T + h - 4);
  g += `<text x="${X(pMax * 0.55)}" y="${lblY}" class="be-lbl el" text-anchor="middle">expected loss if STAY</text>`;
  if (Number.isFinite(ps) && ps > 0 && ps < pMax) {
    g += `<circle cx="${X(ps)}" cy="${Y(be.exit)}" r="4" class="be-cross"/>`;
    g += `<line x1="${X(ps)}" x2="${X(ps)}" y1="${Y(be.exit)}" y2="${T + h}" class="be-guide"/>`;
    g += `<text x="${X(ps)}" y="${T + h - 4}" class="be-lbl" text-anchor="${X(ps) > Wd - 70 ? 'end' : 'start'}" dx="${X(ps) > Wd - 70 ? -4 : 4}">${pct(ps)}</text>`;
  }
  const pc = clamp(p, 0, pMax);
  const verdict = elAt(pc) > be.exit ? 'exit' : 'stay';
  g += `<line x1="${X(pc)}" x2="${X(pc)}" y1="${T}" y2="${T + h}" class="be-marker ${verdict}"/>`;
  g += `<circle cx="${X(pc)}" cy="${Y(elAt(pc))}" r="5" class="be-dot ${verdict}"/>`;
  g += `<line x1="${L}" x2="${L}" y1="${T}" y2="${T + h}" class="be-axis"/><line x1="${L}" x2="${Wd - R}" y1="${T + h}" y2="${T + h}" class="be-axis"/>`;
  svg.innerHTML = g;
  svg.setAttribute('aria-label', `Break-even for ${label}: exit if probability exceeds ${pct(ps)}`);
  return verdict.toUpperCase();
}
