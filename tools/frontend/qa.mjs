// Dev-only end-to-end QA: real browser, live backend. Asserts that the numbers on screen are the API's numbers.
// Usage: node qa.mjs [base=http://127.0.0.1:8000] [outDir]
import { chromium } from 'playwright-core';
import { usd, usdFull } from '../../public/assets/js/core/format.js';

const BASE = process.argv[2] || 'http://127.0.0.1:8000';
const OUT = process.argv[3] || '.';
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };
const IGNORE = /X4122|cannot be represented accurately|GPU stall|GL Driver Message/;

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });

async function newPage(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...opts });
  const page = await ctx.newPage();
  page.errors = [];
  page.on('console', (m) => { if (m.type() === 'error' && !IGNORE.test(m.text())) page.errors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => page.errors.push('pageerror ' + e.message.slice(0, 200)));
  page.payloads = [];
  page.on('response', async (r) => {
    if (r.url().includes('/api/') && r.status() === 200) { try { page.payloads.push({ url: r.url(), data: await r.json() }); } catch {} }
  });
  return { ctx, page };
}
const text = (page, sel) => page.locator(sel).first().innerText().catch(() => '');

// 1. landing
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3500);
  const ready = await page.locator('#heroCanvas.is-ready').count();
  check('landing: WebGL hero renders', ready === 1);
  const hrefs = await page.locator('.hero__cta a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
  check('landing: primary CTAs go to analysis and protection lab', hrefs[0] === '/analyze.html' && hrefs[1] === '/countermove.html', hrefs.join(', '));
  check('landing: headline text is accessible', /When DeFi breaks,\s*FAULTLINE\s*moves first\./i.test((await text(page, '#heroTitle')).replace(/\s+/g, ' ').replace('FAULT LINE', 'FAULTLINE')) || /FAULTLINE/.test(await page.locator('#heroTitle .vh').innerText()));
  await page.click('#heroPause');
  check('landing: pause control toggles', (await page.getAttribute('#heroPause', 'aria-pressed')) === 'true');
  check('landing: no console errors', page.errors.length === 0, page.errors.join(' | '));
  await page.screenshot({ path: `${OUT}/qa-landing.png` });
  await ctx.close();
}
{
  const { ctx, page } = await newPage({ reducedMotion: 'reduce' });
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  check('landing reduced motion: final contained frame, no pause control', (await page.locator('.hero.is-proved').count()) === 1 && !(await page.locator('#heroPause').isVisible()));
  await ctx.close();
}

// 2. analysis, live
{
  const { ctx, page } = await newPage();
  const t0 = Date.now();
  await page.goto(BASE + '/analyze.html', { waitUntil: 'domcontentloaded' });
  check('analysis: honest progress shown while waiting', await page.locator('.work').isVisible({ timeout: 4000 }).catch(() => false));
  await page.waitForSelector('.an-verdict__word', { timeout: 120000 });
  const p = page.payloads.find((x) => !/shock=|exit_cost_pct=|borrower=/.test(x.url)).data;
  check('analysis: live payload loaded', !!p, `${((Date.now() - t0) / 1000).toFixed(1)} s, source ${p && p.source}`);
  const d = p.decision;
  const facts = await text(page, '#facts');
  check('analysis: stay loss shown = decision.expected_loss_usd', facts.includes(usdFull(d.expected_loss_usd)), usdFull(d.expected_loss_usd));
  check('analysis: exit side shown = decision.exit_total_usd', facts.includes(usdFull(d.exit_total_usd)), usdFull(d.exit_total_usd));
  check('analysis: verdict word = decision.verdict', (await text(page, '.an-verdict__word')).toUpperCase() === d.verdict);
  const chip = await text(page, '#shell-end');
  check('analysis: status chip says Live with block', /Live/.test(chip) && /block/.test(chip), chip);

  const oracle = p.nodes.find((n) => n.meta.role === 'oracle');
  await page.click(`.g-node[data-id="${oracle.id}"]`);
  await page.waitForTimeout(600);
  const panel = await text(page, '#nodePanel');
  check('REGRESSION analysis: oracle failure shows "No effect on this position"', /No effect on this position/.test(panel) && !/\$15\dk/.test(panel));
  const issuer = p.nodes.find((n) => n.meta.role === 'issuer');
  const row = p.stress_table.find((r) => r.id === issuer.id);
  await page.click(`.g-node[data-id="${issuer.id}"]`);
  await page.waitForTimeout(600);
  check('analysis: issuer impact = stress_table row', (await text(page, '#nodePanel')).includes(usd(row.conditional_loss_usd)), usd(row.conditional_loss_usd));
  await page.screenshot({ path: `${OUT}/qa-analysis-issuer.png` });

  // exit or hold
  await page.click('#t-options');
  const opt = await text(page, '#p-options');
  if (p.maturity.status === 'ok') {
    const h = p.maturity.options.find((o) => o.option === 'HOLD_TO_MATURITY');
    check('analysis: hold to maturity central = backend', opt.includes(usd(h.central_usd)), usd(h.central_usd));
  } else check('analysis: hold to maturity hidden with reason', opt.includes(p.maturity.reason));

  // incident: issuer at 50%
  await page.click('#t-incident');
  await page.click('.inc-presets button:has-text("Issuer loses 50%")');
  await page.waitForSelector('#incResult .inc-cmp', { timeout: 120000 });
  const ip = page.payloads.find((x) => /shock=/.test(x.url));
  const inc = ip && ip.data.incident;
  const incText = await text(page, '#incResult');
  check('analysis: incident uses the server (shock= request made)', !!ip, ip && ip.url.replace(BASE, ''));
  check('analysis: incident loss = incident.position.conditional_loss_usd', inc && incText.includes(usd(inc.position.conditional_loss_usd)), inc && usd(inc.position.conditional_loss_usd));
  check('analysis: incident verdict = backend', inc && incText.includes(inc.position.verdict === 'EXIT' ? 'Exit' : inc.position.verdict === 'STAY' ? 'Stay' : 'Review'));
  await page.screenshot({ path: `${OUT}/qa-analysis-incident.png`, fullPage: false });

  // book: brief's 11%
  await page.click('#t-book');
  await page.click('#p-book [data-m="brief"]');
  await page.waitForFunction(() => /given/.test(document.querySelector('#p-book').innerText), null, { timeout: 120000 });
  const bp = page.payloads.find((x) => /exit_cost_pct=0.11/.test(x.url));
  const bookTxt = await text(page, '#p-book');
  check('analysis: 11% book uses the server', !!bp);
  if (bp) {
    const b = bp.data.book;
    check('analysis: 11% book total = backend', bookTxt.includes(usd(b.total_optimal_usd)), usd(b.total_optimal_usd));
    const exits = b.pockets.filter((x) => x.verdict === 'EXIT').length;
    const shownExit = await page.locator('#p-book tbody .tag--exit').count();
    const hitTags = b.pockets.filter((x) => x.affected).length;
    check('analysis: 11% book EXIT rows = backend EXIT rows', shownExit - hitTags === exits - 0 || shownExit === exits + hitTags, `backend EXIT ${exits}, hit ${hitTags}, exit tags ${shownExit}`);
  }
  await page.screenshot({ path: `${OUT}/qa-analysis-book.png` });
  check('analysis: no console errors', page.errors.length === 0, page.errors.join(' | '));
  await ctx.close();
}

// 3. API failure, retry, explicit snapshot
{
  const { ctx, page } = await newPage();
  await page.route('**/api/analyze**', (r) => r.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ error: 'RuntimeError: simulated outage', code: 'discovery_failed', hint: 'retry' }) }));
  await page.goto(BASE + '/analyze.html', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[role="alert"]', { timeout: 20000 });
  const alert = await text(page, '[role="alert"]');
  check('failure: UNAVAILABLE with the cause, no substituted numbers', /Live discovery failed/.test(alert) && !/\$\d/.test(await text(page, '#facts')));
  check('failure: header chip says Unavailable', /Unavailable/.test(await text(page, '#shell-end')));
  await page.click('[data-a="snap"]');
  await page.waitForSelector('.an-verdict__word', { timeout: 20000 });
  check('failure: explicit saved snapshot is labelled with block and date', /Saved snapshot/.test(await text(page, '#shell-end')) && /block/.test(await text(page, '#shell-end')));
  check('failure: Re-run live stays available from the snapshot', await page.isEnabled('#rerun'));
  await page.screenshot({ path: `${OUT}/qa-analysis-snapshot.png` });
  await ctx.close();
}
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/analyze.html?snapshot=1', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.an-verdict__word', { timeout: 20000 });
  check('snapshot deep link: labelled, and Re-run live is enabled', /Saved snapshot/.test(await text(page, '#shell-end')) && await page.isEnabled('#rerun'));
  await ctx.close();
}

// 4. legacy URL
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/xray.html?ref=auto', { waitUntil: 'domcontentloaded' });
  await page.waitForURL('**/analyze.html**', { timeout: 10000 }).catch(() => {});
  check('legacy: /xray.html redirects to /analyze.html keeping the query', /analyze\.html\?ref=auto/.test(page.url()), page.url());
  await ctx.close();
}

// 5. countermove: recorded fork run + live dry run
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/countermove.html', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#cm-lab:not([hidden])', { timeout: 30000 });
  const run = page.payloads.find((x) => /\/api\/countermove$/.test(x.url)).data;
  const s5 = run.positions.find((p) => p.scenario === 'S5' || /S5/.test(p.id));
  check('countermove: S5 is the default scenario', /S5/.test(await text(page, '.cm-scen__item[aria-pressed="true"]')));
  const amt = s5.execution.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  check('countermove: executed amount = execution.amount', (await text(page, '#cm-head')).includes(amt), `${amt} ${s5.execution.token}`);
  check('countermove: recorded run labelled Simulated fork', /Simulated fork/.test(await text(page, '#cm-env-chip')) && /Simulated fork/.test(await text(page, '#cm-head')));
  check('countermove: no Etherscan links for fork transactions', (await page.locator('#cm-lab a[href*="etherscan"]').count()) === 0);
  await page.click('#tab-prove');
  const prove = await text(page, '#panel-prove');
  check('countermove: proof shows fork tx and states it is not on mainnet', prove.includes(s5.execution.tx_hash.slice(0, 8)) && /Not verified on Ethereum mainnet/i.test(prove));
  check('countermove: no "sign" call to action anywhere', (await page.locator('button, a.btn').filter({ hasText: /\bsign\b/i }).count()) === 0);
  await page.selectOption('#dry-market', 'weETH/USDC');
  await page.click('#dry-run');
  await page.waitForFunction(() => document.querySelector('#dry-out').innerText.trim().length > 40, null, { timeout: 90000 });
  const dryP = page.payloads.find((x) => /action=dry-run/.test(x.url));
  const dry = await text(page, '#dry-out');
  check('countermove: dry run reads mainnet live at a pinned block', dryP && /Live/.test(dry) && dry.includes(dryP.data.environment.block.toLocaleString('en-US')), dryP && `block ${dryP.data.environment.block}`);
  check('countermove: dry run shows no transaction field', !/0x[0-9a-f]{64}/i.test(dry.replace(dryP ? dryP.data.market.id : '', '')) && !/transaction hash/i.test(dry));
  check('countermove: dry run labelled Dry run', /Dry run/i.test(await text(page, '#dry-chip')));
  await page.screenshot({ path: `${OUT}/qa-countermove-dry.png` });
  check('countermove: no console errors', page.errors.length === 0, page.errors.join(' | '));
  await ctx.close();
}

// 6. vault: Belem example live, then a contract that is not a vault (real 422)
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/vault.html?address=0xD6d4b804014EF27836dBe9f8f6Bf6c71251548Ec&value_usd=1000000&horizon_days=30', { waitUntil: 'domcontentloaded' });
  check('vault: honest progress shown while waiting', await page.locator('#work').isVisible({ timeout: 4000 }).catch(() => false));
  await page.waitForSelector('#result:not([hidden]) .vi-verdict', { timeout: 120000 });
  const v = page.payloads.find((x) => /\/api\/vault\?/.test(x.url)).data;
  const dec = await text(page, '#decision');
  check('vault: verdict = decision.verdict', (await text(page, '.vi-verdict .vword')).toUpperCase() === v.decision.verdict, v.decision.verdict);
  check('vault: stay loss = decision.expected_loss_usd', dec.includes(usd(v.decision.expected_loss_usd)) || dec.includes(usdFull(v.decision.expected_loss_usd)), usd(v.decision.expected_loss_usd));
  check('vault: exit side = decision.exit_side_usd', dec.includes(usd(v.decision.exit_side_usd)) || dec.includes(usdFull(v.decision.exit_side_usd)), usd(v.decision.exit_side_usd));
  check('vault: status chip Live with block', /Live/.test(await text(page, '#shell-end')) && (await text(page, '#shell-end')).includes(String(v.as_of_block).replace(/\B(?=(\d{3})+(?!\d))/g, ',')));
  await page.screenshot({ path: `${OUT}/qa-vault-belem.png` });
  check('vault: no console errors', page.errors.length === 0, page.errors.join(' | '));
  await ctx.close();
}
{
  const { ctx, page } = await newPage();
  await page.goto(BASE + '/vault.html?address=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48&value_usd=1000000', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => /Not a Morpho vault/.test(document.body.innerText), null, { timeout: 60000 }).catch(() => {});
  const body = await text(page, 'main');
  check('vault: non-vault contract shows the 422 inline, no figures', /Not a Morpho vault/.test(body) && (await page.locator('#result').isHidden()));
  await ctx.close();
}

await browser.close();
const fails = results.filter((r) => !r.ok);
console.log(`\n${results.length - fails.length}/${results.length} checks passed`);
process.exitCode = fails.length ? 1 : 0;
