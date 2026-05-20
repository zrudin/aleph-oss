#!/usr/bin/env bash
# Unmount the vault. Data is encrypted at rest after this completes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${PA_VAULT_PATH:=/Volumes/PA-Vault}"

if [[ ! -d "$PA_VAULT_PATH" ]]; then
  echo "Vault is not mounted at $PA_VAULT_PATH"
  exit 0
fi

hdiutil detach "$PA_VAULT_PATH"
echo "Vault unmounted."
