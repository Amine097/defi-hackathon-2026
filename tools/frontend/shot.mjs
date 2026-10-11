// Dev-only screenshot helper for the visual review loop.
// node shot.mjs <url> <out.png> [--w 1440] [--h 900] [--full] [--wait <css>] [--click <css>]... [--delay ms] [--reduced] [--js <code>]
import { chromium } from 'playwright-core';

const a = process.argv.slice(2);
const url = a[0], out = a[1];
const opt = { w: 1440, h: 900, full: false, wait: null, clicks: [], delay: 600, reduced: false, js: [] };
for (let i = 2; i < a.length; i++) {
  const k = a[i];
  if (k === '--w') opt.w = +a[++i];
  else if (k === '--h') opt.h = +a[++i];
  else if (k === '--full') opt.full = true;
  else if (k === '--wait') opt.wait = a[++i];
  else if (k === '--click') opt.clicks.push(a[++i]);
  else if (k === '--delay') opt.delay = +a[++i];
  else if (k === '--reduced') opt.reduced = true;
  else if (k === '--js') opt.js.push(a[++i]);
}
const mobile = opt.w < 600;
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const ctx = await browser.newContext({ viewport: { width: opt.w, height: opt.h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, reducedMotion: opt.reduced ? 'reduce' : 'no-preference' });
const page = await ctx.newPage();
const logs = [];
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) logs.push(`${m.type()}: ${m.text()}`.slice(0, 240)); });
page.on('pageerror', (e) => logs.push(`pageerror: ${e.message}`.slice(0, 240)));
page.on('requestfailed', (r) => logs.push(`failed: ${r.url()}`.slice(0, 200)));
page.on('response', (r) => { if (r.status() >= 400) logs.push(`${r.status()}: ${r.url()}`.slice(0, 200)); });
const t0 = Date.now();
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
if (opt.wait) await page.waitForSelector(opt.wait, { timeout: 120000 }).catch((e) => logs.push('wait timeout ' + opt.wait));
for (const c of opt.clicks) { await page.click(c, { timeout: 15000 }).catch((e) => logs.push('click fail ' + c)); await page.waitForTimeout(500); }
for (const j of opt.js) { const r = await page.evaluate(j).catch((e) => 'js error ' + e.message); if (r !== undefined) console.log('js:', typeof r === 'string' ? r : JSON.stringify(r)); }
await page.waitForTimeout(opt.delay);
await page.screenshot({ path: out, fullPage: opt.full });
const m = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, overflowX: document.documentElement.scrollWidth > innerWidth + 1 }));
console.log(JSON.stringify({ out, ms: Date.now() - t0, ...m, logs }));
await browser.close();
