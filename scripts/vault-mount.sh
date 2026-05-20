#!/usr/bin/env bash
# Mount the encrypted vault. If PA_VAULT_OP_REF is set and `op` is available,
# the passphrase is read from 1Password (which will prompt you to unlock the
# vault via biometric/system auth when needed). Otherwise, macOS shows its
# normal GUI passphrase prompt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${PA_VAULT_SPARSEBUNDLE:=$HOME/Library/PersonalAssistant/PA-Vault.sparsebundle}"
PA_VAULT_SPARSEBUNDLE="${PA_VAULT_SPARSEBUNDLE/#\~/$HOME}"

: "${PA_VAULT_PATH:=/Volumes/PA-Vault}"
: "${PA_VAULT_OP_REF:=}"

if [[ ! -e "$PA_VAULT_SPARSEBUNDLE" ]]; then
  echo "Sparsebundle not found at: $PA_VAULT_SPARSEBUNDLE"
  echo "Create one first with: make vault-create"
  exit 1
fi

# Already mounted?
if [[ -d "$PA_VAULT_PATH" ]]; then
  echo "Vault already mounted at $PA_VAULT_PATH"
  exit 0
fi

if [[ -n "$PA_VAULT_OP_REF" ]] && command -v op >/dev/null 2>&1; then
  echo "→ Unlocking vault via 1Password ($PA_VAULT_OP_REF)…"
  # `op read` triggers the desktop integration if installed (biometric prompt)
  # or falls back to its own session unlock.
  op read "$PA_VAULT_OP_REF" --no-newline \
    | hdiutil attach -stdinpass -nobrowse "$PA_VAULT_SPARSEBUNDLE"
else
  if [[ -n "$PA_VAULT_OP_REF" ]]; then
    echo "PA_VAULT_OP_REF is set but the 1Password CLI (op) was not found."
    echo "Falling back to the interactive GUI prompt."
  fi
  hdiutil attach -nobrowse "$PA_VAULT_SPARSEBUNDLE"
fi

if [[ -d "$PA_VAULT_PATH" ]]; then
  echo "Vault mounted at $PA_VAULT_PATH"
else
  echo "WARNING: hdiutil reported success but $PA_VAULT_PATH is not visible."
  echo "Check `hdiutil info` for the actual mount point."
  exit 1
fi
