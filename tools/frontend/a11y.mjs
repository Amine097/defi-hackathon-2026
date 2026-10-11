// Dev-only accessibility scan with axe-core (WCAG 2.x A/AA rules). node a11y.mjs <url> [more urls]
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';
const axe = readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');
const b = await chromium.launch({ channel: 'chrome', headless: true });
for (const arg of process.argv.slice(2)) {
  const [url, waitSel] = arg.split('|');
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const p = await (await b.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce' })).newPage();
    await p.goto(url, { waitUntil: 'domcontentloaded' });
    if (waitSel) await p.waitForSelector(waitSel, { timeout: 120000 }); else await p.waitForTimeout(url.includes('snapshot') ? 1500 : 2500);
    await p.waitForTimeout(800);
    await p.addScriptTag({ content: axe });
    const r = await p.evaluate(async () => (await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } })).violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, ex: v.nodes.slice(0, 2).map((x) => x.target.join(' ') + ' :: ' + (x.failureSummary || '').split('\n').slice(1, 2).join('')) })));
    console.log(`${url} @${w}: ${r.length ? r.map((v) => `\n  ${v.impact} ${v.id} x${v.n}: ${v.ex.join(' | ').slice(0, 300)}`).join('') : 'no violations'}`);
    await p.context().close();
  }
}
await b.close();

