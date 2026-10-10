/* Breaking Point panel: renders ONLY what payload.liquidation contains (Morpho borrower analysis from the backend).
   Nothing is computed here: the curve is the backend's own `price_grid`, the threshold is its `distance_to_liquidation_pct`. */
(function () {
  const F = (window.FaultLine = window.FaultLine || {});
  const { esc, fmtUsd, fmtPct } = F;
  const num = (v) => (v == null || v === '' || !Number.isFinite(+v) ? null : +v);
  const short = (a) => (a ? String(a).slice(0, 6) + '…' + String(a).slice(-4) : '');

  function view(liq) {
    if (!liq) return { status: 'unavailable', reason: 'The backend returned no liquidation block.' };
    if (liq.mode === 'error') return { status: 'error', reason: liq.error || 'Borrower analysis failed.' };
    if (liq.mode !== 'borrower_position') {
      return { status: 'not_applicable', reason: liq.reason || 'No debt: the position is analysed as unlevered collateral, so it has no liquidation threshold.' };
    }
    const grid = (liq.price_grid || []).map((g) => ({ x: num(g.oracle_drop), y: num(g.health_factor_after), liq: !!g.liquidated })).filter((g) => g.x != null && g.y != null);
    const scen = (liq.scenarios || []).map((s) => ({ name: s.name, x: num(s.oracle_drop), y: num(s.health_factor_after), liq: !!s.liquidated, loss: num(s.borrower_loss_usd), bad: num(s.lender_bad_debt_usd) })).filter((s) => s.x != null);
    return {
      status: 'computed', hf: num(liq.health_factor), dist: num(liq.distance_to_liquidation_pct), lltv: num(liq.lltv), ltv: num(liq.ltv),
      debt: num(liq.debt_value_usd), coll: num(liq.collateral_value_usd_oracle), buffer: num(liq.liquidation_buffer_usd),
      borrower: liq.borrower, selectedBy: liq.selected_by, block: liq.as_of_block, grid, scen,
      pLiq: liq.expected && num(liq.expected.p_liquidation), verdict: liq.decision && liq.decision.verdict, reasons: (liq.decision && liq.decision.reasons) || [],
      market: liq.market_id, sources: liq.sources || {},
    };
  }

  function chart(v, o) {
    const W = 560, H = 260, L = 44, R = 14, T = 16, B = 40, w = W - L - R, h = H - T - B;
    const xMax = Math.max(0.2, ...v.grid.map((g) => g.x), ...v.scen.map((s) => s.x)) * 1.04;
    const yMax = Math.max(1.25, ...v.grid.map((g) => g.y), v.hf || 0) * 1.08;
    const X = (x) => L + (x / xMax) * w, Y = (y) => T + h - (Math.max(0, y) / yMax) * h;
    let g = '';
    if (v.dist != null && v.dist < xMax) g += `<rect x="${X(v.dist)}" y="${T}" width="${L + w - X(v.dist)}" height="${h}" class="bp-zone"/>`;
    for (let i = 0; i <= 4; i++) { const y = (yMax / 4) * i; g += `<line x1="${L}" x2="${L + w}" y1="${Y(y)}" y2="${Y(y)}" class="bp-grid"/><text x="${L - 6}" y="${Y(y) + 4}" class="bp-ax" text-anchor="end">${y.toFixed(1)}</text>`; }
    const tickStep = xMax > 0.35 ? 0.1 : 0.05;
    for (let x = 0; x <= xMax + 1e-9; x += tickStep) g += `<text x="${X(x)}" y="${T + h + 16}" class="bp-ax" text-anchor="middle">${x === 0 ? '0' : '−' + Math.round(x * 100) + '%'}</text>`;
    g += `<text x="${L + w / 2}" y="${H - 6}" class="bp-axt" text-anchor="middle">Collateral oracle price move</text>`;
    g += `<text x="12" y="${T + h / 2}" class="bp-axt" text-anchor="middle" transform="rotate(-90 12 ${T + h / 2})">Health factor</text>`;
    g += `<line x1="${L}" x2="${L + w}" y1="${Y(1)}" y2="${Y(1)}" class="bp-thr"/><text x="${L + w - 4}" y="${Y(1) - 6}" class="bp-thrt" text-anchor="end">liquidation threshold · HF = 1.00</text>`;
    const pts = v.grid.slice().sort((a, b) => a.x - b.x);
    if (pts.length > 1) g += `<polyline class="bp-line" points="${pts.map((p) => X(p.x) + ',' + Y(p.y)).join(' ')}"/>`;
    for (const p of pts) g += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="3.2" class="bp-pt ${p.liq ? 'liq' : ''}"><title>price −${(p.x * 100).toFixed(2)}% → HF ${p.y.toFixed(3)}${p.liq ? ' · liquidatable' : ''}</title></circle>`;
    if (v.dist != null) {
      g += `<line x1="${X(v.dist)}" x2="${X(v.dist)}" y1="${T}" y2="${T + h}" class="bp-break"/>`;
      g += `<text x="${X(v.dist) + 6}" y="${T + 14}" class="bp-breakt">first liquidation −${(v.dist * 100).toFixed(1)}%</text>`;
    }
    if (v.hf != null) g += `<circle cx="${X(0)}" cy="${Y(v.hf)}" r="5" class="bp-now"/><text x="${X(0) + 9}" y="${Y(v.hf) - 7}" class="bp-lbl">now · HF ${v.hf.toFixed(2)}</text>`;
    v.scen.forEach((s, i) => {
      const yy = T + h + 0; // markers sit on the x axis
      g += `<g class="bp-sc ${o.onScenario || o.scenarioHref ? 'click' : ''}" data-i="${i}" tabindex="0" role="button" aria-label="${esc(s.name)}: collateral −${(s.x * 100).toFixed(1)}%, ${s.liq ? 'liquidated' : 'not liquidated'}">
        <path d="M${X(s.x)} ${yy - 1} l-6 -10 h12 z" class="${s.liq ? 'liq' : 'ok'}"/><title>${esc(s.name)} · −${(s.x * 100).toFixed(1)}% · HF ${s.y != null ? s.y.toFixed(2) : '—'}${s.liq ? ' · liquidated' : ''}</title></g>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="bp-svg" role="img" aria-label="Health factor versus collateral price drop. First liquidation at −${v.dist != null ? (v.dist * 100).toFixed(1) : '?'}%.">${g}</svg>`;
  }

  /** o: { onScenario(name), scenarioHref(name)->url } */
  function render(el, liq, o) {
    o = o || {};
    const v = view(liq);
    if (v.status !== 'computed') {
      const head = v.status === 'not_applicable' ? 'N/A · no debt' : v.status === 'error' ? 'Analysis failed' : 'Not available';
      el.innerHTML = `<div class="bp-na"><b>${head}</b><p>${esc(v.reason)}</p>
        <p class="muted">A breaking point only exists for a leveraged position. Add <code>?borrower=0x…</code> (or <code>?borrower=auto</code> for the largest borrower on this market) to analyse one.</p></div>`;
      return v;
    }
    const keyRows = [
      ['Health factor now', v.hf != null ? v.hf.toFixed(3) : '—'],
      ['Liquidates when HF ≤', '1.00 (LLTV ' + fmtPct(v.lltv, 1) + ')'],
      ['Debt', fmtUsd(v.debt)], ['Collateral (oracle)', fmtUsd(v.coll)], ['Buffer to liquidation', fmtUsd(v.buffer)],
    ];
    el.innerHTML = `
      <div class="bp-head">
        <div><span class="bp-k">First modeled liquidation</span>
          <div class="bp-big">${v.dist != null ? 'Collateral price −' + (v.dist * 100).toFixed(1) + '%' : 'Not available'}</div>
          <div class="muted bp-sub">A conditional shock in the model, not a probability.${v.pLiq != null ? ' Model odds of liquidation over the horizon: <b>' + fmtPct(v.pLiq, 2) + '</b>.' : ''}</div></div>
        <span class="badge ${v.verdict === 'EXIT' ? 'badge-exit' : v.verdict === 'STAY' ? 'badge-stay' : 'badge-warn'}" title="Verdict of the borrower analysis">${esc(v.verdict || '')}</span>
      </div>
      ${chart(v, o)}
      <div class="bp-legend"><span><i class="bp-sw ok"></i>backend sample</span><span><i class="bp-sw liq"></i>sample liquidatable</span><span><i class="bp-tri ok"></i>scenario survives</span><span><i class="bp-tri liq"></i>scenario liquidates</span>${o.onScenario || o.scenarioHref ? '<span class="muted">Click a scenario marker to stress it.</span>' : ''}</div>
      ${v.reasons.length ? `<p class="bp-reason">${v.reasons.map(esc).join(' · ')}</p>` : ''}
      <dl class="bp-kv">${keyRows.map(([k, x]) => `<div><dt>${esc(k)}</dt><dd>${esc(x)}</dd></div>`).join('')}</dl>
      <details class="bp-more"><summary>Position, method and data</summary>
        <p class="muted">Borrower <code title="${esc(v.borrower)}">${esc(short(v.borrower))}</code> · ${esc(v.selectedBy || 'borrower given in the URL')} · read on-chain at block ${esc(v.block)}.
        The curve connects the backend's sampled points (health factor is the stressed health factor after the price move); no value is interpolated for the threshold.</p>
        <table class="table bp-table"><thead><tr><th>Price move</th><th class="num">Health factor</th><th>State</th></tr></thead><tbody>
          ${v.grid.map((g) => `<tr><td>−${(g.x * 100).toFixed(2)}%</td><td class="num">${g.y.toFixed(3)}</td><td>${g.liq ? 'liquidatable' : 'healthy'}</td></tr>`).join('')}
        </tbody></table>
        <ul class="muted">${Object.entries(v.sources).map(([k, s]) => `<li><b>${esc(k)}</b>: ${esc(s)}</li>`).join('')}</ul>
      </details>`;
    el.querySelectorAll('.bp-sc.click').forEach((n) => {
      const s = v.scen[+n.dataset.i];
      const go = () => { if (o.onScenario) o.onScenario(s.name); else if (o.scenarioHref) location.href = o.scenarioHref(s.name); };
      n.addEventListener('click', go);
      n.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
    return v;
  }

  F.breakingPoint = { render, view };
})();
