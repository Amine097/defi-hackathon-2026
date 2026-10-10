(function () {
  const F = window.FaultLine || {};
  const path = location.pathname;
  const mod = new URLSearchParams(location.search).get('m');
  const q = (p) => (F.withQuery ? F.withQuery(p, { fail: null, scenario: null, m: null }) : p);

  const I = {
    overview: '<path d="M3 3h5v5H3zM10 3h5v3h-5zM10 8h5v7h-5zM3 10h5v5H3z"/>',
    bp: '<path d="M2 14 6 8l3 3 5-8"/><path d="M2 14h13"/>',
    vault: '<rect x="3" y="4" width="12" height="10" rx="1.5"/><path d="M3 8h12M9 8v3"/>',
    xray: '<circle cx="4" cy="9" r="1.8"/><circle cx="13" cy="4" r="1.8"/><circle cx="13" cy="14" r="1.8"/><path d="M5.7 8.2 11.3 4.8M5.7 9.8l5.6 3.4"/>',
    whale: '<circle cx="9" cy="9" r="6.5"/><circle cx="9" cy="9" r="3"/><path d="M9 9 14 5"/>',
    leverage: '<path d="M3 15 8 3l2.5 6L15 7"/><path d="M3 15h12"/>',
    blame: '<circle cx="3.5" cy="9" r="1.8"/><circle cx="9" cy="9" r="1.8"/><circle cx="14.5" cy="9" r="1.8" stroke-dasharray="2 2"/><path d="M5.3 9h1.9M10.8 9h1.9"/>',
    runway: '<path d="M2 14c3 0 3-9 7-9s4 9 7 9"/><path d="M2 15h14"/>',
    alerts: '<path d="M4 12V8a5 5 0 0 1 10 0v4l1.5 2h-13zM7.5 15.5a1.7 1.7 0 0 0 3 0"/>'
  };
  const icon = (k) => '<svg viewBox="0 0 18 18" aria-hidden="true">' + I[k] + '</svg>';

  // Single source for the future modules; soon.html renders from the same list.
  const SOON = {
    whale:    { name: 'Whale impact',     icon: 'whale',    art: '/assets/art/whale.png',   blurb: 'See which large holders sit behind a dependency and how their exits would move its price and liquidity.' },
    leverage: { name: 'Leverage hunter',  icon: 'leverage', art: '/assets/art/texture.png', blurb: 'Find leveraged positions stacked on the same collateral and see where liquidations would cluster.' },
    blame:    { name: 'Chain of blame',   icon: 'blame',    art: '/assets/art/chain.png',   blurb: 'Trace a loss back through the dependency chain to the component that started it.' },
    runway:   { name: 'Exit runway',      icon: 'runway',   art: '/assets/art/texture.png', blurb: 'Plan an exit over time: how fast the position can leave at each size without moving the market.' },
    alerts:   { name: 'Smart alerts',     icon: 'alerts',   art: '/assets/art/texture.png', blurb: 'Get notified when a dependency crosses a risk threshold you set, before it reaches your position.' }
  };
  window.FaultLine = Object.assign(window.FaultLine || {}, { SOON, soonIcon: icon });

  const brand = '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M6 6h28l-8 17 8 6-6 12 4 17H6z" fill="#ece9e2"/><path d="M40 6h18v52H42l-4-17 6-12-8-6z" fill="#ece9e2"/><path d="M34 6l-8 17 8 6-6 12 4 17h6l-4-17 6-12-8-6 8-17z" fill="#ff5b3a"/></svg>';
  const isOverview = path === '/' || /\/index\.html$/.test(path);
  const isX = /xray/.test(path);
  const isVault = /vault/.test(path);
  const link = (href, label, ico, on, tail) =>
    '<a class="side-link" href="' + href + '"' + (on ? ' aria-current="page"' : '') + '>' + icon(ico) + '<span>' + label + '</span>' + (tail || '') + '</a>';

  const side = document.createElement('aside');
  side.className = 'side';
  side.id = 'side';
  side.setAttribute('aria-label', 'FaultLine navigation');
  side.innerHTML =
    '<a class="side-brand" href="' + q('/') + '" aria-label="FaultLine overview">' + brand + '<b>FAULTLINE</b></a>' +
    '<nav class="side-group" aria-label="Analysis"><h2>Analysis</h2>' +
      link(q('/'), 'Overview', 'overview', isOverview) +
      link(q('/') + '#bp-card', 'Breaking point', 'bp', false) +
      link(q('/xray.html'), 'Dependency X-Ray', 'xray', isX) +
      link('/vault.html', 'Vault analyzer', 'vault', isVault) +
    '</nav>' +
    '<details class="side-group"' + (path.indexOf('soon') > -1 ? ' open' : '') + '><summary>Coming soon (' + Object.keys(SOON).length + ')</summary>' +
      Object.keys(SOON).map((k) => link('/soon.html?m=' + k, SOON[k].name, SOON[k].icon, path.indexOf('soon') > -1 && mod === k)).join('') +
    '</details>' +
    '<div class="side-foot">EPFL DeFi Hackathon 2026<br>Belem Capital track</div>';

  const toggle = document.createElement('button');
  toggle.className = 'side-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-label', 'Open navigation');
  toggle.setAttribute('aria-controls', 'side');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.innerHTML = '<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 5h12M3 9h12M3 13h12"/></svg>';
  const scrim = document.createElement('div');
  scrim.className = 'side-scrim';

  const setOpen = (on) => { document.body.classList.toggle('side-open', on); toggle.setAttribute('aria-expanded', String(on)); };
  toggle.addEventListener('click', () => setOpen(!document.body.classList.contains('side-open')));
  scrim.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.body.classList.contains('side-open')) setOpen(false); });
  side.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });

  document.body.classList.add('has-side');
  document.body.prepend(scrim);
  document.body.prepend(side);
  document.body.prepend(toggle);

  const footer = document.getElementById('footer');
  if (footer) {
    footer.className = 'footer';
    footer.innerHTML = '<div class="container">Modeled estimates under stated assumptions, not financial advice. Nothing here executes a transaction.</div>';
  }
})();
