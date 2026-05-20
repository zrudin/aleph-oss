# Vault layout

The vault is the assistant's memory. It is a directory of plain Markdown files
that you can read, edit, or grep by hand — the agent has no privileged channel
into it.

When mounted, it lives at the path in `PA_VAULT_PATH` (default
`/Volumes/PA-Vault` for production, `./.dev-vault` for `make dev`). The
canonical names of every directory and reserved file are defined in
`src/pa/vault/conventions.py`; bootstrap creates the skeleton on first run via
`VaultManager.bootstrap()` (`src/pa/vault/manager.py`).

```
<vault root>/
  profile.md              # You
  people/                 # One note per person
  interests/              # Hobbies, topics, learning threads
  projects/               # Personal and side projects
  work/                   # Job context, colleagues, ongoing work threads
  journal/YYYY/MM/DD.md   # Daily notes
  reminders/active.md     # Open checkbox list
  reminders/archive.md    # Completed items
  inbox/                  # Quick captures awaiting triage
  threads/<id>.md         # Past chat conversations (one file per thread)
  .pa/                    # Internal index/state (see "System directory" below)
```

## Frontmatter conventions

Every note the agent creates has YAML frontmatter at the top. The `type` field
is what lets the agent (and you) filter notes by category without parsing prose.
Templates for new notes live in `src/pa/vault/templates.py`.

When the agent updates a note, it is expected to preserve existing frontmatter
keys and bump an `updated` field if you have one.

## `profile.md`

Your single profile note. Created on first bootstrap with placeholder content
under the name "You" so the agent has something to fill in.

```yaml
---
type: profile
name: <your name>
---
```

Sections: **Bio**, **Preferences**, **Values**, **Current focus**.

The agent reads this on every turn as part of the bootstrap context, so keep it
reasonably short — long bios will be truncated at ~4k characters when injected
into the prompt.

## `people/`

One Markdown file per person you know. Filenames are typically the person's
name lowercased and hyphenated (`jane-smith.md`).

```yaml
---
type: person
name: <person's name>
tags: []
last_contact: null        # ISO date of the last interaction
cadence_weeks: null       # How often you'd like to keep in touch
---
```

Sections: **Background**, **Recent interactions**.

The agent appends dated lines under **Recent interactions** when you tell it
about a conversation, and updates `last_contact` in frontmatter. `cadence_weeks`
is what the scheduler uses to surface "haven't talked to X in a while"
follow-ups.

## `interests/`

One file per hobby, topic, or learning thread (e.g., `interests/rust.md`,
`interests/woodworking.md`).

```yaml
---
type: interest
name: <topic>
tags: []
---
```

Sections: **What I'm exploring**, **Notes**.

## `projects/`

One file per personal or side project.

```yaml
---
type: project
name: <project>
status: active            # active | paused | done
tags: []
---
```

Sections: **Goal**, **Status**, **Next steps**.

## `work/`

Free-form notes about your job: colleagues, ongoing work threads, decisions,
recurring meetings. No fixed template — write whatever shape of note fits. The
agent treats anything here as work context when it lists or searches files.

## `journal/`

Daily notes, nested by date. The path for a given day is built by
`VaultManager.journal_path_for(d)`:

```
journal/2026/05/19.md
```

```yaml
---
type: journal
date: 2026-05-19
---
```

Sections: **What happened**, **What I learned**.

Today's journal entry, if it exists, is read in full into every turn's
bootstrap context (truncated at ~2k characters).

## `reminders/`

Two files, both plain Markdown checkbox lists. We deliberately avoid a real
task DB — a checkbox list is editable by hand and the model can read the whole
thing in one go.

- `reminders/active.md` — open reminders.

  ```markdown
  # Active reminders

  - [ ] Email the landlord (due 2026-05-22)
  - [ ] Finish profile bio
  ```

- `reminders/archive.md` — completed items, with a trailing `— done <date>`
  stamp appended by `complete_reminder`.

The active file is also injected into every turn's bootstrap context, so the
agent always knows what's open.

## `inbox/`

A staging area for quick captures the agent (or you) can dump into without
deciding where they belong yet. Files here are normal notes; expect to move or
delete them during periodic triage.

## `threads/`

One file per past chat conversation, named `<32-hex-id>.md`. Frontmatter
captures thread-level metadata; the body is alternating user/assistant blocks
parsed by `_SECTION_RE` in `src/pa/threads.py`.

```yaml
---
thread_id: <32-hex-id>
title: <short title>
created: <iso timestamp>
last_message_at: <iso timestamp>
message_count: <int>
---
```

```markdown
## user · 2026-05-19T10:14:02
…

## assistant · 2026-05-19T10:14:07
…
```

**Important:** thread files are deliberately excluded from semantic search
(`VaultManager.iter_notes()` skips `threads/`) so chat history doesn't pollute
the vector index. The agent can still reach them through the dedicated
`list_threads` and `read_thread` tools — see `docs/tools.md`.

## `.pa/` — system directory

Hidden directory the app uses for state. Don't edit unless you're prepared to
lose things.

- `.pa/index.lance/` — LanceDB table holding vault chunk embeddings. The
  embedding dimension is detected from the live `PA_EMBED_MODEL` on first run
  and frozen for the life of the table; if you switch embedding models, delete
  this directory so it can be rebuilt.
- `.pa/tool_gate.json` — persisted state for tool toggles (which external tool
  groups and per-tool overrides are on).
- Other internal logs/state added by the app over time.

Both `.pa/` and `threads/` are skipped by `iter_notes`, so anything inside them
is invisible to text and semantic search.

## Path safety

Every file-writing tool routes through `VaultManager.resolve_inside(path)`,
which rejects absolute paths, `~`-prefixed paths, and any path that resolves
outside the vault root. If you add a new tool that mutates the vault, use this
helper rather than touching `pathlib.Path` directly.
