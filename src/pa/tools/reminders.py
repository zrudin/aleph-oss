"""Reminder tools backed by `reminders/active.md` and `reminders/archive.md`.

Reminders are a single Markdown checkbox list — easy for the user to edit by hand
and easy for the model to read in full. We do simple line manipulation rather
than a real task DB; that's the right scope for v1.
"""

from __future__ import annotations

import re
from datetime import date

from pa.vault.conventions import REMINDERS_ACTIVE, REMINDERS_ARCHIVE
from pa.vault.manager import get_vault

_ITEM_RE = re.compile(r"^(\s*)-\s*\[(?P<state>[ xX])\]\s*(?P<text>.+?)\s*$")


def _read(path: str) -> list[str]:
    vault = get_vault()
    target = vault.resolve_inside(path)
    if not target.exists():
        return []
    return target.read_text(encoding="utf-8").splitlines()


def _write(path: str, lines: list[str]) -> None:
    vault = get_vault()
    target = vault.resolve_inside(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


async def list_reminders(filter: str = "") -> dict:
    items: list[dict] = []
    for it in list_active_items():
        if filter and filter.lower() not in it["text"].lower():
            continue
        items.append(it)
    return {"active": items}


def list_active_items() -> list[dict]:
    """Synchronous helper used by the web routes."""
    out: list[dict] = []
    for lineno, line in enumerate(_read(REMINDERS_ACTIVE), start=1):
        m = _ITEM_RE.match(line)
        if not m:
            continue
        out.append({
            "line": lineno,
            "text": m.group("text"),
            "done": m.group("state").lower() == "x",
        })
    return out


def append_line(text: str) -> int:
    """Append a new open reminder. Returns its 1-based line number."""
    lines = _read(REMINDERS_ACTIVE)
    if not lines:
        lines = ["# Active reminders", ""]
    lines.append(f"- [ ] {text}")
    _write(REMINDERS_ACTIVE, lines)
    return len(lines)


def set_done_at_line(line: int, done: bool) -> bool:
    """Toggle the checkbox on a specific line. Returns False if no match."""
    lines = _read(REMINDERS_ACTIVE)
    idx = line - 1
    if idx < 0 or idx >= len(lines):
        return False
    m = _ITEM_RE.match(lines[idx])
    if not m:
        return False
    state = "x" if done else " "
    lines[idx] = f"{m.group(1)}- [{state}] {m.group('text')}"
    _write(REMINDERS_ACTIVE, lines)
    return True


def delete_at_line(line: int) -> bool:
    """Remove the reminder at this line. Returns False if no match."""
    lines = _read(REMINDERS_ACTIVE)
    idx = line - 1
    if idx < 0 or idx >= len(lines):
        return False
    if not _ITEM_RE.match(lines[idx]):
        return False
    del lines[idx]
    _write(REMINDERS_ACTIVE, lines)
    return True


async def create_reminder(text: str, due: str | None = None) -> dict:
    """Append a new reminder. `due` is optional ISO date (free-form is fine too)."""
    suffix = f" (due {due})" if due else ""
    new_line = f"- [ ] {text}{suffix}"
    lines = _read(REMINDERS_ACTIVE)
    if not lines:
        lines = ["# Active reminders", ""]
    lines.append(new_line)
    _write(REMINDERS_ACTIVE, lines)
    return {"added": new_line}


async def complete_reminder(text: str) -> dict:
    """Mark the first matching reminder complete and move it to the archive."""
    active = _read(REMINDERS_ACTIVE)
    matched_idx: int | None = None
    for i, line in enumerate(active):
        m = _ITEM_RE.match(line)
        if not m:
            continue
        if text.lower() in m.group("text").lower() and m.group("state").lower() != "x":
            matched_idx = i
            break

    if matched_idx is None:
        return {"completed": False, "reason": "no matching active reminder"}

    completed_line = active[matched_idx]
    del active[matched_idx]
    _write(REMINDERS_ACTIVE, active)

    archive = _read(REMINDERS_ARCHIVE)
    if not archive:
        archive = ["# Completed reminders", ""]
    archive.append(f"{completed_line.rstrip()}  — done {date.today().isoformat()}")
    _write(REMINDERS_ARCHIVE, archive)

    return {"completed": True, "text": completed_line.strip()}
