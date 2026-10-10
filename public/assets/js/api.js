(function () {
  const LAYER_META = {
    chain:        { label: 'Settlement chain', short: 'L1', color: 'var(--layer-chain)',    hex: '#7f8c9a' },
    yield_source: { label: 'Yield source',     short: 'L2', color: 'var(--layer-yield)',    hex: '#2ecc71' },
    oracle:       { label: 'Oracle',           short: 'L3', color: 'var(--layer-oracle)',   hex: '#f1c40f' },
    amm:          { label: 'PT market / AMM',  short: 'L4', color: 'var(--layer-amm)',      hex: '#3498db' },
    lending:      { label: 'Lending market',   short: 'L5', color: 'var(--layer-lending)',  hex: '#b05cf0' },
    protocol:     { label: 'Other protocol',   short: 'P',  color: 'var(--layer-protocol)', hex: '#ec6fb0' },
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

  // ---- formatting: the only implementation used by every page. A missing value is "—", never "$0".
  const fmtUsd = (n, opts) => {
    if (n == null || n === '' || !Number.isFinite(+n)) return '—';
    n = +n;
    const sign = opts && opts.sign && n > 0 ? '+' : '';
    const s = n < 0 ? '−' : sign, a = Math.abs(n);
    if (a >= 1e9) return s + '$' + (a / 1e9).toFixed(2) + 'B';
    if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(2) + 'M';
    if (a >= 1e4) return s + '$' + (a / 1e3).toFixed(1) + 'k';
    return s + '$' + Math.round(a).toLocaleString('en-US');
  };
  const fmtPct = (n, d) => {
    if (n == null || n === '' || !Number.isFinite(+n)) return '—';
    const x = +n * 100;
    const dd = d != null ? d : (Math.abs(x) >= 10 || x === 0 ? 0 : Math.abs(x) >= 1 ? 1 : 2);
    return x.toFixed(dd) + '%';
  };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const verdictBadge = (v) => '<span class="badge badge-' + (v === 'EXIT' ? 'exit' : v === 'STAY' ? 'stay' : 'warn') + '">' + esc(v) + '</span>';

  // ---- provenance: one label for every page. tone: ok | warn | bad
  const SOURCE_LABEL = {
    live: ['Live on-chain data', 'ok', 'Fetched now from Pendle, Morpho, DefiLlama and Ethereum RPC'],
    cache: ['Real data (cached)', 'warn', 'Real API responses replayed from data/cache'],
    mixed: ['Real data (part cached)', 'warn', 'Some API calls failed and were served from data/cache'],
    mock: ['MOCK data', 'bad', 'Demo graph requested explicitly: numbers are not real'],
    'mock-fallback': ['MOCK · live discovery failed', 'bad', 'Live discovery failed; showing the demo graph'],
  };
  const isoMin = (ts) => new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

  /** kind: payload.source, or 'demo' for a bundled file. explicit: the user picked the file (?data=). */
  function sourceInfo(kind, data, explicit) {
    const asOf = data && data.data_as_of ? isoMin(data.data_as_of) : '';
    if (kind === 'demo') {
      if (data && ['live', 'cache', 'mixed'].includes(data.source)) {
        return { text: 'Real data snapshot · ' + (asOf ? asOf.slice(0, 10) : 'saved run'), tone: 'warn', asOf,
          tip: 'Saved run of the real pipeline' + (explicit ? '' : ' (the live API did not answer)') + (asOf ? ' · as of ' + asOf : '') };
      }
      return explicit
        ? { text: 'Demo data · synthetic', tone: 'bad', asOf: '', tip: 'Synthetic demo book requested explicitly: numbers are not real' }
        : { text: 'MOCK · API offline', tone: 'bad', asOf: '', tip: 'API unreachable; bundled sample data, numbers are not real' };
    }
    const [text, tone, tip] = SOURCE_LABEL[kind] || ['Unknown source', 'bad', 'Payload did not say where its data came from'];
    let t = tip;
    if (asOf && kind !== 'live') t += ' · as of ' + asOf;
    if (data && data.discovery_error) t += ' · error: ' + data.discovery_error;
    return { text, tone, asOf, tip: t };
  }
  const TONE_BADGE = { ok: 'badge-stay', warn: 'badge-warn', bad: 'badge-exit' };
  function sourceBadge(kind, data, explicit) {
    const i = sourceInfo(kind, data, explicit);
    return '<span class="badge ' + TONE_BADGE[i.tone] + '" title="' + esc(i.tip) + '">' + esc(i.text) + '</span>' +
      (i.asOf ? ' <span class="muted fl-asof">as of ' + esc(i.asOf) + '</span>' : '');
  }

  // ---- verdict numbers on one basis: exit side = execution + carry forgone (same as the engine's decision)
  function decisionNumbers(d) {
    const dec = d.decision || {};
    const exitTotal = dec.exit_total_usd != null ? +dec.exit_total_usd
      : dec.exit_band && dec.exit_band.central_usd != null ? +dec.exit_band.central_usd : +dec.exit_cost_usd;
    const carry = dec.carry && dec.carry.status === 'estimated' ? +dec.carry.usd : (dec.carry_usd != null ? +dec.carry_usd : null);
    return { stay: +dec.expected_loss_usd, exit: exitTotal, exec: +dec.exit_cost_usd, carry,
      lossBand: dec.loss_band || null, exitBand: dec.exit_band || null };
  }

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

  // ---- shared context between pages: keep the query string (borrower, value_usd, ref, data…) and add to it.
  function withQuery(path, extra) {
    const q = new URLSearchParams(location.search);
    for (const [k, v] of Object.entries(extra || {})) { if (v == null) q.delete(k); else q.set(k, v); }
    const s = q.toString();
    return path + (s ? '?' + s : '');
  }

  const F = (window.FaultLine = window.FaultLine || {});
  Object.assign(F, { loadData, fmtUsd, fmtPct, esc, verdictBadge, sourceInfo, sourceBadge, signalDetails, decisionNumbers, withQuery, isoMin, LAYER_META });
})();
