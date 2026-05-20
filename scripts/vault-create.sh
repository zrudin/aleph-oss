#!/usr/bin/env bash
# One-time: create the encrypted sparsebundle that backs the vault.
#
# Flow:
#   1. If PA_VAULT_OP_REF is set and the 1Password CLI is available, generate
#      a strong passphrase, store it in 1Password at that reference, and use
#      it for hdiutil. You'll authenticate with 1Password (biometric/system
#      auth) instead of typing a password.
#   2. Otherwise fall back to hdiutil's interactive password prompt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${PA_VAULT_SPARSEBUNDLE:=$HOME/Library/PersonalAssistant/PA-Vault.sparsebundle}"
PA_VAULT_SPARSEBUNDLE="${PA_VAULT_SPARSEBUNDLE/#\~/$HOME}"

: "${PA_VAULT_SIZE:=2g}"
: "${PA_VAULT_VOLNAME:=PA-Vault}"
: "${PA_VAULT_OP_REF:=}"

if [[ -e "$PA_VAULT_SPARSEBUNDLE" ]]; then
  echo "Sparsebundle already exists at: $PA_VAULT_SPARSEBUNDLE"
  echo "Aborting to avoid clobbering. Delete it manually if you want to start over."
  exit 1
fi

mkdir -p "$(dirname "$PA_VAULT_SPARSEBUNDLE")"

use_1password=false
if [[ -n "$PA_VAULT_OP_REF" ]] && command -v op >/dev/null 2>&1; then
  use_1password=true
fi

if $use_1password; then
  echo "→ Generating a strong passphrase and storing it in 1Password at $PA_VAULT_OP_REF"

  # Parse the op:// reference into vault / item / field.
  ref="${PA_VAULT_OP_REF#op://}"
  vault_name="${ref%%/*}"; rest="${ref#*/}"
  item_name="${rest%%/*}";  field_name="${rest#*/}"
  if [[ -z "$vault_name" || -z "$item_name" || -z "$field_name" ]]; then
    echo "Invalid PA_VAULT_OP_REF: expected op://VAULT/ITEM/FIELD"
    exit 1
  fi

  passphrase=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)

  if op item get "$item_name" --vault "$vault_name" >/dev/null 2>&1; then
    op item edit "$item_name" --vault "$vault_name" "$field_name=$passphrase" >/dev/null
  else
    op item create --category=password --title="$item_name" --vault="$vault_name" \
      "$field_name=$passphrase" >/dev/null
  fi
  echo "  ✓ Stored. Verify with:  op read \"$PA_VAULT_OP_REF\""

  printf '%s' "$passphrase" | hdiutil create \
    -size "$PA_VAULT_SIZE" \
    -fs APFS \
    -encryption AES-256 \
    -stdinpass \
    -type SPARSEBUNDLE \
    -volname "$PA_VAULT_VOLNAME" \
    "$PA_VAULT_SPARSEBUNDLE"
else
  if [[ -n "$PA_VAULT_OP_REF" ]]; then
    echo "PA_VAULT_OP_REF is set but the 1Password CLI (op) was not found."
    echo "Install it from https://developer.1password.com/docs/cli/ and re-run,"
    echo "or unset PA_VAULT_OP_REF to use the interactive prompt."
    exit 1
  fi
  echo "→ Creating sparsebundle with interactive passphrase prompt."
  hdiutil create \
    -size "$PA_VAULT_SIZE" \
    -fs APFS \
    -encryption AES-256 \
    -type SPARSEBUNDLE \
    -volname "$PA_VAULT_VOLNAME" \
    "$PA_VAULT_SPARSEBUNDLE"
fi

echo ""
echo "Sparsebundle ready: $PA_VAULT_SPARSEBUNDLE"
echo "Next: make vault-mount"
