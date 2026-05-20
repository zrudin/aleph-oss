#!/usr/bin/env bash
# Run the FastAPI server against an unencrypted dev vault stored inside the
# project at ./.dev-vault/. The vault skeleton is created by the app's own
# bootstrap() on first run, so its structure is identical to the real vault.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

export PA_VAULT_PATH="$(pwd)/.dev-vault"
export PA_VAULT_REQUIRE_MOUNT=false

mkdir -p "$PA_VAULT_PATH"
echo "→ Dev mode: vault at $PA_VAULT_PATH (unencrypted, gitignored)"
uv run python -m pa
