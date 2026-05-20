"""VaultManager: filesystem-level vault operations, mount checks, path safety."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from pa.vault.conventions import (
    BOOTSTRAP_DIRECTORIES,
    INBOX_DIR,
    INTERESTS_DIR,
    JOURNAL_DIR,
    PEOPLE_DIR,
    PROFILE_FILE,
    PROJECTS_DIR,
    REMINDERS_ACTIVE,
    SYSTEM_DIR,
    THREADS_DIR,
    WORK_DIR,
)
from pa.vault.note import Note
from pa.vault.templates import render_template


class VaultNotMountedError(RuntimeError):
    """Raised when a vault operation is attempted but the vault path isn't accessible."""


_SUMMARY_DIRS = [
    ("people", PEOPLE_DIR),
    ("interests", INTERESTS_DIR),
    ("projects", PROJECTS_DIR),
    ("work", WORK_DIR),
    ("journal", JOURNAL_DIR),
    ("inbox", INBOX_DIR),
]


class VaultManager:
    def __init__(self, root: Path, require_mount: bool = True) -> None:
        self.root = Path(root)
        self.require_mount = require_mount

    def is_mounted(self) -> bool:
        if not self.root.is_dir():
            return False
        if sys.platform == "darwin" and self.require_mount:
            # On macOS the vault lives inside an attached sparsebundle, so the
            # root must be an actual mount point — a plain empty directory at
            # /Volumes/PA-Vault would mean the user forgot `make vault-mount`.
            return os.path.ismount(self.root)
        return True

    def ensure_mounted(self) -> None:
        if not self.is_mounted():
            raise VaultNotMountedError(
                f"vault not mounted at {self.root} — run `make vault-mount`"
            )

    def bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for rel in BOOTSTRAP_DIRECTORIES:
            (self.root / rel).mkdir(parents=True, exist_ok=True)

        active = self.root / REMINDERS_ACTIVE
        if not active.exists():
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text("# Active reminders\n\n", encoding="utf-8")

        profile = self.root / PROFILE_FILE
        if not profile.exists():
            rendered = render_template("profile", name="You")
            note = Note.parse(profile, rendered)
            note.save()

    def resolve_inside(self, path: str) -> Path:
        if path.startswith("/") or path.startswith("~"):
            raise ValueError(f"absolute paths are not allowed: {path!r}")
        root_resolved = self.root.resolve()
        target = (self.root / path).resolve()
        if target != root_resolved and not target.is_relative_to(root_resolved):
            raise ValueError(f"path escapes vault: {path!r}")
        return target

    def list_directory(self, rel: str = "") -> list[dict]:
        base = self.resolve_inside(rel) if rel else self.root
        if not base.is_dir():
            return []
        entries: list[dict] = []
        for child in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name.startswith("."):
                continue
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "path": str(child.relative_to(self.root)),
                }
            )
        return entries

    def iter_notes(self) -> Iterator[Path]:
        # Chat threads live under THREADS_DIR and are surfaced to the agent via
        # dedicated list_threads/read_thread tools — keep them out of the
        # vector index so semantic searches over user notes aren't polluted.
        for path in self.root.rglob("*.md"):
            rel = path.relative_to(self.root)
            if SYSTEM_DIR in rel.parts or THREADS_DIR in rel.parts:
                continue
            yield path

    def relative(self, path: Path) -> str:
        return str(Path(path).resolve().relative_to(self.root.resolve()))

    def journal_path_for(self, d: date) -> Path:
        return (
            self.root
            / JOURNAL_DIR
            / f"{d.year:04d}"
            / f"{d.month:02d}"
            / f"{d.day:02d}.md"
        )

    def tree_summary(self) -> str:
        lines: list[str] = []
        for label, rel in _SUMMARY_DIRS:
            base = self.root / rel
            count = 0
            if base.is_dir():
                for path in base.rglob("*.md"):
                    if SYSTEM_DIR in path.relative_to(self.root).parts:
                        continue
                    count += 1
            lines.append(f"{label}: {count}")
        return "\n".join(lines)


_vault: VaultManager | None = None


def get_vault() -> VaultManager:
    global _vault
    if _vault is None:
        from pa.config import settings

        _vault = VaultManager(
            root=settings.vault_path,
            require_mount=settings.require_mount,
        )
    return _vault
