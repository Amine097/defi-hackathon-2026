# GitHub cleanup: 2026-10-11

Scope: documentation and ignore rules only. This pass did not change any code paths, deployment entry points, design export, recorded
evidence, fixtures or tests. Nothing was committed, pushed, deployed, deleted or rewritten.

## Starting state

| Item | Value |
|---|---|
| Branch / HEAD | `main` @ `91048be` ("Trigger Vercel deployment from project owner"), equal to `origin/main` |
| Working tree | Clean before this pass |
| Tracked files | 2,779 (1,341 under `resources/`, 754 under `public/assets/`, 433 under `docs/design` + `docs/frontend`) |
| Remote branches | `main`; `railway/code-change-5JdXQ6` (fully merged via #2); `work/frontend-redesign` (2 docs commits not in `main`, 2026-10-10) |
| Repo visibility | Private |
| Deployment config | `vercel.json` (static `public/` + `api/*.py`, CSP headers), `railway.json` → `Dockerfile.keeper` → `scripts/railway_keeper.py`, `.dockerignore`. Inspected and **left unchanged** |

## Secret check (no values printed)

- History: no `.env`, `*.pem`, keystore or password file has ever been added (`git log --all --diff-filter=A`). Only `.env.example` is tracked.
  It contains only a public RPC URL and empty keys.
- Content: a local regex scan of all tracked text files (excluding the logo pack and design screenshots) found no private keys, PEM blocks,
  GitHub/AWS tokens, keyed RPC URLs or API keys. The only hit was `signer.py`'s runtime-generated random keystore password, a false positive.
  The Anvil mnemonic in the code is the public Foundry default, used only for test chains.
- GitHub Advanced Security is not enabled on this private repository, so neither GitHub's secret-scanning service nor its alert list
  could be queried. Treat the local scan as best-effort.

## Changes made

| File | Change | Why |
|---|---|---|
| `README.md` | Rewrote the Vercel steps: `data/cache/` is gitignored, so it is not deployed; `DEFIRISK_OFFLINE=1` without a cache breaks live calls; all three API functions listed | The previous text told readers to "commit `data/cache/`" and set `DEFIRISK_OFFLINE=1`, which contradicts `.gitignore` |
| `README.md` | Added the "Hosted keeper on Railway" section | Railway was undocumented in the README |
| `README.md` | Added a "What is real and what is demonstration" table | Separates live mainnet reads, recorded live runs, hypothetical notionals, assumptions, fork runs and the mock |
| `README.md` | Documented `deploy-vercel.cmd/.sh` as owner-specific | They hard-code a WSL path and the owner's Git email |
| `README.md` | Expanded the Layout section (`api/`, `public/`, fixtures, `audit/`, `docs/audit/`) | Missing from the layout |
| `docs/README.md` | Added links to backend, deployment, figure traceability, frontend, jury script and these audit docs | These documents were not linked from the index |
| `docs/features/README.md` | Fixed the broken link `leverage-hunter/README.md` → `cascade-radar/README.md` | The folder was renamed in `7c992e8`. This was the only broken relative Markdown link in the repo |
| `.gitignore` | Added `.vercel/`, tool caches, OS files, `*.password`, `anvil-test-*`; annotated `resources/` | `vercel` CLI creates `.vercel/`; keeper keystore/password files must never be committed. None of the new patterns matches a tracked file |
| `src/defirisk/data/http.py` | Docstring only: removed "then commit data/cache" | Same stale instruction; no behaviour change |

## Deliberately preserved

The Claude Design v2 export (`docs/design/claude-design-v2/`) and frontend (`public/`, `tools/frontend/`), all APIs and `src/`, `vercel.json`,
`railway.json`, `Dockerfile.keeper`, `.dockerignore`, `scripts/railway_keeper.py` and the deploy scripts. Also kept: the recorded S1–S5
fork evidence (`data/countermove/demo/latest/`, including `anvil.log`), `audit/*.json`, the Slither output, vault fixtures,
`data/calibration/`, `public/data/recorded/`, the tests, legacy pages (`/analyze.html`, `/vault.html`, `/countermove.html`, still reachable),
`PLAN.md` and every hackathon document.

## Validation

`python -m pytest`: 359 passed, 18 skipped (e2e/live tests skip without Foundry artifacts or `DEFIRISK_LIVE_TESTS=1`). There are no
broken relative links in tracked Markdown after the fix.

## Open items requiring a team decision (not done)

1. **`resources/` is tracked although ignored**: 1,341 files, 24.9 MB, added in `e95c528`. Nothing at runtime reads it. It appears only as a
   scan-skip prefix in `collect_phase2_evidence.py` and in provenance notes. `git rm -r --cached resources` would shrink the
   tree, but it would **delete those files from teammates' checkouts on their next pull**, and it would not shrink history. Recommend doing it
   only with the team's agreement.
2. **`public/NOTES-xray.md` and `public/NOTES-frontend.md` are served publicly** by Vercel. They are internal development notes; the first is marked
   superseded. They are referenced from `PLAN.md` and design docs, so moving them needs link updates.
3. **Two different versions of the Belem brief review**: `docs/FAULTLINE_BELEM_BRIEF_REVIEW.md` and `docs/reference-context/briefs/…` (different
   hashes). Identify the canonical one before removing either.
4. **`docs/The Hackathon BSA.docx`**: provenance and purpose are unclear; not referenced from the index.
5. **Branch `railway/code-change-5JdXQ6`** is fully merged and could be deleted on GitHub. `work/frontend-redesign` holds 2 unmerged docs
   commits. Neither was touched.
6. **The Vercel environment cannot be verified from the repo.** Confirm in Project Settings that `DEFIRISK_OFFLINE` is not `1`.
7. Volume: `docs/frontend/fidelity/` (168 files) and `docs/design/` (231 files) are mostly QA screenshots and prototypes. They are kept
   as design evidence.
