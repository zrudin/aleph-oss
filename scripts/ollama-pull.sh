#!/usr/bin/env bash
# Pull the chat + embedding models defined in .env (with sensible defaults).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${PA_CHAT_MODEL:=qwen2.5:32b-instruct-q4_K_M}"
: "${PA_EMBED_MODEL:=nomic-embed-text}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it from https://ollama.com"
  exit 1
fi

echo "→ Pulling chat model: $PA_CHAT_MODEL"
ollama pull "$PA_CHAT_MODEL"

echo "→ Pulling embedding model: $PA_EMBED_MODEL"
ollama pull "$PA_EMBED_MODEL"

echo ""
echo "Done. Available models:"
ollama list
