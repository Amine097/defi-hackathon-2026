// API client: timeouts, cancellation, in-flight de-duplication, structured errors and an explicit,
// labelled session cache. It never substitutes other data when a call fails.
const inflight = new Map();
const CACHE_PREFIX = 'fl:v1:';

export class ApiError extends Error {
  constructor({ status = 0, code = 'network_error', message = 'request failed', hint = '', detail = null } = {}) {
    super(message);
    Object.assign(this, { status, code, hint, detail });
  }
}

function parseError(status, body) {
  if (body && typeof body.error === 'object' && body.error) {
    const e = body.error;
    return new ApiError({ status: e.status || status, code: e.code || 'error', message: e.message || 'request failed', detail: e });
  }
  if (body && body.error) return new ApiError({ status, code: body.code || 'error', message: String(body.error), hint: body.hint || '' });
  return new ApiError({ status, code: 'http_' + status, message: `the server answered ${status}` });
}

function anySignal(signals) {
  const list = signals.filter(Boolean);
  if (AbortSignal.any) return AbortSignal.any(list);
  const c = new AbortController();
  list.forEach((s) => (s.aborted ? c.abort(s.reason) : s.addEventListener('abort', () => c.abort(s.reason), { once: true })));
  return c.signal;
}

/** A result fetched earlier in THIS browser session; reused only when asked, and shown as CACHED with its age. */
export function cached(url) {
  try {
    const raw = sessionStorage.getItem(CACHE_PREFIX + url);
    if (!raw) return null;
    const { t, data } = JSON.parse(raw);
    return { data, ageS: (Date.now() - t) / 1000, savedAt: t };
  } catch { return null; }
}
function remember(url, data) {
  try { sessionStorage.setItem(CACHE_PREFIX + url, JSON.stringify({ t: Date.now(), data })); }
  catch { /* quota: caching is optional */ }
}

/**
 * GET JSON. Resolves { data, fromCache, ageS, ms }. Rejects with ApiError (code 'aborted' | 'timeout' | server code).
 * timeout: Vercel caps functions at 60 s; a little more is allowed for transfer.
 */
export async function getJson(url, { timeout = 75000, signal, useCache = false, maxCacheAgeS = Infinity, store = true } = {}) {
  if (useCache) {
    const c = cached(url);
    if (c && c.ageS <= maxCacheAgeS) return { data: c.data, fromCache: true, ageS: c.ageS, ms: 0 };
  }
  if (inflight.has(url)) return inflight.get(url);
  const timer = new AbortController();
  const tid = setTimeout(() => timer.abort(), timeout);
  const t0 = performance.now();
  const p = (async () => {
    let r;
    try {
      r = await fetch(url, { signal: anySignal([signal, timer.signal]), cache: 'no-store', headers: { Accept: 'application/json' } });
    } catch (e) {
      if (signal && signal.aborted) throw new ApiError({ code: 'aborted', message: 'request cancelled' });
      if (timer.signal.aborted) throw new ApiError({ code: 'timeout', message: `no answer after ${Math.round(timeout / 1000)} s` });
      throw new ApiError({ code: 'network_error', message: 'the server could not be reached' });
    } finally { clearTimeout(tid); }
    let body = null;
    try { body = await r.json(); } catch { /* non-JSON */ }
    if (!r.ok) throw parseError(r.status, body);
    if (!body) throw new ApiError({ status: r.status, code: 'invalid_payload', message: 'the server returned no JSON' });
    if (store) remember(url, body);
    return { data: body, fromCache: false, ageS: 0, ms: performance.now() - t0 };
  })();
  inflight.set(url, p);
  p.finally(() => inflight.delete(url)).catch(() => {});
  return p;
}

export function apiUrl(path, params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') q.set(k, v);
  const s = q.toString();
  return path + (s ? '?' + s : '');
}

/** Human explanation + next step for an ApiError. */
export function explain(err) {
  const e = err || {};
  if (e.code === 'timeout') return { title: 'The analysis did not finish in time', body: `${e.message}. Public RPC endpoints and data APIs can be slow; retrying usually works.` };
  if (e.code === 'network_error') return { title: 'The FAULTLINE API could not be reached', body: 'Check the connection, then retry.' };
  if (e.code === 'discovery_failed') return { title: 'Live discovery failed', body: `${e.message}${e.hint ? ` — ${e.hint}` : ''}` };
  if (e.code === 'aborted') return { title: 'Cancelled', body: 'The request was cancelled.' };
  return { title: `The server could not complete the request (${e.status || '—'} ${e.code || ''})`, body: e.message || '' };
}
