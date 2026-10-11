import { chromium } from 'playwright-core';
const b = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
for (const [w, h, dpr, out] of [[1920, 1080, 1, 'hero-poster'], [390, 844, 2, 'hero-poster-mobile']]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr, isMobile: w < 600, hasTouch: w < 600 });
  const p = await ctx.newPage();
  await p.goto('http://127.0.0.1:8000/', { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(9800);
  await p.locator('#heroCanvas').screenshot({ path: `../../public/assets/img/${out}.png` });
  await ctx.close();
}
await b.close();
