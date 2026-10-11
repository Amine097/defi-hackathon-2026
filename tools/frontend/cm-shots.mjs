// Countermove page QA: screenshots at 1440x900 and 390x844, tab keyboard navigation, dry run, live oracle read,
// console errors and horizontal overflow. Run with the dev server up: node cm-shots.mjs [baseUrl]
import { chromium } from 'playwright-core';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const OUT = process.env.CM_QA_OUT || 'C:\\Users\\badis\\.copilot\\session-state\\906236c3-17d7-49f9-95cf-905ac38c1fe9\\files\\qa';
const BASE = process.argv[2] || 'http://127.0.0.1:8101/countermove.html';
const ONLY = process.env.CM_ONLY || '';
const SKIP_NET = process.env.CM_SKIP_NET === '1';
mkdirSync(OUT, { recursive: true });

const problems = [];
const browser = await chromium.launch({ channel: 'chrome' });

async function check(page, name, label) {
  const r = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out = [];
    for (const el of document.querySelectorAll('main *')) {
      if (!el.getClientRects().length) continue;
      const b = el.getBoundingClientRect();
      if (b.right > vw + 1 && !el.closest('.tablewrap, pre')) out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} right=${Math.round(b.right)}`);
    }
    return { sw: document.documentElement.scrollWidth, cw: vw, h: document.documentElement.scrollHeight, out: out.slice(0, 8) };
  });
  if (r.sw > r.cw) problems.push(`${name} ${label}: page overflows horizontally (${r.sw} > ${r.cw})`);
  if (r.out.length) problems.push(`${name} ${label}: elements past the viewport: ${r.out.join(', ')}`);
  console.log(`${name} ${label}: page height ${r.h}px`);
}

for (const [name, viewport, dpr] of [['desktop', { width: 1440, height: 900 }, 1], ['mobile', { width: 390, height: 844 }, 2]]) {
  if (ONLY && ONLY !== name) continue;
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: dpr });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) problems.push(`${name} console ${m.type()}: ${m.text()}`); });
  page.on('pageerror', (e) => problems.push(`${name} page error: ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`${name} request failed: ${r.url()} ${r.failure() && r.failure().errorText}`));
  page.on('response', (r) => { if (r.status() >= 400) problems.push(`${name} HTTP ${r.status()}: ${r.url()}`); });
  const shot = (file, opts = {}) => page.screenshot({ path: join(OUT, `${name}-${file}.png`), ...opts });

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('#cm-lab:not([hidden])', { timeout: 15000 });
  await page.evaluate(() => document.fonts.ready);
  await shot('01-top');
  await check(page, name, 'arm');
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-02-arm.png`) });

  await page.click('#tab-defend');
  await check(page, name, 'defend');
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-03-defend.png`) });

  // keyboard: ArrowRight from Defend selects Prove and moves focus
  await page.focus('#tab-defend');
  await page.keyboard.press('ArrowRight');
  const sel = await page.evaluate(() => ({ sel: document.querySelector('[role=tab][aria-selected=true]').id, focus: document.activeElement.id, hash: location.hash }));
  if (sel.sel !== 'tab-prove' || sel.focus !== 'tab-prove') problems.push(`${name}: ArrowRight did not move to Prove (${JSON.stringify(sel)})`);
  await check(page, name, 'prove');
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-04-prove.png`) });

  // replay (motion allowed here): mid-replay frame
  await page.click('#tab-defend');
  await page.click('#tl-replay');
  await page.waitForTimeout(2600);
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-05-replay-mid.png`) });
  await page.click('#tl-replay');

  // S3 (no action) and S4 (full repay)
  await page.click('.cm-scen__item[data-i="2"]');
  await page.locator('.cm-lab').screenshot({ path: join(OUT, `${name}-06-s3-defend.png`) });
  await page.click('#tab-prove');
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-07-s3-prove.png`) });
  await page.click('.cm-scen__item[data-i="3"]');
  await page.click('#tab-defend');
  await page.locator('.cm-acts').screenshot({ path: join(OUT, `${name}-08-s4-defend.png`) });
  await check(page, name, 's4 defend');

  // policy preview: invalid then valid
  await page.click('.cm-scen__item[data-i="4"]');
  await page.click('#tab-arm');
  const det = page.locator('#pv-details');
  if (!(await det.evaluate((d) => d.open))) await page.click('#pv-details > summary');
  await page.fill('input[name="min_ltv_after"]', '95');
  await page.click('#pv-form [type="submit"]');
  await page.waitForSelector('#pv-out .cm-pv__res', { timeout: 15000 });
  await page.locator('.cm-pv').screenshot({ path: join(OUT, `${name}-09-preview-invalid.png`) });
  await page.fill('input[name="min_ltv_after"]', '40');
  await page.click('#pv-form [type="submit"]');
  await page.waitForSelector('#pv-out .cm-pv__res.is-ok', { timeout: 15000 });
  await page.click('.cm-pv__calls > summary');
  await page.locator('.cm-pv').screenshot({ path: join(OUT, `${name}-10-preview-valid.png`) });
  await check(page, name, 'preview');

  if (!SKIP_NET) {
    await page.click('#dry-run');
    await page.waitForSelector('#dry-work .work', { timeout: 5000 }).catch(() => {});
    await page.locator('.cm-dry').screenshot({ path: join(OUT, `${name}-11-dry-waiting.png`) });
    await page.waitForSelector('#dry-out .cm-dry__chips, #dry-out .alert', { timeout: 60000 });
    await page.locator('.cm-dry').screenshot({ path: join(OUT, `${name}-12-dry-result.png`) });
    await check(page, name, 'dry run');

    await page.click('#live-box > summary');
    await page.waitForSelector('#live-out .cm-oracle, #live-out .alert', { timeout: 70000 });
    await page.locator('.cm-live').screenshot({ path: join(OUT, `${name}-13-live.png`) });
    await check(page, name, 'live');
  }
  await shot('14-full', { fullPage: true });
  await ctx.close();
}

// reduced motion: the replay button is hidden and every step is visible
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await page.goto(`${BASE}#S5-defend`, { waitUntil: 'networkidle' });
  await page.waitForSelector('#cm-lab:not([hidden])');
  const r = await page.evaluate(() => ({ btn: getComputedStyle(document.getElementById('tl-replay')).display, pending: document.querySelectorAll('.is-pending').length, act: document.querySelector('[role=tab][aria-selected=true]').id }));
  if (r.btn !== 'none' || r.pending || r.act !== 'tab-defend') problems.push(`reduced motion: ${JSON.stringify(r)}`);
  await ctx.close();
}

// unavailable: the recorded run fails -> alert with Retry, no figures
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.route('**/api/countermove', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'unavailable', status: 503, message: 'recorded run missing' } }) }));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('#cm-boot .alert--error');
  const ok = await page.evaluate(() => Boolean(document.getElementById('boot-retry')) && document.getElementById('cm-lab').hidden);
  if (!ok) problems.push('unavailable state: no Retry or lab still visible');
  await page.screenshot({ path: join(OUT, 'mobile-15-unavailable.png') });
  await ctx.close();
}

await browser.close();
console.log(problems.length ? `PROBLEMS (${problems.length}):\n- ${problems.join('\n- ')}` : 'No problems found.');
