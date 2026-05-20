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

Never commit directly to `main`. Multiple Claude Code sessions may run in parallel against this repo, so a bare feature branch in the shared checkout is unsafe — `git switch` flips files under any other session in that checkout. **Every task must run in its own git worktree**, never in the parent checkout on `main`.

For every task:

1. **Check for in-progress work before creating anything new.** A previous session may have been interrupted, leaving a worktree with WIP that this task could resume. Run `git worktree list` and, for each non-`main` worktree, read its `PLAN.md` at the worktree root (see "Resumable plans" below). If you find a worktree whose plan plausibly matches the user's current request, surface it to them — e.g. *"I see in-progress work on branch `feat/foo-…` with 3 unchecked steps in `PLAN.md`. Resume that, or start fresh?"* — and wait for their answer. **Never auto-resume**; the agent that left the WIP may have been on a different mental model, and conflating two tasks is worse than starting clean.
2. **Create a worktree with a uniquified slug, based on the freshest `origin/main`.** Use a timestamped slug so two sessions can't collide on branch name or directory name, and `git fetch origin` first so you don't accidentally branch off a parent checkout that's behind the remote:

   ```bash
   git fetch origin                              # make sure origin/main is current
   slug="<short-task-slug>-$(date +%Y%m%d-%H%M%S)"
   git worktree add ../aleph-$slug -b <prefix>/$slug origin/main   # prefix: feat, fix, chore, docs, …
   cd ../aleph-$slug
   ```

   Explicitly basing the new branch on `origin/main` (not the parent checkout's `HEAD`) avoids the classic foot-gun where the parent checkout hasn't been `git pull`ed in a while and your "fresh" branch is actually missing commits already on the remote. If the user mentions they just pushed or pulled something, re-fetch before branching to be sure.

   If you were already invoked inside an existing worktree (not the parent `aleph/` checkout on `main`), keep working in it instead of nesting another one. The rule is one task per worktree.
3. **Commit your work to that branch.** Stay inside the worktree; do not operate on the parent checkout or on `main` directly.
4. **When the task is done, open a PR to `main`** with `gh pr create`, then merge and close it with `gh pr merge --merge --delete-branch` (a regular merge commit). **Do NOT squash-merge** — the user wants every individual commit preserved on `main`, even if that means a lot of commits in the history. Only use a different strategy if the user explicitly asks for one. Report the PR URL in your final message.
5. **Remove the worktree** once the PR is merged, best-effort: `git -C <parent-checkout> worktree remove ../aleph-$slug`. The merge commit is already on `main`; this just frees the sibling directory. If the agent can't safely `cd` out of the worktree to remove it, leave a note for the user and move on.

Apply this even for small changes — the user expects every task to land via a reviewed, merged PR rather than a direct push.

### Resumable plans for multi-step tasks

For any task with more than a couple of steps, drop a `PLAN.md` at the root of your worktree the first time you settle on a multi-step approach, and update it as you go. `PLAN.md` is gitignored — it stays on disk so a future session can resume from it, but it never enters commits or PRs.

Format is a plain checklist; keep it terse, one line per step:

```markdown
# Plan: <one-line task summary>

- [x] Stand up worktree and read related code
- [ ] Update `src/pa/foo.py` to handle the new case
- [ ] Add tests in `tests/test_foo.py`
- [ ] Run `make lint && make test`
- [ ] Open PR

next: editing `_handle_x` in foo.py — about to wire up the early-return branch.
```

Conventions:

- **Check items off as you complete them.** Don't batch; if you've done it, mark it.
- **Add new items if scope shifts.** A plan that no longer reflects reality is worse than no plan.
- **Leave a `next:` line at the bottom** before any context-risky moment (long command, large refactor step) so an interrupted session knows where to pick up.
- **On resume**, read `PLAN.md` first thing and continue from the first unchecked item. If the plan looks stale or doesn't match what the user is now asking for, surface that to them rather than blindly resuming.
- **Don't create `PLAN.md` for trivial single-step tasks** (one-line edits, simple renames). The cost of writing the file exceeds the value of resumability.
- `PLAN.md` is throwaway and gets removed with the worktree at step 5. It does not need to be tidied up before opening the PR.

### Parallel sessions: shared state outside git

A worktree isolates the working tree and the branch. These things are still shared across all parallel sessions and need explicit coordination — Git won't protect you here:

- **`make dev` binds `127.0.0.1:8765`.** Only one session can run the FastAPI server at a time. Don't try to start a second `make dev`; instead, see "Self-testing" below for the throwaway-port pattern.
- **The vault is shared mutable state.** `<vault>/.pa/index.lance/`, `<vault>/threads/`, and the `VaultWatcher` are not safe for concurrent writers. Don't trigger a real reindex, write thread files, or run anything that mutates the live vault when another session might be doing the same. Tests that use a temporary vault fixture are fine and should be preferred.
- **Don't touch the parent checkout's `main`.** Let the user manage the parent checkout. Worktree sessions push their branch, open a PR, optionally remove their worktree, and stop there — they never `git pull` or `git checkout main` in the parent.
- **Only push to `origin`.** The `public` mirror is a single-writer release flow owned by the maintainer (see below). Never push from a parallel session.

## Self-testing and verification

Be proactive about confirming changes actually work before declaring them done. The user can't see most tool calls — when you say "this is fixed," they trust it. The harness can run short read-only probes and isolated server instances freely; use them.

### Spin up a parallel instance when changes touch the running app

If your change affects HTTP endpoints, SSE streams, the agent loop, lifespan, or anything the live server exposes, start your own instance on a non-default port against a throwaway vault and exercise it before reporting the work done. The defaults would collide with the user's `make dev`; explicit overrides make a parallel instance safe:

```bash
PA_PORT=8766 \
PA_VAULT_PATH=/tmp/aleph-test-vault-$USER \
PA_VAULT_REQUIRE_MOUNT=false \
uv run python -m pa
```

Then `curl http://127.0.0.1:8766/health`, `curl http://127.0.0.1:8766/ollama/status`, POST to `/chat` and read the SSE stream, etc. Stop the instance when done. The throwaway vault lets you write threads, reindex, and mutate state without touching the user's real vault.

For driving multi-turn chat conversations against the parallel instance, `scripts/dev-chat.py` consumes the `/chat` SSE stream and prints a per-turn digest (assistant text, every tool call with arguments, generated title). Pass `--thread <id>` to continue a thread across invocations:

```bash
uv run python scripts/dev-chat.py --base http://127.0.0.1:8766 "hi"
uv run python scripts/dev-chat.py --base http://127.0.0.1:8766 --thread <id> "follow up"
```

UI changes (CSS, layout, focus, animation) still need a browser, and a browser still needs the user. When you've verified the backend but can't verify the rendered UI, **say so explicitly** rather than implying the whole change is tested.

### Probe external APIs before parsing them

Before writing code that parses a response from an external library or service (Ollama, MCP server, third-party API), confirm its actual shape with a tiny script. Two minutes of probing beats shipping a parser based on how the API "should" look:

```bash
uv run python -c "
import asyncio
from ollama import AsyncClient
async def main():
    resp = await AsyncClient().list()
    print('type:', type(resp).__name__)
    print('has .models:', hasattr(resp, 'models'))
    print('first entry:', dir(resp.models[0]) if getattr(resp, 'models', None) else 'none')
asyncio.run(main())
"
```

These probes are read-only and don't bind ports — run them freely. Especially do this when a library has bumped a major version (pydantic v1 → v2, ollama 0.3 → 0.6, etc.) or when the docs and the installed version disagree.

### Tests are part of the change, not a follow-up

When adding or refactoring code, write tests for the new behavior in the same PR:

- The new happy path.
- Whatever edge case motivated the change (the bug that triggered the fix, the case the user mentioned).
- Each new error-handling branch.

`make test` must pass before you open the PR — that's the floor. If a test would have caught the bug you're fixing, write that test too, so a future regression surfaces immediately instead of waiting for the user to try the feature again. A "tested" claim without a corresponding committed test is a claim about the past, not a guard against the future.

## Public mirror

This project has two GitHub repos:

- **`origin`** → `zrudin/aleph` (private) — where day-to-day development happens. All PRs land here.
- **`public`** → `zrudin/aleph-oss` (public mirror) — a curated subset, pushed manually from a `public-main` orphan branch.

When working in this repo, **only push to `origin`**. Never push to the `public` remote — that's a manual release flow the maintainer owns. A local `.git/hooks/pre-push` refuses `main → public` as a backstop.

Files that intentionally do **not** ship to the public mirror:

- `TODO.md` — personal local paths.
- `.github/workflows/claude*.yml` — would trigger on any contributor's `@claude` mention.
- `RELEASE.md` — private maintainer notes (tracked on `origin`, excluded from the public mirror by `scripts/check-public-safe.sh`).

If you add a file that should be tracked on `origin` but **must not** ship publicly (maintainer-only scripts, personal notes, release docs, etc.), commit it normally and add its path to the `PRIVATE_PATHS` array in `scripts/check-public-safe.sh`, plus document it in `RELEASE.md`. The safety script does two things: (a) greps tracked files for blocklisted personal info, and (b) refuses to proceed if any path in `PRIVATE_PATHS` is tracked on the branch being released. Don't use `.gitignore` for this — the goal is that the private repo retains everything; only the public mirror omits these files.

**Detailed public-sync recipe lives in `RELEASE.md`** at the repo root. It is tracked on the private `origin` only — the safety script refuses to push if `RELEASE.md` appears on `public-main` — so it won't be present in the public mirror.

Note: `CLAUDE.md` itself ships to the public mirror. Don't put PII, maintainer-only secrets, or private-context-only details in this file.
