#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Error: run this script from the main branch." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Error: tracked files have local changes. Commit or discard them before deploying." >&2
  exit 1
fi

owner_email="aminenouira123@gmail.com"
current_email="$(git config --get user.email || true)"
if [[ "$current_email" != "$owner_email" ]]; then
  echo "Error: the configured Git email is '$current_email'." >&2
  echo "Vercel Hobby requires a commit authored by the project owner: $owner_email." >&2
  exit 1
fi

git pull --ff-only origin main
git commit --allow-empty -m "Trigger Vercel deployment from project owner"

if ! git push origin main; then
  echo "The commit is local, but the push failed. Resolve the issue, then run: git push origin main" >&2
  exit 1
fi

echo "Commit pushed. Check the result in Vercel deployments."
