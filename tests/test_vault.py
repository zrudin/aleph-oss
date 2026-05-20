"""Vault: path safety, bootstrap, note round-trip."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pa.vault.conventions import (
    BOOTSTRAP_DIRECTORIES,
    REMINDERS_ACTIVE,
)
from pa.vault.manager import VaultManager
from pa.vault.note import Note, slugify


def test_bootstrap_creates_expected_directories(temp_vault):
    for rel in BOOTSTRAP_DIRECTORIES:
        assert (temp_vault.root / rel).is_dir(), f"missing: {rel}"
    assert (temp_vault.root / REMINDERS_ACTIVE).is_file()


def test_resolve_inside_rejects_traversal(temp_vault):
    with pytest.raises(ValueError):
        temp_vault.resolve_inside("../../etc/passwd")
    with pytest.raises(ValueError):
        temp_vault.resolve_inside("/etc/passwd")


def test_resolve_inside_accepts_relative(temp_vault):
    resolved = temp_vault.resolve_inside("people/alice.md")
    assert resolved.is_relative_to(temp_vault.root)


def test_note_round_trip(temp_vault):
    path = temp_vault.root / "people" / "alice.md"
    note = Note(
        path=path,
        metadata={"type": "person", "name": "Alice", "tags": ["friend"]},
        body="# Alice\n\nNotes.\n",
    )
    note.save()

    reloaded = Note.load(path)
    assert reloaded.metadata["name"] == "Alice"
    assert reloaded.metadata["type"] == "person"
    assert "Notes." in reloaded.body
    assert "created" in reloaded.metadata
    assert "updated" in reloaded.metadata


def test_slugify_handles_unicode_and_punctuation():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  café—latte  ") == "cafe-latte"
    assert slugify("") == "untitled"


def test_is_mounted_respects_require_mount_flag(tmp_path: Path):
    # A plain directory is not a real mount point, so with require_mount=True
    # is_mounted() must return False on darwin (the production check).
    if sys.platform == "darwin":
        assert VaultManager(root=tmp_path, require_mount=True).is_mounted() is False

    # With require_mount=False (dev mode), the same directory is considered
    # mounted as long as it exists — that's what `make dev` relies on.
    assert VaultManager(root=tmp_path, require_mount=False).is_mounted() is True

    # A missing directory is never "mounted", regardless of the flag.
    missing = tmp_path / "does-not-exist"
    assert VaultManager(root=missing, require_mount=False).is_mounted() is False


def test_tree_summary_lists_known_dirs(temp_vault):
    (temp_vault.root / "people" / "x.md").write_text("---\ntype: person\n---\n# X")
    (temp_vault.root / "projects" / "y.md").write_text("---\ntype: project\n---\n# Y")
    summary = temp_vault.tree_summary()
    assert "people: 1" in summary
    assert "projects: 1" in summary
