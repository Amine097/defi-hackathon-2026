// Shared shell: header with navigation (mobile disclosure), footer. Pages call mountShell({ active }).
const LINKS = [
  ['analyze', '/analyze.html', 'Analysis'],
  ['vault', '/vault.html', 'Vaults'],
  ['countermove', '/countermove.html', 'Countermove'],
];

export function mountShell({ active = '', end = '' } = {}) {
  const header = document.querySelector('[data-shell="header"]');
  if (header) {
    header.className = 'topbar';
    header.innerHTML = `
      <a class="skip" href="#main">Skip to content</a>
      <div class="wrap topbar__in">
        <a class="brand" href="/" aria-label="FAULTLINE home"><img src="/assets/brand/logo.svg" alt="" width="26" height="26">FAULTLINE</a>
        <button class="menu-btn" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
        <nav class="nav" id="site-nav" aria-label="Main">
          ${LINKS.map(([k, href, label]) => `<a href="${href}"${k === active ? ' aria-current="page"' : ''}>${label}</a>`).join('')}
        </nav>
        <div class="topbar__end" id="shell-end">${end}</div>
      </div>`;
    const btn = header.querySelector('.menu-btn');
    const nav = header.querySelector('.nav');
    btn.addEventListener('click', () => {
      const open = !nav.classList.contains('is-open');
      nav.classList.toggle('is-open', open);
      btn.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) { nav.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); btn.focus(); }
    });
  }
  const footer = document.querySelector('[data-shell="footer"]');
  if (footer) {
    footer.className = 'footer';
    footer.innerHTML = `<div class="wrap footer__in">
      <span>FAULTLINE — EPFL DeFi Hackathon 2026, Belem Capital track.</span>
      <span>Model output, not financial advice. Nothing on this site signs or sends a transaction.</span></div>`;
  }
}

export function setShellEnd(html) {
  const el = document.getElementById('shell-end');
  if (el) el.innerHTML = html;
}
