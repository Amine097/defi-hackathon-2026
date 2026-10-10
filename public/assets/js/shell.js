(function () {
  const path = location.pathname;
  const active = (p) => (p === '/xray.html' ? /xray/.test(path) : !/xray/.test(path)) ? ' class="active"' : '';

  const nav = document.getElementById('nav');
  if (nav) {
    nav.className = 'nav';
    nav.innerHTML = '<div class="container"><a class="brand" href="/"><img src="/assets/brand/logo.svg" alt="" width="28" height="28">FaultLine</a>' +
      '<div class="links"><a href="/"' + active('/') + '>Dashboard</a><a href="/xray.html"' + active('/xray.html') + '>X-Ray</a></div></div>';
  }
  const footer = document.getElementById('footer');
  if (footer) {
    footer.className = 'footer';
    footer.innerHTML = '<div class="container">FaultLine &middot; Know where it breaks before it does. &middot; EPFL DeFi Hackathon 2026 &middot; Belem Capital track. Not financial advice.</div>';
  }
})();
