# Tools

The agent's only side effects on the world go through tools. Schemas live in
`src/pa/tools/registry.py`; runtime gating lives in `src/pa/tool_gate.py`. Every
tool returns a JSON-serializable dict; the registry stringifies it before
handing it back to the LLM.

Two big things to know before reading the list below:

- **Built-in vault tools are always on.** They have no group gate and cannot be
  toggled off (per-tool overrides aside).
- **External tools are fail-closed.** A tool in the `web` or `notion` group is
  only visible to the model when its group is both _available_ (configured at
  startup) and _enabled_ (toggled on by you in the UI). Dispatch also rejects
  disabled tools as a defense-in-depth backstop.

## Vault file tools

Source: `src/pa/tools/files.py`. All writes go through
`VaultManager.resolve_inside(path)`, which refuses absolute paths and anything
that escapes the vault root.

### `list_files(directory: str = "")`

List immediate files and subdirectories inside the vault. Pass an empty string
for the root. Hidden entries (anything starting with `.`) are skipped, so
`.pa/` doesn't show up.

Returns `{"directory": <dir>, "entries": [{"name", "type", "path"}, ...]}`.

### `read_file(path: str)`

Read a single file in the vault. Returns `{"path", "content"}` or an `error`
field if the file doesn't exist or isn't a regular file.

### `write_file(path: str, content: str, template: str | None = None)`

Create or fully replace a note. If `template` is provided **and the file
doesn't exist**, the named template (`profile`, `person`, `project`,
`interest`, `journal`) is rendered first and `content` is appended as the body.
If the file already exists, `template` is ignored and `content` is written
as-is — full replacement, not a merge. Prefer `append_to_file` for additive
edits.

Returns `{"path", "created": <bool>}`.

### `append_to_file(path: str, content: str)`

Append content to the end of a note, creating the file if it doesn't exist.
Inserts a blank-line separator when needed so consecutive appends don't run
together. Best for journal entries and adding interactions to a person note.

Returns `{"path", "appended": true}`.

## Search

Source: `src/pa/tools/search.py`.

### `semantic_search(query: str, k: int = 5)`

Vector search across all indexed vault notes via LanceDB + local embeddings.
Returns the top `k` chunks. Threads and `.pa/` are not indexed, so this only
returns user notes.

### `text_search(pattern: str, directory: str = "")`

Case-insensitive Python regex match across vault Markdown. Optionally scoped to
a subdirectory. Skips hidden directories and `threads/`. Returns up to 50
matches; the response carries `truncated: true` if the cap was hit. Use this
when you know an exact phrase or proper noun and want every occurrence.

## Reminders

Source: `src/pa/tools/reminders.py`. Backed by the plain Markdown checkbox
lists at `reminders/active.md` and `reminders/archive.md` — no DB, no schema
migrations.

### `list_reminders(filter: str = "")`

Return the current open reminders. The optional `filter` is a case-insensitive
substring match on the reminder text. Each item is
`{"line", "text", "done": <bool>}`.

### `create_reminder(text: str, due: str | None = None)`

Append a new open reminder to `reminders/active.md`. If `due` is provided, it's
suffixed as `(due <due>)` — ISO date or free-form, the agent doesn't try to
parse it. Returns `{"added": <full line>}`.

### `complete_reminder(text: str)`

Mark the first reminder whose text contains `text` (case-insensitive) as
complete, remove it from `active.md`, and append it to `archive.md` with a
trailing `— done <today>` stamp.

Returns `{"completed": true, "text": ...}` on a hit, or
`{"completed": false, "reason": "no matching active reminder"}` otherwise.

## Past conversations

Source: `src/pa/tools/threads_tool.py`. The vault's `threads/` directory holds
every past chat, but those files are kept out of semantic / text search to
avoid polluting the index — these two tools are how the agent reaches them.

### `list_threads(limit: int = 20)`

Recent threads sorted by most recent activity. Each entry includes
`thread_id`, `title`, `last_message_at`, and `message_count`. Use this before
`read_thread` so you have an id to pass.

### `read_thread(thread_id: str)`

Full content of a single thread — all messages with timestamps, plus
`title`, `created`, `last_message_at`. Use after `list_threads` when the
user references something discussed before.

## Time

Source: `src/pa/tools/datetime_tool.py`.

### `current_datetime()`

Returns `{"iso", "date", "weekday", "timezone"}` for the local timezone (the
user's laptop). Useful when the model needs to do anything date-relative — the
date is also in the bootstrap context but the timestamp / weekday / zone come
from this tool.

## Web (external — group `web`)

Source: `src/pa/tools/web_search.py`. These tools touch the public internet,
so they're gated behind both `PA_ENABLE_WEB` (env, default true) and the
UI toggle. They never touch the vault, and the system prompt forbids putting
vault content into search queries.

All outbound HTTP goes through `src/pa/net.py`'s `safe_get` / `build_client`,
which sets `trust_env=False`, disables cookies, caps response size, rejects
non-http(s) schemes, and refuses any host that resolves to a private /
loopback / link-local address.

### `web_search(query: str, max_results: int = 5)`

DuckDuckGo search via the `ddgs` package — no API key, no cookies. Clamps
`max_results` to 1–10. On rate-limit (DDG's 202 response) it backs off
exponentially up to `PA_WEB_SEARCH_MAX_RETRIES` attempts. Returns a list of
`{title, url, snippet}`.

### `web_fetch(url: str, max_chars: int = 20000)`

Download a single page and return extracted main-text via `trafilatura`.
JavaScript is never executed. `max_chars` is clamped to 500–200000, and longer
pages are truncated with a `... [truncated]` marker. Returns
`{url, title, text}`.

## MCP-provided tools (external — group `notion`, etc.)

The agent can also call any tool exposed by an MCP server configured at
startup. Today that means Notion, but other servers can be wired in the same
way (`src/pa/mcp/client.py`).

MCP tool names are namespaced as `<server>__<tool>` (e.g.
`notion__page_get`). The split happens in `pa.mcp.split_qualified`, and
`dispatch()` routes any namespaced name through `MCPManager.call_tool` rather
than the built-in registry.

Like the web tools, MCP groups are fail-closed: a group must be both available
(MCP handshake succeeded at startup) and enabled (UI toggle on) before its
tools appear in the schema list the model sees.

## The tool gate

`src/pa/tool_gate.py` is the runtime authority on what tools the model sees
and is allowed to call. Two layers:

1. **Group level.** Defined in `GROUPS` (currently `web` and `notion`). Each
   group has an `_available` flag set at startup and an `_enabled` flag toggled
   from the UI. `is_enabled(group_id) == available AND enabled`. If a group
   becomes unavailable while it was enabled, the gate also flips `enabled` off
   and saves, so the UI can't claim something is on that can't actually run.
2. **Per-tool overrides.** A `{tool_name: bool}` map for fine-grained on/off
   inside a group (or even on a built-in tool). Surfaced in the Tools modal.

`is_tool_allowed(name) == (group available AND group enabled if applicable) AND per-tool override on`.

State persists to `<vault>/.pa/tool_gate.json` so toggles survive restart.
`tool_schemas()` strips disabled tools before handing the list to Ollama;
`dispatch()` also rejects disabled tools at call time. Either layer alone is
enough to block a call — both together make accidental exposure very hard.

## Adding a new tool

The minimum change is:

1. Write the async function in `src/pa/tools/<area>.py` that returns a
   JSON-serializable dict.
2. Register it in `_TOOLS` and add a `_schema(...)` entry in
   `src/pa/tools/registry.py` (Ollama expects OpenAI-style function schemas).
3. If the tool touches anything outside the vault, put it in a `ToolGroup`
   (`src/pa/tool_gate.py`) so it's gated, and wire `set_available(...)` from
   the relevant startup code in `src/pa/server.py`.
4. If it writes to the vault, route every path through
   `VaultManager.resolve_inside`. If it makes HTTP calls, route through
   `pa.net.safe_get`.
