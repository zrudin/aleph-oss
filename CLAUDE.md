# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

All workflows go through the Makefile (which shells out to `uv`):

```bash
make install            # uv sync --extra dev
make dev                # uv run python -m pa  (FastAPI on 127.0.0.1:8765)
make test               # uv run pytest -q
make lint               # uv run ruff check src tests
make format             # uv run ruff format src tests

make vault-create       # one-time: create the encrypted sparsebundle
make vault-mount        # mount /Volumes/PA-Vault (1Password unlock if PA_VAULT_OP_REF set)
make vault-unmount
make ollama-pull        # pull PA_CHAT_MODEL + PA_EMBED_MODEL
```

Run a single test: `uv run pytest tests/test_threads.py::test_name -q`.
`pytest` is configured with `asyncio_mode = "auto"`, so `async def test_*` works without decorators.

**The vault must be mounted before `make dev`** — `pa.__main__` calls `VaultManager.ensure_mounted()` and exits with code 2 otherwise. On macOS this is checked via `os.path.ismount` so an empty `/Volumes/PA-Vault` does not count as mounted.

## High-level architecture

This is a **local-first AI assistant**: Ollama for inference, LanceDB for vector search, a directory of Markdown files for memory, FastAPI bound to loopback. Nothing leaves the laptop unless the user explicitly toggles an external connector on.

### Startup / lifespan (`src/pa/server.py`)

`lifespan()` runs, in order: ensure vault mounted → `vault.bootstrap()` (create directory skeleton + `profile.md`) → best-effort initial reindex (failure is logged, not fatal — Ollama may be down) → start `VaultWatcher` → start APScheduler → mark `web` group available based on `PA_ENABLE_WEB` → spawn MCP servers via `MCPManager` and mark `notion` available iff handshake succeeded. Shutdown reverses this.

### Agent loop (`src/pa/agent.py`)

`run_turn(conv, message)` is an async generator that yields `TurnEvent`s (`thread`, `tool_start`, `tool_result`, `token`, `title`, `done`). Per turn:

1. Append user message to in-memory `Conversation` and to the thread file on disk.
2. Up to `PA_MAX_TOOL_ITERATIONS` (default 8) **non-streaming** chat calls so we can read `tool_calls`. Each iteration re-fetches `tool_schemas()` so a connector toggled mid-conversation takes effect on the next call.
3. When the model stops asking for tools, do **one streaming** chat with the same accumulated `working_messages` — that's the user-visible reply.
4. After the very first exchange (`len(messages) == 2`), `_maybe_generate_title` asks the LLM for a 3–6 word title and rewrites the thread's frontmatter.

`_conversations` is a process-local cache mirroring on-disk threads. Tests reset it with `reset_conversations()`. After any thread mutation through routes (rename/delete), the cache entry is dropped via `drop_conversation`.

### Tool registry + gate (`src/pa/tools/registry.py`, `src/pa/tool_gate.py`)

Two-layer tool system:

- **Built-in vault tools** (`list_files`, `read_file`, `semantic_search`, `list_threads`, …) are always on. Vault tools are **soft-imported** — if `pa.vault` ever fails to load, the registry still works for web/MCP tools (`_HAS_VAULT_TOOLS = False`).
- **External groups** (`web`, `notion`, future Gmail/etc.) defined in `tool_gate.GROUPS` are **fail-closed**: a group must be both *available* (configured at startup) and *enabled* (user-toggled). `tool_schemas()` filters the schemas the model sees; `dispatch()` also rejects disabled tools as a defense-in-depth backstop. State persists to `<vault>/.pa/tool_gate.json`.

MCP tools are namespaced `server__tool` (see `qualified_name`). The `MCPManager` keeps each subprocess alive for the app lifetime via an `AsyncExitStack`; `set_mcp_manager(manager)` wires it into the registry so its schemas merge into `tool_schemas()` and `dispatch()` routes namespaced names through `manager.call_tool`.

### Threads (`src/pa/threads.py`)

Conversations persist as Markdown notes under `<vault>/threads/<32-hex-id>.md` with YAML frontmatter (`thread_id`, `title`, `last_message_at`, `message_count`). The body is alternating `## user · <iso-ts>` / `## assistant · <iso-ts>` blocks parsed by `_SECTION_RE`. `VaultManager.iter_notes()` deliberately skips `THREADS_DIR` and `SYSTEM_DIR` so chat history does not pollute semantic search — threads are exposed to the agent only via the `list_threads` / `read_thread` tools.

### Memory / index (`src/pa/memory/`)

`VaultIndex` keeps a LanceDB table under `<vault>/.pa/index.lance/`. Schema is `(path, chunk_id, text, mtime, vector)` and the embedding dimension is detected from the live `PA_EMBED_MODEL` on first run (defaults to 768 for `nomic-embed-text`). `VaultWatcher` debounces filesystem events (`_DEBOUNCE_SECONDS = 1.5`) and triggers per-file reindex, so editing a note in any editor surfaces seconds later in `semantic_search`. APScheduler also runs a full reindex every 6 hours and a morning briefing cron at 08:00.

### Vault safety (`src/pa/vault/manager.py`)

All write tools resolve paths through `VaultManager.resolve_inside()` which rejects absolute / `~`-prefixed paths and refuses anything that escapes the vault root via `Path.is_relative_to`. Use this for any new file-mutating tool.

### Outbound HTTP (`src/pa/net.py`)

Every external fetch must go through `safe_get` / `build_client`, which:
- Sets `trust_env=False` so a stray `HTTP_PROXY` cannot intercept.
- Disables cookies, caps response size at `PA_WEB_MAX_FETCH_BYTES`, and revalidates after redirects.
- Rejects non-http(s) schemes and any host that resolves to a private/loopback/link-local address (prevents the model from being tricked into scanning the LAN or hitting our own loopback services).

### Secrets (`src/pa/secrets.py`)

Connector credentials live in the macOS Keychain under service `pa`. `get_secret(key)` checks the env var `PA_SECRET_<UPPER_KEY>` first so tests and headless CI can inject values without a keyring backend.

### Web UI (`src/pa/web/routes.py`)

FastAPI router serves Jinja templates from `src/pa/web/templates`, static assets from `/static`, streams chat over SSE at `POST /chat`, and exposes `/threads`, `/vault/tree`, `/vault/file`, `/tools/state`, `/reminders`, `/health`. Every route that touches the vault calls `_require_mounted_vault()` and returns 503 if not mounted.

## Things worth knowing before editing

- **Don't index threads.** If you add new content under the vault, decide whether it should appear in semantic search — `iter_notes` is the single chokepoint.
- **Tool-call iteration cap.** If you add a long-running multi-tool workflow, `PA_MAX_TOOL_ITERATIONS` may need to grow; the loop hard-stops with a user-visible "tool-use safety limit" message.
- **MCP imports are lazy.** `from mcp import ...` happens inside `_spawn`, so the rest of the package (and most tests) still import without the `mcp` SDK installed.
- **Embedding dim drift.** Switching `PA_EMBED_MODEL` while a `.lance` table exists keeps the old dim (read from row 0). Delete `<vault>/.pa/index.lance/` if you change models.
- **Path conventions** are centralized in `src/pa/vault/conventions.py` — import constants from there rather than hardcoding `"people"` etc.

## Workflow: branches and PRs

Never commit directly to `main`. For every task:

1. **Start on an isolated workspace** — either a fresh feature branch off `main` (`git switch -c feat/<short-slug>`) or a git worktree (`git worktree add ../pa-<slug> -b feat/<slug>`). If the user invokes you on `main`, branch before making any changes.
2. **Commit your work to that branch.**
3. **When the task is done, open a PR to `main`** with `gh pr create`, then merge and close it with `gh pr merge --merge --delete-branch` (a regular merge commit). **Do NOT squash-merge** — the user wants every individual commit preserved on `main`, even if that means a lot of commits in the history. Only use a different strategy if the user explicitly asks for one. Report the PR URL in your final message.

Apply this even for small changes — the user expects every task to land via a reviewed, merged PR rather than a direct push.
