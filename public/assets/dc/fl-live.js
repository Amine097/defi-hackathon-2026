/* FAULTLINE backend adapter for the Claude Design app (public/app.html, logic in /assets/dc/app.js).
   Turns real backend responses (/api/analyze, /api/vault, /api/countermove, and recorded copies of them in
   /data/recorded) into the view data the approved design renders. It formats and arranges values; it never computes
   an expected loss, an exit cost, a verdict, a transmission or a conditional loss: those come from the payload. */
(function () {
  'use strict';
  const INK = '#e9edf2', MUTE = '#8a94a3', CYAN = '#2bb8ff', EMBER = '#ff6a3d', AMBER = '#ffb547';

  // ---------------------------------------------------------------- formatting only
  const fin = v => typeof v === 'number' && isFinite(v);
  const usd = v => !fin(v) ? '—' : (v < 0 ? '−$' : '$') + Math.round(Math.abs(v)).toLocaleString('en-US');
  const usdM = v => {
    if (!fin(v)) return '—';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    if (a >= 1e9) return s + +(a / 1e9).toFixed(1) + 'B';
    if (a >= 1e8) return s + +(a / 1e6).toFixed(1) + 'M';
    if (a >= 1e6) return s + +(a / 1e6).toFixed(2) + 'M';
    if (a >= 1e4) return s + Math.round(a / 1e3) + 'k';
    return usd(v);
  };
  const amt = (v, d = 2) => !fin(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const qty = v => {
    if (!fin(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (a >= 1e3) return Math.round(v).toLocaleString('en-US');
    return String(+v.toPrecision(4));
  };
  const pct = (v, d = 2) => !fin(v) ? '—' : (v * 100).toFixed(d) + '%';
  const pct0 = v => !fin(v) ? '—' : +(v * 100).toFixed(1) + '%';
  const blk = n => n == null ? '—' : Number(n).toLocaleString('en-US');
  const short = (a, n = 6) => !a ? '—' : String(a).slice(0, n) + '…' + String(a).slice(-4);
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const date = t => { const d = new Date(typeof t === 'number' ? t * 1000 : t); return isNaN(d) ? '—' : d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()] + ' ' + d.getUTCFullYear(); };
  const ago = s => { if (!fin(s)) return ''; s = Math.max(0, Math.round(s)); return s < 90 ? s + ' s ago' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' d ago'; };
  const strip = l => String(l || '').replace(/\s*\([^)]*\)\s*$/, '').replace(/\s*\([^)]*\)\s*$/, '');
  const verdictColor = v => v === 'EXIT' ? EMBER : v === 'STAY' ? CYAN : v === 'HOLD_TO_MATURITY' ? CYAN : v === 'REVIEW' ? AMBER : INK;
  const sentence = (s, n = 1) => String(s || '').split(/(?<=\.)\s+/).slice(0, n).join(' ');
  const F = { usd, usdM, amt, qty, pct, pct0, blk, short, date, ago, strip, verdictColor, sentence, fin };

  // ---------------------------------------------------------------- fetch
  const inflight = new Map();
  function getJson(url, opts) {
    const timeout = (opts && opts.timeout) || 70000;
    if (inflight.has(url)) return inflight.get(url);
    const ctl = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = setTimeout(() => ctl && ctl.abort(), timeout);
    const p = fetch(url, { cache: 'no-store', signal: ctl ? ctl.signal : undefined, headers: { Accept: 'application/json' } })
      .then(r => r.text().then(t => { let body = null; try { body = JSON.parse(t); } catch (e) { body = null; } return { ok: r.ok, status: r.status, body }; }))
      .catch(e => ({ ok: false, status: 0, body: null, network: true, aborted: e && e.name === 'AbortError' }))
      .finally(() => { clearTimeout(timer); inflight.delete(url); });
    p.abort = () => ctl && ctl.abort();
    inflight.set(url, p);
    return p;
  }
  function errText(res) {
    const b = res && res.body;
    if (!res || res.network) return res && res.aborted ? 'The request was cancelled or took longer than 70 s.' : 'The backend did not answer (network error).';
    if (b && b.error) return typeof b.error === 'string' ? b.error : (b.error.message || b.error.code || 'error');
    return 'The backend answered HTTP ' + res.status + '.';
  }

  // ---------------------------------------------------------------- dependency graph (analyze payload)
  // Belem layer numbers used by the design: 0 position, 1 chain, 2 yield source / issuer, 3 oracle, 4 PT / AMM, 5 lending.
  const LAYER_NUM = { chain: 1, yield_source: 2, oracle: 3, amm: 4, lending: 5, protocol: 5 };
  const COL_X = { 0: 70, 5: 250, 4: 430, 3: 610, 2: 800, 1: 915 };
  const COLS = [{ x: 70, label: 'POSITION' }, { x: 250, label: '05 LENDING' }, { x: 430, label: '04 PT / AMM' },
    { x: 610, label: '03 ORACLE' }, { x: 800, label: '02 YIELD / ISSUER' }, { x: 915, label: '01 CHAIN' }];
  const ROLE_TEXT = {
    lending: 'Lending market holding the PT as collateral', morpho_blue: 'Singleton lending contract behind every Morpho market',
    pendle_core: 'PT and SY contracts: they redeem the PT at maturity', amm: 'PT market and AMM curve: the exit route before maturity',
    oracle: 'Prices the PT for the lending market', feed_provider: 'Feed provider behind the oracle',
    underlying: 'Yield-bearing asset wrapped by the PT', issuer: 'Issuer and manager of the yield source',
    stablecoin: 'Stablecoin in the dependency chain', base_asset: 'Base asset, found by look-through', chain: 'Settlement chain'
  };
  function nodeShort(n) {
    const r = (n.meta || {}).role;
    if (r === 'lending') return 'Morpho market';
    if (r === 'morpho_blue') return 'Morpho Blue';
    if (r === 'pendle_core') return 'Pendle PT / SY';
    if (r === 'amm') return 'Pendle AMM';
    if (r === 'oracle') return 'Price oracle';
    if (r === 'feed_provider') return strip(n.label) + ' feed';
    if (r === 'base_asset') return 'USD reserves';
    return strip(n.label);
  }
  function nodeWhy(n, stress, P) {
    const m = n.meta || {}, r = m.role, out = [];
    if (r === 'lending') out.push(`LLTV ${pct0(m.lltv)}, ${pct0(m.utilization)} utilized, ${usdM(m.liquidity_usd)} available liquidity, ${m.bad_debt_usd ? usd(m.bad_debt_usd) + ' bad debt' : 'no bad debt'}.`);
    if (r === 'morpho_blue' || r === 'issuer') out.push(`TVL ${usdM(m.tvl_usd)}${m.audits ? ', ' + m.audits + ' audits' : ''}.`);
    if (r === 'amm') out.push(`${usdM(m.liquidity_usd)} pool liquidity, PT implied APY ${pct(m.implied_apy)}, expires ${date(m.expiry)}.`);
    if (r === 'pendle_core') out.push(`The PT redeems at par through these contracts at maturity, ${date(m.expiry)}.`);
    if (r === 'oracle') out.push([m.single_feed ? 'Single price feed' : (m.sources || 'Several') + ' price feeds', m.computed_on_read ? 'computed on read' : null, m.heartbeat == null ? 'no heartbeat or staleness guard' : 'heartbeat ' + m.heartbeat + ' s', m.provider ? 'provider ' + m.provider : null].filter(Boolean).join(', ') + '.');
    if (r === 'feed_provider' && m.description) out.push(m.description + '.');
    if (r === 'underlying' || r === 'issuer') { const c = ((P.position || {}).meta || {}).coverage; if (c && r === 'underlying') out.push(sentence(c.summary, 2)); }
    if (r === 'stablecoin' && m.depeg_stats) out.push(`Severity is the measured mean depth of past depegs (${pct(m.depeg_stats.severity, 1)}, low $${(+m.depeg_stats.min_price).toFixed(3)}).`);
    if (r === 'base_asset' && !n.p_fail) out.push('Failure probability is 0 here because the parent tokens already carry this risk. Shocking it is a what-if only.');
    if (r === 'chain') out.push('Every contract in this position settles here.');
    const note = stress && stress.channel && stress.channel.note;
    if (note) out.push(note.charAt(0).toUpperCase() + note.slice(1) + '.');
    return out.join(' ');
  }
  // Logos for the X-Ray nodes (public/assets/logos, see SOURCES.md). Unknown issuers and feeds keep the plain node.
  const L = '/assets/logos/';
  const ICON_BY_ROLE = { lending: 'morpho.webp', morpho_blue: 'morpho.webp', pendle_core: 'pendle.svg', amm: 'pendle.svg', oracle: 'morpho.webp', chain: 'eth.svg' };
  const ICON_BY_SYMBOL = { USDC: 'usdc.svg', USDT: 'usdt.svg', DAI: 'dai.svg', USDS: 'usds.svg', FRAX: 'frax.svg', ETH: 'eth.svg', WETH: 'eth.svg', WEETH: 'etherfi.webp', STETH: 'steth.svg', WSTETH: 'steth.svg', WBTC: 'wbtc.svg', CBBTC: 'btc.svg', BTC: 'btc.svg', LINK: 'link.svg', PENDLE: 'pendle.svg', MORPHO: 'morpho.webp' };
  function iconFor(role, label) {
    if (ICON_BY_ROLE[role]) return L + ICON_BY_ROLE[role];
    const sym = String(label || '').replace(/\s*\(.*$/, '').trim().toUpperCase();
    if (ICON_BY_SYMBOL[sym]) return L + ICON_BY_SYMBOL[sym];
    if (/chainlink/i.test(label || '')) return L + 'link.svg';
    if (/redstone/i.test(label || '')) return L + 'redstone.webp';
    return null;
  }
  function graphFromAnalyze(P) {
    const S = {}; (P.stress_table || []).forEach(r => { S[r.id] = r; });
    const contrib = P.node_contrib_usd || {};
    const nodes = P.nodes.map(n => {
      const isPos = n.id === 'pos', st = S[n.id] || {}, m = n.meta || {};
      return {
        id: n.id, layer: isPos ? 0 : (LAYER_NUM[n.layer] || 5), label: isPos ? 'Your position' : n.label, short: isPos ? 'POSITION' : nodeShort(n),
        hidden: !!m.hidden, depth: m.depth || 0, p: n.p_fail || 0, lgf: n.loss_given_failure || 0, contrib: contrib[n.id] || 0,
        sev: st.severity != null ? st.severity : n.loss_given_failure, T: st.transmission != null ? st.transmission : 0,
        path: st.path || (isPos ? ['pos'] : ['pos', n.id]), cond: st.conditional_loss_usd, verdictIf: st.verdict_if_shocked,
        blocked: !!(st.channel && st.channel.blocked_by), note: st.channel && st.channel.note, role: isPos ? 'The analysed position' : (ROLE_TEXT[m.role] || m.role || ''),
        why: isPos ? '' : nodeWhy(n, st, P), exitTotal: st.exit_total_usd, icon: isPos ? null : iconFor(m.role, n.label)
      };
    });
    // Same coordinates as the approved design for the node ids it defines; new ids fill the remaining slots of their column.
    const PREF_Y = { pos: 260, lending: 330, morpho: 455, pendle_core: 165, amm: 330, oracle: 330, feed: 455, issuer: 55, underlying: 165, usd_usdc: 290, base_usd_fiat: 410, chain: 300 };
    const cols = {};
    nodes.forEach(n => { (cols[n.layer] = cols[n.layer] || []).push(n); });
    Object.keys(cols).forEach(k => {
      const list = cols[k].sort((a, b) => (a.hidden - b.hidden) || (a.depth - b.depth) || (b.contrib - a.contrib));
      const taken = list.filter(n => PREF_Y[n.id] != null).map(n => PREF_Y[n.id]);
      const free = [55, 165, 290, 410, 470, 110, 230, 350].filter(y => taken.every(t => Math.abs(t - y) > 70));
      const crowded = list.length > 5 || new Set(taken).size !== taken.length;
      list.forEach((n, i) => {
        n.x = COL_X[n.layer];
        if (!crowded && PREF_Y[n.id] != null) n.y = PREF_Y[n.id];
        else if (!crowded && free.length) n.y = free.shift();
        else { const c = list.length, gap = c <= 1 ? 0 : Math.min(125, 400 / (c - 1)); n.y = Math.round(260 + (i - (c - 1) / 2) * gap); }
      });
    });
    const edges = P.edges.map(e => [e.src, e.dst, e.transmission, e.reason || '', e.channel || 'principal']);
    return { NODES: nodes, EDGES: edges, COLS };
  }

  // ---------------------------------------------------------------- shared pieces
  function sourceOf(mode, block, endpoint, extra) {
    if (mode === 'live') return { source: 'LIVE', sourceNote: 'Ethereum block ' + blk(block) + ' · ' + endpoint + (extra ? ' · ' + extra : '') };
    return { source: 'RECORDED LIVE RUN', sourceNote: 'Ethereum block ' + blk(block) + ' · ' + endpoint };
  }
  function niceAxis(maxVal) {
    const raw = Math.max(1, maxVal) / 3, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(k => k * mag).find(s => s >= raw);
    const lbl = v => v === 0 ? '$0' : v >= 1e6 ? '$' + +(v / 1e6).toFixed(2) + 'M' : v >= 1e3 ? '$' + +(v / 1e3).toFixed(1) + 'k' : '$' + v;
    return { max: step * 3, vals: [0, step, step * 2, step * 3], labels: [0, step, step * 2, step * 3].map(lbl) };
  }
  function statusPill(verdict, point) {
    if (verdict === 'EXIT') return { tint: 'rgba(255,106,61,.08)', status: 'Exit recommended', pillBg: 'rgba(255,106,61,.14)', pillC: EMBER };
    if (verdict === 'STAY') return { tint: 'rgba(43,184,255,.08)', status: 'Stay recommended', pillBg: 'rgba(43,184,255,.14)', pillC: CYAN };
    return { tint: 'rgba(255,181,71,.08)', status: 'Review recommended', pillBg: 'rgba(255,181,71,.14)', pillC: AMBER };
  }
  function compareCopy(kind, d) {
    // d: verdict, point, el, lo, hi, exit, mult, reasons, blockers
    const what = kind === 'vault' ? 'staying in the vault' : 'keeping this position', leave = kind === 'vault' ? 'withdrawing' : 'leaving';
    const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
    if (d.verdict === 'STAY') return { headline: `${cap(what)} is cheaper than ${leave}, even at the top of the risk range.`, note: 'The two ranges do not overlap: staying is cheaper across the whole risk range.' };
    if (d.verdict === 'EXIT') return { headline: `${cap(leave)} is cheaper than ${what}, even at the bottom of the risk range.`, note: 'The two ranges do not overlap: leaving is cheaper across the whole risk range.' };
    const blocked = d.blockers && d.blockers.length;
    if (d.point === 'EXIT') return { headline: `${cap(leave)} looks cheaper than ${what}, but the estimate is uncertain.`, note: blocked ? 'A data check blocks a firm verdict: ' + d.blockers[0] + '.' : 'The two ranges overlap, which is why the verdict is "review".' };
    return { headline: `${cap(what)} looks cheaper than ${leave}, but the estimate is uncertain.`,
      note: blocked ? 'A data check blocks a firm verdict: ' + d.blockers[0] + '.' : `The two ranges overlap, which is why the verdict is "review". Staying remains the better choice unless the real risk is about ${d.mult >= 10 ? Math.round(d.mult) : d.mult.toFixed(1)} times higher than estimated.` };
  }
  function band(label, sub, value, range, lo, hi, mid, max, c, bandC) {
    const pc = (v, a, b) => (Math.max(0, Math.min(1, (v - a) / (b - a))) * 100).toFixed(2) + '%';
    return { label, sub, value, range, c, bandL: pc(lo, 0, max), bandW: Math.max(0.8, (hi - lo) / max * 100).toFixed(2) + '%', markL: pc(mid, 0, max), bandC };
  }
  function ticksFor(ax) {
    const n = ax.vals.length;
    return ax.vals.map((v, i) => ({ l: (v / ax.max * 100).toFixed(2) + '%', label: ax.labels[i], tf: i === 0 ? 'none' : i === n - 1 ? 'translateX(-100%)' : 'translateX(-50%)' }));
  }
  function plainDrivers(G, n) {
    return G.NODES.filter(x => x.id !== 'pos' && x.contrib > 0).sort((a, b) => b.contrib - a.contrib).slice(0, n || 3)
      .map((x, i) => ({ rank: String(i + 1), label: x.short === 'USDC' ? 'USDC stablecoin' : strip(x.label), v: usd(x.contrib), sub: x.role, hidden: x.hidden }));
  }
  function techDrivers(G) {
    return G.NODES.filter(n => n.contrib > 0).sort((a, b) => b.contrib - a.contrib).slice(0, 5);
  }

  // ---------------------------------------------------------------- /api/analyze -> context (PT position or borrower)
  function fromAnalyze(P, o) {
    o = o || {};
    const pos = P.position, m = pos.meta || {}, dec = P.decision || {}, lb = dec.loss_band || {}, eb = dec.exit_band || {};
    const L = P.liquidation || {}, borrower = L.mode === 'borrower_position';
    const kind = borrower ? 'borrow' : 'pt', mode = o.mode || 'recorded';
    const ptName = String(pos.label || '').split(' on ')[0];
    const loanSym = (String(pos.label || '').match(/\(([^)]+)\)\s*$/) || [])[1] || 'USDC';
    const block = m.block_number || (P._snapshot || {}).block;
    const G = graphFromAnalyze(P);
    const lend = (P.nodes.find(n => n.id === 'lending') || {}).meta || {};
    const amm = (P.nodes.find(n => n.id === 'amm') || {}).meta || {};
    const oracle = (P.nodes.find(n => n.id === 'oracle') || {}).meta || {};
    const carry = dec.carry || {}, ex = P.exit || {}, V = pos.value_usd, H = pos.horizon_days || 30;
    const ref = borrower ? 'borrower=' + (L.selected_by && /^auto/.test(L.selected_by) ? 'auto' : short(L.borrower, 8)) : (m.ref || 'auto');
    const src = sourceOf(mode, block, '/api/analyze', o.elapsed ? Math.round(o.elapsed) + ' s' : null);
    const tokens = ((m.lookthrough || {}).tokens || []).map(t => t.symbol);
    const scen = (P.scenarios || []).map((s, i) => ({
      id: 'scen' + i, name: s.name, desc: s.description, targets: Object.keys(s.overrides || {}),
      sev: Object.keys(s.overrides || {}).map(k => (+((s.overrides[k] || {}).loss_given_failure || 0)).toFixed(2)).join(' · '),
      loss: s.conditional_loss_usd, exec: s.exit_cost_usd, carry: s.carry_usd, exit: s.exit_total_usd, mult: s.exit_total_usd ? s.conditional_loss_usd / s.exit_total_usd : 0,
      verdict: s.verdict, stressed: s.exit_cost_usd > (dec.exit_cost_usd || 0) + 0.5, notes: s.channel_notes || {}
    }));
    const mat = P.maturity && P.maturity.status === 'ok' ? P.maturity : null;
    const htm = mat ? mat.options.find(x => x.option === 'HOLD_TO_MATURITY') : null, exitWin = mat ? mat.options.find(x => x.option === 'EXIT') : null;
    const ctx = {
      id: o.id || kind, kind, mode, payload: P, G, scen, graph: true, maturity: mat, htm, exitWin,
      name: borrower ? 'Borrower ' + short(L.borrower) : ptName,
      sub: borrower ? `Real borrower on the ${ptName} / ${loanSym} Morpho market` : `Pendle PT collateral market on Morpho Blue · ${loanSym}`,
      protocol: 'Morpho Blue · Pendle', network: 'Ethereum',
      ident: borrower ? ref + ' · ' + short(L.borrower, 10) : 'Market ' + short(m.morpho_market, 10),
      identFull: borrower ? L.borrower : m.morpho_market,
      size: borrower ? `${usdM(L.collateral_value_usd_oracle)} PT collateral with ${loanSym} debt` : `${usd(V)} hypothetical PT exposure, unlevered`,
      assets: borrower ? `${ptName} collateral · ${loanSym} debt` : [ptName].concat(tokens).join(' · '),
      source: src.source, sourceNote: src.sourceNote, block, verdict: borrower ? (L.decision || {}).verdict || dec.verdict : dec.verdict,
      can: borrower ? [['Analyze', 'Yes'], ['Simulate attack', 'Yes (stress values for a ' + usd(V) + ' position on this market)'], ['Arm protection', 'Policy preview and live dry run']]
        : [['Analyze', 'Yes'], ['Simulate attack', 'Yes'], ['Arm protection', 'Not applicable: no debt']],
      exec: dec.exit_cost_usd, carry: dec.carry_usd, exitTotal: dec.exit_total_usd, band: [lb.low_usd, lb.high_usd], V, H, loanSym, ptName
    };
    const drivers = techDrivers(G);
    const d = { verdict: dec.verdict, point: dec.point_verdict, el: dec.expected_loss_usd, lo: lb.low_usd, hi: lb.high_usd, exit: dec.exit_total_usd, mult: dec.breakeven_risk_multiplier || 0, blockers: ((dec.freshness || {}).blockers || []) };
    const cc = compareCopy('pt', d);
    const asOf = (mode === 'live' ? 'Live run · ' : 'Recorded live run · ') + 'Ethereum block ' + blk(block);
    const oracleWatch = oracle.single_feed ? { t: 'The price oracle relies on a single feed' + (oracle.computed_on_read && oracle.heartbeat == null ? ' with no staleness check.' : '.'), c: EMBER } : null;
    const cov = m.coverage || {};
    if (!borrower) {
      const ax = niceAxis(Math.max(lb.high_usd || 0, eb.high_usd || 0));
      ctx.dash = {
        kicker: `DECISION · ${H}-DAY HORIZON · ${usd(V)}`, verdict: dec.verdict, vColor: verdictColor(dec.verdict),
        lean: dec.verdict === 'REVIEW' ? 'Lean ' + dec.point_verdict + ' · ' + (dec.confidence || 'low') + ' confidence' : dec.verdict + ' · ' + (dec.confidence || '') + ' confidence',
        text: `Staying is expected to cost about ${usd(d.el)} over ${H} days, but the plausible range runs from ${usd(d.lo)} to ${usd(d.hi)}. Exiting now would cost ${usd(d.exit)}: ${usd(dec.exit_cost_usd)} to sell, plus ${usd(dec.carry_usd)} of yield given up.` + (dec.verdict === 'REVIEW' ? ' The two ranges overlap, so FAULTLINE does not make the call outright.' : ''),
        metrics: [['EXPECTED LOSS · ' + H + ' D', usd(d.el), `${usd(d.lo)} to ${usd(d.hi)} band`, INK], ['EXIT SIDE', usd(d.exit), `${usd(dec.exit_cost_usd)} execution + ${usd(dec.carry_usd)} carry forgone`, INK],
          ['MARGIN', usd(dec.margin_usd), dec.margin_usd < 0 ? `STAY holds below ×${(d.mult).toFixed(2)} the central risk` : 'Staying costs more than the exit side', verdictColor(dec.verdict)],
          ['DEBT AND HEALTH', 'No debt', 'Unlevered, so no liquidation threshold', INK],
          ['EXIT COST', pct(dec.exit_cost_pct), (ex.method === 'pendle_sdk_quote' ? 'Pendle SDK quote' : ex.method || 'quote') + (ex.quote_status === 'simulated' ? ', simulated eth_call' : ', ' + (ex.quote_status || 'not simulated')), INK],
          ['CARRY', pct(carry.pt_implied_apy), `PT implied APY vs ${pct(carry.reference_apy)} ${loanSym} supply`, INK]],
        driversTitle: 'MAIN RISK CONTRIBUTORS · OF ' + usd(d.el), drivers,
        prot: { chipLabel: 'NOT APPLICABLE', short: 'No debt, so there is no liquidation to defend. See how protection works on the fork demo.', text: 'This position has no debt, so there is nothing to liquidate and nothing to repay. Protection policies apply to borrow positions.', action: 'toFork' },
        simShort: `Shock any of ${G.NODES.length - 1} dependencies and watch the failure travel. Nothing is armed, signed or spent.`
      };
      ctx.db = Object.assign(statusPill(dec.verdict), {
        asOf, headline: cc.headline,
        rec: dec.point_verdict === 'STAY'
          ? `FAULTLINE leans toward staying: the expected ${H}-day loss (${usd(d.el)}) is lower than the cost of exiting (${usd(d.exit)}).` + (dec.verdict === 'REVIEW' ? ' The risk range is wide, so it asks you to review the position rather than calling it safe.' : '')
          : `FAULTLINE leans toward leaving: the expected ${H}-day loss (${usd(d.el)}) is higher than the cost of exiting (${usd(d.exit)}).` + (dec.verdict === 'REVIEW' ? ' The ranges overlap, so it asks you to review the position.' : ''),
        visTitle: 'Stay or leave?', visSub: `Estimated cost over the next ${H} days`, isCompare: true,
        rows: [band('If you stay', 'Expected loss if a dependency fails', usd(d.el), `likely between ${usd(d.lo)} and ${usd(d.hi)}`, d.lo, d.hi, d.el, ax.max, AMBER, 'rgba(255,181,71,.22)'),
          band('If you leave now', 'Selling the PT, plus the extra yield you give up', usd(d.exit), `between ${usd(eb.low_usd)} and ${usd(eb.high_usd)}`, eb.low_usd, eb.high_usd, d.exit, ax.max, INK, 'rgba(233,237,242,.18)')],
        ticks: ticksFor(ax), visNote: cc.note,
        facts: [{ k: 'Position value', v: usd(V), s: 'Hypothetical PT exposure', c: INK }, { k: 'Debt', v: 'None', s: 'No liquidation risk', c: CYAN },
          { k: 'Yield', v: pct(carry.pt_implied_apy), s: `vs ${pct(carry.reference_apy)} if you move to ${loanSym}`, c: INK }],
        drivers: plainDrivers(G), moreLabel: `See all ${G.NODES.length - 1} dependencies`,
        watch: [cov.summary ? { t: sentence(cov.summary, 1), c: cov.traced_pct === 0 ? EMBER : AMBER } : null, oracleWatch].filter(Boolean), protTag: 'not needed'
      });
    } else {
      const E = L.expected || {}, LD = L.decision || {}, dist = L.distance_to_liquidation_pct, hf = L.health_factor, hist = L.historical_check || {};
      const pc = (v, a, b) => (Math.max(0, Math.min(1, (v - a) / (b - a))) * 100).toFixed(2) + '%';
      const tk = (v, label, i, n) => ({ l: pc(v, 0, 25), label, tf: i === 0 ? 'none' : i === n - 1 ? 'translateX(-100%)' : 'translateX(-50%)' });
      ctx.dash = {
        kicker: 'LIQUIDATION RISK · REAL MORPHO BORROWER', verdict: LD.verdict || dec.verdict, vColor: verdictColor(LD.verdict || dec.verdict),
        lean: (LD.reasons && LD.reasons[0]) ? LD.reasons[0].charAt(0).toUpperCase() + LD.reasons[0].slice(1) : 'Point comparison: ' + LD.point_verdict,
        text: `This borrower is ${pct(dist)} away from liquidation (health factor ${(+hf).toFixed(3)}). FAULTLINE puts the chance of liquidation at ${pct(E.p_liquidation)} over the horizon, but PT price volatility is not modelled, so the position is flagged for review rather than called safe.`,
        metrics: [['HEALTH FACTOR', (+hf).toFixed(3), 'Liquidation at 1.000', AMBER], ['DISTANCE', pct(dist), 'Collateral price drop to liquidation', AMBER], ['P(LIQUIDATION)', pct(E.p_liquidation), 'Over the horizon', INK],
          ['BORROWER LOSS', usd(E.expected_borrower_loss_usd), 'Expected, if liquidated', INK], ['LENDER BAD DEBT', usd(E.expected_lender_bad_debt_usd), 'Expected', INK], ['DELEVERAGE COST', usd(LD.exit_cost_usd), 'To step back from the threshold (indicative)', INK]],
        driversTitle: 'MARKET DEPENDENCIES · SAME PT MARKET', drivers,
        prot: { chipLabel: 'PREVIEW ONLY', short: 'Configure and validate a policy. Nothing can execute: no RescueVault is deployed for it.', text: 'You can configure and validate a protection policy for this borrower. Nothing can execute: no RescueVault is deployed, funded or monitored for this position.', action: 'configure' },
        simShort: `Shock a dependency of this market. Losses shown are for a ${usd(V)} position on this market.`
      };
      ctx.db = {
        tint: 'rgba(255,106,61,.08)', status: (LD.verdict || dec.verdict) === 'REVIEW' ? 'Review recommended' : statusPill(LD.verdict).status, pillBg: 'rgba(255,106,61,.14)', pillC: EMBER, asOf,
        headline: `This loan is close to liquidation: a ${pct(dist)} price drop would trigger it.`,
        rec: `The health factor is ${(+hf).toFixed(3)}. FAULTLINE estimates a ${pct(E.p_liquidation)} chance of liquidation, but it does not model PT price swings, so treat that number as optimistic. Consider setting up protection or reducing the loan.`,
        visTitle: 'How far is liquidation?', visSub: 'Collateral price drop before the loan can be liquidated', isGauge: true,
        zones: [{ l: '0%', w: '20%', c: 'rgba(255,106,61,.55)', r: '7px 0 0 7px' }, { l: '20%', w: '20%', c: 'rgba(255,181,71,.4)', r: '0' }, { l: '40%', w: '60%', c: 'rgba(43,184,255,.22)', r: '0 7px 7px 0' }],
        markers: [{ l: pc(dist * 100, 0, 25), label: 'You are here · ' + pct(dist), c: INK, pos: 'bottom:32px' }],
        ticks: [[0, 'Liquidation'], [5, '5%'], [10, '10%'], [25, '25% drop']].map((t, i) => tk(t[0], t[1], i, 4)),
        visNote: dist < 0.10 ? 'Below 10% the margin is thin. A single bad oracle update or PT price move could close the gap.' : 'The margin is above 10%, but the PT oracle and price moves can still close it.',
        facts: [{ k: 'Collateral', v: usdM(L.collateral_value_usd_oracle), s: ptName.split('-').slice(0, 2).join('-'), c: INK }, { k: 'Health factor', v: (+hf).toFixed(3), s: 'Liquidation at 1.000', c: hf < 1.1 ? EMBER : INK },
          { k: 'If liquidated', v: usd(E.expected_borrower_loss_usd), s: 'Expected borrower loss', c: INK }],
        drivers: plainDrivers(G), moreLabel: `See all ${G.NODES.length - 1} dependencies`,
        watch: [oracleWatch ? { t: 'The oracle that decides liquidation' + (oracle.computed_on_read && oracle.heartbeat == null ? ' has no staleness check.' : ' relies on a single feed.'), c: EMBER } : null,
          hist.relative_error != null ? { t: 'The liquidation math was checked against a real Morpho liquidation (error ' + (+hist.relative_error).toExponential(1) + ').', c: CYAN } : null].filter(Boolean),
        protTag: 'preview only'
      };
    }
    // Positions & Vaults
    const supplying = (lend.supplying_vaults || lend.supplyingVaults || []).slice(0, 2).map(v => (v.name || short(v.address)) + (v.total_assets_usd || v.totalAssetsUsd ? ' ' + usdM(v.total_assets_usd || v.totalAssetsUsd) : '')).join(' · ');
    const routes = [];
    if (!borrower) {
      const qd = ex.decomposition || {};
      routes.push({ name: `Sell PT on Pendle for ${loanSym}`, val: `${usd(ex.usd)} · ${pct(ex.pct)}`, note: `${qty(ex.pt_in)} PT → ${qty(ex.out_amount)} ${ex.out_symbol || loanSym} via the Pendle SDK${ex.aggregator ? ' (' + ex.aggregator + ')' : ''}${ex.quote_status === 'simulated' ? ', eth_call at block ' + blk(ex.quote_block) + '. No transaction sent.' : '. Quote not re-executed on-chain.'}`, status: ex.quote_status === 'simulated' ? 'SIMULATED' : 'INDICATIVE', qd });
      if (htm) routes.push({ name: 'Hold to maturity', val: `${usd(htm.central_usd)} · ${date(amm.expiry)}`, note: `${htm.label}: ${htm.basis}. Over the ${mat.window.replace('now -> maturity ', '')} window, selling now costs ${usd(exitWin.central_usd)} (execution + carry forgone); best over the window: ${mat.best_over_window.replace(/_/g, ' ')} (${mat.confidence} confidence).`, status: 'MODELLED' });
      else routes.push({ name: 'Hold to maturity', val: '—', note: (P.maturity && P.maturity.reason) || 'Not available for this position.', status: 'UNAVAILABLE' });
    } else {
      const LD = L.decision || {};
      routes.push({ name: 'Deleverage', val: usd(LD.exit_cost_usd), note: LD.exit_method || 'Cost to step back from the liquidation threshold, from the backend.', status: /indicative/i.test(LD.exit_method || '') ? 'INDICATIVE' : 'RECORDED LIVE RUN' });
      routes.push({ name: 'Automated protection', val: '—', note: 'Policy preview and live dry run only. No RescueVault exists for this position.', status: 'PREVIEW ONLY' });
    }
    ctx.pv = borrower ? {
      facts: [['BORROWER', short(L.borrower, 10)], ['MARKET', `${ptName} / ${loanSym}`], ['HEALTH FACTOR', (+L.health_factor).toFixed(5)], ['COLLATERAL', usdM(L.collateral_value_usd_oracle)], ['DEBT', usdM(L.debt_value_usd)],
        ['DISTANCE TO LIQUIDATION', pct(L.distance_to_liquidation_pct)], ['P(LIQUIDATION)', pct((L.expected || {}).p_liquidation)], ['MODEL CHECK', (L.historical_check || {}).relative_error != null ? 'Replayed real liquidation, error ' + (+L.historical_check.relative_error).toExponential(1) : '—']],
      routesTitle: 'DEFENSIVE ROUTES', routes, markets: null
    } : {
      facts: [['MARKET ID', short(m.morpho_market, 10)], ['LLTV', pct0(lend.lltv)], ['UTILIZATION', pct(lend.utilization, 1)], ['MARKET SUPPLY', usdM(lend.supply_usd)], ['BORROWED', usdM(lend.borrow_usd)],
        ['AVAILABLE LIQUIDITY', usdM(lend.liquidity_usd)], ['BAD DEBT', usd(lend.bad_debt_usd || 0)], ['PT MATURITY', date(amm.expiry)], ['PENDLE POOL LIQUIDITY', usdM(amm.liquidity_usd)]].concat(supplying ? [['SUPPLYING VAULTS', supplying]] : []),
      routesTitle: 'EXIT AND WITHDRAWAL ROUTES', routes, markets: null
    };
    // Countermove context (borrower only): real market, real borrower, backend-suggested policy
    if (borrower) {
      const sug = (L.countermove_suggestion || {}).policy_draft_query || null;
      ctx.arm = { eligible: true, lltv: L.lltv * 100, ltv: L.ltv * 100, coll: 'PT', loanSym, debt: L.debt_assets, marketId: L.market_id, borrower: L.borrower,
        loanDecimals: L.loan_decimals, collDecimals: L.collateral_decimals, suggestion: sug, hf: L.health_factor,
        ctxLine: `${ptName} / ${loanSym} · LLTV ${pct0(L.lltv)} · current LTV ${pct(L.ltv)} (HF ${(+L.health_factor).toFixed(3)})` };
    } else ctx.arm = { eligible: false };
    ctx.activity = [{
      id: 'a-' + ctx.id, kind: 'analysis', title: borrower ? `Analysis · borrower ${short(L.borrower)}` : `Analysis · ${usd(V)} ${ptName}`, meta: (borrower ? 'Ethereum block ' + blk(L.as_of_block || block) : 'Ethereum block ' + blk(block)),
      status: mode === 'live' ? 'LIVE' : 'RECORDED LIVE RUN', result: borrower ? `${(L.decision || {}).verdict} · HF ${(+L.health_factor).toFixed(3)}` : `${dec.verdict} · lean ${dec.point_verdict}`,
      fields: borrower ? [['Distance to liquidation', pct(L.distance_to_liquidation_pct)], ['P(liquidation)', pct((L.expected || {}).p_liquidation)], ['Reason', ((L.decision || {}).reasons || [])[0] || '—'], ['Source', mode === 'live' ? '/api/analyze?borrower=…, this session' : 'public/data/recorded/analyze-borrower.json']]
        : [['Expected loss', `${usd(d.el)} (${usd(d.lo)} to ${usd(d.hi)})`], ['Exit side', `${usd(d.exit)} = ${usd(dec.exit_cost_usd)} + ${usd(dec.carry_usd)} carry`], ['Exit quote', (ex.quote_status === 'simulated' ? 'Pendle SDK, simulated eth_call at block ' + blk(ex.quote_block) : 'Pendle SDK quote, ' + ex.quote_status)],
          ['Freshness', ((dec.freshness || {}).label || '—') + ' at capture'], ['Source', mode === 'live' ? '/api/analyze, this session' : 'public/data/recorded/analyze-pt.json']]
    }];
    if (borrower && L.historical_check && L.historical_check.tx) {
      const h = L.historical_check;
      ctx.activity.push({ id: 'h-liq', kind: 'history', title: 'Validation · real Morpho liquidation', meta: 'Mainnet block ' + blk(h.block), status: 'MAINNET CONFIRMED', result: 'Formula matched', tx: h.tx,
        fields: [['What it is', 'A third-party liquidation used to check the liquidation model. Not a FAULTLINE transaction.'], ['Seized amount error', (+h.relative_error).toExponential(1) + ' relative'], ['Market', short(h.market_id, 10)]] });
    }
    return ctx;
  }

  // ---------------------------------------------------------------- /api/vault -> context
  const VROLE = { lending: 'The vault you deposit into (contracts and curator)', morpho_blue: 'Singleton lending contract behind every market', chain: 'Settlement chain',
    stablecoin: 'Deposit asset of the vault', fx: 'FX reference used to value the asset in USD', adapter: 'Adapter routing vault assets to markets',
    market: 'Morpho market receiving vault assets', collateral: 'Collateral backing loans made with vault assets', oracle: 'Prices that collateral for liquidations' };
  function fromVault(P, o) {
    o = o || {};
    const mode = o.mode || 'recorded', v = P.vault || {}, a = v.asset || {}, risk = P.risk || {}, dec = P.decision || {}, ex = P.exit || {}, al = P.allocations || {};
    const items = al.items || [], sym = a.symbol || 'asset', block = P.as_of_block, V = (P.input || {}).value_usd, H = (P.input || {}).horizon_days || 30;
    const src = sourceOf(mode, block, '/api/vault', o.elapsed ? Math.round(o.elapsed) + ' s' : null);
    const feas0 = ex.withdrawal_feasibility || dec.withdrawal_feasibility, route = ex.executable_route || dec.executable_route;
    const feas = /^full/.test(feas0 || '') ? 'full' : /^partial/.test(feas0 || '') ? 'partial' : /^zero/.test(feas0 || '') ? 'zero' : 'unknown';
    const R = ex.routes || {}, ord = R.ordinary || {}, force = R.force_deallocate || {}, uc = ex.usd_conversion || {};
    const ucCost = fin(uc.cost_usd) ? uc.cost_usd : fin(uc.conversion_cost_usd) ? uc.conversion_cost_usd : fin(uc.usd) ? uc.usd : null;
    const deps = (P.dependencies || {}).nodes || [];
    const drv = deps.filter(n => !n.decision_neutral && n.expected_loss_usd > 0).sort((x, y) => y.expected_loss_usd - x.expected_loss_usd);
    const lo = (risk.band_usd || [])[0], hi = (risk.band_usd || [])[1], el = risk.expected_loss_usd, exitSide = dec.exit_side_usd, eb = dec.exit_band_usd || ex.exit_band_usd || [];
    const ax = niceAxis(Math.max(hi || 0, eb[1] || 0));
    const busy = items.filter(i => i.utilization >= 0.89 && i.share_of_vault > 0.001).length, live = items.length;
    const feasTxt = feas === 'full' ? 'Full' : feas === 'partial' ? 'Partial' : feas === 'zero' ? 'None' : 'Unknown';
    const routeTxt = route === 'force_deallocate' ? 'Via force-deallocate, penalty ' + usd(force.penalty_usd || 0) : route === 'ordinary' ? 'Ordinary redeem' : (route || '—');
    const d = { verdict: dec.verdict, point: dec.point_verdict, el, lo, hi, exit: exitSide, mult: dec.breakeven_risk_multiplier || 0, blockers: dec.blockers || [] };
    const cc = compareCopy('vault', d);
    const adapters = (v.adapters || []).length || ((al.reconciliation || {}).adapters || []).length || 1;
    const ctx = {
      id: o.id || 'vault', kind: 'vault', mode, payload: P, graph: false, G: null, scen: [],
      name: v.name || short(v.address), sub: `Morpho Vault ${(v.version || '').toUpperCase()} · asset ${sym} · ${live} markets`,
      protocol: 'Morpho Vault ' + (v.version || '').toUpperCase(), network: 'Ethereum', ident: 'Vault ' + short(v.address), identFull: v.address,
      size: `${usd(V)} hypothetical deposit`, assets: `${v.symbol || 'vault'} shares · ${sym}`, source: src.source, sourceNote: src.sourceNote, block, verdict: dec.verdict,
      can: [['Analyze', 'Yes'], ['Simulate attack', 'Vault scenarios are in the backend payload; no designed view yet'], ['Arm protection', 'Not applicable: deposit']],
      exec: dec.execution_cost_usd, carry: dec.carry_usd, exitTotal: exitSide, band: [lo, hi], V, H, arm: { eligible: false }
    };
    ctx.dash = {
      kicker: `DECISION · ${H}-DAY HORIZON · ${usd(V)} DEPOSIT`, verdict: dec.verdict, vColor: verdictColor(dec.verdict), lean: dec.verdict === 'REVIEW' ? 'Point comparison: ' + dec.point_verdict : dec.verdict + ' · ' + (dec.confidence || '') + ' confidence',
      text: `Expected loss over ${H} days is ${usd(el)}, against an exit side of ${usd(exitSide)}. ` + (feas === 'full' ? (route === 'force_deallocate' ? `A full withdrawal is possible today through force-deallocate with a ${usd(force.penalty_usd || 0)} penalty.` : 'A full withdrawal is possible today.') : `Only ${usdM(ex.immediately_withdrawable_usd)} can be withdrawn now.`) + (dec.verdict === 'REVIEW' ? ' Inputs or bands are not firm enough for a confident call.' : ''),
      metrics: [['EXPECTED LOSS · ' + H + ' D', usd(el), lo != null ? `${usd(lo)} to ${usd(hi)} band` : 'Probability-weighted', INK], ['EXIT SIDE', usd(exitSide), `${usd(dec.execution_cost_usd)} execution + ${usd(dec.carry_usd)} carry`, INK],
        ['MARGIN', usd(dec.margin_usd), 'Point comparison favours ' + dec.point_verdict, verdictColor(dec.verdict)], ['WITHDRAWAL', feasTxt, routeTxt, feas === 'full' ? CYAN : AMBER],
        ['COVERAGE', pct0(al.coverage), `Assets reconciled across ${live} markets`, INK], ['TO USDC', ucCost != null ? usd(ucCost) : '—', 'Indicative KyberSwap route, not simulated', AMBER]],
      driversTitle: 'MAIN RISK CONTRIBUTORS · OF ' + usd(el), drivers: [], noDrivers: null,
      prot: { chipLabel: 'NOT APPLICABLE', short: 'A deposit has no debt to defend. Simulate an attack to test STAY or EXIT.', text: 'A vault deposit has no debt, so automated repayment does not apply. FAULTLINE can still stress the vault and recommend STAY or EXIT.', action: 'toFork' },
      simShort: 'Vault scenarios exist in the backend payload; the interactive graph covers PT markets and borrowers.'
    };
    ctx.db = Object.assign(statusPill(dec.verdict), {
      asOf: (mode === 'live' ? 'Live run · ' : 'Recorded live run · ') + 'Ethereum block ' + blk(block), headline: cc.headline + (feas === 'full' ? '' : ''),
      rec: `Expected ${H}-day loss is ${usd(el)}, against ${usd(exitSide)} to leave. ` + (feas === 'full' ? 'You could withdraw everything now' + (route === 'force_deallocate' ? ` (force-deallocate, ${usd(force.penalty_usd || 0)} penalty).` : '.') : `Only ${usdM(ex.immediately_withdrawable_usd)} is withdrawable now.`) + (ucCost != null ? ` Converting ${sym} to USDC would cost about ${usd(ucCost)}, and that quote is only indicative.` : ''),
      visTitle: 'Stay or leave?', visSub: `Estimated cost over the next ${H} days`, isCompare: true,
      rows: [band('If you stay', 'Expected loss if a dependency fails', usd(el), lo != null ? `likely between ${usd(lo)} and ${usd(hi)}` : 'point estimate', lo != null ? lo : 0, lo != null ? hi : el, el, ax.max, AMBER, 'rgba(255,181,71,.22)'),
        band('If you leave now', 'Withdrawal plus yield given up', usd(exitSide), eb.length ? `between ${usd(eb[0])} and ${usd(eb[1])}` : 'point estimate', eb.length ? eb[0] : 0, eb.length ? eb[1] : exitSide, exitSide, ax.max, INK, 'rgba(233,237,242,.18)')],
      ticks: ticksFor(ax), visNote: cc.note,
      facts: [{ k: 'Deposit', v: usd(V), s: 'Hypothetical', c: INK }, { k: 'Withdrawal', v: feasTxt, s: feas === 'full' ? 'Available now' + (force.penalty_usd ? '' : ', no penalty') : usdM(ex.immediately_withdrawable_usd) + ' available now', c: feas === 'full' ? CYAN : AMBER },
        { k: 'Spread across', v: `${live} markets`, s: `${pct0(al.coverage)} of assets accounted for`, c: INK }],
      drivers: drv.slice(0, 3).map((n, i) => ({ rank: String(i + 1), label: strip(n.label), v: usd(n.expected_loss_usd), sub: VROLE[n.role] || n.role, hidden: n.role !== 'lending' })),
      noDrivers: drv.length ? null : 'The backend attributes no expected loss to individual dependencies for this vault.', moreLabel: 'Open X-Ray',
      watch: [busy ? { t: `${busy} of the ${live} markets are more than 89% borrowed, which can slow withdrawals.`, c: AMBER } : null,
        ucCost != null ? { t: `The exit conversion to USDC is an estimate, not a tested quote.`, c: AMBER } : null,
        a.currency === 'EUR' ? { t: `The vault asset is ${sym}; USD values use the Chainlink EUR/USD feed.`, c: INK } : null].filter(Boolean).slice(0, 2),
      protTag: 'not needed'
    });
    ctx.dash.drivers = drv.slice(0, 5).map(n => ({ label: n.label, contrib: n.expected_loss_usd, hidden: n.role !== 'lending', layer: n.layer, T: n.affected_fraction || 0 }));
    const sp = v.share_price || {};
    ctx.pv = {
      facts: [['VERSION', `Vault ${(v.version || '').toUpperCase()} (factory-verified)`], ['ASSET', sym], ['TOTAL ASSETS', qty(al.total_assets) + ' ' + sym],
        ['SHARE PRICE', (fin(sp.assets_per_share) ? (+sp.assets_per_share).toFixed(6) : fin(sp) ? (+sp).toFixed(6) : (sp.value != null ? (+sp.value).toFixed(6) : '—')) + ' ' + sym],
        ['ADAPTER', ((al.reconciliation || {}).adapters || []).map(x => x.type).filter((x, i, s) => s.indexOf(x) === i).join(' · ') || '—'], ['RECONCILIATION', pct0(al.coverage) + ' of assets'],
        ['FORCE-DEALLOCATE PENALTY', usd(force.penalty_usd || 0)], ['SOURCES', `${(P.provenance || {}).live || 0} live reads · ${(P.provenance || {}).cached || 0} cached`]],
      marketsTitle: 'ALLOCATED MARKETS · ' + (adapters === 1 ? 'ONE ADAPTER' : adapters + ' ADAPTERS'),
      markets: items.map(i => ({ c: i.collateral_symbol, l: pct0(i.lltv), s: qty(i.market_total_supply) + ' ' + sym, u: pct(i.utilization, 1), uc: i.utilization > 0.89 ? AMBER : INK })),
      routesTitle: 'WITHDRAWAL ROUTES',
      routes: [{ name: 'Ordinary redeem', val: `${(ord.capacity_usd || 0) >= V ? 'full' : 'partial'} · gas ${'$' + ((ord.gas || {}).gas_usd || 0).toFixed(2)}`, note: `Up to ${usdM(ord.capacity_usd)} through idle assets and the liquidity-adapter market at block ${blk(block)}. Liquidity is shared with other depositors.`, status: /simulated/.test(ord.status || '') ? 'SIMULATED' : 'UNAVAILABLE' },
        { name: 'Force-deallocate, then redeem', val: `${(force.capacity_usd || 0) >= V ? 'full' : 'partial'} · gas ${'$' + ((force.gas || {}).gas_usd || 0).toFixed(2)}`, note: `VaultV2.multicall([forceDeallocate…, redeem…]) as eth_call with a state override. Penalty ${usd(force.penalty_usd || 0)}.`, status: force.status === 'simulated' ? 'SIMULATED' : 'UNAVAILABLE' }]
        .concat(ucCost != null ? [{ name: `Convert ${sym} to USDC`, val: usd(ucCost), note: 'KyberSwap public route. Indicative only, not simulated on-chain.', status: 'INDICATIVE' }] : [])
    };
    ctx.activity = [{ id: 'a-' + ctx.id, kind: 'analysis', title: `Analysis · ${v.name} vault, ${usd(V)}`, meta: 'Ethereum block ' + blk(block), status: mode === 'live' ? 'LIVE' : 'RECORDED LIVE RUN',
      result: `${dec.verdict} · point ${dec.point_verdict}`, fields: [['Expected loss', `${usd(el)}` + (lo != null ? ` (${usd(lo)} to ${usd(hi)})` : '')], ['Exit side', usd(exitSide)],
        ['Withdrawal', `${feasTxt} · ${routeTxt}`], ['Sources', `${(P.provenance || {}).live || 0} live reads, ${(P.provenance || {}).cached || 0} cached`], ['Source', mode === 'live' ? '/api/vault, this session' : 'public/data/recorded/vault-belem.json']] }];
    return ctx;
  }

  // ---------------------------------------------------------------- /api/countermove (recorded local-fork run) -> fork context + replay
  const STRAT = { REPAY: 'Repay', TOP_UP: 'top-up', FULL_REPAY: 'full repay' };
  function forkPos(cm, scen) { return ((cm && cm.positions) || []).find(p => p.scenario === scen) || null; }
  function forkReserve(p) {
    const c = (p.decision && p.decision.candidates) || [], b = (p.before && p.before.vault) || {};
    const loan = fin(b.loan_reserve) ? b.loan_reserve : (c.find(x => x.token === p.before.loan.symbol) || {}).reserve;
    const coll = fin(b.collateral_reserve) ? b.collateral_reserve : (c.find(x => x.token === p.before.collateral.symbol) || {}).reserve;
    return { loan, coll };
  }
  function forkPolicy(p) {
    const b = ((p.before || {}).vault || {}).policy, pr = p.protections || {}, rl = p.remaining_limits || {};
    return { strategies: (b && b.strategies) || pr.strategies || [], trigger: pr.trigger_ltv, floor: pr.min_ltv_after, cooldown: pr.cooldown_s, validUntil: pr.valid_until,
      repayCap: rl.max_repay_per_action, topupCap: rl.max_top_up_per_action, fullCap: rl.max_full_repay, repayTotal: b ? b.max_repay_total_h : null, topupTotal: b ? b.max_top_up_total_h : null,
      minLoan: rl.min_loan_reserve, minColl: rl.min_collateral_reserve };
  }
  function fromFork(cm, scen) {
    const p = forkPos(cm, scen || 'S1'); if (!p) return null;
    const env = cm.environment || {}, b = p.before, loan = b.loan.symbol, coll = b.collateral.symbol, res = forkReserve(p), pol = forkPolicy(p);
    const user = (String(p.label).match(/user ([A-Z])/) || [])[1] || '?', dec = p.decision || {};
    const ctx = {
      id: 'fork', kind: 'fork', mode: 'fork', payload: p, cm, graph: false, G: null, scen: [],
      name: `${p.scenario} · ${coll} / ${loan} borrow`, sub: 'Test position on a local Anvil fork of Ethereum', protocol: 'Morpho Blue (forked) · RescueVault', network: 'Local fork · chain ' + env.chain_id,
      ident: `Fork user ${user} ${short(p.user)}`, identFull: p.user, size: `${qty(b.collateral_amount)} ${coll} collateral · ${amt(b.debt)} ${loan} debt`, assets: `${coll} collateral · ${loan} debt · test funds`,
      source: 'LOCAL FORK', sourceNote: `Forked at block ${blk(env.fork_block)} · test funds`, verdict: 'WATCHING', block: env.fork_block,
      can: [['Analyze', 'Countermove engine'], ['Simulate attack', 'Replay recorded incident'], ['Arm protection', 'Fork demonstration']], arm: null
    };
    const pc = (v, a, z) => (Math.max(0, Math.min(1, (v - a) / (z - a))) * 100).toFixed(2) + '%';
    const lltv = b.lltv || 0.86, L0 = 60, L1 = 95;
    ctx.dash = {
      kicker: 'COUNTERMOVE · LOCAL FORK · TEST FUNDS', verdict: 'WATCHING', vColor: INK, lean: 'Recorded state before the shock',
      text: `On the fork, user ${user} borrows ${amt(b.debt)} ${loan} against ${qty(b.collateral_amount)} ${coll} at ${pct(b.ltv)} LTV. The owner's policy triggers at ${pct0(pol.trigger)}; the market liquidates at ${pct0(lltv)}. A keeper watches the position and can act only inside that policy.`,
      metrics: [['LTV', pct(b.ltv), `Trigger ${pct0(pol.trigger)} · LLTV ${pct0(lltv)}`, INK], ['DEBT', amt(b.debt), loan, INK], ['COLLATERAL', qty(b.collateral_amount), coll, INK],
        ['RESCUE RESERVE', qty(res.loan), `${loan}, plus ${qty(res.coll)} ${coll}`, CYAN], ['POLICY', Math.round((pol.validUntil - b.timestamp) / 86400) + ' d', 'Expiry · cooldown ' + Math.round(pol.cooldown / 3600) + ' h', INK], ['KEEPER', 'WATCHING', 'Recorded keeper state', INK]],
      driversTitle: 'DEPENDENCIES', drivers: [], noDrivers: 'This fork position is used to demonstrate Countermove. Its dependency chain is shown in the incident replay.',
      prot: { chipLabel: 'FORK DEMONSTRATION', short: 'Armed on a local fork with test funds. Not protecting anything on mainnet.', text: 'This policy is armed on a local fork with test funds. It demonstrates the mechanism; it does not protect any mainnet position.', action: 'replay' },
      simShort: `Replay recorded fork scenario ${p.scenario}, from shock to verified ${dec.decision === 'EXECUTE' ? 'execution' : 'outcome'}.`
    };
    ctx.db = {
      tint: 'rgba(43,184,255,.08)', status: 'Fork demo · watching', pillBg: 'rgba(43,184,255,.14)', pillC: CYAN, asOf: `Local Anvil fork · test funds · chain ${env.chain_id}`,
      headline: 'A test loan on a local fork, guarded by a policy set in advance.',
      rec: `User ${user} borrows ${amt(b.debt)} ${loan} against ${qty(b.collateral_amount)} ${coll}. If the loan-to-value rises above ${pct0(pol.trigger)}, the keeper may act from a ${qty(res.loan)} ${loan} reserve before the ${pct0(lltv)} liquidation line. Everything here uses test funds.`,
      visTitle: 'Loan-to-value today', visSub: 'How much of the collateral value is borrowed', isGauge: true,
      zones: [{ l: '0%', w: pc(pol.trigger * 100, L0, L1), c: 'rgba(43,184,255,.22)', r: '7px 0 0 7px' }, { l: pc(pol.trigger * 100, L0, L1), w: ((lltv - pol.trigger) * 100 / (L1 - L0) * 100).toFixed(2) + '%', c: 'rgba(255,181,71,.45)', r: '0' },
        { l: pc(lltv * 100, L0, L1), w: ((L1 - lltv * 100) / (L1 - L0) * 100).toFixed(2) + '%', c: 'rgba(255,106,61,.55)', r: '0 7px 7px 0' }],
      markers: [{ l: pc(b.ltv * 100, L0, L1), label: 'Now ' + pct0(b.ltv), c: INK, pos: 'bottom:32px' }, { l: pc(pol.trigger * 100, L0, L1), label: 'Policy acts ' + pct0(pol.trigger), c: CYAN, pos: 'top:32px' }, { l: pc(lltv * 100, L0, L1), label: 'Liquidation ' + pct0(lltv), c: EMBER, pos: 'bottom:32px' }],
      ticks: [{ l: '0.00%', label: L0 + '%', tf: 'none' }, { l: '100.00%', label: L1 + '%', tf: 'translateX(-100%)' }],
      visNote: `Between ${pct0(pol.trigger)} and ${pct0(lltv)} the keeper can act from the reserve. It cannot spend more than the policy allows.`,
      facts: [{ k: 'Debt', v: `${Math.round(b.debt).toLocaleString('en-US')} ${loan}`, s: 'Test funds', c: INK }, { k: 'Collateral', v: `${qty(b.collateral_amount)} ${coll}`, s: 'Test funds', c: INK }, { k: 'Rescue reserve', v: `${qty(res.loan)} ${loan}`, s: `Plus ${qty(res.coll)} ${coll}`, c: CYAN }],
      drivers: [], noDrivers: 'This fork position exists to demonstrate Countermove. Its dependency chain is shown step by step in the incident replay.', moreLabel: 'Open X-Ray',
      watch: [{ t: 'Nothing here touches mainnet. The shock in the replay was injected on purpose.', c: AMBER }], protTag: 'fork demo'
    };
    const ex = p.execution || {};
    ctx.pv = {
      facts: [['ENVIRONMENT', `Anvil fork · chain ${env.chain_id}`], ['FORKED AT', 'Ethereum block ' + blk(env.fork_block)], ['MORPHO BLUE', short(env.morpho_blue) + ' (real code, forked)'],
        ['MARKET', `${coll} / ${loan} · ${short(p.market_id)}`], ['RESCUEVAULT', short(p.rescue_vault) + ' (fork only)'], ['KEEPER', short(ex.signed_by || env.keeper) + ' (test account)'], ['FUNDS', 'Test balances written to storage']],
      routesTitle: 'COUNTERMOVE STRATEGIES', markets: null,
      routes: [['REPAY', `REPAY from the ${loan} reserve`, `cap ${qty(pol.repayCap)} ${loan} / action`, 'executeRepay on the RescueVault, repaying Morpho on behalf of the owner.'],
        ['TOP_UP', `TOP_UP from the ${coll} reserve`, `cap ${qty(pol.topupCap)} ${coll} / action`, 'executeTopUp, supplying collateral on behalf of the owner.'],
        ['FULL_REPAY', 'FULL_REPAY', `cap ${qty(pol.fullCap)} ${loan}`, 'executeFullRepay closes the debt when the reserve can cover it.']]
        .map(r => ({ name: r[1], val: pol.strategies.indexOf(r[0]) >= 0 ? r[2] : 'not allowed', note: r[3], status: pol.strategies.indexOf(r[0]) >= 0 && ex.strategy === r[0] ? 'FORK CONFIRMED' : pol.strategies.indexOf(r[0]) >= 0 ? 'FORK DEMONSTRATION' : 'NOT APPLICABLE' }))
    };
    ctx.arm = { eligible: true, fork: true, lltv: lltv * 100, ltv: b.ltv * 100, coll, loanSym: loan, debt: b.debt, loanDecimals: b.loan.decimals, collDecimals: b.collateral.decimals,
      ctxLine: `${coll} / ${loan} · LLTV ${pct0(lltv)} · current LTV ${pct(b.ltv)} · local fork`, pol, reserve: res, reqs: p.reserve_requirements || [], shockBps: (p.shock || {}).shock_bps };
    return ctx;
  }
  function forkTab(cm, scen) {
    const p = forkPos(cm, scen || 'S1'); if (!p) return null;
    const env = cm.environment || {}, pol = forkPolicy(p), ex = p.execution || {}, b = p.before, loan = b.loan.symbol, coll = b.collateral.symbol;
    const user = (String(p.label).match(/user ([A-Z])/) || [])[1] || '?';
    const verb = ex.strategy === 'TOP_UP' ? 'added' : 'repaid', what = ex.strategy === 'TOP_UP' ? `${qty(ex.amount)} ${ex.token} of collateral` : `${amt(ex.amount)} ${ex.token}`;
    return {
      kicker: `RECORDED FORK RUN · ${p.scenario} · TEST FUNDS`,
      text: `User ${user} armed a RescueVault on an Anvil fork of Ethereum (block ${blk(env.fork_block)}, chain ${env.chain_id}). A controlled −${((p.shock || {}).shock_bps / 100).toFixed(0)}% feed shock pushed the position over its trigger. The keeper ${verb} ${what} from the reserve and verified the result. ` + (p.user_signed_during_crisis === false ? 'The user signed nothing during the crisis.' : ''),
      trigger: 'LTV ' + pct0(pol.trigger), floor: 'LTV ' + pct0(pol.floor), actions: pol.strategies.map(s => STRAT[s] || s).join(' · ').replace(/^./, c => c.toUpperCase()),
      buffer: `${qty((p.decision || {}).safety_margin)} ${loan}`, caps: `${qty(pol.repayCap)} ${loan} · ${qty(pol.topupCap)} ${coll}`,
      totals: pol.repayTotal != null ? `${qty(pol.repayTotal)} ${loan} · ${qty(pol.topupTotal)} ${coll}` : `${qty((p.remaining_limits || {}).repay_budget_left + (ex.strategy !== 'TOP_UP' ? ex.amount || 0 : 0))} ${loan} · ${qty((p.remaining_limits || {}).top_up_budget_left + (ex.strategy === 'TOP_UP' ? ex.amount || 0 : 0))} ${coll}`,
      reserveAfter: `${amt((p.remaining_limits || {}).loan_reserve_left)} ${loan}`, expiry: `${Math.round((pol.validUntil - b.timestamp) / 86400)} days · ${Math.round(pol.cooldown / 3600)} h`
    };
  }
  const RN_POS = [['feed', 90, 90], ['ethusd', 90, 250], ['oracle', 300, 170], ['market', 510, 170], ['pos', 740, 170], ['keeper', 740, 300], ['vault', 510, 300]];
  const REDGES = [['feed', 'oracle'], ['ethusd', 'oracle'], ['oracle', 'market'], ['market', 'pos'], ['keeper', 'pos'], ['keeper', 'vault'], ['vault', 'market']];
  const RSTATE = [
    [{}, {}], [{ feed: 'threat' }, {}],
    [{ feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', ethusd: 'hypo' }, { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'ethusd-oracle': 'hypo' }],
    [{ feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', ethusd: 'hypo', keeper: 'defense' }, { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'ethusd-oracle': 'hypo', 'keeper-pos': 'defense' }],
    [{ feed: 'threat', oracle: 'threat', market: 'threat', pos: 'threat', keeper: 'defense', vault: 'defense' }, { 'feed-oracle': 'threat', 'oracle-market': 'threat', 'market-pos': 'threat', 'keeper-vault': 'defense' }],
    [{ feed: 'threat', oracle: 'threat', keeper: 'defense', vault: 'defense', market: 'defense', pos: 'defense' }, { 'feed-oracle': 'threat', 'keeper-vault': 'defense', 'vault-market': 'defense', 'market-pos': 'defense' }],
    [{ feed: 'threat', pos: 'defense', vault: 'defense' }, {}]];
  function replay(cm, scen) {
    const p = forkPos(cm, scen); if (!p || p.status !== 'CONFIRMED') return null;
    const b = p.before, cr = p.crisis || {}, cs = cr.snapshot || {}, dec = p.decision || {}, ex = p.execution || {}, af = p.after_snapshot || {}, val = p.validation || {};
    const loan = b.loan.symbol, coll = b.collateral.symbol, lltv = b.lltv || 0.86, res = forkReserve(p), pol = forkPolicy(p);
    const user = (String(p.label).match(/user ([A-Z])/) || [])[1] || '?', sh = p.shock || {};
    const fo = (dec.scenarios || []).find(s => s.id === 'follow_on') || {}, foShock = (fo.shocks || [])[0] || {};
    const breach = (cr.scenario_breaches || [])[0] || {}, chosen = (dec.candidates || []).find(c => c.status === 'eligible' && c.rank === 1) || {};
    const chosenFo = (chosen.scenarios_after || []).find(s => s.label === fo.label) || {};
    const tl = s => (p.timeline || []).find(t => t.state === s) || {};
    const exAfterLtv = (ex.after || {}).ltv != null ? ex.after.ltv : af.ltv, exAfterDebt = (ex.after || {}).debt != null ? ex.after.debt : af.debt;
    const resAfter = (p.remaining_limits || {}).loan_reserve_left;
    const checks = (ex.checks || []).filter(c => c.ok).length;
    const foTxt = fo.label ? fo.label.replace(' follow-on', '') : 'a follow-on drop';
    const steps = [
      { t: 'T0', title: 'Stable position', block: blk(b.block), chip: 'FORK STATE', body: `User ${user} borrows ${amt(b.debt)} ${loan} against ${qty(b.collateral_amount)} ${coll}. LTV ${pct(b.ltv)}. The owner armed a policy that triggers at ${pct0(pol.trigger)}; the market liquidates at ${pct0(lltv)}. The RescueVault holds ${amt(res.loan)} ${loan} and ${qty(res.coll)} ${coll}.`, ltv: pct(b.ltv), debt: amt(b.debt), reserve: amt(res.loan), state: 'WATCHING' },
      { t: 'T1', title: 'A dependency deteriorates', block: 'before ' + blk(tl('DETECTED').block || cs.block), chip: 'SIMULATED SHOCK', body: `The ${sh.original_description} feed is replaced on the fork with a value ${(sh.shock_bps / 100).toFixed(2)}% lower (anvil_setCode). This did not happen on mainnet.`, ltv: pct(b.ltv), debt: amt(b.debt), reserve: amt(res.loan), state: 'WATCHING' },
      { t: 'T2', title: 'The signal propagates', block: blk(cs.block), chip: 'MODELLED', body: `The Morpho oracle composes the shocked feed, so the collateral price falls ${pct(Math.abs(cr.oracle_change || 0))} and LTV reaches ${pct(cr.ltv)}. Countermove also tests a further ${foTxt} drop: the liquidation buffer would be ${amt(breach.buffer)} ${loan}, so the position would be liquidatable.`, ltv: pct(cr.ltv), debt: amt(cs.debt), reserve: amt(res.loan), state: 'WATCHING' },
      { t: 'T3', title: 'FAULTLINE detects the risk', block: blk(cs.block), chip: 'FORK OBSERVATION', body: `The keeper reads the position on-chain: LTV ${pct(cr.ltv)} is above the ${pct(cr.trigger_ltv)} trigger the owner set, and the follow-on scenario is liquidatable. State moves to DETECTED.`, ltv: pct(cr.ltv), debt: amt(cs.debt), reserve: amt(res.loan), state: 'DETECTED' },
      { t: 'T4', title: 'The decision engine evaluates actions', block: blk(val.validated_block || cs.block), chip: 'MODEL DECISION', body: `${dec.why} ${(val.checks || []).filter(c => c.ok).length} of ${(val.checks || []).length} pre-send checks pass.`, ltv: pct(cr.ltv), debt: amt(cs.debt), reserve: amt(res.loan), state: 'PLANNING → VALIDATING' },
      { t: 'T5', title: 'The defense is executed', block: blk(ex.block), chip: 'FORK CONFIRMED', body: `The keeper calls execute${ex.strategy === 'TOP_UP' ? 'TopUp' : ex.strategy === 'FULL_REPAY' ? 'FullRepay' : 'Repay'} on the RescueVault. Tx ${short(ex.tx_hash, 10)}, status 1, ${blk(ex.gas_used)} gas.` + (p.user_signed_during_crisis === false ? ' The user signed nothing during the crisis.' : ''), ltv: pct(exAfterLtv), debt: amt(exAfterDebt), reserve: amt(resAfter), state: 'EXECUTING → CONFIRMED' },
      { t: 'T6', title: 'Proof and outcome', block: blk(af.block), chip: 'VERIFIED ON FORK', body: `Verified from the receipt and events: ${checks} of ${(ex.checks || []).length} checks passed, the action matches the plan and the reserve moved by exactly the executed amount.` + (chosenFo.ltv != null ? ` Under the ${foTxt} follow-on the LTV would now be ${pct(chosenFo.ltv)}, below the ${pct0(lltv)} LLTV.` : ''), ltv: pct(af.ltv), debt: amt(af.debt), reserve: amt(resAfter), state: (p.timeline || []).slice(-1)[0] ? p.timeline.slice(-1)[0].state : 'WATCHING' }
    ].map((s, i) => Object.assign(s, { nodes: RSTATE[i][0], edges: RSTATE[i][1], ltvNum: parseFloat(s.ltv), trigger: (cr.trigger_ltv || pol.trigger) * 100 }));
    const subs = { feed: [String(sh.original_description || 'Price feed').replace(/ exchange rate$/, '').replace(/ Chainlink-compatible Oracle$/, '') + ' feed', 'shocked −' + (sh.shock_bps / 100).toFixed(2) + '%'],
      ethusd: [foShock.label && !/SIMULATED/.test(foShock.label) ? foShock.label + ' feed' : 'Further feed drop', 'follow-on −' + Math.round((foShock.drop || 0) * 100) + '% (hypothesis)'],
      oracle: ['Morpho oracle', `${coll} / ${loan}`], market: ['Morpho market', 'LLTV ' + pct0(lltv)], pos: ['Position · user ' + user, `${qty(b.collateral_amount)} ${coll} · ${loan} debt`],
      keeper: ['Keeper (off-chain)', 'test account #1'], vault: ['RescueVault', 'owner-funded reserve'] };
    const feedIcon = /weETH/i.test(sh.original_description || '') ? L + 'etherfi.webp' : /ETH/.test(sh.original_description || '') ? L + 'eth.svg' : /BTC/i.test(sh.original_description || '') ? L + 'btc.svg' : null;
    const foIcon = /ETH/.test(foShock.label || '') ? L + 'eth.svg' : /BTC/.test(foShock.label || '') ? L + 'btc.svg' : feedIcon;
    const icons = { feed: feedIcon, ethusd: foIcon, oracle: L + 'morpho.webp', market: L + 'morpho.webp', pos: iconFor('', coll) || (/^PT-/.test(coll) ? L + 'pendle.svg' : null), keeper: null, vault: null };
    return { scenario: p.scenario, steps, rnodes: RN_POS.map(r => ({ id: r[0], x: r[1], y: r[2], label: subs[r[0]][0], sub: subs[r[0]][1], icon: icons[r[0]] })), redges: REDGES, label: p.label };
  }
  function forkActivity(cm) {
    return ((cm && cm.positions) || []).map(p => {
      const ex = p.execution || {}, b = p.before, loan = b.loan.symbol, coll = b.collateral.symbol, conf = p.status === 'CONFIRMED';
      const user = (String(p.label).match(/user ([A-Z])/) || [])[1] || '?';
      return { id: 'f-' + p.scenario, kind: 'fork', title: conf ? `Fork execution ${p.scenario} · ${ex.strategy} ${ex.strategy === 'TOP_UP' ? qty(ex.amount) : amt(ex.amount)} ${ex.token}` : `Fork run ${p.scenario} · ${p.status === 'NO_ACTION' ? 'no action' : p.status.toLowerCase()}`,
        meta: (ex.block ? 'Fork block ' + blk(ex.block) + ' · ' : 'Fork · ') + 'chain ' + ((cm.environment || {}).chain_id || 31337), status: 'FORK CONFIRMED', result: p.status, tx: ex.tx_hash || null,
        fields: [['Position', `user ${user} · ${coll} / ${loan}`], ['Shock', `${(p.shock || {}).original_description} −${((p.shock || {}).shock_bps / 100).toFixed(2)}% (simulated)`]]
          .concat(conf ? [['LTV', `${pct((p.crisis || {}).ltv)} → ${pct((p.after_snapshot || {}).ltv)}`], ['Signed by', p.user_signed_during_crisis === false ? 'keeper; no user signature' : 'see journal'], ['Verification', `${(ex.checks || []).filter(c => c.ok).length} checks passed from receipt and events`]]
            : [['Outcome', ((p.decision || {}).why || 'No transaction sent').slice(0, 260)]]) };
    });
  }

  // ---------------------------------------------------------------- loaders
  const REC = { pt: '/data/recorded/analyze-pt.json', borrow: '/data/recorded/analyze-borrower.json', vault: '/data/recorded/vault-belem.json' };
  function loadDemo() {
    const get = u => getJson(u, { timeout: 30000 }).then(r => (r.ok && r.body ? r.body : Promise.reject(Object.assign(new Error(errText(r)), { res: r, url: u }))));
    return Promise.allSettled([get(REC.pt), get(REC.vault), get(REC.borrow), get('/api/countermove')]).then(([pt, vault, borrow, cm]) => {
      const ctx = {}, errors = {};
      if (pt.status === 'fulfilled') ctx.pt = fromAnalyze(pt.value, { mode: 'recorded', id: 'pt' }); else errors.pt = pt.reason.message;
      if (vault.status === 'fulfilled') ctx.vault = fromVault(vault.value, { mode: 'recorded', id: 'vault' }); else errors.vault = vault.reason.message;
      if (borrow.status === 'fulfilled') ctx.borrow = fromAnalyze(borrow.value, { mode: 'recorded', id: 'borrow' }); else errors.borrow = borrow.reason.message;
      const cmBody = cm.status === 'fulfilled' && cm.value.status === 'ok' ? cm.value : null;
      if (cmBody) ctx.fork = fromFork(cmBody, 'S1'); else errors.fork = cm.status === 'fulfilled' ? (cm.value.message || 'no recorded fork run') : cm.reason.message;
      return { ctx, cm: cmBody, errors };
    });
  }

  // Look up a pasted identifier without running the full analysis (backend ?lookup=1: factory checks / market match).
  function lookup(q) {
    q = String(q || '').trim();
    if (q.length === 42) {
      return getJson('/api/vault?lookup=1&address=' + encodeURIComponent(q), { timeout: 25000 }).then(r => {
        if (r.ok && r.body && r.body.kind === 'vault') {
          const v = r.body;
          return { status: 'found', cand: { id: 'live-vault', kind: 'vault', name: v.name || short(v.address), sub: `Morpho Vault ${(v.version || '').toUpperCase()} · asset ${v.asset_symbol || '?'}`,
            protocol: 'Morpho Vault ' + (v.version || '').toUpperCase(), network: 'Ethereum', ident: 'Vault ' + short(v.address), identFull: v.address, size: '$1,000,000 hypothetical deposit',
            assets: `${v.symbol || 'vault'} shares · ${v.asset_symbol || '?'}`, source: 'LIVE', sourceNote: `Recognized at block ${blk(v.block)} · full analysis runs live on start`,
            can: [['Analyze', 'Yes, live (about 10 to 40 s)'], ['Simulate attack', 'Vault scenarios are in the backend payload; no designed view yet'], ['Arm protection', 'Not applicable: deposit']],
            run: '/api/vault?address=' + encodeURIComponent(v.address) + '&value_usd=1000000&horizon_days=30' } };
        }
        if (r.status === 404 || r.status === 422) return { status: 'unsupported', msg: (r.status === 404 ? 'No contract at this address on Ethereum mainnet.' : 'Not a Morpho vault: the V1 and V2 factory checks both returned false (422 unsupported_contract).') + ' If this is a wallet, FAULTLINE cannot list its positions automatically. Paste the market id it borrows on instead.' };
        if (r.status === 400) return { status: 'invalid', msg: errText(r) };
        return { status: 'error', msg: errText(r) };
      });
    }
    return getJson('/api/analyze?lookup=1&ref=morpho:1:' + encodeURIComponent(q.toLowerCase()), { timeout: 25000 }).then(r => {
      if (r.ok && r.body && r.body.kind === 'pt_market') {
        const m = r.body;
        return { status: 'found', cand: { id: 'live-pt', kind: 'pt', name: m.pt_symbol || m.label, sub: `Pendle PT collateral market on Morpho Blue · ${m.loan_symbol}`, protocol: 'Morpho Blue · Pendle', network: 'Ethereum',
          ident: 'Market ' + short(m.market_id, 10), identFull: m.market_id, size: '$1,000,000 hypothetical PT exposure, unlevered', assets: `${m.pt_symbol} · ${m.loan_symbol}`, source: 'LIVE',
          sourceNote: `Recognized from the Pendle and Morpho APIs · full analysis runs live on start`,
          can: [['Analyze', 'Yes, live (about 30 s)'], ['Simulate attack', 'Yes'], ['Arm protection', 'Not applicable: no debt']],
          run: '/api/analyze?ref=' + encodeURIComponent('morpho:1:' + m.market_id) + '&value_usd=1000000' } };
      }
      if (r.status === 404) return { status: 'unsupported', msg: 'Valid market id, but it is not in the supported set. FAULTLINE currently covers Morpho Blue markets that take a Pendle PT as collateral.' + (r.body && r.body.error ? ' (' + (r.body.error.message || r.body.error) + ')' : '') };
      if (r.status === 400) return { status: 'invalid', msg: errText(r) };
      return { status: 'error', msg: errText(r) };
    });
  }
  function runLive(cand) {
    const t0 = Date.now(), url = cand.run;
    const p = getJson(url, { timeout: 75000 });
    return p.then(r => {
      if (!r.ok || !r.body) throw Object.assign(new Error(errText(r)), { res: r });
      const elapsed = (Date.now() - t0) / 1000;
      return /^\/api\/vault/.test(url) ? fromVault(r.body, { mode: 'live', id: cand.id, elapsed }) : fromAnalyze(r.body, { mode: 'live', id: cand.id, elapsed });
    });
  }

  // ---------------------------------------------------------------- Countermove policy: backend validation and live dry run
  function policyParams(arm, pol, withReserves) {
    const on = pol.order.filter(k => pol.on[k]);
    const q = { strategies: on.join(','), trigger_ltv: (pol.trigger / 100).toFixed(4), min_ltv_after: (pol.minAfter / 100).toFixed(4), lltv: (arm.lltv / 100).toFixed(4),
      max_repay_per_action: pol.repayCap, max_top_up_per_action: pol.topupCap, max_full_repay: pol.fullCap, max_repay_total: pol.repayTotal, max_top_up_total: pol.topupTotal,
      min_loan_reserve: pol.minLoan || 0, min_collateral_reserve: pol.minColl || 0, valid_days: pol.expiry, cooldown_s: Math.round(pol.cooldown * 3600),
      loan_decimals: arm.loanDecimals, collateral_decimals: arm.collDecimals };
    if (withReserves) Object.assign(q, { loan_reserve: pol.loanRes, collateral_reserve: pol.collRes, safety_margin: pol.buffer, follow_on_drop: (pol.followOn / 100).toFixed(4) });
    return q;
  }
  const qs = o => Object.keys(o).filter(k => o[k] !== '' && o[k] != null).map(k => encodeURIComponent(k) + '=' + encodeURIComponent(o[k])).join('&');
  function policyDraft(arm, pol) { return getJson('/api/countermove?action=policy-draft&' + qs(policyParams(arm, pol, false)), { timeout: 20000 }); }
  function dryRun(arm, pol) {
    const q = policyParams(arm, pol, true);
    ['lltv', 'loan_decimals', 'collateral_decimals'].forEach(k => delete q[k]);
    q.market = arm.marketId; q.borrower = arm.borrower;
    return getJson('/api/countermove?action=dry-run&' + qs(q), { timeout: 45000 });
  }

  window.FLX = { F, getJson, errText, graphFromAnalyze, fromAnalyze, fromVault, fromFork, forkTab, replay, forkActivity, loadDemo, lookup, runLive, policyDraft, dryRun, policyParams,
    COLS, colors: { INK, MUTE, CYAN, EMBER, AMBER } };
})();
