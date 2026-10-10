// Minimal CDP driver (Node 22, Windows Chrome). Used only for QA; not part of the product.
import { spawn } from 'node:child_process'; import fs from 'node:fs';
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function launch({ port = 9400, flags = [], profile = 'fl-drv' } = {}) {
  const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', ['--headless=new', '--remote-debugging-port=' + port, '--hide-scrollbars', '--ignore-gpu-blocklist', '--no-first-run', '--user-data-dir=C:\\Temp\\' + profile + '-' + Date.now(), ...flags, 'about:blank'], { stdio: 'ignore' });
  let ver; for (let i = 0; i < 40; i++) { try { ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); break; } catch { await sleep(250); } }
  if (!ver) throw new Error('chrome did not start');
  async function page({ w = 1440, h = 900, mobile = false, reduced = false, init = '' } = {}) {
    const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
    const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
    let id = 0; const pend = new Map(), log = { errors: [], failed: [], requests: 0 };
    ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); return; }
      if (d.method === 'Runtime.exceptionThrown') log.errors.push('exception: ' + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text).slice(0, 200));
      if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') log.errors.push('console.error: ' + d.params.args.map((a) => a.value || a.description || '').join(' ').slice(0, 200));
      if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') log.errors.push('log: ' + d.params.entry.text.slice(0, 160) + ' ' + (d.params.entry.url || '').slice(-60));
      if (d.method === 'Network.responseReceived') { log.requests++; if (d.params.response.status >= 400) log.failed.push(d.params.response.status + ' ' + d.params.response.url.replace(/^https?:\/\/[^/]+/,'').slice(0,70)); }
      if (d.method === 'Network.loadingFailed' && !d.params.canceled) log.failed.push('failed ' + d.params.errorText); };
    const send = (method, params = {}) => new Promise((res, rej) => { const k = ++id; const to = setTimeout(() => { pend.delete(k); rej(new Error('timeout ' + method)); }, 30000); pend.set(k, (d) => { clearTimeout(to); d.error ? rej(new Error(method + ': ' + d.error.message)) : res(d.result); }); ws.send(JSON.stringify({ id: k, method, params })); });
    await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: mobile ? 2 : 1, mobile }); if (mobile) await send('Emulation.setTouchEmulationEnabled', { enabled: true });
    if (reduced) await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    if (init) await send('Page.addScriptToEvaluateOnNewDocument', { source: init });
    const ev = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error('eval: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text).slice(0, 300)); return r.result.value; };
    const P = { log, send, ev,
      goto: async (url, wait = 2500) => { await send('Page.navigate', { url }); await sleep(wait); },
      rect: (sel) => ev(`(()=>{const e=document.querySelector(${JSON.stringify(sel)});if(!e)return null;e.scrollIntoView({block:'center',inline:'center',behavior:'instant'});const r=e.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height}})()`),
      clickXY: async (x, y) => { for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 }); await sleep(120); },
      click: async (sel) => { const r = await P.rect(sel); if (!r) throw new Error('no element ' + sel); await sleep(80); const r2 = await P.rect(sel); await P.clickXY(r2.x, r2.y); },
      key: async (key, code, vk, mods = 0) => { const base = { key, code: code || key, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: mods }; await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...base }); if (key.length === 1 || key === 'Enter') await send('Input.dispatchKeyEvent', { type: 'char', ...base, text: key === 'Enter' ? '\r' : key }); await send('Input.dispatchKeyEvent', { type: 'keyUp', ...base }); await sleep(90); },
      tab: (shift) => P.key('Tab', 'Tab', 9, shift ? 8 : 0), enter: () => P.key('Enter', 'Enter', 13), esc: () => P.key('Escape', 'Escape', 27), space: () => P.key(' ', 'Space', 32), right: () => P.key('ArrowRight', 'ArrowRight', 39),
      active: () => ev(`(()=>{const a=document.activeElement;return a?(a.tagName+(a.id?'#'+a.id:'')+' "'+(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,40)+'"'):''})()`),
      shot: async (file, { full = false, format = 'png', quality } = {}) => { let clip; if (full) { const m = await send('Page.getLayoutMetrics'); clip = { x: 0, y: 0, width: m.cssContentSize.width, height: m.cssContentSize.height, scale: 1 }; } const r = await send('Page.captureScreenshot', { format, quality, clip, captureBeyondViewport: !!full }); fs.writeFileSync(file, Buffer.from(r.data, 'base64')); return file; },
      close: async () => { try { ws.close(); await fetch(`http://127.0.0.1:${port}/json/close/${t.id}`); } catch {} } };
    return P;
  }
  return { page, close: () => { try { chrome.kill(); } catch {} } };
}
