(function () {
  const LAYER_META = {
    chain:        { label: 'Settlement chain', short: 'L1', color: 'var(--layer-chain)',    hex: '#7f8c9a' },
    yield_source: { label: 'Yield source',     short: 'L2', color: 'var(--layer-yield)',    hex: '#2ecc71' },
    oracle:       { label: 'Oracle',           short: 'L3', color: 'var(--layer-oracle)',   hex: '#f1c40f' },
    amm:          { label: 'PT market / AMM',  short: 'L4', color: 'var(--layer-amm)',      hex: '#3498db' },
    lending:      { label: 'Lending market',   short: 'L5', color: 'var(--layer-lending)',  hex: '#b05cf0' },
    protocol:     { label: 'Position',         short: 'P',  color: 'var(--layer-position)', hex: '#ff8a3d' },
  };

  const valid = (d) => d && d.position && Array.isArray(d.nodes) && Array.isArray(d.edges) && d.decision;

  async function tryFetch(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(url + ' ' + r.status);
    const d = await r.json();
    if (!valid(d)) throw new Error('invalid payload');
    return d;
  }

  // Resolves { data, source }; source = payload.source from the API (live|cache|mixed|mock|mock-fallback),
  // or 'demo' when the API is unreachable and the bundled sample is shown. Never rejects unless sample.json is missing.
  async function loadData() {
    try { const d = await tryFetch('/api/analyze' + location.search); return { data: d, source: d.source || 'unknown' }; }
    catch (_) { const d = await tryFetch('/data/sample.json'); d._snapshot = true; return { data: d, source: 'demo' }; }
  }

  const fmtUsd = (n) => {
    n = Number(n) || 0;
    const a = Math.abs(n), s = n < 0 ? '-' : '';
    if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(2) + 'M';
    if (a >= 1e4) return s + '$' + (a / 1e3).toFixed(1) + 'k';
    return s + '$' + Math.round(a).toLocaleString('en-US');
  };
  const fmtPct = (n, d = 1) => ((Number(n) || 0) * 100).toFixed(d) + '%';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const verdictBadge = (v) => '<span class="badge badge-' + (v === 'EXIT' ? 'exit' : v === 'STAY' ? 'stay' : 'warn') + '">' + esc(v) + '</span>';

  // One line a portfolio manager can act on: bands, carry, quote status, data freshness, liquidation mode.
  function signalDetails(d) {
    const dec = d.decision || {}, lb = dec.loss_band, eb = dec.exit_band, c = dec.carry, fr = dec.freshness, liq = d.liquidation;
    const out = [];
    if (dec.verdict === 'REVIEW' && dec.lean) out.push(esc(dec.lean));
    if (lb) out.push('Stay loss ' + fmtUsd(lb.low_usd) + '–' + fmtUsd(lb.high_usd) + ' (central ' + fmtUsd(lb.central_usd) + ')');
    if (eb) out.push('Exit ' + fmtUsd(eb.low_usd) + '–' + fmtUsd(eb.high_usd) + ' incl. carry · quote ' + esc(eb.quote_status));
    if (c) out.push(c.status === 'estimated' ? 'Carry forgone ' + fmtUsd(c.usd) + ' (PT ' + fmtPct(c.pt_implied_apy, 2) + ' vs USDC ' + fmtPct(c.reference_apy, 2) + ')' : 'Carry unknown (excluded)');
    if (d._snapshot) out.push('Data: saved snapshot, not fresh (re-run live before acting)');
    else if (fr) out.push('Data ' + esc(fr.label) + (fr.blockers && fr.blockers.length ? ': ' + esc(fr.blockers.join('; ')) : ''));
    if (liq) out.push(liq.mode === 'borrower_position'
      ? 'Borrower ' + esc(String(liq.borrower).slice(0, 10)) + '… HF ' + Number(liq.health_factor).toFixed(3) + ', ' + fmtPct(liq.distance_to_liquidation_pct) + ' to liquidation'
      : 'Liquidation: ' + esc(liq.liquidation || liq.mode) + (liq.reason ? ' (no debt given)' : ''));
    return out.join(' · ');
  }

  const SOURCE_LABEL = {
    live: ['live on-chain data', 'badge-stay', 'Fetched now from Pendle, Morpho, DefiLlama and Ethereum RPC'],
    cache: ['real data (cached)', 'badge-warn', 'Real API responses replayed from data/cache (see data_as_of)'],
    mixed: ['real data (part cached)', 'badge-warn', 'Some API calls failed and were served from data/cache'],
    mock: ['MOCK data', 'badge-exit', 'Demo graph requested explicitly; numbers are not real'],
    'mock-fallback': ['MOCK (live failed)', 'badge-exit', 'Live discovery failed; showing the demo graph'],
    demo: ['MOCK (API offline)', 'badge-exit', 'API unreachable; bundled sample data, numbers are not real'],
  };

  function sourceBadge(source, data) {
    const [label, cls, tip] = SOURCE_LABEL[source] || ['unknown source', 'badge-exit', 'Payload did not say where its data came from'];
    let title = tip;
    if (data && data.data_as_of && source !== 'live') title += ' — as of ' + new Date(data.data_as_of * 1000).toISOString();
    if (data && data.discovery_error) title += ' — error: ' + data.discovery_error;
    return '<span class="badge ' + cls + '" title="' + esc(title) + '">' + esc(label) + '</span>';
  }

  window.FaultLine = { loadData, fmtUsd, fmtPct, esc, verdictBadge, sourceBadge, signalDetails, LAYER_META };
})();
