#!/usr/bin/env bash
# Refuse to proceed if a public-release tree contains:
#   (a) blocklisted personal info in any tracked file, or
#   (b) a tracked file that should only exist on the private dev branch.
#
# Meant to be run on the public-mirror branch (public-main) before
# `git push public public-main:main`. On the private `main` branch the
# script will intentionally fail — those files belong there.
#
# The script excludes itself from the grep in (a) because the blocklist
# literal necessarily contains the strings it's searching for.
set -euo pipefail

# (a) Blocklist grep.
BAD='zackrudin|zacharyrudin|/Users/zackrudin|~/Downloads/personal-assistant'
if git grep -nE "$BAD" -- ':!uv.lock' ':!scripts/check-public-safe.sh'; then
  echo "BLOCKLIST hit — fix before publishing." >&2
  exit 1
fi

# (b) Private-only paths must not be tracked on the public-mirror branch.
PRIVATE_PATHS=(
  TODO.md
  RELEASE.md
  .github/workflows/claude.yml
  .github/workflows/claude-code-review.yml
)
leaked=()
for path in "${PRIVATE_PATHS[@]}"; do
  if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    leaked+=("$path")
  fi
done
if [ ${#leaked[@]} -gt 0 ]; then
  echo "PRIVATE-FILE LEAK — these must not be tracked on the public mirror:" >&2
  printf '  %s\n' "${leaked[@]}" >&2
  exit 1
fi

echo "scripts/check-public-safe.sh: OK"
