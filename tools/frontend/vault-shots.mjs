// Browser QA for /vault.html: screenshots at 1440x900 and 390x844, error case, console errors, page height.
// Usage: node vault-shots.mjs <outDir> [live|mock] [baseUrl] [mockPayload.json]
// live: real backend (15-25 s per analysis). mock: /api/vault answered from a saved real payload (layout iteration only).
import { chromium } from 'playwright-core';
import { readFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const [outDir = 'shots', mode = 'live', base = 'http://127.0.0.1:8102', mockFile] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const BELEM = '0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec';
const USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48';
const mock = mode === 'mock' && mockFile ? readFileSync(mockFile, 'utf8') : null;
const report = { mode, pages: {} };

const browser = await chromium.launch({ channel: 'chrome' });

async function open(name, viewport, extra = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, ...extra });
  const page = await ctx.newPage();
  const log = { console: [], pageErrors: [], failed: [] };
  report.pages[name] = log;
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') log.console.push(`${m.type()}: ${m.text()}`); });
  page.on('pageerror', (e) => log.pageErrors.push(String(e)));
  page.on('requestfailed', (r) => log.failed.push(`${r.url()} ${r.failure() && r.failure().errorText}`));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/api/vault')) log.failed.push(`${r.status()} ${r.url()}`); });
  if (mock) {
    await page.route('**/api/vault?**', async (route) => {
      const u = new URL(route.request().url());
      await new Promise((r) => setTimeout(r, 1500));
      if ((u.searchParams.get('address') || '').toLowerCase() === USDC.toLowerCase()) {
        return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ error: { code: 'unsupported_contract', status: 422, message: 'contract is not a Morpho vault: not registered by the Morpho VaultV2 or MetaMorpho factories' } }) });
      }
      let body = mock;
      if (u.searchParams.get('shock')) {
        const p = JSON.parse(mock);
        p.scenarios.unshift({ ...p.scenarios[0], name: `Custom shock: ${u.searchParams.get('shock')}`, custom: true });
        body = JSON.stringify(p);
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body });
    });
  }
  return { ctx, page, log };
}

const metrics = (page) => page.evaluate(() => ({
  height: document.documentElement.scrollHeight,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
}));
const shot = (page, f, opts = {}) => page.screenshot({ path: join(outDir, f), ...opts });
const waitResult = (page) => page.waitForSelector('#result:not([hidden]) .vi-verdict', { timeout: 120000 });

// ---- desktop: before, loading, result, tabs, graph selection, custom shock
{
  const { ctx, page, log } = await open('desktop', { width: 1440, height: 900 });
  await page.goto(`${base}/vault.html`, { waitUntil: 'networkidle' });
  await shot(page, 'd1-before.png');
  await page.fill('#fValue', '1000000');
  await page.click('.vi-ex >> nth=0');
  await page.waitForTimeout(2500);
  await shot(page, 'd2-loading.png');
  const t0 = Date.now();
  await waitResult(page);
  log.analysisSeconds = (Date.now() - t0) / 1000 + 2.5;
  await page.waitForTimeout(400);
  await shot(page, 'd3-result-viewport.png');
  await shot(page, 'd4-result-full.png', { fullPage: true });
  await page.evaluate(() => { document.querySelector('.topbar').style.position = 'static'; });
  for (const t of ['alloc', 'deps', 'stress', 'sens', 'assum']) {
    await page.click(`#tab-${t}`);
    await page.waitForTimeout(250);
    await page.locator(`#tp-${t}`).screenshot({ path: join(outDir, `d5-tab-${t}.png`) });
  }
  for (const id of ['exit', 'fx']) await page.locator('#' + id).screenshot({ path: join(outDir, `d5-${id}.png`) });
  await page.click('#tab-deps');
  await page.click('.vi-g-node[data-id="morpho_blue"]');
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(200);
  log.focusedAfterArrow = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('data-id'));
  await page.locator('#tp-deps').screenshot({ path: join(outDir, 'd6-deps-selected.png') });
  await page.click('#tab-stress');
  await page.click('#shockSubmit');
  await page.waitForTimeout(1500);
  await page.locator('#tp-stress').screenshot({ path: join(outDir, 'd7-shock-running.png') });
  await page.waitForSelector('.vi-shockres, #shockOut .alert', { timeout: 120000 });
  await page.locator('#tp-stress').screenshot({ path: join(outDir, 'd8-shock-result.png') });
  await page.evaluate(() => { document.querySelector('.topbar').style.position = ''; });
  await page.click('[data-act="edit"]');
  await page.waitForTimeout(200);
  await shot(page, 'd9-edit-open.png');
  log.metrics = await metrics(page);
  await ctx.close();
}

// ---- mobile: deep link, full page, height, overflow, tabs
{
  const { ctx, page, log } = await open('mobile', { width: 390, height: 844 }, { isMobile: true, hasTouch: true });
  await page.goto(`${base}/vault.html`, { waitUntil: 'networkidle' });
  await shot(page, 'm1-before.png', { fullPage: true });
  await page.goto(`${base}/vault.html?address=${BELEM}&value_usd=1000000&horizon_days=30`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  await shot(page, 'm2-loading.png');
  await waitResult(page);
  await page.waitForTimeout(400);
  await shot(page, 'm3-result-viewport.png');
  await shot(page, 'm4-result-full.png', { fullPage: true });
  log.metrics = await metrics(page);
  await page.evaluate(() => { document.querySelector('.topbar').style.position = 'static'; });
  for (const id of ['bar', 'decision', 'exit', 'fx']) await page.locator('#' + id).screenshot({ path: join(outDir, `m6-${id}.png`) });
  const tabs = {};
  for (const t of ['deps', 'stress', 'sens', 'assum']) {
    await page.click(`#tab-${t}`);
    await page.waitForTimeout(250);
    if (t === 'deps') { await page.click('.vi-chip[data-id="morpho_blue"]'); await page.waitForTimeout(250); }
    await page.locator(`#tp-${t}`).screenshot({ path: join(outDir, `m5-tab-${t}.png`) });
    tabs[t] = await metrics(page);
  }
  log.tabMetrics = tabs;
  await page.evaluate(() => { document.querySelector('.topbar').style.position = ''; });
  await ctx.close();
}

// ---- error case: not a Morpho vault (422), desktop and mobile
for (const [name, vp] of [['error-desktop', { width: 1440, height: 900 }], ['error-mobile', { width: 390, height: 844 }]]) {
  const { ctx, page, log } = await open(name, vp);
  await page.goto(`${base}/vault.html`, { waitUntil: 'networkidle' });
  await page.fill('#fAddress', USDC);
  await page.click('#fSubmit');
  await page.waitForSelector('#notice .alert', { timeout: 120000 });
  log.alert = await page.locator('#notice .alert').innerText();
  await shot(page, `${name === 'error-desktop' ? 'e1' : 'e2'}-422.png`);
  await page.fill('#fAddress', '0x123');
  await page.click('#fSubmit');
  log.fieldError = await page.locator('#fAddressErr').innerText();
  log.metrics = await metrics(page);
  await ctx.close();
}

await browser.close();
console.log(JSON.stringify(report, null, 2));
