"""Vault file tools: list / read / write / append / structured edits. All writes are sandboxed."""

from __future__ import annotations

import re
from typing import Any

from pa.vault.conventions import PROFILE_FILE
from pa.vault.manager import get_vault
from pa.vault.note import Note
from pa.vault.templates import render_template

_ONBOARDING_REQUIRED_SECTIONS = ("Bio", "Current focus", "Preferences")


async def list_files(directory: str = "") -> dict:
    vault = get_vault()
    entries = vault.list_directory(directory)
    return {"directory": directory or "/", "entries": entries}


async def read_file(path: str) -> dict:
    vault = get_vault()
    target = vault.resolve_inside(path)
    if not target.exists():
        return {"error": f"not found: {path}"}
    if not target.is_file():
        return {"error": f"not a file: {path}"}
    return {"path": path, "content": target.read_text(encoding="utf-8")}


async def write_file(path: str, content: str, template: str | None = None) -> dict:
    """Create or replace a note.

    If `template` is provided and the file doesn't exist, render the template
    first and let `content` be appended as the body. If the file exists, treat
    `content` as a full replacement (use `append_to_file` for additive edits).
    """
    vault = get_vault()
    target = vault.resolve_inside(path)
    existed = target.exists()

    if template and not existed:
        rendered = render_template(template, name=target.stem.replace("-", " ").title())
        note = Note.parse(target, rendered)
        if content.strip():
            note.body = (note.body.rstrip() + "\n\n" + content.strip() + "\n")
        note.save()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return {"path": path, "created": not existed}


async def append_to_file(path: str, content: str) -> dict:
    vault = get_vault()
    target = vault.resolve_inside(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    # Ensure a blank line separator.
    if existing.endswith("\n\n") or not existing:
        separator = ""
    elif existing.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    target.write_text(existing + separator + content.rstrip() + "\n", encoding="utf-8")
    return {"path": path, "appended": True}


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _replace_section(body: str, heading: str, new_body: str) -> str | None:
    """Replace the content under the first heading matching `heading`.

    The heading line itself is preserved; everything between it and the next
    heading of the same or higher level (fewer #s) is replaced with `new_body`.
    Sub-headings nested under the target are considered part of the section
    and get replaced too. Returns None if the heading is not found.
    """
    target = heading.strip()
    matches = list(_HEADING_RE.finditer(body))
    target_idx = None
    target_level = 0
    for i, m in enumerate(matches):
        if m.group(2).strip() == target:
            target_idx = i
            target_level = len(m.group(1))
            break
    if target_idx is None:
        return None

    heading_match = matches[target_idx]
    body_start = heading_match.end()
    # The heading line normally ends with a `\n` that `\s*` consumes — body_start
    # already sits just past it. But when the heading is the very last line of
    # the body with no trailing newline (Note.parse strips trailing newlines
    # from post.content via python-frontmatter), body_start lands at len(body)
    # mid-heading-line. We need to remember to terminate the heading ourselves
    # so the new body doesn't get jammed onto the heading text.
    heading_needs_terminator = not (
        body_start <= 0 or body[body_start - 1] == "\n"
    )
    if body_start < len(body) and body[body_start] == "\n":
        body_start += 1

    section_end = len(body)
    has_next_heading = False
    for j in range(target_idx + 1, len(matches)):
        m = matches[j]
        if len(m.group(1)) <= target_level:
            section_end = m.start()
            has_next_heading = True
            break

    stripped = new_body.rstrip()
    if has_next_heading:
        replacement = (stripped + "\n\n") if stripped else "\n"
    else:
        replacement = (stripped + "\n") if stripped else ""

    if heading_needs_terminator:
        replacement = ("\n\n" + replacement) if stripped else ("\n" + replacement)

    return body[:body_start] + replacement + body[section_end:]


async def update_section(path: str, heading: str, new_body: str) -> dict:
    """Replace the body under a single Markdown heading in an existing note.

    Leaves frontmatter, sibling sections, and any unrelated content untouched.
    Bumps `updated` in frontmatter (via Note.save). Errors if the file or
    heading is missing — use `write_file` to create a new note or add a new
    section.
    """
    vault = get_vault()
    target = vault.resolve_inside(path)
    if not target.exists():
        return {"error": f"not found: {path}"}
    if not target.is_file():
        return {"error": f"not a file: {path}"}

    note = Note.load(target)
    new_body_text = _replace_section(note.body, heading, new_body)
    if new_body_text is None:
        return {"error": f"heading not found in {path}: {heading!r}"}

    note.body = new_body_text
    note.save()
    return {"path": path, "heading": heading, "updated": True}


async def update_frontmatter(path: str, key: str, value: Any) -> dict:
    """Set a single frontmatter key on an existing note. Body is preserved verbatim.

    Use for durable structured fields (`last_contact`, `cadence_weeks`, `status`,
    `tags`, etc.). Setting `value` to `null` writes a YAML null. To remove a key
    entirely, pass an empty string and edit by hand if needed — this tool does
    not support deletion.
    """
    vault = get_vault()
    target = vault.resolve_inside(path)
    if not target.exists():
        return {"error": f"not found: {path}"}
    if not target.is_file():
        return {"error": f"not a file: {path}"}
    if not key or not key.strip():
        return {"error": "key must be a non-empty string"}

    note = Note.load(target)

    # NB: `vault.root` may be unresolved (e.g. `/tmp/...`) while `target` was
    # resolved through symlinks by `resolve_inside` (`/private/tmp/...` on
    # macOS). Compare both as resolved paths so the equality check survives
    # the symlink hop and the guard actually fires on profile.md.
    is_profile = target == (vault.root / PROFILE_FILE).resolve()
    if key == "first_run_complete" and value is True and is_profile:
        missing = [
            heading
            for heading in _ONBOARDING_REQUIRED_SECTIONS
            if not _section_body(note.body, heading)
        ]
        if missing:
            return {
                "error": (
                    "refusing to flip first_run_complete=true while onboarding "
                    f"sections are still empty: {', '.join(missing)}. "
                    "Ask the user the question for each missing section and "
                    "persist the answer with update_section first."
                ),
                "missing_sections": missing,
            }

    note.metadata[key] = value
    note.save()
    return {"path": path, "key": key, "updated": True}


def _section_body(body: str, heading: str) -> str:
    """Return the body text under `## <heading>` in `body`, or '' if missing/empty."""
    lines = body.splitlines()
    in_section = False
    collected: list[str] = []
    target = f"## {heading}"
    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == target
            continue
        if in_section:
            collected.append(line)
    return "\n".join(collected).strip()
