#!/usr/bin/env bash
# Delete the local dev vault (./.dev-vault/) so the next `make dev` boots
# from a fresh, just-bootstrapped state. Useful for testing first-run
# onboarding and other empty-vault flows. Only touches the in-repo dev
# vault — never the encrypted production sparsebundle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEV_VAULT="$REPO_ROOT/.dev-vault"

if [ ! -e "$DEV_VAULT" ]; then
  echo "→ No dev vault at $DEV_VAULT (already clean)"
  exit 0
fi

# Refuse to wipe while the dev server is running — it may have files open
# or be midway through a write, and the user almost certainly didn't mean to.
if lsof -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "✗ Aborting: something is listening on 127.0.0.1:8765 — stop \`make dev\` first" >&2
  exit 1
fi

echo "→ Wiping dev vault at $DEV_VAULT"
rm -rf "$DEV_VAULT"
echo "✓ Done. Next \`make dev\` will bootstrap a fresh empty vault."
