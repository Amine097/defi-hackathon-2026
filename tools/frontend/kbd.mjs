// Dev-only keyboard check: Tab order, skip link, visible focus ring on each focused element.
import { chromium } from 'playwright-core';
const b = await chromium.launch({ channel: 'chrome', headless: true });
const routes = [['/', null], ['/analyze.html?snapshot=1', '.an-verdict__word'], ['/countermove.html', '#cm-lab:not([hidden])'], ['/vault.html', null]];
for (const [path, wait] of routes) {
  const p = await (await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })).newPage();
  await p.goto('http://127.0.0.1:8000' + path, { waitUntil: 'domcontentloaded' });
  if (wait) await p.waitForSelector(wait, { timeout: 30000 }); else await p.waitForTimeout(1200);
  const seen = [], noRing = [];
  for (let i = 0; i < 22; i++) {
    await p.keyboard.press('Tab');
    const f = await p.evaluate(() => {
      const e = document.activeElement; if (!e || e === document.body) return null;
      const cs = getComputedStyle(e); const ring = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || /\d+px/.test(cs.boxShadow.replace('none', ''));
      const lab = (e.getAttribute('aria-label') || e.innerText || e.value || e.id || e.tagName).trim().replace(/\s+/g, ' ').slice(0, 28);
      return { lab, ring, tag: e.tagName.toLowerCase() };
    });
    if (!f) continue;
    seen.push(f.lab); if (!f.ring) noRing.push(`${f.tag}:${f.lab}`);
  }
  console.log(`${path}\n  order: ${seen.slice(0, 14).join(' > ')}\n  without visible focus: ${noRing.length ? noRing.join(', ') : 'none'}`);
  await p.context().close();
}
await b.close();
