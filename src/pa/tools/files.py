"""Vault file tools: list / read / write / append. All writes are sandboxed."""

from __future__ import annotations

from pa.vault.manager import get_vault
from pa.vault.note import Note
from pa.vault.templates import render_template


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
    separator = "" if existing.endswith("\n\n") or not existing else ("\n" if existing.endswith("\n") else "\n\n")
    target.write_text(existing + separator + content.rstrip() + "\n", encoding="utf-8")
    return {"path": path, "appended": True}
