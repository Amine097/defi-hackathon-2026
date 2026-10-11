// One data-status vocabulary for every page. Always rendered as words + a distinct shape, never colour alone.
import { esc, ago, num } from './format.js';

export const STATUS = {
  live: { label: 'Live', why: 'Read now from Ethereum mainnet and public data APIs (read-only).' },
  cached: { label: 'Cached', why: 'Real responses replayed from the server cache; see the data time.' },
  mixed: { label: 'Mixed', why: 'Some calls were live, some replayed from the server cache.' },
  stale: { label: 'Stale', why: 'Older than the freshness limit for decisive inputs: re-run before acting.' },
  snapshot: { label: 'Saved snapshot', why: 'A recorded backend response, opened on purpose. Not current.' },
  demo: { label: 'Demo graph', why: 'The bundled demonstration graph: not real data.' },
  simulated: { label: 'Simulated fork', why: 'Local Anvil fork of mainnet at a pinned block, test funds, controlled shocks. Never Ethereum mainnet.' },
  dryrun: { label: 'Dry run', why: 'Hypothetical policy on live data: the engine plans, nothing is signed or sent.' },
  unavailable: { label: 'Unavailable', why: 'The request failed; no figures are shown.' },
  loading: { label: 'Analysing', why: 'Waiting for the backend.' },
};

/** Status of an /api/analyze payload as received by the page. */
export function analyzeStatus(payload, { fromCache = false, ageS = 0, snapshot = null } = {}) {
  if (snapshot) return { key: 'snapshot', meta: snapshot.label };
  const src = payload && payload.source;
  const block = payload && payload.position && payload.position.meta && payload.position.meta.block_number;
  const blockTxt = block ? `block ${num(block)}` : '';
  if (src === 'mock') return { key: 'demo', meta: 'not real data' };
  const blockers = payload && payload.decision && payload.decision.freshness && payload.decision.freshness.blockers;
  if (src === 'live' && !fromCache) return { key: (blockers && blockers.length) ? 'stale' : 'live', meta: blockTxt };
  if (fromCache) return { key: 'cached', meta: `${blockTxt}${blockTxt ? ', ' : ''}fetched ${ago(ageS)}` };
  if (src === 'cache') return { key: 'cached', meta: payload.data_as_of ? `data from ${new Date(payload.data_as_of * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC` : blockTxt };
  if (src === 'mixed') return { key: 'mixed', meta: blockTxt };
  return { key: 'unavailable', meta: 'unknown source' };
}

export function statusChip(key, meta = '', { id = '', live = false } = {}) {
  const s = STATUS[key] || STATUS.unavailable;
  return `<span class="status status--${key}"${id ? ` id="${id}"` : ''}${live ? ' role="status" aria-live="polite"' : ''} title="${esc(s.why)}">` +
    `<i class="status__mark" aria-hidden="true"></i><span>${esc(s.label)}</span>${meta ? `<span class="status__meta">${esc(meta)}</span>` : ''}</span>`;
}
