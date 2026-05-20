# aleph

A local-first AI personal assistant. Everything — inference, memory, and storage — runs on
your laptop. The assistant's "memory" is a directory of plain Markdown files that you can
also read and edit by hand. The vault is stored inside a macOS-encrypted sparsebundle so
it's encrypted at rest with AES-256, and only decrypted while you've mounted it.

## What it does

- Chats with you using a local LLM via [Ollama](https://ollama.com).
- Reads and writes structured notes about people, projects, interests, work, and your daily
  life — all in a vault directory you control.
- Indexes notes with local embeddings for semantic recall ("who haven't I talked to in a
  while?", "what was I thinking about that startup idea last month?").
- Tracks reminders and surfaces follow-ups, including friends you want to keep in touch
  with on a chosen cadence.
- Talks to you through a minimal local web UI at `http://127.0.0.1:8765`.

No telemetry. The server binds to loopback only. Web search (DuckDuckGo) and Notion
access are available but user-toggled from the UI — both are off by default except
web search, which can be disabled there or by setting `PA_ENABLE_WEB=false` in `.env`.

## Requirements

- macOS on Apple Silicon (built and tested against M3 Max / 36 GB).
- [Ollama](https://ollama.com) installed and running.
- Python 3.12.
- [uv](https://github.com/astral-sh/uv) (recommended) or pip.

## First-time setup

```bash
# 1. Install Python deps
make install

# 2. Pull the local models
make ollama-pull

# 3. Create the encrypted vault (one-time; you'll set a passphrase)
make vault-create

# 4. Copy and tweak environment defaults
cp .env.example .env
```

## Daily flow

```bash
make run             # mounts the vault, starts the server, unmounts on Ctrl+C
# open http://127.0.0.1:8765 in your browser
# ... talk to your assistant ...
# Ctrl+C — the vault is unmounted and encrypted at rest before the shell prompt returns
```

If the vault is already mounted when you run `make run`, the server reuses the existing
mount and leaves it attached on exit (so a parallel session keeps working); you'll see
a reminder to run `make vault-unmount` when you're done.

`make vault-mount` and `make vault-unmount` are still available as standalone commands
for the rare case you want to mount the vault without starting the server.

## Development

For iterating on code or the UI without unlocking the encrypted vault, run:

```bash
make dev             # starts the server against ./.dev-vault/ (unencrypted, gitignored)
```

The dev vault is created the first time `make dev` runs and uses the same `bootstrap()`
that produces the real vault, so its directory structure (`people/`, `journal/`,
`reminders/`, …) is identical. The only difference between `make run` and `make dev` is
which `PA_VAULT_PATH` the app points at.

## Project layout

```
src/pa/                Application code
  config.py            Settings (env-driven via pydantic-settings)
  agent.py             The chat loop with tool dispatch
  llm.py               Ollama client wrapper
  prompts.py           System prompt + per-turn context bootstrap
  tools/               Tools the agent can call (files, search, reminders, ...)
  vault/               Vault structure, note model, frontmatter handling
  memory/              Embeddings + LanceDB vector index + file watcher
  web/                 FastAPI routes, HTML, JS, CSS
  scheduler.py         Background jobs (reindex, morning briefing)
  server.py            App factory + lifespan
scripts/               Bash helpers for vault and Ollama
tests/                 Pytest suite
```

## Vault layout (inside the mounted volume)

```
/Volumes/PA-Vault/
  profile.md           You: bio, preferences, values, current focus
  people/              One note per person
  interests/           Hobbies, topics, learning threads
  projects/            Personal projects (and side projects)
  work/                Job context, colleagues, ongoing threads
  journal/YYYY/MM/DD.md
  reminders/active.md
  reminders/archive.md
  inbox/               Quick captures the agent triages later
  .pa/                 Index, state, logs (created automatically)
```

Notes use YAML frontmatter so the agent can filter without parsing prose. Template
schemas live in `src/pa/vault/templates.py`. For a full breakdown of each
directory and the kinds of notes it holds, see [`docs/vault.md`](docs/vault.md);
the tools the agent uses to read and write them are documented in
[`docs/tools.md`](docs/tools.md).

## Security model

- **At rest:** the vault lives inside an APFS-encrypted sparsebundle. Unmounted, the data
  is opaque ciphertext. macOS handles the crypto; no third-party FUSE driver is required.
- **In use:** while mounted, files are plaintext under `/Volumes/PA-Vault` and visible to
  both you and the assistant. Treat that mount the way you would `~/Documents`.
- **Network:** the server binds to `127.0.0.1`. Ollama is contacted on `localhost`.
  Outbound calls are opt-in: web search (DuckDuckGo) and Notion MCP are controlled by
  per-group toggles in the UI and the `PA_ENABLE_WEB` / `PA_ENABLE_NOTION` env vars.
- **Tool sandboxing:** all file-writing tools refuse paths that resolve outside
  `PA_VAULT_PATH`.

## Status

v1 prototype. The full design doc — model-sizing notes for M3 Max, encryption rationale,
phased roadmap — lives alongside this code as the original plan that produced it.
