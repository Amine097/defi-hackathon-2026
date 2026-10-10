import { launch, sleep } from './drv.mjs'; import fs from 'node:fs';
const OUT = process.argv[2], U = 'http://localhost:8766'; const R = []; const shot = (p, n, o) => p.shot(OUT + '\\' + n + '.png', o);
const check = (name, ok, detail = '') => { R.push({ name, ok: !!ok, detail: String(detail).slice(0, 160) }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  [' + String(detail).slice(0, 110) + ']' : '')); };
const step = async (name, fn) => { try { await fn(); } catch (e) { check(name + ' (threw)', false, e.message); } };
// A clearly named TEST provider, announced through EIP-6963. It is injected by this QA script only; it is not in the product.
const TESTP = (mode) => `(()=>{const A='0x71C7656EC7ab88b098defB751B7401B5f6d8976F',h={},calls=[];window.__calls=calls;window.__h=h;
 const p={on:(e,f)=>{h[e]=f},removeListener:(e)=>{delete h[e]},request:({method})=>{calls.push(method);return new Promise((res,rej)=>{
  if(method==='eth_requestAccounts'){'${mode}'==='reject'?rej({code:4001,message:'User rejected the request.'}):res([A])}
  else if(method==='eth_accounts')res(sessionStorage.getItem('faultline.wallet.session')?[A]:[]);else if(method==='eth_chainId')res('0x1');
  else if(method==='wallet_revokePermissions'){'${mode}'==='revoke'?res(null):rej({code:-32601,message:'not supported'})}else rej({code:4200,message:'unsupported'})})}};
 const ann=()=>window.dispatchEvent(new CustomEvent('eip6963:announceProvider',{detail:Object.freeze({info:{uuid:'qa-test',name:'QA test provider (not a real wallet)',icon:'',rdns:'test.faultline.qa'},provider:p})}));
 window.addEventListener('eip6963:requestProvider',ann);ann();})();`;
const b = await launch({ port: 9410 });

await step('routes', async () => { const p = await b.page();
  for (const u of ['/', '/overview.html', '/countermove.html', '/xray.html', '/vault.html', '/soon.html?m=whale', '/landing.html']) { const s = await (await fetch(U + u)).status; check('route ' + u + ' -> ' + s, u === '/landing.html' ? s === 404 : s === 200); }
  await p.goto(U + '/overview.html', 3500); check('overview renders data', (await p.ev(`document.getElementById('m-cap').textContent`)) !== '—', await p.ev(`document.getElementById('m-cap').textContent+' / '+document.getElementById('verdict').textContent`));
  check('overview sidebar: Overview is current, brand goes to /', await p.ev(`!!document.querySelector('.side-link[aria-current="page"][href^="/overview.html"]') && document.querySelector('.side-brand').getAttribute('href')==='/'`));
  await p.click('.side-link[href="/xray.html"], .side-link[href^="/xray.html"]'); await sleep(2500); check('sidebar click -> X-Ray', (await p.ev('location.pathname')) === '/xray.html');
  await p.click('.side-brand'); await sleep(2000); check('brand click -> landing /', (await p.ev('location.pathname')) === '/' && (await p.ev(`document.querySelector('h1').textContent`)).includes('moves'));
  const unexpected = p.log.failed.filter((f) => !/\/api\/analyze|\/exit-cost\//.test(f)); console.log('  failed requests on the static server:', JSON.stringify(p.log.failed)); check('routes: only the expected 404s (no /api and no /exit-cost on a static server)', !unexpected.length && !p.log.errors.filter((e) => e.startsWith('exception')).length, JSON.stringify(unexpected)); await p.close(); });

await step('landing', async () => { const p = await b.page(); await p.goto(U + '/', 2500);
  const n = await p.ev(`(()=>{const n=performance.getEntriesByType('navigation')[0],f=performance.getEntriesByName('first-contentful-paint')[0],r=performance.getEntriesByType('resource');return{fcp:Math.round(f.startTime),dcl:Math.round(n.domContentLoadedEventEnd),req:r.length,kb:Math.round(r.reduce((s,x)=>s+(x.transferSize||x.encodedBodySize||0),0)/1024),three:r.some(x=>x.name.includes('three'))}})()`); R.perf = n; console.log('PERF', JSON.stringify(n));
  check('hero: Three.js not loaded up front, no canvas in the hero', !n.three && await p.ev(`!document.querySelector('.hero canvas')`));
  check('hero: no film control without a configured film', await p.ev(`document.getElementById('filmToggle').hidden && !document.querySelector('.film video')`));
  check('hero: artwork caption present', (await p.ev(`document.getElementById('filmNote').innerText`)).includes('Not a live event'));
  check('hero: headline and both CTAs inside the first screen', await p.ev(`(()=>{const b=[...document.querySelectorAll('.hero .cta .btn')].map(e=>e.getBoundingClientRect());return document.querySelector('h1').getBoundingClientRect().top>=0&&b.every(r=>r.bottom<=innerHeight)})()`));
  await shot(p, '01-landing-desktop-1440');
  const span = await p.ev(`document.getElementById('story').offsetHeight-innerHeight`), top = await p.ev(`document.getElementById('story').offsetTop`);
  for (const i of [0, 1, 2]) { await p.ev(`scrollTo({top:${top}+${span}*${(i + 0.5) / 3},behavior:'instant'})`); await sleep(1200); check('story moment ' + i, (await p.ev(`(document.querySelector('.story-copy article.on')||{dataset:{}}).dataset.m`)) === String(i)); if (i === 1) await shot(p, '02-story-defend'); }
  check('nav solid when scrolled', await p.ev(`document.querySelector('.nav').classList.contains('solid')`));
  await p.ev(`scrollTo({top:0,behavior:'instant'})`); await sleep(300); await p.click('.nav a[data-jump="2"]'); await sleep(1800); check('nav "Prove" jumps to the third moment', (await p.ev(`document.querySelector('.story-copy article.on').dataset.m`)) === '2');
  await p.click('.nav a[href="#demo"]'); await sleep(6500); check('demo: graph loads on approach and is not under the header', await p.ev(`document.getElementById('heroStage').classList.contains('on') && document.querySelector('.stage-frame').getBoundingClientRect().top >= document.querySelector('.nav').getBoundingClientRect().bottom - 1 && document.querySelector('.stage-frame').getBoundingClientRect().bottom <= innerHeight + 1`), await p.ev(`JSON.stringify([Math.round(document.querySelector('.stage-frame').getBoundingClientRect().top),Math.round(document.querySelector('.stage-frame').getBoundingClientRect().bottom),innerHeight])`));
  const s0 = await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`); await sleep(5200); const s1 = await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`); check('demo: sequence plays', s0 !== s1, s0 + '->' + s1);
  await p.click('#seqToggle'); const a = await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`); await sleep(4500); check('demo: Pause stops it', (await p.ev(`document.getElementById('seqToggle').textContent`)) === 'Play' && a === await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`));
  await p.click('#seq [data-s="3"]'); await sleep(2400); await shot(p, '03-demo-graph');
  const ft = await p.ev(`new Promise(r=>{const a=[];let l=performance.now();const f=t=>{a.push(t-l);l=t;a.length<200?requestAnimationFrame(f):r(a)};requestAnimationFrame(f)})`); const srt = [...ft].sort((x, y) => x - y); R.perf.demo_median_ms = +srt[100].toFixed(1); R.perf.demo_p95_ms = +srt[190].toFixed(1); console.log('PERF demo frames', R.perf.demo_median_ms, R.perf.demo_p95_ms);
  await p.click('#enter a.btn'); await sleep(3000); check('Enter the demo -> Countermove, no wallet chip', (await p.ev('location.pathname')) === '/countermove.html' && await p.ev(`document.getElementById('wchip').hidden`));
  await p.goto(U + '/', 2000); await p.click('.hero .cta a.btn'); await sleep(2500); check('Explore demo -> Countermove', (await p.ev('location.pathname')) === '/countermove.html');
  check('landing: no console errors / failed requests', !p.log.errors.length && !p.log.failed.length, JSON.stringify([p.log.errors, p.log.failed])); await p.close(); });

await step('reduced motion', async () => { const p = await b.page({ reduced: true }); await p.goto(U + '/', 3000);
  check('reduced motion: story is a plain stacked section, all three readable', await p.ev(`document.getElementById('story').classList.contains('flat') && [...document.querySelectorAll('.story-copy article')].every(a=>getComputedStyle(a).opacity==='1')`));
  await p.ev(`document.getElementById('demo').scrollIntoView({behavior:'instant'})`); await sleep(5500); const a = await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`); await sleep(3500);
  check('reduced motion: demo does not auto-play', a === 0 && (await p.ev(`document.getElementById('seqToggle').textContent`)) === 'Play' && 0 === await p.ev(`[...document.querySelectorAll('#seq [data-s]')].findIndex(b=>b.hasAttribute('aria-current'))`)); await p.close(); });

await step('wallet: no provider', async () => { const p = await b.page(); await p.goto(U + '/', 2500);
  check('no request is made on load', (await p.ev('typeof window.ethereum')) === 'undefined');
  await p.ev(`document.getElementById('walletBtn').focus()`); await p.enter(); await sleep(400); check('Enter on the button opens the dialog', await p.ev(`document.getElementById('wallet').open`));
  check('no-provider message with install guidance', (await p.ev(`document.getElementById('walletBody').innerText`)).includes('No browser wallet was found'));
  const seen = new Set(); for (let i = 0; i < 8; i++) { await p.tab(); seen.add(await p.ev(`document.getElementById('wallet').contains(document.activeElement)`)); } check('Tab keeps focus inside the dialog', !seen.has(false), [...seen].join(','));
  await shot(p, '04-wallet-no-provider'); await p.esc(); await sleep(300); check('Escape closes and returns focus to the button', (await p.ev(`!document.getElementById('wallet').open && document.activeElement.id`)) === 'walletBtn', await p.active()); await p.close(); });

await step('wallet: test provider', async () => { const p = await b.page({ init: TESTP('ok') }); await p.goto(U + '/', 2500);
  check('provider discovered, nothing requested yet', (await p.ev('JSON.stringify(window.__calls)')) === '[]');
  await p.click('.cta .btn.primary'); await sleep(400); check('dialog lists the announced provider', (await p.ev(`document.querySelector('.wl button').innerText`)).includes('QA test provider'));
  await p.click('.wl button'); await sleep(600); const body = await p.ev(`document.getElementById('walletBody').innerText`);
  check('connected: full address shown', body.includes('0x71C7656EC7ab88b098defB751B7401B5f6d8976F')); check('connected: chain shown as Ethereum', body.includes('Ethereum'));
  check('connected: says positions are not discovered and nothing is armed', body.includes('not built yet') && body.includes('Nothing is armed'));
  check('header button shows the short address', (await p.ev(`document.getElementById('walletBtn').innerText`)).includes('0x71C7…976F')); await shot(p, '03-wallet-connected-test-provider');
  await p.ev(`window.__h.chainChanged('0x7a69')`); await sleep(200); check('chainChanged -> Local fork (31337)', (await p.ev(`document.getElementById('walletBody').innerText`)).includes('Local fork (31337)'));
  await p.ev(`window.__h.accountsChanged(['0x000000000000000000000000000000000000dEaD'])`); await sleep(200); check('accountsChanged -> new address', (await p.ev(`document.getElementById('walletBody').innerText`)).includes('0x000000000000000000000000000000000000dEaD'));
  const calls = JSON.parse(await p.ev('JSON.stringify(window.__calls)')); check('only account/chain methods were called', calls.every((m) => ['eth_requestAccounts', 'eth_chainId', 'eth_accounts'].includes(m)), calls.join(','));
  await p.click('#walletBody a.btn.primary'); await sleep(3500); check('Enter FaultLine -> Countermove', (await p.ev('location.pathname')) === '/countermove.html');
  check('Countermove shows the wallet chip', (await p.ev(`!document.getElementById('wchip').hidden && document.getElementById('wchip').innerText`)) === '0x71C7…976F', await p.ev(`document.getElementById('wchip').innerText`));
  const arm = await p.ev(`document.getElementById('view').innerText`); check('Arm screen: position is not this wallet\\u2019s, status still Draft', arm.includes('not this wallet') && arm.includes('Draft, not armed'));
  await shot(p, '08-countermove-with-wallet-chip');
  await p.click('#wchip'); await sleep(2500); check('chip -> landing with dialog open, session restored without prompt', (await p.ev(`document.getElementById('wallet').open && document.getElementById('walletTitle').textContent`)) === 'Wallet connected');
  await p.click('#wDisc'); await sleep(500); const after = await p.ev(`document.getElementById('walletBody').innerText`); check('Disconnect: session cleared, wording does NOT claim revocation (provider refused)', after.includes('may still list') && !after.includes('revoked this site') && (await p.ev(`sessionStorage.getItem('faultline.wallet.session')`)) === null);
  await p.close();
  const q = await b.page({ init: TESTP('revoke') }); await q.goto(U + '/?wallet=1', 2500); await q.click('.wl button'); await sleep(500); await q.click('#wDisc'); await sleep(500); check('Disconnect with a provider that confirms revocation says so', (await q.ev(`document.getElementById('walletBody').innerText`)).includes('revoked this site')); await q.close();
  const r = await b.page({ init: TESTP('reject') }); await r.goto(U + '/?wallet=1', 2500); await r.click('.wl button'); await sleep(500); const rb = await r.ev(`document.getElementById('walletBody').innerText`); check('Rejected: message shown, not connected', rb.includes('You declined') && (await r.ev(`document.getElementById('walletBtn').innerText`)) === 'Connect wallet'); await shot(r, '05-wallet-rejected-test-provider'); await r.close(); });

await step('countermove by clicks', async () => { const p = await b.page(); await p.goto(U + '/countermove.html', 4500);
  await p.click('#arm'); await sleep(400); check('Arm the demo -> simulated, not armed for real', (await p.ev(`document.querySelector('.status').innerText`)).includes('Demo armed (simulated)'));
  const pos = await p.ev(`(()=>{const l=[...document.querySelectorAll('.cm-lbl')].find(e=>e.style.display!=='none'&&e.textContent.includes('Morpho market'));if(!l)return null;const r=l.getBoundingClientRect();return{x:r.left-24,y:r.top+r.height/2}})()`);
  if (pos) { await p.clickXY(pos.x, pos.y); await sleep(500); check('3D node click selects it', await p.ev(`!!document.querySelector('.cm-lbl.sel') && document.querySelector('.cm-lbl.sel').innerText`), await p.ev(`(document.querySelector('.cm-lbl.sel')||{}).innerText||'no selection label'`)); await shot(p, '06-countermove-arm-node-selected'); } else check('3D node click selects it', false, 'label not found');
  await p.click('.armbar a[data-go="defend"]'); await sleep(500); await p.click('#start'); await sleep(2500);
  check('Replay starts at DETECTED', (await p.ev(`document.querySelector('.timeline li.now b').innerText`)) === 'DETECTED');
  await p.click('#next'); await sleep(800); check('Next -> PLANNING, comparison appears', (await p.ev(`document.querySelector('.timeline li.now b').innerText`)) === 'PLANNING' && (await p.ev(`document.querySelectorAll('.strat article').length`)) === 3);
  await p.click('#next'); await sleep(2600); await shot(p, '07-countermove-defend-logos'); await p.ev(`document.getElementById('stage').blur()`); await p.space(); await sleep(900);
  check('Space advances to the result, shown as SIMULATED', (await p.ev(`document.querySelector('.timeline li.now b').innerText`)) === 'SIMULATED');
  await p.click('#play a[data-go="proof"]'); await sleep(900); const proof = await p.ev(`document.getElementById('view').innerText`); check('Proof: SIMULATED, demo fixture, 0 of 5 checks', proof.includes('SIMULATED') && proof.includes('0 of 5 checks') && !proof.includes('CONFIRMED')); await shot(p, '09-countermove-proof');
  check('countermove: no console errors / failed requests', !p.log.errors.length && !p.log.failed.length, JSON.stringify([p.log.errors, p.log.failed])); await p.close(); });

await step('no WebGL', async () => { const g = await launch({ port: 9411, flags: ['--disable-3d-apis'], profile: 'fl-nogl' }); const p = await g.page(); await p.goto(U + '/', 5000);
  await p.ev(`document.getElementById('demo').scrollIntoView({behavior:'instant'})`); await sleep(4000); check('no WebGL: hero intact, demo graph and its controls hidden', await p.ev(`!document.getElementById('heroStage').classList.contains('on') && document.getElementById('seq').hidden && document.querySelector('h1').offsetHeight>0`)); await shot(p, '14-landing-no-webgl');
  await p.goto(U + '/countermove.html?run=repay&step=2#defend', 4500); check('no WebGL: Countermove falls back, path listed as text', await p.ev(`document.body.classList.contains('no3d') && document.querySelectorAll('.path li').length>=3`)); await shot(p, '15-countermove-no-webgl');
  check('no WebGL: no uncaught errors', !p.log.errors.filter((e) => e.startsWith('exception')).length, JSON.stringify(p.log.errors).slice(0, 150)); await p.close(); g.close(); });

fs.writeFileSync(OUT + '\\results.json', JSON.stringify({ perf: R.perf, checks: R }, null, 1)); console.log('TOTAL', R.filter((x) => x.ok).length + '/' + R.length); process.exit(0);
