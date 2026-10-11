// Fidelity QA: drives the approved Claude Design export and the implementation through the same states, at the same
// viewports, and saves paired screenshots for side-by-side review (docs/frontend/fidelity/<viewport>/<state>.<side>.png).
// The design export runs on its own runtime and mock data (faultline-data.js); the implementation runs on the backend.
//
//   python scripts/dev_server.py 8000                                   (implementation + API)
//   python -m http.server 8001 --directory docs/design/claude-design-v2 (design export; needs internet: unpkg, Google Fonts)
//   node tools/frontend/dc-qa.mjs [--only=app|landing] [--vp=1440,1024,390] [--side=design|app]
import { chromium } from 'playwright-core';
import { mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'docs', 'frontend', 'fidelity');
const arg = (k, d) => (process.argv.find(a => a.startsWith('--' + k + '=')) || '').split('=')[1] || d;
const VPS = arg('vp', '1440,1024,390').split(',').map(Number);
const ONLY = arg('only', '');
const SIDES = arg('side', 'design,app').split(',');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const SITE = {
  design: { landing: 'http://127.0.0.1:8001/Faultline%20Landing%20v2.dc.html', app: 'http://127.0.0.1:8001/Faultline%20App.dc.html' },
  app: { landing: 'http://127.0.0.1:8000/', app: 'http://127.0.0.1:8000/app.html' }
};
// Known, harmless: the browser parses the raw <x-dc> template (SVG attributes holding {{ }} placeholders) before the
// design runtime replaces it. The design export logs exactly the same messages.
const NOISE = [/attribute [a-z0-9]+: Expected (length|moveto)/i, /The specified value "\{\{/];

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function clickText(p, t, opts) { await p.getByText(t, Object.assign({ exact: true }, opts || {})).first().click(); }

const LANDING = [
  ['landing-hero', async p => { await sleep(2500); }],
  ['landing-layers', async p => { await clickText(p, 'DEPENDENCIES'); await sleep(2500); }],
  ['landing-arm', async p => { await clickText(p, 'ARM'); await sleep(3000); }],
  ['landing-defend', async p => { await clickText(p, 'DEFEND'); await sleep(3000); }],
  ['landing-prove', async p => { await clickText(p, 'PROVE'); await sleep(3000); }],
  ['landing-enter', async p => { await clickText(p, 'ENTER'); await sleep(2500); }]
];
const APP = [
  ['app-select', async p => { await sleep(1500); }],
  ['app-select-candidate', async p => { await p.getByText('Start analysis').waitFor({ state: 'detached', timeout: 100 }).catch(() => {}); await p.locator('main button').filter({ hasText: /PT-reUSD/ }).first().click(); await sleep(500); }],
  ['app-loading', async p => { await clickText(p, 'Start analysis'); await sleep(900); }],
  ['app-dashboard', async p => { await sleep(3500); }],
  ['app-dashboard-details', async p => { await p.getByText(/Show technical details/).click(); await sleep(500); }],
  ['app-positions', async p => { await p.locator('aside button, nav button').filter({ hasText: /Positions/ }).first().click(); await sleep(700); }],
  ['app-xray', async p => { await p.locator('aside button, nav button').filter({ hasText: /X-Ray/ }).first().click(); await sleep(900); }],
  ['app-xray-revealed', async p => { await p.getByText(/^Reveal \d+ hidden dependencies$/).click(); await sleep(900); }],
  ['app-xray-node', async p => { await p.locator('svg g[style*="cursor"]').nth(5).click(); await sleep(700); }],
  ['app-xray-list', async p => { await clickText(p, 'LIST'); await sleep(500); }],
  ['app-simulate', async p => { await clickText(p, 'GRAPH'); await clickText(p, 'Simulate attack'); await sleep(700); }],
  ['app-simulate-result', async p => { await clickText(p, 'Launch simulation'); await sleep(4500); }],
  ['app-simulate-scenario', async p => { await clickText(p, 'INCIDENT TYPE'); await p.locator('button').filter({ hasText: /^Underlying depeg/ }).first().click(); await clickText(p, 'Launch simulation'); await sleep(4500); }],
  ['app-replay', async p => { await clickText(p, 'Replay incident'); await sleep(800); }],
  ['app-replay-t5', async p => { for (let i = 0; i < 5; i++) { await p.getByLabel('Next step').click(); await sleep(250); } await sleep(700); }],
  ['app-replay-s5', async p => { await p.locator('button').filter({ hasText: 'S5 · Pendle PT on Morpho' }).first().click(); await sleep(800); }],
  ['app-countermove', async p => { await p.locator('aside button, nav button').filter({ hasText: /Countermove|Protect/ }).first().click(); await sleep(700); }],
  ['app-countermove-fork-preview', async p => { await clickText(p, 'Use fork position S1'); await sleep(700); }],
  ['app-countermove-validated', async p => { await clickText(p, 'Validate policy preview'); await sleep(3500); }],
  ['app-countermove-fork', async p => { await p.locator('button').filter({ hasText: /Fork demonstration/ }).first().click(); await sleep(600); }],
  ['app-countermove-deployed', async p => { await p.locator('button').filter({ hasText: /Autonomous protection/ }).first().click(); await sleep(600); }],
  ['app-activity', async p => { await p.locator('aside button, nav button').filter({ hasText: /Activity|Evidence/ }).first().click(); await sleep(700); }]
];

const browser = await chromium.launch({ executablePath: CHROME, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const report = [];
for (const vp of VPS) {
  const dir = join(OUT, String(vp)); mkdirSync(dir, { recursive: true });
  for (const side of SIDES) {
    for (const [kind, steps] of [['landing', LANDING], ['app', APP]]) {
      if (ONLY && ONLY !== kind) continue;
      const page = await browser.newPage({ viewport: { width: vp, height: vp >= 1000 ? 900 : 844 }, deviceScaleFactor: 1 });
      const errs = [];
      page.on('console', m => { if (m.type() === 'error' && !NOISE.some(r => r.test(m.text()))) errs.push(m.text().slice(0, 240)); });
      page.on('pageerror', e => errs.push('pageerror: ' + e.message.slice(0, 240)));
      await page.goto(SITE[side][kind], { waitUntil: 'networkidle', timeout: 60000 }).catch(e => errs.push('goto: ' + e.message));
      for (const [name, step] of steps) {
        let ok = true;
        try { await step(page); } catch (e) { ok = false; errs.push(name + ': ' + e.message.split('\n')[0].slice(0, 200)); }
        await page.screenshot({ path: join(dir, `${name}.${side}.png`), fullPage: kind === 'app' }).catch(() => {});
        report.push({ vp, side, name, ok });
      }
      if (errs.length) report.push({ vp, side, kind, errors: errs });
      await page.close();
    }
  }
}
await browser.close();
const failed = report.filter(r => r.ok === false).map(r => `${r.vp} ${r.side} ${r.name}`);
console.log(JSON.stringify({ states: report.filter(r => 'ok' in r).length, failed, errors: report.filter(r => r.errors) }, null, 1));
