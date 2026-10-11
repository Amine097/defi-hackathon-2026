/* FAULTLINE app logic: the <script data-dc-script> class of docs/design/claude-design-v2/Faultline App.dc.html, wired
   to the real backend through window.FLX (/assets/dc/fl-live.js). State machine, timings, animations, render-value
   shapes and copy follow the export; every figure now comes from a backend payload (live, or a recorded live run that
   is labelled as such) instead of the prototype's faultline-data.js. The browser computes no financial value. */
FLRegister(function (DCLogic, React) {
const CH = {
  ink: ['#e9edf2', 'rgba(233,237,242,.35)', 'transparent'],
  amber: ['#ffb547', 'rgba(255,181,71,.5)', 'rgba(255,181,71,.07)'],
  cyan: ['#2bb8ff', 'rgba(43,184,255,.5)', 'rgba(43,184,255,.07)'],
  ember: ['#ff6a3d', 'rgba(255,106,61,.5)', 'rgba(255,106,61,.07)'],
  mute: ['#8a94a3', 'rgba(138,148,163,.4)', 'transparent'],
  solid: ['#05070b', '#e9edf2', '#e9edf2']
};
const CHMAP = { 'RECORDED LIVE RUN': 'ink', 'FORK STATE': 'ink', 'HISTORICAL DATA': 'ink', 'LOCAL FORK': 'amber', 'SIMULATED': 'amber', 'SIMULATED SHOCK': 'ember', 'MODELLED': 'amber', 'DRY RUN': 'amber', 'PREVIEW ONLY': 'amber', 'POLICY PREVIEW': 'amber', 'THIS SESSION': 'amber', 'INDICATIVE': 'amber', 'FORK CONFIRMED': 'cyan', 'VERIFIED ON FORK': 'cyan', 'FORK OBSERVATION': 'cyan', 'MODEL DECISION': 'cyan', 'AVAILABLE': 'cyan', 'FORK DEMONSTRATION': 'cyan', 'MAINNET CONFIRMED': 'solid', 'UNAVAILABLE': 'mute', 'NOT APPLICABLE': 'mute', 'PENDING': 'mute', 'DESIGN TARGET': 'mute', 'NOT MONITORING': 'mute', 'LIVE': 'cyan', 'RECOGNIZED': 'cyan', 'LOCAL TEST': 'amber', 'HASH CHAIN VALID': 'cyan', 'HASH CHAIN BROKEN': 'ember' };
const chip = l => { const c = CH[CHMAP[l] || 'mute']; return { label: l, fg: c[0], bd: c[1], bg: c[2] }; };
const X = window.FLX, Fm = X.F;
const usd = Fm.usd;
const AMBER = '#ffb547', CYAN = '#2bb8ff', EMBER = '#ff6a3d', INK = '#e9edf2', MUTE = '#8a94a3';
const PT_MARKET = '0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64';
const DEMO_IDS = ['pt', 'vault', 'borrow', 'fork'];
const QA = /[?&]qa=1\b/.test(location.search);

class Component extends DCLogic {
  state = {
    ready: false, ctxs: {}, cm: null, demoErr: {}, liveCand: null, loadLive: false, loadT0: 0, now: 0,
    screen: 'select', query: '', lk: { status: 'idle' }, candId: null, posId: 'pt', pvId: null,
    section: 'dashboard', loadStep: 0, width: typeof innerWidth === 'number' ? innerWidth : 1280,
    xrMode: 'inspect', xrView: 'graph', revealed: false, selNode: null,
    simKind: 'node', simNode: null, simScen: 0, simStep: -1, simDone: false,
    rpStep: 0, rpPlaying: false, rpScen: 'S1',
    armTab: 'preview', armPos: null, policy: null, dry: null, dryBusy: false, dep: null,
    session: [], actFilter: 'all', actSel: 'f-S1'
  };

  componentDidMount() {
    this.onResize = () => this.setState({ width: innerWidth });
    addEventListener('resize', this.onResize);
    this.depLoad();
    X.loadDemo().then(({ ctx, cm, errors }) => {
      this.setState({ ready: true, ctxs: ctx, cm, demoErr: errors });
      const h = (location.hash || '').replace('#', '');
      const start = h || this.props.startAt || 'select';
      if (start !== 'select') this.jump(start);
    });
  }
  componentDidUpdate() { this.fixSvg(); }
  fixSvg() { try { document.querySelectorAll('svg[data-vb]').forEach(s => { if (s.getAttribute('viewBox') !== s.dataset.vb) s.setAttribute('viewBox', s.dataset.vb); }); } catch (e) {} }
  componentWillUnmount() {
    removeEventListener('resize', this.onResize);
    clearInterval(this.loadT); clearTimeout(this.lkT); clearTimeout(this.lkT2); clearInterval(this.simT); clearInterval(this.rpT); clearInterval(this.tickT); clearInterval(this.depT);
  }
  reduced() { return !!this.props.reduceMotion || (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches); }
  ctx(id) { return this.state.ctxs[id || this.state.posId] || null; }
  jump(where) {
    const map = { demo: ['pt', 'dashboard'], dashboard: ['pt', 'dashboard'], positions: ['vault', 'positions'], xray: ['pt', 'xray'], simulate: ['pt', 'xray', 'simulate'], replay: ['fork', 'xray', 'replay'], arm: ['fork', 'countermove'], autonomous: ['fork', 'countermove'], activity: ['pt', 'activity'] };
    const m = map[where] || map.demo;
    const id = this.state.ctxs[m[0]] ? m[0] : DEMO_IDS.find(k => this.state.ctxs[k]);
    if (!id) return;
    if (where === 'demo') { this.setState({ posId: id, candId: id }, () => this.startAnalysis()); return; }
    if (where === 'autonomous') { this.setState({ armTab: 'deployed' }); this.depWatch(); }
    this.setState({ screen: 'app', posId: id, section: m[1], xrMode: m[2] || 'inspect', revealed: !!m[2] });
  }
  // ---------- autonomous protection: hosted keeper status, read server-side by /api/countermove (G18-G20) ----------
  depLoad() {
    if (this.depBusy) return;
    this.depBusy = true;
    const B = '/api/countermove?action=', o = { timeout: 15000 };
    const KINDS = 'lifecycle,transition,trigger,decision,rejected_strategy,validation,execution_attempt,receipt,verification,finality,failure,error';
    Promise.all([X.getJson(B + 'keeper-status', o), X.getJson(B + 'policy-status', o), X.getJson(B + 'evidence&source=store&limit=500&kinds=' + KINDS, o)])
      .then(([k, p, e]) => this.setState({ dep: { k, p, e, at: Date.now() } }))
      .catch(() => {})
      .then(() => { this.depBusy = false; });
  }
  depWatch() {
    clearInterval(this.depT);
    this.depLoad();
    this.depT = setInterval(() => {
      if (this.state.armTab !== 'deployed' || this.state.section !== 'countermove') { clearInterval(this.depT); return; }
      if (!document.hidden) this.depLoad();
    }, 5000);
  }
  depVals() {
    const d = this.state.dep, F = Fm;
    const body = r => (r && r.ok && r.body ? r.body : null);
    const k = body(d && d.k), p = body(d && d.p), e = body(d && d.e);
    const hosted = !!(k && k.hosted && k.hosted.status === 'ok');
    const h = (k && k.health) || {};
    const live = hosted && !!p && !!p.state;
    const stC = s => /^(MONITORING|VERIFIED|ARMED|CONFIRMED)$/.test(s) ? CYAN : /^(DETECTED|EXECUTING|PLANNING|VALIDATING|SUBMITTED|AWAITING|ARMED_NOT)/.test(s) ? AMBER : /^(FAILED|PAUSED|REVOKED|EXPIRED)$/.test(s) ? EMBER : MUTE;
    const why = (k && k.reason) || (k && k.hosted && k.hosted.reason) || 'No keeper service answered.';
    if (!live) {
      const no = t => ({ t, d: '', v: 'NO', c: EMBER });
      return { live: false, kicker: 'DESIGN TARGET · NOT AVAILABLE YET', kC: MUTE, bd: '1px dashed rgba(233,237,242,.25)', op: '.55',
        text: 'In the deployed product, this view shows the live policy, the reserve, the last block checked and every action taken. The status reads as protected only when all four requirements below are verified on-chain. Today none of them are met.',
        gates: [no('RescueVault deployed and source-verified on mainnet'), no('Reserves funded by the owner'), no('Keeper monitoring running and reporting'), no('Owner policy and keeper confirmed on-chain')],
        panelTitle: 'WIREFRAME OF THE FUTURE STATUS PANEL', rows: [['Status', 'UNAVAILABLE'], ['Last block checked', '—'], ['Reserve', '—'], ['Remaining limits', '—'], ['Policy expires', '—']].map(r => ({ k: r[0], v: r[1], c: MUTE })),
        note: 'Keeper: ' + F.sentence(why), events: [], hasEvents: false, integ: chip('UNAVAILABLE'), integText: '' };
    }
    const A = p.assets || {}, L = A.loan || { symbol: 'loan', decimals: 18 }, C = A.collateral || { symbol: 'collateral', decimals: 18 };
    const u = (v, t) => (Number(v || 0) / Math.pow(10, t.decimals)).toLocaleString('en-US', { maximumFractionDigits: t.decimals > 8 ? 4 : 2 }) + ' ' + t.symbol;
    const v = p.vault || {}, pol = v.policy || {};
    const GL = { vault_code: 'RescueVault contract deployed (test chain)', not_revoked: 'Owner has not revoked the policy', policy_signed: 'Owner policy signed on-chain', not_paused: 'Vault not paused', not_expired: 'Policy not expired', keeper_authorized: 'This keeper is authorized by the owner', reserves_sufficient: 'Reserves sufficient for a requested action', keeper_heartbeat: 'Keeper monitoring running and reporting' };
    const GD = { not_expired: () => 'valid until ' + F.date(pol.valid_until), keeper_heartbeat: g => (g.detail || '') + ' · last heartbeat ' + F.ago(h.heartbeat_age_s) + ', stale after ' + (h.stale_after_s || '—') + ' s' };
    const gates = (p.gates || []).map(g => ({ t: GL[g.gate] || (g.gate.charAt(0).toUpperCase() + g.gate.slice(1).replace(/_/g, ' ')), d: GD[g.gate] ? GD[g.gate](g) : g.detail || '', v: g.ok === true ? 'YES' : g.ok === false ? 'NO' : 'NOT CHECKED', c: g.ok === true ? CYAN : g.ok === false ? EMBER : MUTE }));
    gates.push({ t: 'RescueVault deployed on Ethereum mainnet', d: 'Not deployed. This keeper only acts on its own test chain.', v: 'NO', c: EMBER });
    const head = h.head || {};
    const rows = [
      { k: 'Status', v: p.state.replace(/_/g, ' '), c: stC(p.state) },
      { k: 'Keeper', v: k.status + ' · heartbeat ' + F.ago(h.heartbeat_age_s), c: k.status === 'OK' ? CYAN : EMBER },
      { k: 'Last block checked', v: F.blk(head.number) + ' · chain ' + (h.chain_id || '—'), c: INK },
      { k: 'Reserve', v: u(v.loan_reserve, L) + ' · ' + u(v.collateral_reserve, C), c: INK },
      { k: 'Remaining limits', v: 'repay ' + u(Number(pol.max_repay_total || 0) - Number(v.repaid_total || 0), L) + ' · top-up ' + u(Number(pol.max_top_up_total || 0) - Number(v.topped_up_total || 0), C), c: INK },
      { k: 'Actions executed', v: String(v.action_count != null ? v.action_count : '—'), c: INK },
      { k: 'Policy expires', v: F.date(pol.valid_until), c: INK }
    ];
    const st = (e && e.store) || {}, ig = st.integrity || {};
    const now = Date.now() / 1000;
    const events = (st.events || []).slice(-8).reverse().map(r => ({ t: (r.kind || 'event').replace(/_/g, ' '), s: r.state || '', c: stC(r.state || ''),
      m: '#' + r.seq + ' · ' + (r.block != null ? 'block ' + F.blk(r.block) + ' · ' : '') + (r.tx_hash ? 'tx ' + F.short(r.tx_hash, 10) + ' · ' : '') + F.ago(now - r.ts) }));
    return { live: true, kicker: 'LOCAL TEST CHAIN · HOSTED KEEPER', kC: AMBER, bd: '1px solid rgba(255,181,71,.4)', op: '1',
      text: 'A keeper runs around the clock on a hosted test chain (chain ' + (h.chain_id || 31337) + ', test tokens, a simulated ETH/USD feed) and watches one RescueVault test position the owner authorized once. Every state below is read from that chain now. This is not Ethereum mainnet: no real position is protected.',
      gates, panelTitle: 'STATUS · ' + (k.hosted.host || 'hosted keeper'), rows,
      note: F.sentence(p.reason || '', 2).replace(/([^.])$/, '$1.') + ' Updated ' + F.ago((Date.now() - d.at) / 1000) + ', refreshed every 5 s.',
      events, hasEvents: events.length > 0, integ: chip(ig.ok ? 'HASH CHAIN VALID' : ig.ok === false ? 'HASH CHAIN BROKEN' : 'UNAVAILABLE'),
      integText: (ig.rows != null ? ig.rows + ' evidence rows' : st.reason || '') + (ig.head ? ' · head ' + F.short(ig.head, 10) : '') };
  }
  scrollTop() { try { scrollTo({ top: 0 }); } catch (e) {} }
  go(section, extra) { this.stopSim(); this.setState(Object.assign({ section }, extra || {})); this.scrollTop(); }

  // ---------- select / lookup (real backend lookups; the two simulated states exist only with ?qa=1) ----------
  lookup(q, mode) {
    clearTimeout(this.lkT); clearTimeout(this.lkT2);
    const seq = this.lkSeq = (this.lkSeq || 0) + 1;
    q = (q || '').trim().toLowerCase();
    if (mode === 'error') { this.setState({ lk: { status: 'checking' } }); this.lkT = setTimeout(() => this.setState({ lk: { status: 'error', msg: 'QA state: simulated network error.' } }), 900); return; }
    if (mode === 'slow') { this.setState({ lk: { status: 'slow', t0: Date.now() } }); this.lkT = setTimeout(() => this.setState({ lk: { status: 'slow2' } }), 3500); return; }
    if (!q) { this.setState({ lk: { status: 'idle' } }); return; }
    if (!/^0x[0-9a-f]*$/.test(q)) { this.setState({ lk: { status: 'invalid', msg: 'That is not a 0x address or market id.' } }); return; }
    if (q.length !== 42 && q.length !== 66) { this.setState({ lk: { status: 'invalid', msg: 'Length does not match an address (42 characters) or a Morpho market id (66 characters).' } }); return; }
    if (/^0x0+$/.test(q)) { this.setState({ lk: { status: 'invalid', msg: 'The null address cannot hold a position.' } }); return; }
    this.setState({ lk: { status: 'checking', kind: q.length === 42 ? 'address' : 'market' } });
    this.lkT = setTimeout(() => { if (this.lkSeq === seq) this.setState({ lk: { status: 'slow', kind: this.state.lk.kind } }); }, 3500);
    this.lkT2 = setTimeout(() => { if (this.lkSeq === seq) this.setState({ lk: { status: 'slow2' } }); }, 15000);
    X.lookup(q).then(res => {
      if (this.lkSeq !== seq) return;
      clearTimeout(this.lkT); clearTimeout(this.lkT2);
      if (res.status === 'found') this.setState({ lk: { status: 'found', name: res.cand.name }, liveCand: res.cand, candId: res.cand.id });
      else this.setState({ lk: { status: res.status, msg: res.msg } });
    });
  }
  candidate(id) {
    if (!id) return null;
    const c = this.state.ctxs[id];
    if (c) return c;
    const lc = this.state.liveCand;
    return lc && lc.id === id ? lc : null;
  }
  startAnalysis() {
    const id = this.state.candId || 'pt';
    clearInterval(this.loadT); clearInterval(this.tickT);
    const lc = this.state.liveCand;
    if (lc && lc.id === id && lc.run) {
      // LIVE: one real backend request; no per-step progress exists, so steps are not ticked off one by one.
      this.setState({ posId: this.state.ctxs[id] ? id : this.state.posId, screen: 'loading', loadLive: true, loadStep: -1, loadT0: Date.now(), now: Date.now(), loadName: lc.name });
      this.tickT = setInterval(() => this.setState({ now: Date.now() }), 1000);
      X.runLive(lc).then(ctx => {
        clearInterval(this.tickT);
        this.setState(s => ({ ctxs: Object.assign({}, s.ctxs, { [id]: ctx }), loadStep: 6, posId: id }));
        setTimeout(() => { this.setState({ screen: 'app', section: 'dashboard', xrMode: 'inspect', selNode: null, simNode: null, loadLive: false }); this.scrollTop(); }, this.reduced() ? 0 : 500);
      }).catch(err => {
        clearInterval(this.tickT);
        this.setState({ screen: 'select', loadLive: false, lk: { status: 'error', msg: 'The analysis failed: ' + err.message } });
      });
      return;
    }
    if (!this.state.ctxs[id]) return;
    if (this.reduced()) { this.setState({ posId: id, screen: 'app', section: 'dashboard', loadStep: 9, simNode: null }); return; }
    this.setState({ posId: id, screen: 'loading', loadLive: false, loadStep: 0, simNode: null });
    this.loadT = setInterval(() => {
      const n = this.state.loadStep + 1;
      if (n > 6) { clearInterval(this.loadT); this.setState({ screen: 'app', section: 'dashboard', xrMode: 'inspect', selNode: null }); this.scrollTop(); return; }
      this.setState({ loadStep: n });
    }, 420);
  }

  // ---------- simulation (results are backend stress-table and scenario values) ----------
  stopSim() { clearInterval(this.simT); clearInterval(this.rpT); if (this.state.rpPlaying) this.setState({ rpPlaying: false }); }
  simNodeId(p) { p = p || this.ctx(); const G = p && p.G; if (!G) return null; const s = this.state.simNode; if (s && G.NODES.some(n => n.id === s)) return s; const u = G.NODES.find(n => n.id === 'underlying'); return (u || G.NODES.find(n => n.id !== 'pos')).id; }
  simTargets(p) { p = p || this.ctx(); return this.state.simKind === 'node' ? [this.simNodeId(p)] : ((p.scen[this.state.simScen] || p.scen[0] || {}).targets || []); }
  simOrder(p) {
    p = p || this.ctx(); const ord = {};
    this.simTargets(p).forEach(id => { const n = p.G.NODES.find(x => x.id === id); if (!n) return; const P = n.path; P.forEach((pid, i) => { const o = P.length - 1 - i; ord[pid] = ord[pid] == null ? o : Math.min(ord[pid], o); }); });
    return ord;
  }
  launchSim() {
    clearInterval(this.simT);
    const ord = this.simOrder(); const max = Math.max.apply(null, Object.values(ord).concat([0]));
    if (this.reduced()) { this.setState({ simStep: max, simDone: true, revealed: true }); this.logSim(); return; }
    this.setState({ simStep: 0, simDone: false, revealed: true });
    this.simT = setInterval(() => {
      const s = this.state.simStep + 1;
      if (s > max) { clearInterval(this.simT); this.setState({ simDone: true }); this.logSim(); return; }
      this.setState({ simStep: s });
    }, 800);
  }
  logSim() {
    const r = this.simResult(), p = this.ctx();
    this.setState(s => ({ session: [{ id: 's' + Date.now(), kind: 'sim', title: 'Simulation · ' + r.name, meta: 'This session · ' + (p.mode === 'live' ? 'live' : 'recorded') + ' backend values · block ' + Fm.blk(p.block), status: 'SIMULATED', result: r.verdict + ' · ' + usd(r.loss), fields: [['Shock', r.desc], ['Conditional loss if you stay', usd(r.loss)], ['Exit side', usd(r.exit)], ['Armed, signed or spent', 'Nothing']] }].concat(s.session) }));
  }
  simResult(p) {
    p = p || this.ctx();
    const fmtSev = v => (+v).toFixed(v < 0.1 ? 4 : 2);
    if (this.state.simKind === 'node') {
      const n = p.G.NODES.find(x => x.id === this.simNodeId(p));
      const exit = Fm.fin(n.exitTotal) ? n.exitTotal : p.exitTotal;
      return { name: n.short + ' fails', desc: n.label + ' at severity ' + fmtSev(n.sev) + ' (node default)', loss: n.cond, exec: p.exec, carry: p.carry, exit, mult: exit ? n.cond / exit : 0, verdict: n.verdictIf, sev: fmtSev(n.sev), T: n.T, node: n };
    }
    const s = p.scen[this.state.simScen] || p.scen[0];
    return { name: s.name, desc: s.desc, loss: s.loss, exec: s.exec, carry: s.carry, exit: s.exit, mult: s.mult, verdict: s.verdict, sev: s.sev, stressed: s.stressed, notes: s.notes };
  }
  allPaths(target, p) {
    const G = (p || this.ctx()).G, out = [];
    const walk = (cur, path) => { if (cur === target) { out.push(path); return; } G.EDGES.forEach(e => { if (e[0] === cur && path.indexOf(e[1]) < 0) walk(e[1], path.concat(e[1])); }); };
    walk('pos', ['pos']);
    return out.map(q => { let t = 1; for (let i = 0; i < q.length - 1; i++) t *= G.EDGES.find(e => e[0] === q[i] && e[1] === q[i + 1])[2]; return { p: q, t }; }).sort((a, b) => b.t - a.t);
  }

  // ---------- replay (recorded local-fork runs S1 and S5) ----------
  replayData() { const s = this.state.rpScen; if (s === 'SVB') return null; this.rpCache = this.rpCache || {}; if (!(s in this.rpCache)) this.rpCache[s] = this.state.cm ? X.replay(this.state.cm, s) : null; return this.rpCache[s]; }
  playReplay() {
    clearInterval(this.rpT);
    const rd = this.replayData(); if (!rd) return;
    const last = rd.steps.length - 1;
    if (this.reduced()) { this.setState({ rpStep: last, rpPlaying: false }); return; }
    this.setState({ rpStep: 0, rpPlaying: true });
    this.rpT = setInterval(() => {
      const s = this.state.rpStep + 1;
      if (s > last) { clearInterval(this.rpT); this.setState({ rpPlaying: false }); return; }
      this.setState({ rpStep: s });
    }, 2600);
  }

  // ---------- policy defaults come from the backend (recorded fork policy, or the borrower's suggested policy) ----------
  defaultPolicy(p) {
    const a = p.arm || {};
    if (a.fork) {
      const pol = a.pol, res = a.reserve, on = {}; ['REPAY', 'TOP_UP', 'FULL_REPAY'].forEach(k => { on[k] = pol.strategies.indexOf(k) >= 0; });
      const fo = (((p.payload.decision || {}).scenarios || []).find(s => s.id === 'follow_on') || {}).shocks || [];
      return { trigger: +(pol.trigger * 100).toFixed(1), followOn: Math.round(((fo[0] || {}).drop || 0.08) * 100), buffer: (p.payload.decision || {}).safety_margin || 250, minAfter: Math.round(pol.floor * 100),
        loanRes: res.loan, collRes: res.coll, repayCap: pol.repayCap, topupCap: pol.topupCap, fullCap: pol.fullCap, repayTotal: pol.repayTotal != null ? pol.repayTotal : 30000, topupTotal: pol.topupTotal != null ? pol.topupTotal : pol.topupCap,
        expiry: Math.round((pol.validUntil - p.payload.before.timestamp) / 86400), cooldown: Math.round(pol.cooldown / 3600), minLoan: pol.minLoan, minColl: pol.minColl, order: ['REPAY', 'TOP_UP', 'FULL_REPAY'], on };
    }
    const s = a.suggestion || {}, rd = ((p.payload.liquidation || {}).countermove_suggestion || {}).reserve_to_deposit || {};
    const st = String(s.strategies || 'REPAY,TOP_UP').split(',');
    const r2 = v => Math.round(v * 100) / 100;
    return { trigger: +((s.trigger_ltv || 0.82) * 100).toFixed(1), followOn: 8, buffer: 250, minAfter: +((s.min_ltv_after || 0.4) * 100).toFixed(1),
      loanRes: r2(rd.loan_token || 0), collRes: r2(rd.collateral_token || 0), repayCap: r2(s.max_repay_per_action || 0), topupCap: r2(s.max_top_up_per_action || 0), fullCap: r2(s.max_full_repay || 0),
      repayTotal: r2(s.max_repay_total || 0), topupTotal: r2(s.max_top_up_total || 0), expiry: s.valid_days || 30, cooldown: 1, minLoan: s.min_loan_reserve || 0, minColl: s.min_collateral_reserve || 0,
      order: ['REPAY', 'TOP_UP', 'FULL_REPAY'], on: { REPAY: st.indexOf('REPAY') >= 0, TOP_UP: st.indexOf('TOP_UP') >= 0, FULL_REPAY: st.indexOf('FULL_REPAY') >= 0 } };
  }

  // ---------- render ----------
  renderVals() {
    const st = this.state;
    const F = st.ready;
    const wide = st.width >= 900;
    const base = {
      isSelect: !F || st.screen === 'select', isLoading: !!F && st.screen === 'loading', isApp: !!F && st.screen === 'app' && !!this.ctx(),
      wide, narrow: !wide, bottomPad: wide ? '0px' : '64px', query: st.query
    };
    if (!F) return Object.assign(base, { lk: { border: 'rgba(233,237,242,.2)', color: MUTE, msg: 'Loading recorded runs from the backend…', spinning: true }, cands: [], demoInputs: [], cand: null, nav: [], sec: {}, pos: {}, dash: {}, db: {}, modeBox: {} });

    // lookup message
    const L = st.lk;
    const lkMap = {
      idle: [MUTE, 'rgba(233,237,242,.2)', 'Paste an identifier, or pick a demonstration position.'],
      checking: [INK, CYAN, L.kind === 'market' ? 'Matching the market id against Pendle and Morpho market lists…' : 'Reading contract code and factory registries at the latest block…'],
      found: [CYAN, CYAN, 'Recognized: ' + (L.name || '') + '. Review it on the right, then start the analysis.'],
      invalid: [EMBER, EMBER, L.msg || ''],
      unsupported: [AMBER, AMBER, L.msg || ''],
      error: [EMBER, EMBER, (L.msg || 'Network error.') + ' Nothing was analysed. You can retry, or use a demonstration position.'],
      slow: [INK, CYAN, 'Reading on-chain state. Live reads usually take a few seconds, sometimes up to 40 s…'],
      slow2: [INK, CYAN, 'Still working. Public RPC endpoints can be slow. You can keep this tab open or cancel.']
    };
    const lm = lkMap[L.status] || lkMap.idle;
    const lk = { color: lm[0], border: lm[1], msg: lm[2], spinning: L.status === 'checking' || L.status === 'slow' || L.status === 'slow2', retry: L.status === 'error' || L.status === 'slow2' };

    const candChip = p => chip(p.kind === 'fork' ? 'LOCAL FORK' : p.source === 'LIVE' ? 'LIVE' : 'RECORDED LIVE RUN');
    const cands = DEMO_IDS.filter(id => st.ctxs[id]).map(id => { const p = st.ctxs[id]; const on = st.candId === id; return { name: p.name, sub: p.sub, chip: candChip(p), bg: on ? 'rgba(43,184,255,.06)' : 'transparent', bar: on ? CYAN : 'transparent', pick: () => this.setState({ candId: id }) }; });
    const cp = this.candidate(st.candId);
    const cand = cp ? Object.assign({}, cp, { chip: candChip(cp), canRows: cp.can.map(r => ({ k: r[0], v: r[1] })) }) : null;
    const demoInputs = [
      { label: 'PT MARKET ID', go: () => { this.setState({ query: PT_MARKET }); this.lookup(PT_MARKET); } },
      { label: 'UNSUPPORTED WALLET', go: () => { const q = '0x8f3cf7ad23cd3cadbd9735aff958023239c6a063'; this.setState({ query: q }); this.lookup(q); } },
      { label: 'INVALID INPUT', go: () => { this.setState({ query: '0x12ab' }); this.lookup('0x12ab'); } }
    ].concat(QA ? [{ label: 'NETWORK ERROR', go: () => this.lookup('', 'error') }, { label: 'SLOW REQUEST', go: () => this.lookup('', 'slow') }] : []);

    const loadingLive = st.screen === 'loading' && st.loadLive && st.liveCand;
    const pos0 = loadingLive ? st.liveCand : (this.ctx() || st.ctxs[DEMO_IDS.find(k => st.ctxs[k])]);
    const pos = Object.assign({}, pos0, { chip: candChip(pos0) });

    // loading steps (recorded runs replay the saved result; live runs show elapsed time, never fake per-step progress)
    const LS = ['Pin a block and read contract code', 'Read market, oracle and IRM state', 'Discover dependencies and token lineage', 'Price failure priors (DefiLlama history)', 'Simulate the exit (eth_call, no transaction)', 'Compare stay, exit and uncertainty bands'];
    const loadSteps = LS.map((l, i) => loadingLive
      ? { label: l, state: st.loadStep >= 6 ? 'DONE' : '', color: INK, dot: st.loadStep >= 6 ? CYAN : 'rgba(233,237,242,.15)' }
      : { label: l, state: i < st.loadStep ? 'DONE' : i === st.loadStep ? 'RUNNING' : '', color: i <= st.loadStep ? INK : MUTE, dot: i < st.loadStep ? CYAN : i === st.loadStep ? INK : 'rgba(233,237,242,.15)' });
    const el = Math.max(0, Math.round(((st.now || Date.now()) - st.loadT0) / 1000));
    const snap = pos0 && pos0.payload && pos0.payload._snapshot;
    const loadNote = loadingLive
      ? `Live analysis in progress · ${el} s elapsed. A live run usually takes 10 to 40 s. The backend does not report each step separately, so they are marked done together when the result arrives. Every result keeps the block it was read at.`
      : pos0 && pos0.kind === 'fork' ? 'This demo loads the recorded local-fork run, so it is quick. Fork results keep the fork block they were read at.'
      : `This demo loads a recorded live run${snap && snap.duration_s ? ' (it took ' + Math.round(snap.duration_s) + ' s live)' : ''}, so it is quick. Every result keeps the block it was read at.`;

    // nav
    const NAV = [['dashboard', '01', 'Dashboard', 'Home'], ['positions', '02', 'Positions & Vaults', 'Positions'], ['xray', '03', 'Dependency X-Ray', 'X-Ray'], ['countermove', '04', 'Countermove', 'Protect'], ['activity', '05', 'Activity & Evidence', 'Evidence']];
    const nav = NAV.map(n => { const on = st.section === n[0]; return { num: n[1], label: n[2], short: n[3], color: on ? INK : '#b4bcc8', bg: on ? 'rgba(233,237,242,.05)' : 'transparent', bar: on ? CYAN : 'transparent', go: () => this.go(n[0], n[0] === 'xray' ? { xrMode: 'inspect' } : null) }; });
    const sec = {}; NAV.forEach(n => sec[n[0]] = st.section === n[0]);
    const modeBox = pos0 && pos0.mode === 'live'
      ? { label: 'LIVE · ETHEREUM MAINNET · READ-ONLY', c: CYAN, text: 'Nothing here can sign, spend or arm. Figures come from the live backend run shown in the header.' }
      : { label: 'DEMO · RECORDED DATA', c: AMBER, text: 'Nothing here can sign, spend or arm. Figures come from saved backend runs.' };

    const out = Object.assign(base, {
      lk, cands, cand, demoInputs, pos, loadSteps, loadNote, nav, sec, modeBox,
      onQuery: e => { const v = e.target.value; this.setState({ query: v }); if (st.lk.status !== 'idle' && st.lk.status !== 'checking') this.setState({ lk: { status: 'idle' } }); },
      onQueryKey: e => { if (e.key === 'Enter') this.lookup(this.state.query); },
      runLookup: () => this.lookup(this.state.query),
      cancelLookup: () => { this.lkSeq = (this.lkSeq || 0) + 1; clearTimeout(this.lkT); clearTimeout(this.lkT2); this.setState({ lk: { status: 'idle' } }); },
      startAnalysis: () => this.startAnalysis(),
      goSelect: () => { this.stopSim(); this.setState({ screen: 'select', candId: st.posId }); this.scrollTop(); },
      goArm: () => this.go('countermove'),
      goSim: () => this.go('xray', { xrMode: pos0 && pos0.graph ? 'simulate' : 'replay', revealed: true, simStep: -1, simDone: false }),
      goXray: () => this.go('xray', { xrMode: 'inspect' })
    });
    if (!base.isApp) return Object.assign(out, { dash: {}, db: {}, posRows: [], pv: {}, xr: { tabs: [], cols: [], edges: [], nodes: [], tLabels: [], list: [], simList: [], scenList: [], log: [], rpScens: [], rp: { steps: [] }, rpNodes: [], rpEdges: [], result: {} }, arm: { tabs: [], actions: [], fields: [], pol: {}, fk: {}, dry: {} }, act: { filters: [], rows: [], legend: [] } });
    Object.assign(out, this.dashVals(pos0), this.posVals(), this.xrayVals(pos0), this.armVals(pos0), this.actVals());
    return out;
  }

  dashVals(p) {
    const toFork = () => this.setState({ posId: this.state.ctxs.fork ? 'fork' : this.state.posId, section: 'countermove', armTab: 'fork' });
    const actions = { toFork, configure: () => this.go('countermove', { armTab: 'preview' }), replay: () => this.go('xray', { xrMode: 'replay' }) };
    const d = p.dash, ctas = { toFork: 'See protection on the fork demo', configure: 'Configure protection', replay: 'Replay the recorded incident' };
    const dash = Object.assign({}, d, {
      metrics: d.metrics.map(m => ({ k: m[0], v: m[1], s: m[2], c: m[3] })), noDrivers: d.noDrivers || null,
      prot: { chip: chip(d.prot.chipLabel), short: d.prot.short, text: d.prot.text, cta: ctas[d.prot.action], go: actions[d.prot.action] }
    });
    const st = this.state;
    const db = Object.assign({ isCompare: false, isGauge: false, rows: [], zones: [], markers: [], noDrivers: null }, p.db, {
      showDetails: !!st.dashDetails, detailsLabel: st.dashDetails ? 'Hide technical details ▴' : 'Show technical details ▾',
      toggleDetails: () => this.setState({ dashDetails: !this.state.dashDetails })
    });
    return { db, dash };
  }

  posVals() {
    const st = this.state;
    const ids = DEMO_IDS.filter(k => st.ctxs[k]).concat(Object.keys(st.ctxs).filter(k => DEMO_IDS.indexOf(k) < 0));
    const id = st.pvId && st.ctxs[st.pvId] ? st.pvId : st.posId;
    const p = st.ctxs[id];
    const VC = { REVIEW: AMBER, WATCHING: INK, STAY: CYAN, EXIT: EMBER };
    const posRows = ids.map(k => { const q = st.ctxs[k]; const on = k === id; return { name: q.name + (q.mode === 'live' ? ' · live' : ''), sub: q.sub, verdict: q.verdict, vc: VC[q.verdict] || INK, bg: on ? 'rgba(233,237,242,.04)' : 'transparent', bar: on ? CYAN : 'transparent', view: () => this.setState({ pvId: k }) }; });
    const v = p.pv;
    return { posRows, pv: { kicker: (id === st.posId ? 'CURRENT CONTEXT · ' : '') + p.protocol.toUpperCase(), name: p.name, sub: p.sub, notCurrent: id !== st.posId, use: () => this.setState({ posId: id, pvId: null, section: 'dashboard', simNode: null, selNode: null }),
      facts: v.facts.map(f => ({ k: f[0], v: f[1] })), markets: v.markets || null, marketsTitle: v.marketsTitle || '', routes: v.routes.map(r => ({ name: r.name, val: r.val, note: r.note, chip: chip(r.status) })), routesTitle: v.routesTitle } };
  }

  xrayVals(p) {
    const st = this.state, mode = st.xrMode;
    const edgeD = (a, b) => { const dx = b.x - a.x; if (Math.abs(dx) < 20) { const o = 64; return `M${a.x} ${a.y} C${a.x + o} ${a.y}, ${b.x + o} ${b.y}, ${b.x} ${b.y}`; } const k = dx * 0.5; return `M${a.x} ${a.y} C${a.x + k} ${a.y}, ${b.x - k} ${b.y}, ${b.x} ${b.y}`; };
    const tabs = [['inspect', 'Inspect'], ['simulate', 'Simulate attack'], ['replay', 'Replay incident']].map(t => { const on = mode === t[0]; return { label: t[1], c: on ? '#05070b' : '#b4bcc8', bg: on ? (t[0] === 'inspect' ? INK : t[0] === 'simulate' ? EMBER : AMBER) : 'transparent', bd: on ? 'transparent' : 'rgba(233,237,242,.2)', go: () => { this.stopSim(); this.setState({ xrMode: t[0], simStep: -1, simDone: false, revealed: t[0] !== 'inspect' ? true : st.revealed }); } }; });
    const live = p.mode === 'live';
    const xr = {
      tabs, inspect: mode === 'inspect', simulate: mode === 'simulate', replay: mode === 'replay', simBanner: mode !== 'inspect',
      simBannerText: 'Nothing is armed, signed or spent. Financial values come from ' + (live ? 'the live backend run' : p.kind === 'fork' ? 'the recorded fork run' : 'recorded backend runs') + ', not from the animation.',
      noGraph: !p.graph && mode !== 'replay', graphOk: p.graph && mode !== 'replay',
      noGraphTitle: p.kind === 'vault' ? 'The interactive graph covers PT markets and borrowers.' : 'This fork position is shown in the incident replay.',
      noGraphText: p.kind === 'vault' ? 'The vault endpoint returns its own multi-market dependency graph and scenarios; they have no designed view yet. Positions & Vaults lists every allocated market. Switch context to see the five-layer X-Ray.'
        : "The fork position's dependency chain is shown step by step in the incident replay. Switch context to see the five-layer X-Ray.",
      toPt: () => this.setState({ posId: this.state.ctxs.pt ? 'pt' : this.state.posId, xrMode: 'inspect' }), toReplay: () => this.setState({ xrMode: 'replay' }),
      sevNote: 'The backend also accepts a custom severity (?shock=, ?severity=). This view shows backend results at each dependency\'s default severity.'
    };
    // replay (independent of the graph)
    Object.assign(xr, this.replayVals(edgeD));
    if (!p.graph) return { xr: Object.assign(xr, { cols: [], edges: [], nodes: [], tLabels: [], list: [], simList: [], scenList: [], log: [], result: {}, isGraph: true, isList: false }) };

    const G = p.G, N = {};
    G.NODES.forEach(n => N[n.id] = n);
    const sim = mode === 'simulate';
    const simNode = this.simNodeId(p);
    const ord = sim ? this.simOrder(p) : {};
    const step = st.simStep;
    const hit = id => sim && step >= 0 && ord[id] != null && ord[id] <= step;
    const targets = sim ? this.simTargets(p) : (st.selNode && N[st.selNode] ? [st.selNode] : []);
    const pathE = new Set();
    targets.forEach(t => { const P = (N[t] || {}).path || []; for (let i = 0; i < P.length - 1; i++) pathE.add(P[i] + '>' + P[i + 1]); });
    const alt = sim && st.simKind === 'node' ? this.allPaths(simNode, p).slice(1) : [];
    const altE = new Set(); alt.forEach(a => { for (let i = 0; i < a.p.length - 1; i++) { const k = a.p[i] + '>' + a.p[i + 1]; if (!pathE.has(k)) altE.add(k); } });
    const vis = id => st.revealed || !N[id].hidden;
    const tLabels = [];
    const edges = G.EDGES.filter(e => N[e[0]] && N[e[1]]).map(e => {
      const a = N[e[0]], b = N[e[1]], k = e[0] + '>' + e[1], v = vis(e[0]) && vis(e[1]);
      let stroke = 'rgba(233,237,242,.22)', w = 1.2, dash = 'none', op = v ? 1 : 0;
      if (sim) {
        if (pathE.has(k)) { const h = hit(e[0]) && hit(e[1]); stroke = h ? EMBER : 'rgba(255,106,61,.35)'; w = h ? 2.6 : 1.6; dash = h ? 'none' : '5 5'; if (h) tLabels.push({ x: (a.x + b.x) / 2 + (Math.abs(b.x - a.x) < 20 ? 52 : 0), y: (a.y + b.y) / 2 - 6, t: '×' + e[2].toFixed(2), c: EMBER }); }
        else if (altE.has(k)) { stroke = 'rgba(138,148,163,.7)'; dash = '2 6'; w = 1.4; }
        else op = v ? 0.3 : 0;
      } else if (st.selNode) {
        if (pathE.has(k)) { stroke = CYAN; w = 2.4; tLabels.push({ x: (a.x + b.x) / 2 + (Math.abs(b.x - a.x) < 20 ? 52 : 0), y: (a.y + b.y) / 2 - 6, t: '×' + e[2].toFixed(2), c: CYAN }); }
        else op = v ? 0.4 : 0;
      }
      return { d: edgeD(a, b), stroke, w, dash, op };
    });
    const fmtSev = v => (+v).toFixed(v < 0.1 ? 4 : 2);
    const nodes = G.NODES.map(n => {
      const isPos = n.id === 'pos', v = vis(n.id), sel = !sim && st.selNode === n.id;
      let fill = '#0a0e14', stroke = n.hidden ? MUTE : INK, halo = 0, haloC = 'transparent', lc = INK, sub = '';
      if (isPos) { fill = INK; stroke = INK; sub = p.kind === 'borrow' ? 'HF ' + (+p.payload.liquidation.health_factor).toFixed(3) : Fm.usdM(p.V) + ' PT'; }
      else sub = (n.hidden ? 'HIDDEN' : 'DIRECT') + ' · ×' + n.T.toFixed(2);
      if (sim) {
        if (hit(n.id)) { fill = EMBER; stroke = EMBER; halo = isPos ? 30 : 22; haloC = 'rgba(255,106,61,.18)'; lc = INK; sub = targets.indexOf(n.id) >= 0 ? 'SHOCKED · sev ' + fmtSev(n.sev) : isPos ? 'REACHED' : 'TRANSMITS ×' + n.T.toFixed(2); }
        else if (ord[n.id] != null) { stroke = EMBER; }
        else { lc = MUTE; }
      } else if (sel) { stroke = CYAN; halo = 20; haloC = 'rgba(43,184,255,.16)'; }
      const r = isPos ? 12 : n.hidden ? 7 : 9;
      return { bg: n.icon ? "url('" + n.icon + "')" : 'none', is: n.icon ? (n.hidden ? '17px' : '21px') : '0px', iy: (n.y / 520 * 100).toFixed(2) + '%', iop: !v || !n.icon ? 0 : sim && hit(n.id) ? 0.3 : 1, lx: (n.x / 1010 * 100).toFixed(2) + '%', ly: ((n.y + (isPos ? 20 : 15)) / 520 * 100).toFixed(2) + '%', x: n.x, y: n.y, r, fill, stroke, halo, haloC, op: v ? 1 : 0, short: n.short, sub, lc, subC: n.hidden && !sim ? EMBER : MUTE, ty: n.y + (isPos ? 34 : 28), sy: n.y + (isPos ? 49 : 43),
        click: () => { if (isPos) return; if (sim) { if (st.simKind === 'node' && (st.simStep < 0 || st.simDone)) this.setState({ simNode: n.id, simStep: -1, simDone: false }); } else this.setState({ selNode: st.selNode === n.id ? null : n.id, revealed: true }); } };
    });
    const LAYER = ['Position', 'Settlement chain', 'Yield source / issuer', 'Oracle', 'PT market / AMM', 'Lending'];
    const sn = st.selNode && N[st.selNode] ? N[st.selNode] : null;
    const pct = (v, d) => (v * 100).toFixed(d) + '%';
    const node = sn ? {
      label: sn.label, layer: 'LAYER ' + sn.layer + ' · ' + LAYER[sn.layer].toUpperCase(), hiddenChip: sn.hidden ? 'HIDDEN DEPENDENCY' : 'DIRECT DEPENDENCY', hc: sn.hidden ? EMBER : INK, role: sn.role, why: sn.why,
      rows: [['Failure probability · ' + p.H + ' d', sn.p === 0 ? '0 (carried by parents)' : pct(sn.p, 3)], ['Loss given failure', pct(sn.lgf, sn.lgf < 0.1 ? 2 : 1)], ['Best-path transmission', '×' + sn.T.toFixed(2)], ['Share of expected loss', usd(sn.contrib)], ['If it fails (conditional)', usd(sn.cond) + ' → ' + (sn.verdictIf || '—')]].map(r => ({ k: r[0], v: r[1] })),
      path: sn.path.map(id => (N[id] || { short: id }).short).join(' → '),
      reasons: G.EDGES.filter(e => e[0] === sn.id || e[1] === sn.id).map(e => ({ t: (N[e[0]] || {}).short + ' → ' + (N[e[1]] || {}).short + ' · ×' + e[2].toFixed(2) + (e[4] && e[4] !== 'principal' ? ' · ' + e[4] + ' channel' : ''), r: e[3] })),
      shock: () => this.setState({ xrMode: 'simulate', simKind: 'node', simNode: sn.id, simStep: -1, simDone: false })
    } : null;
    const list = G.NODES.filter(n => n.id !== 'pos').sort((a, b) => b.layer - a.layer).map(n => ({ layer: n.layer + ' · ' + LAYER[n.layer], label: n.label, vis: n.hidden ? 'Hidden' : 'Direct', vc: n.hidden ? EMBER : INK, p: n.p === 0 ? '0' : pct(n.p, 3), t: '×' + n.T.toFixed(2), c: usd(n.contrib), cond: usd(n.cond), go: () => this.setState({ selNode: n.id, revealed: true }) }));

    // simulate panel
    const r = this.simResult(p);
    const maxO = Math.max.apply(null, Object.values(this.simOrder(p)).concat([0]));
    const log = [];
    if (sim && step >= 0) {
      for (let s = 0; s <= Math.min(step, maxO); s++) {
        Object.keys(ord).filter(id => ord[id] === s).forEach(id => {
          const n = N[id]; if (!n) return;
          let t = '';
          if (s === 0) t = n.label + ' fails at severity ' + fmtSev(n.sev);
          else if (id === 'pos') t = n.blocked && st.simKind === 'node' ? 'The path reaches your position, but this channel carries no loss here' : 'The failure reaches your position';
          else t = 'Passes through ' + n.label;
          log.push({ t, k: 'T+' + s, c: s === 0 ? EMBER : id === 'pos' ? INK : '#b4bcc8' });
        });
      }
    }
    const simList = G.NODES.filter(n => n.id !== 'pos').map(n => { const on = simNode === n.id; return { label: n.label, sub: 'layer ' + n.layer + ' · ×' + n.T.toFixed(2) + ' · sev ' + fmtSev(n.sev), bg: on ? 'rgba(255,106,61,.08)' : 'transparent', bar: on ? EMBER : 'transparent', pick: () => { if (st.simStep >= 0 && !st.simDone) return; this.setState({ simNode: n.id, simStep: -1, simDone: false }); } }; });
    const scenList = p.scen.map((s, i) => { const on = st.simScen === i; return { label: s.name, sub: s.desc, bg: on ? 'rgba(255,106,61,.08)' : 'transparent', bar: on ? EMBER : 'transparent', pick: () => { if (st.simStep >= 0 && !st.simDone) return; this.setState({ simScen: i, simStep: -1, simDone: false }); } }; });
    const running = st.simStep >= 0 && !st.simDone;
    const altRows = alt.map(a => ({ t: a.p.map(id => N[id].short).join(' → '), v: '×' + a.t.toFixed(2) }));
    const bestT = st.simKind === 'node' ? N[simNode].T : null;
    const sn2 = r.node || null, chNote = sn2 && sn2.note ? sn2.note.charAt(0).toUpperCase() + sn2.note.slice(1) + '.' : '';
    const scNote = !sn2 && r.notes ? Object.keys(r.notes).map(k => (N[k] ? N[k].short : k) + ': ' + r.notes[k].note).join(' · ') : '';
    const maxContrib = Math.max.apply(null, G.NODES.map(n => n.contrib));
    const mat = p.maturity;
    const vMult = r.mult >= 10 ? r.mult.toFixed(1) : r.mult.toFixed(2);
    const result = {
      verdict: r.verdict, vC: Fm.verdictColor(r.verdict), name: r.name, chip: live ? 'SIMULATED · LIVE BACKEND VALUES' : 'SIMULATED · RECORDED BACKEND VALUES',
      stay: usd(r.loss), stayPct: (r.loss / p.V * 100).toFixed(2) + '% of the ' + usd(p.V) + ' position', exit: usd(r.exit), exitSub: usd(r.exec) + ' execution + ' + usd(r.carry) + ' carry forgone' + (r.stressed ? ' (stressed exit)' : ''),
      mult: '×' + vMult,
      reason: 'If this shock happens, staying is expected to lose ' + usd(r.loss) + ' over ' + p.H + ' days. Leaving costs ' + usd(r.exit) + '. Staying costs ' + vMult + ' times the exit side, so under this shock the recommendation is ' + r.verdict + '.',
      alt: altRows, hasAlt: altRows.length > 0, altNote: bestT != null ? 'Not counted. The model keeps the strongest path (×' + bestT.toFixed(2) + ') and ignores weaker routes to the same dependency.' : '',
      zeroNote: chNote || scNote || (sn2 && sn2.p === 0 ? 'In the baseline this node adds $0: its risk is already carried by its parent tokens. Only a what-if shock moves it.' : sn2 && sn2.contrib === maxContrib && sn2.contrib > 0 ? sn2.short + ' carries the largest baseline share (' + usd(sn2.contrib) + ') yet a small shock (severity ' + fmtSev(sn2.sev) + ').' : ''),
      borrowNote: p.kind === 'borrow' ? 'Values are for a ' + usd(p.V) + ' position on this market with the debt channel on (borrower mode); the borrower\'s own liquidation figures are on the Dashboard.' : '',
      htm: 'n/a', htmC: MUTE,
      htmSub: !mat ? 'Not applicable to this position' : (sn2 && sn2.id === 'amm' && mat.if_amm_fails ? mat.if_amm_fails.charAt(0).toUpperCase() + mat.if_amm_fails.slice(1) : 'Not computed per shock. Baseline to maturity (' + Fm.date((p.payload.nodes.find(n => n.id === 'amm') || { meta: {} }).meta.expiry) + '): ' + usd(p.htm.central_usd)),
      uncert: 'This is a point value conditional on the shock, not a forecast. Uncertainty bands are computed for the baseline only (' + usd(p.band[0]) + ' to ' + usd(p.band[1]) + '). Transmission weights are expert estimates.'
    };
    const hiddenCount = G.NODES.filter(n => n.hidden).length;
    const direct = G.NODES.filter(n => n.id !== 'pos' && !n.hidden).map(n => n.short);
    const howTo = 'Your wallet shows ' + (direct.length === 1 ? 'one dependency' : direct.length + ' dependencies') + ': ' + (direct.length > 1 ? direct.slice(0, -1).join(', ') + ' and ' + direct[direct.length - 1] : direct[0] || 'none') + '. FAULTLINE traced ' + hiddenCount + ' more behind them.';
    return {
      xr: Object.assign(xr, {
        isGraph: st.xrView === 'graph', isList: st.xrView === 'list',
        viewGraph: () => this.setState({ xrView: 'graph' }), viewList: () => this.setState({ xrView: 'list' }),
        gC: st.xrView === 'graph' ? INK : MUTE, lC: st.xrView === 'list' ? INK : MUTE,
        cols: G.COLS.map(c => ({ x: c.x, label: c.label, lx: (c.x / 1010 * 100).toFixed(2) + '%' })), edges, nodes, tLabels: tLabels.map(l => Object.assign(l, { lx: (l.x / 1010 * 100).toFixed(2) + '%', ly: (l.y / 520 * 100).toFixed(2) + '%' })), list, node, noNode: !node,
        revealed: st.revealed, notRevealed: !st.revealed, reveal: () => this.setState({ revealed: true }), hide: () => this.setState({ revealed: false, selNode: null }),
        revealLabel: 'Reveal ' + hiddenCount + ' hidden dependencies', hiddenCount, howTo,
        kindNode: st.simKind === 'node', kindScen: st.simKind !== 'node',
        kN: st.simKind === 'node' ? INK : MUTE, kS: st.simKind !== 'node' ? INK : MUTE,
        setKindNode: () => { if (running) return; this.setState({ simKind: 'node', simStep: -1, simDone: false }); },
        setKindScen: () => { if (running) return; this.setState({ simKind: 'scen', simStep: -1, simDone: false }); },
        simList, scenList, sev: r.sev, launch: () => this.launchSim(), launchLabel: running ? 'Propagating…' : st.simDone ? 'Run again' : 'Launch simulation', launchBg: running ? 'rgba(255,106,61,.3)' : EMBER,
        log, hasLog: log.length > 0, done: st.simDone, result,
        idle: sim && st.simStep < 0
      })
    };
  }

  replayVals(edgeD) {
    const st = this.state, cm = st.cm;
    const have = s => !!(cm && X.replay(cm, s));
    const rpScens = [
      { id: 'S1', name: 'S1 · weETH / USDC · USDC reserve', sub: 'Recorded local-fork run: shock, decision, repayment, proof.', chip: chip(have('S1') ? 'FORK CONFIRMED' : 'UNAVAILABLE') },
      { id: 'S5', name: 'S5 · Pendle PT on Morpho', sub: have('S5') ? 'The Belem-relevant case: PT-reUSD collateral, incident on the oracle that prices the PT. Recorded local-fork run.' : 'The Belem-relevant case. No S5 recording exists in data/countermove yet.', chip: chip(have('S5') ? 'FORK CONFIRMED' : 'UNAVAILABLE') },
      { id: 'SVB', name: 'USDC depeg · March 2023', sub: 'A real event, used to check the risk model without look-ahead.', chip: chip('HISTORICAL DATA') }
    ].map(s => Object.assign(s, { bg: st.rpScen === s.id ? 'rgba(233,237,242,.05)' : 'transparent', bar: st.rpScen === s.id ? CYAN : 'transparent', pick: () => { clearInterval(this.rpT); this.setState({ rpScen: s.id, rpPlaying: false, rpStep: 0 }); } }));
    const rd = this.replayData();
    if (!rd) return { rpScens, rp: { isS1: false, isS5: st.rpScen === 'S5', isSVB: st.rpScen === 'SVB', steps: [], chip: chip('UNAVAILABLE') }, rpNodes: [], rpEdges: [] };
    const RP = rd.steps, rs = Math.min(st.rpStep, RP.length - 1), cur = RP[rs];
    const RN = {}; rd.rnodes.forEach(n => RN[n.id] = n);
    const SC = { threat: [EMBER, EMBER, 'rgba(255,106,61,.18)'], defense: [CYAN, CYAN, 'rgba(43,184,255,.16)'], hypo: ['#0a0e14', AMBER, 'transparent'], calm: ['#0a0e14', 'rgba(233,237,242,.5)', 'transparent'] };
    const rpNodes = rd.rnodes.map(n => { const s = cur.nodes[n.id] || 'calm', c = SC[s]; return { bg: n.icon ? "url('" + n.icon + "')" : 'none', is: n.icon ? '20px' : '0px', iy: (n.y / 400 * 100).toFixed(2) + '%', iop: !n.icon ? 0 : s === 'threat' || s === 'defense' ? 0.35 : 1, lx: (n.x / 860 * 100).toFixed(2) + '%', ly: ((n.y + 16) / 400 * 100).toFixed(2) + '%', x: n.x, y: n.y, label: n.label, sub: n.sub, fill: c[0], stroke: c[1], haloC: c[2], halo: s === 'threat' || s === 'defense' ? 24 : 0, ty: n.y + 32, sy: n.y + 47, lc: s === 'calm' ? '#b4bcc8' : INK }; });
    const ES = { threat: [EMBER, 2.6, 'none'], defense: [CYAN, 2.6, 'none'], hypo: [AMBER, 1.6, '5 5'] };
    const rpEdges = rd.redges.map(e => { const a = RN[e[0]], b = RN[e[1]], s = cur.edges[e[0] + '-' + e[1]], c = ES[s] || ['rgba(233,237,242,.2)', 1.2, 'none']; return { d: edgeD(a, b), stroke: c[0], w: c[1], dash: c[2] }; });
    const rp = {
      isS1: true, isS5: false, isSVB: false,
      t: cur.t, title: cur.title, block: cur.block, body: cur.body, chip: chip(cur.chip), ltv: cur.ltv, debt: cur.debt, reserve: cur.reserve, state: cur.state,
      steps: RP.map((x, i) => ({ t: x.t, title: x.title, c: i === rs ? INK : i < rs ? CYAN : MUTE, bar: i <= rs ? (i === rs ? INK : CYAN) : 'rgba(233,237,242,.15)', go: () => { clearInterval(this.rpT); this.setState({ rpStep: i, rpPlaying: false }); } })),
      playLabel: st.rpPlaying ? 'Playing…' : rs === RP.length - 1 ? 'Replay again' : 'Replay incident',
      play: () => this.playReplay(),
      prev: () => { clearInterval(this.rpT); this.setState({ rpStep: Math.max(0, rs - 1), rpPlaying: false }); },
      next: () => { clearInterval(this.rpT); this.setState({ rpStep: Math.min(RP.length - 1, rs + 1), rpPlaying: false }); },
      ltvC: cur.ltvNum >= cur.trigger ? EMBER : rs >= 5 ? CYAN : INK
    };
    if (st.rpScen === 'SVB') Object.assign(rp, { isS1: false, isSVB: true });
    return { rpScens, rp, rpNodes, rpEdges };
  }

  armVals(p) {
    const st = this.state;
    const A0 = p.arm || {}, eligible = !!A0.eligible;
    const fk = (st.cm && X.forkTab(st.cm, 'S1')) || {};
    const dep = this.depVals();
    const tabsDef = [['preview', '1', 'Policy preview', 'AVAILABLE'], ['fork', '2', 'Fork demonstration', 'SIMULATED'], ['deployed', '3', 'Autonomous protection', dep.live ? 'LOCAL TEST' : 'UNAVAILABLE']];
    const tabs = tabsDef.map(t => { const on = st.armTab === t[0]; const c = chip(t[3]); return { num: t[1], label: t[2], chip: c, bd: on ? INK : 'rgba(233,237,242,.14)', bg: on ? 'rgba(233,237,242,.04)' : 'transparent', go: () => this.setState({ armTab: t[0] }, () => { if (t[0] === 'deployed') this.depWatch(); }) }; });
    const common = { tabs, dep, isPreview: st.armTab === 'preview', isFork: st.armTab === 'fork', isDeployed: st.armTab === 'deployed', posName: p.name, fk,
      useFork: () => this.setState({ posId: 'fork', armTab: 'preview', policy: null, dry: null }), useBorrow: () => this.setState({ posId: 'borrow', armTab: 'preview', policy: null, dry: null }),
      toReplay: () => this.go('xray', { xrMode: 'replay', rpScen: 'S1' }) };
    if (!eligible) return { arm: Object.assign(common, { eligible: false, notEligible: true, pol: {}, actions: [], fields: [], dry: { checks: [], summary: '', note: '' }, hasDry: false }) };
    const pol = st.policy && st.policy.pid === p.id ? st.policy : Object.assign({ pid: p.id }, this.defaultPolicy(p));
    const set = (k, v) => this.setState({ policy: Object.assign({}, pol, { [k]: v }), dry: null });
    const fork = !!A0.fork, ctx = { lltv: A0.lltv, ltv: A0.ltv, coll: A0.coll, loan: A0.loanSym, debt: A0.debt };
    const nf = v => (+v).toLocaleString('en-US', { maximumFractionDigits: 2 });
    const A = { REPAY: ['Repay debt', `From the ${ctx.loan} reserve`, 'repayCap', `${ctx.loan} / action`], TOP_UP: ['Add collateral', 'From the ' + ctx.coll + ' reserve', 'topupCap', ctx.coll + ' / action'], FULL_REPAY: ['Close the debt', 'Emergency full repayment', 'fullCap', `${ctx.loan} max`] };
    const actions = pol.order.map((k, i) => ({ rank: String(i + 1), key: k, label: A[k][0], sub: A[k][1] + ' · cap ' + nf(pol[A[k][2]]) + ' ' + A[k][3], on: pol.on[k], onLabel: pol.on[k] ? 'ALLOWED' : 'OFF', onC: pol.on[k] ? CYAN : MUTE, onBd: pol.on[k] ? 'rgba(43,184,255,.5)' : 'rgba(233,237,242,.2)',
      toggle: () => set('on', Object.assign({}, pol.on, { [k]: !pol.on[k] })),
      up: () => { if (i === 0) return; const o = pol.order.slice(); o.splice(i - 1, 0, o.splice(i, 1)[0]); set('order', o); },
      down: () => { if (i === pol.order.length - 1) return; const o = pol.order.slice(); o.splice(i + 1, 0, o.splice(i, 1)[0]); set('order', o); } }));
    const num = (k, label, unit, step, note) => ({ label, unit, value: String(pol[k]), step: String(step), note: note || '', onInput: e => set(k, Math.max(0, parseFloat(e.target.value) || 0)) });
    const fields = [num('loanRes', 'Loan reserve', ctx.loan, 100, pol.minLoan ? 'Policy floor kept after an action: ' + nf(pol.minLoan) : 'No policy floor'), num('collRes', 'Collateral reserve', ctx.coll, 0.01, pol.minColl ? 'Policy floor kept after an action: ' + nf(pol.minColl) : 'No policy floor'),
      num('repayTotal', 'Total repay limit', ctx.loan, 1000, 'Across the policy lifetime'), num('topupTotal', 'Total top-up limit', ctx.coll, 0.1, ''), num('expiry', 'Policy expires after', 'days', 1, 'Maximum 90'), num('cooldown', 'Cooldown between actions', 'hours', 1, '')];
    const scale = v => Math.max(0, Math.min(100, (v - 50) / 50 * 100)).toFixed(1) + '%';
    let dry = { checks: [], summary: '', note: '' };
    if (st.dry && st.dry.pid === p.id) {
      const C = [];
      const ok = (t, d) => C.push({ s: 'PASS', c: CYAN, t, d }), warn = (t, d) => C.push({ s: 'WARN', c: AMBER, t, d }), block = (t, d) => C.push({ s: 'BLOCKED', c: EMBER, t, d });
      const pd = st.dry.draft, dr = st.dry.run;
      if (!pd || !pd.ok || !pd.body) block('Policy rules (backend)', 'The policy check did not answer: ' + X.errText(pd) + ' Nothing was validated.');
      else {
        const b = pd.body;
        b.valid ? ok('Policy rules (backend)', 'Accepted by the same rules as RescueVault.setPolicy: ' + (pol.order.filter(k => pol.on[k]).join(' → ') || 'no action') + '. setPolicy calldata is ready for the owner\'s wallet; it was not signed.') : null;
        (b.errors || []).forEach(e => block('Policy rule', e.charAt(0).toUpperCase() + e.slice(1) + '.'));
        (b.warnings || []).forEach(w => warn('Policy warning', w.charAt(0).toUpperCase() + w.slice(1) + '.'));
      }
      const defOrder = ['REPAY', 'TOP_UP', 'FULL_REPAY'].filter(k => pol.on[k]).join(), curOrder = pol.order.filter(k => pol.on[k]).join();
      defOrder === curOrder ? ok('Priority order', 'The keeper ranks fundable actions by the least reserve committed; ties follow REPAY → TOP_UP → FULL_REPAY.') : warn('Priority order', 'A custom order is not enforced: the keeper ranks fundable actions by the least reserve committed (engine rule). Custom ordering needs backend support.');
      ctx.ltv < pol.trigger ? ok('Current position', 'LTV ' + ctx.ltv.toFixed(2) + '% is below the trigger.') : warn('Current position', 'LTV ' + ctx.ltv.toFixed(2) + '% is already above the trigger. The policy would act at the first check.');
      if (fork) {
        const reqs = A0.reqs || [], hit = (A0.shockBps || 900) / 10000, r = reqs.find(x => Math.abs(x.first_hit - hit) < 1e-9) || reqs[0];
        if (r) {
          const lbl = 'Recorded need after the −' + (hit * 100).toFixed(0) + '% shock: ';
          if (pol.on.REPAY) (r.repay_possible && pol.loanRes >= r.min_repay && pol.repayCap >= r.min_repay) ? ok('REPAY fundable', lbl + nf(r.min_repay) + ' ' + ctx.loan + ', inside the reserve and the per-action cap.') : warn('REPAY fundable', lbl + nf(r.min_repay) + ' ' + ctx.loan + '. The reserve or the per-action cap is too small: REPAY would be rejected at feasibility.');
          if (pol.on.TOP_UP) (pol.collRes >= r.min_top_up && pol.topupCap >= r.min_top_up) ? ok('TOP_UP fundable', lbl + nf(r.min_top_up) + ' ' + ctx.coll + ', inside the reserve and the cap.') : warn('TOP_UP fundable', nf(pol.collRes) + ' ' + ctx.coll + ' in reserve vs ' + nf(r.min_top_up) + ' needed to hold the buffer. TOP_UP would be rejected.');
          if (pol.on.FULL_REPAY) (pol.loanRes >= r.full_repay && pol.fullCap >= r.full_repay) ? ok('FULL_REPAY fundable', 'Reserve and cap can close the ' + nf(r.full_repay) + ' ' + ctx.loan + ' debt.') : warn('FULL_REPAY fundable', nf(pol.loanRes) + ' ' + ctx.loan + ' cannot close the ' + nf(r.full_repay) + ' ' + ctx.loan + ' debt. FULL_REPAY would be rejected.');
        }
      } else if (dr) {
        if (!dr.ok || !dr.body) warn('Live dry run', 'The read-only mainnet dry run did not answer: ' + X.errText(dr));
        else {
          const b = dr.body, w = b.watcher || {}, env = b.environment || {}, ch = (b.decision || {}).chosen;
          const txt = (w.reason || '').slice(0, 320);
          (w.outcome === 'WOULD_EXECUTE' ? ok : w.outcome === 'HOLD' || w.outcome === 'NOTHING_TO_PROTECT' ? ok : warn)('Keeper decision now (dry run, block ' + Fm.blk(env.block) + ')', w.outcome + (ch ? ' · ' + ch.strategy + ' ' + nf(ch.amount) + ' ' + ch.token : '') + '. ' + txt);
          const rr = (b.reserve_requirements || []).filter(x => x.first_hit >= pol.followOn / 100 - 1e-9)[0] || (b.reserve_requirements || [])[0];
          if (rr) {
            const cov = rr.hypothetical_reserves_cover || {};
            if (pol.on.REPAY) cov.repay ? ok('REPAY fundable', 'After a −' + (rr.first_hit * 100).toFixed(0) + '% first hit the keeper needs ' + nf(rr.min_repay) + ' ' + ctx.loan + '; the reserve covers it.') : warn('REPAY fundable', 'After a −' + (rr.first_hit * 100).toFixed(0) + '% first hit the keeper needs ' + (rr.repay_possible ? nf(rr.min_repay) + ' ' + ctx.loan : 'more than a full repay') + '; the reserve does not cover it.');
            if (pol.on.TOP_UP) cov.top_up ? ok('TOP_UP fundable', 'Needs ' + nf(rr.min_top_up) + ' ' + ctx.coll + ' after that hit; the reserve covers it.') : warn('TOP_UP fundable', 'Needs ' + nf(rr.min_top_up) + ' ' + ctx.coll + ' after that hit; the reserve does not cover it.');
          }
          ((b.hypothetical || {}).warnings || []).slice(0, 2).forEach(x => warn('Dry-run warning', x));
        }
      }
      pol.expiry >= 1 && pol.expiry <= 90 ? ok('Expiry', pol.expiry + ' days.') : warn('Expiry', 'Use 1 to 90 days.');
      block('Execution', fork ? 'Executes only on the local fork. No RescueVault exists on mainnet.' : 'No RescueVault is deployed, funded or monitored for this position.');
      const n = s => C.filter(c => c.s === s).length;
      dry = { checks: C, summary: n('PASS') + ' passed · ' + n('WARN') + ' warnings · ' + n('BLOCKED') + ' blocked',
        note: 'Checks come from /api/countermove (policy-draft' + (dr && dr.ok ? ', and a read-only mainnet dry run for this borrower' : fork ? ', plus the recorded fork run\'s reserve needs' : '') + '). No signature was requested and no transaction was sent.' };
    } else if (st.dryBusy) dry = { checks: [{ s: 'RUNNING', c: INK, t: 'Backend validation', d: fork ? 'Checking the policy with /api/countermove…' : 'Checking the policy and running a read-only mainnet dry run (up to 45 s)…' }], summary: 'in progress', note: 'No signature is requested and no transaction is sent.' };
    const runDry = () => {
      if (this.state.dryBusy) return;
      const pid = p.id;
      this.setState({ dryBusy: true, dry: null });
      Promise.all([X.policyDraft(A0, pol), fork ? Promise.resolve(null) : X.dryRun(A0, pol)]).then(([draft, run]) => {
        const valid = draft && draft.ok && draft.body && draft.body.valid;
        this.setState(s => ({ dryBusy: false, dry: { pid, draft, run, at: Date.now() }, session: [{ id: 'd' + Date.now(), kind: 'policy', title: 'Policy preview · ' + p.name, meta: 'This session · no signature, no transaction', status: 'DRY RUN', result: valid ? 'Validated preview' : 'Rejected by the policy rules', fields: [['Trigger', pol.trigger + '% LTV'], ['Actions', pol.order.filter(k => pol.on[k]).join(' → ') || 'none'], ['Reserves', nf(pol.loanRes) + ' ' + ctx.loan + ' · ' + nf(pol.collRes) + ' ' + ctx.coll], ['Expiry', pol.expiry + ' days · cooldown ' + pol.cooldown + ' h'], ['Checked by', fork ? '/api/countermove policy-draft' : '/api/countermove policy-draft and dry-run'], ['Armed', 'No']] }].concat(s.session) }));
      });
    };
    return {
      arm: Object.assign(common, {
        eligible, notEligible: !eligible, ctxLine: A0.ctxLine,
        pol, trigMax: String(Math.floor((ctx.lltv - 0.5) * 2) / 2), minMax: String(Math.max(10, pol.trigger - 1)),
        onTrigger: e => set('trigger', parseFloat(e.target.value)), onFollow: e => set('followOn', parseFloat(e.target.value)), onBuffer: e => set('buffer', parseFloat(e.target.value)), onMin: e => set('minAfter', parseFloat(e.target.value)),
        ltvL: scale(ctx.ltv), trigL: scale(pol.trigger), lltvL: scale(ctx.lltv), ltvTxt: ctx.ltv.toFixed(2) + '%', lltvTxt: +ctx.lltv.toFixed(2) + '%',
        actions, fields, runDry, dry, hasDry: dry.checks.length > 0, reset: () => this.setState({ policy: null, dry: null }),
        coll: ctx.coll, loanRes: nf(pol.loanRes), collRes: String(pol.collRes)
      })
    };
  }

  actVals() {
    const st = this.state, C = st.ctxs;
    const analyses = [], hist = [];
    DEMO_IDS.concat(Object.keys(C).filter(k => DEMO_IDS.indexOf(k) < 0)).forEach(k => { (C[k] && C[k].activity || []).forEach(a => (a.kind === 'history' ? hist : analyses).push(a)); });
    hist.push({ id: 'h-svb', kind: 'history', title: 'Historical replay · USDC depeg (SVB)', meta: 'Cutoff 2023-03-11', status: 'HISTORICAL DATA', result: 'No look-ahead', fields: [['What it is', 'The risk priors rebuilt with data available before the event. A model check, not a protection event.'], ['Daily close 2023-03-12', '$0.961'], ['Limit', 'Intraday low not in the dataset'], ['Artifact', 'data/fixtures/replay_h04.json · tests/test_hardening.py']] });
    const all = st.session.concat(analyses, X.forkActivity(st.cm), hist);
    const FL = [['all', 'All'], ['analysis', 'Analyses'], ['sim', 'Simulations'], ['policy', 'Policy'], ['fork', 'Fork executions'], ['history', 'Historical'], ['monitoring', 'Monitoring']];
    const counts = k => k === 'all' ? all.length : all.filter(a => a.kind === k).length;
    const filters = FL.map(f => { const on = st.actFilter === f[0]; return { label: f[1] + ' · ' + counts(f[0]), c: on ? '#05070b' : '#b4bcc8', bg: on ? INK : 'transparent', bd: on ? INK : 'rgba(233,237,242,.18)', go: () => this.setState({ actFilter: f[0] }) }; });
    const rows = (st.actFilter === 'all' ? all : all.filter(a => a.kind === st.actFilter)).map(a => ({ title: a.title, meta: a.meta, result: a.result, chip: chip(a.status), bg: st.actSel === a.id ? 'rgba(233,237,242,.04)' : 'transparent', bar: st.actSel === a.id ? CYAN : 'transparent', go: () => this.setState({ actSel: a.id }) }));
    const s = all.find(a => a.id === st.actSel) || all[0];
    const sel = s ? { title: s.title, meta: s.meta, chip: chip(s.status), result: s.result, fields: s.fields.map(f => ({ k: f[0], v: f[1] })), tx: s.tx || null } : null;
    const emptyMsg = st.actFilter === 'monitoring' ? 'No monitoring events. No monitoring service is deployed, so nothing has been watched or detected on mainnet. Events will appear here only once a keeper is running against a deployed RescueVault.' : st.actFilter === 'sim' ? 'No simulations yet in this session. Run one from Simulate attack. Sessions are not persisted: there is no account storage yet.' : st.actFilter === 'policy' ? 'No policy previews yet. Validate one in Countermove. Nothing is stored after you leave.' : null;
    const legend = ['RECORDED LIVE RUN', 'LIVE', 'SIMULATED', 'DRY RUN', 'FORK CONFIRMED', 'MAINNET CONFIRMED', 'HISTORICAL DATA', 'PENDING', 'UNAVAILABLE'].map(chip);
    return { act: { filters, rows, hasRows: rows.length > 0, empty: rows.length === 0 ? (emptyMsg || 'Nothing here yet.') : null, sel, hasSel: !!sel && rows.length > 0, legend } };
  }
}
return Component;
});
