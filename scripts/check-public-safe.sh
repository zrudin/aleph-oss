#!/usr/bin/env bash
# Refuse to proceed if blocklisted personal info appears in tracked files.
# The script excludes itself from the grep because the blocklist literal
# necessarily contains the strings it's searching for.
set -euo pipefail
BAD='zackrudin|zacharyrudin|/Users/zackrudin|~/Downloads/personal-assistant'
if git grep -nE "$BAD" -- ':!uv.lock' ':!scripts/check-public-safe.sh'; then
  echo "BLOCKLIST hit — fix before publishing." >&2
  exit 1
fi
echo "scripts/check-public-safe.sh: OK"
