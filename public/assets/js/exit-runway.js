/* Exit Runway card (docs/design/frontend.md §20.4).
   The frontend NEVER computes these numbers: it reads GET /exit-cost/{position_id} and renders what comes back.
   Until that backend exists the card shows `not_connected`. `?runway=demo` loads a clearly labelled rehearsal fixture. */
(function () {
  const F = (window.FaultLine = window.FaultLine || {});
  const { esc, fmtUsd, fmtPct } = F;
  const num = (v) => (v == null || v === '' || !Number.isFinite(+v) ? null : +v);
  const pctOf = (v) => (num(v) == null ? null : +v); // backend gives % as a fraction (0.004 = 0.4%)
  const NA = '<span class="er-na">Not available</span>';

  async function load(positionId) {
    const demo = new URLSearchParams(location.search).get('runway') === 'demo';
    const url = demo ? '/data/exit-runway-demo.json' : '/exit-cost/' + encodeURIComponent(positionId || 'position');
    let res;
    try { res = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } }); }
    catch (e) { return { state: 'not_connected', url, detail: 'network: ' + (e && e.message) }; }
    if (res.status === 404 || res.status === 405 || res.status === 501) return { state: 'not_connected', url, detail: 'HTTP ' + res.status };
    if (!res.ok) return { state: 'error', url, detail: 'HTTP ' + res.status };
    if (!/json/i.test(res.headers.get('content-type') || '')) return { state: 'not_connected', url, detail: 'not a JSON endpoint' };
    let r;
    try { r = await res.json(); } catch (e) { return { state: 'error', url, detail: 'invalid JSON' }; }
    if (!r || typeof r !== 'object' || Array.isArray(r) || r.error) return { state: 'error', url, detail: (r && r.error) || 'unexpected shape' };
    return { state: 'data', url, demo: demo || r.demo === true, r };
  }

  const range = (r, key) => {
    const lo = num(r[key + '_low_pct'] ?? (r[key] && r[key].low)), hi = num(r[key + '_high_pct'] ?? (r[key] && r[key].high));
    return lo != null && hi != null ? [lo, hi] : null;
  };
  const hours = (h) => (h == null ? '' : h < 1 ? Math.round(h * 60) + ' min' : h < 48 ? (Math.round(h * 10) / 10) + ' h' : Math.round(h / 24) + ' d');

  function rows(r) {
    const out = [];
    const alonePct = pctOf(r.exit_cost_alone_pct), aloneUsd = num(r.exit_cost_alone_usd);
    out.push({ k: 'Exit alone', tip: 'Cost to exit now, with nobody else selling.', val: alonePct != null || aloneUsd != null ? `<b>${fmtPct(alonePct, 2)}</b> · ${fmtUsd(aloneUsd)}` : null });
    const stPct = pctOf(r.exit_cost_stressed_pct), stUsd = num(r.exit_cost_stressed_usd), rg = range(r, 'exit_cost_stressed');
    out.push({ k: 'Under stress', tip: 'Cost to exit if the stress scenario hits and others sell first.' + (r.stress_scenario ? ' Scenario: ' + r.stress_scenario : ''),
      val: stPct != null || stUsd != null ? `<b>${fmtPct(stPct, 2)}</b> · ${fmtUsd(stUsd)}${rg ? ` <span class="muted">(${fmtPct(rg[0], 1)}–${fmtPct(rg[1], 1)})</span>` : ''}` : null });
    let stuck = null;
    if (r.stuck_share === 'N/A' || r.stuck_applicable === false) stuck = '<span class="muted">N/A · pure AMM exit</span>';
    else if (num(r.stuck_share) != null) stuck = `<b>${fmtPct(r.stuck_share, 0)}</b> <span class="muted">not withdrawable now</span>`;
    out.push({ k: 'Stuck', tip: 'Share of the position that cannot be withdrawn immediately (lending / vault positions).', val: stuck });
    const tr = r.exit_cost_trend;
    let trend = null;
    if (tr && tr.insufficient_history) trend = '<span class="muted">Insufficient history</span>';
    else if (tr) {
      const w = ['6h', '1h', '24h'].find((x) => num(tr[x]) != null);
      if (w) { const d = +tr[w] * 100; trend = `<b>${d > 0 ? '▲ +' : d < 0 ? '▼ ' : ''}${d.toFixed(1)} pts</b> <span class="muted">over ${w}</span>`; }
    }
    out.push({ k: 'Trend', tip: 'How the exit cost moved over recent snapshots.', val: trend });
    const tl = r.time_left;
    let left = null;
    if (tl && tl.status === 'no_deadline') left = '<b>No deadline</b> <span class="muted">nothing is moving adversely</span>';
    else if (tl && tl.time_left_hours && num(tl.time_left_hours.central) != null) {
      const t = tl.time_left_hours;
      left = `<b>~${hours(+t.central)}</b>${num(t.low) != null && num(t.high) != null ? ` <span class="muted">(${hours(+t.low)}–${hours(+t.high)})</span>` : ''}<br><span class="muted">at the current pace${tl.binding_runway ? ' · limited by ' + esc(tl.binding_runway) : ''}</span>`;
    }
    out.push({ k: 'Time left', tip: 'Estimate at the current adverse trend, with a range. Not a prediction.', val: left });
    const q = r.queue;
    out.push({ k: 'Queue position', tip: 'Scenario: holders exit largest first.', val: q && num(q.holders_covered_by_liquidity) != null
      ? `<b>Behind ${+q.holders_covered_by_liquidity} larger holder${+q.holders_covered_by_liquidity === 1 ? '' : 's'}</b> <span class="muted">(scenario${q.method ? ' · ' + esc(q.method) : ''})</span>` : null });
    const s = r.shocks;
    let fs = null;
    if (s && s.oracle_market_gap_pct != null) fs = `<b>Oracle–market gap ${fmtPct(s.oracle_market_gap_pct, 1)}</b> <span class="muted">hidden loss (fixed-rate oracle)</span>`;
    else if (s && num(s.forced_sellers) != null) fs = `<b>${+s.forced_sellers} position${+s.forced_sellers === 1 ? '' : 's'}</b>${num(s.forced_selling_usd) != null ? ' · ' + fmtUsd(s.forced_selling_usd) + ' before us' : ''}${s.scenario ? ` <span class="muted">(${esc(s.scenario)})</span>` : ''}`;
    out.push({ k: 'Forced sellers', tip: 'Leveraged positions that would be liquidated and sell before us under the shock.', val: fs });
    return out;
  }

  /** st: result of load(); o: { onFocusNode(id) } */
  function render(el, st, o) {
    o = o || {};
    const head = (chip) => `<div class="er-h"><h3>Exit runway</h3>${chip || ''}</div>`;
    if (st.state === 'loading') { el.innerHTML = head('<span class="chip">loading…</span>') + '<div class="er-skel"></div>'; return; }
    if (st.state === 'not_connected') {
      el.innerHTML = head('<span class="chip warn">not connected</span>') +
        `<p class="er-msg"><b>Not available: exit-cost layer not connected.</b></p>
         <p class="muted">Exit cost under stress, stuck value and time left are not estimated. The exit estimate in the verdict (execution plus carry forgone) remains valid.</p>
         <details class="er-foot"><summary>Technical detail</summary><p class="muted">These numbers come from a dedicated backend endpoint (<code>GET /exit-cost/{position_id}</code>) that is not deployed here, so nothing is estimated in the browser.</p></details>`;
      return;
    }
    if (st.state === 'error') {
      el.innerHTML = head('<span class="chip bad">error</span>') + `<p class="er-msg"><b>Exit runway unavailable.</b></p><p class="muted">${esc(st.detail || '')}</p>`;
      return;
    }
    const r = st.r, rs = rows(r), have = rs.filter((x) => x.val != null).length;
    const stale = num(r.freshness_seconds) != null && num(r.stale_after_seconds) != null && +r.freshness_seconds > +r.stale_after_seconds;
    const chip = st.demo ? '<span class="chip bad">DEMO fixture</span>' : stale ? '<span class="chip warn">stale</span>' : have < rs.length ? '<span class="chip warn">partial</span>' : '<span class="chip ok">available</span>';
    const asOf = r.as_of ? (typeof r.as_of === 'number' && r.as_of > 1e9 ? F.isoMin(r.as_of) : esc(r.as_of)) : null;
    el.innerHTML = head(chip) +
      (st.demo ? '<p class="er-demo">Rehearsal fixture, not real data. Values are not produced by the risk engine.</p>' : '') +
      `<dl class="er-rows">${rs.map((x, i) => `<div class="er-row${x.val == null ? ' off' : ''}" ${x.val != null ? `data-i="${i}" tabindex="0"` : ''}><dt title="${esc(x.tip)}">${x.k}</dt><dd>${x.val == null ? NA : x.val}</dd></div>`).join('')}</dl>
       <div class="er-foot">
         ${r.method ? `<div><b>Method</b> ${esc(r.method)}</div>` : '<div class="muted">Method not provided.</div>'}
         <div class="muted">${asOf ? 'as of ' + asOf : 'as-of not provided'}${num(r.freshness_seconds) != null ? ' · ' + Math.round(+r.freshness_seconds) + ' s old' : ''}${r.data_sources && r.data_sources.length ? ' · ' + r.data_sources.map(esc).join(', ') : ''}</div>
         ${(r.assumptions || r.approximations) ? `<details><summary>Assumptions</summary><ul>${[].concat(r.assumptions || [], r.approximations || []).map((a) => `<li>${esc(typeof a === 'string' ? a : JSON.stringify(a))}</li>`).join('')}</ul></details>` : ''}
       </div>`;
    el.querySelectorAll('.er-row[data-i]').forEach((row) => {
      const x = rs[+row.dataset.i];
      const act = () => {
        if (x.k === 'Forced sellers' && r.shocks && r.shocks.market_node_id && o.onFocusNode) o.onFocusNode(r.shocks.market_node_id);
        else row.classList.toggle('open');
      };
      row.addEventListener('click', act);
      row.addEventListener('keydown', (e) => { if (e.key === 'Enter') act(); });
      row.insertAdjacentHTML('beforeend', `<p class="er-tip">${esc(x.tip)}</p>`);
    });
  }

  F.exitRunway = { load, render };
})();
