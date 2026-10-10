#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Error: run this script from the main branch." >&2
  exit 1
fi

owner_email="aminenouira123@gmail.com"
current_email="$(git config --get user.email || true)"
if [[ "$current_email" != "$owner_email" ]]; then
  echo "Error: the configured Git email is '$current_email'." >&2
  echo "Vercel Hobby requires a commit authored by the project owner: $owner_email." >&2
  exit 1
fi

stashed_changes=false
restore_local_changes() {
  local result=$?
  trap - EXIT
  if [[ "$stashed_changes" == true ]]; then
    if git stash pop --index; then
      echo "Local tracked changes restored."
    else
      echo "Warning: local changes could not be restored automatically. They remain in the latest Git stash; resolve the conflict before deploying again." >&2
      exit 1
    fi
  fi
  exit "$result"
}
trap restore_local_changes EXIT

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  git stash push -m "Temporary changes for Vercel deployment"
  stashed_changes=true
  echo "Local tracked changes saved temporarily."
fi

git pull --ff-only origin main
git commit --allow-empty -m "Trigger Vercel deployment from project owner"

if ! git push origin main; then
  echo "The commit is local, but the push failed. Resolve the issue, then run: git push origin main" >&2
  exit 1
fi

echo "Commit pushed. Check the result in Vercel deployments."
