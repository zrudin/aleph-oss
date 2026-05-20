#!/usr/bin/env bash
# Mount the encrypted vault (if needed), run the FastAPI server, and unmount
# on exit. If the vault was already mounted before this script ran, the mount
# is left attached on exit and the user is reminded to run `make vault-unmount`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${PA_VAULT_PATH:=/Volumes/PA-Vault}"

we_mounted=false

cleanup() {
  if $we_mounted; then
    echo ""
    echo "→ Unmounting vault…"
    ./scripts/vault-unmount.sh || true
  else
    echo ""
    echo "⚠️  Vault at $PA_VAULT_PATH was already mounted before \`make run\` — leaving it attached."
    echo "   Run \`make vault-unmount\` to encrypt at rest."
  fi
}

if mount | grep -q " on $PA_VAULT_PATH "; then
  echo "Vault already mounted at $PA_VAULT_PATH — reusing."
else
  ./scripts/vault-mount.sh
  we_mounted=true
fi

trap cleanup EXIT INT TERM
uv run python -m pa
