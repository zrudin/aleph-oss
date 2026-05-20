"""Tools (the parts that don't require Ollama)."""

from __future__ import annotations

import json

import pytest

from pa.tools.files import (
    append_to_file,
    list_files,
    read_file,
    update_frontmatter,
    update_section,
    write_file,
)
from pa.tools.reminders import complete_reminder, create_reminder, list_reminders
from pa.tools.search import text_search
from pa.vault.note import Note


@pytest.mark.asyncio
async def test_write_then_read(temp_vault):
    await write_file("people/bob.md", "# Bob\n\nSome notes.\n")
    result = await read_file("people/bob.md")
    assert "# Bob" in result["content"]


@pytest.mark.asyncio
async def test_write_with_template(temp_vault):
    result = await write_file("people/carol.md", "Met at a conference.", template="person")
    assert result["created"] is True
    body = (temp_vault.root / "people" / "carol.md").read_text()
    assert "type: person" in body
    assert "Met at a conference." in body


@pytest.mark.asyncio
async def test_append_to_file(temp_vault):
    await write_file("journal/today.md", "# Today\n\nFirst line.\n")
    await append_to_file("journal/today.md", "Second line.")
    content = (temp_vault.root / "journal" / "today.md").read_text()
    assert "First line." in content
    assert "Second line." in content


@pytest.mark.asyncio
async def test_list_files_skips_system_dir(temp_vault):
    result = await list_files("")
    names = {e["name"] for e in result["entries"]}
    assert ".pa" not in names
    assert "people" in names


@pytest.mark.asyncio
async def test_reminder_lifecycle(temp_vault):
    await create_reminder("Send Alice the book recommendation")
    listed = await list_reminders()
    assert any("Alice" in r["text"] for r in listed["active"])

    completed = await complete_reminder("alice")
    assert completed["completed"] is True

    listed_after = await list_reminders()
    assert not any("Alice" in r["text"] for r in listed_after["active"])


@pytest.mark.asyncio
async def test_text_search_finds_matches(temp_vault):
    await write_file("people/dan.md", "# Dan\n\nLikes mountain biking.\n")
    await write_file("interests/cycling.md", "# Cycling\n\nMountain biking is fun.\n")
    result = await text_search(r"mountain biking")
    assert len(result["results"]) >= 2
    assert {r["path"] for r in result["results"]} >= {"people/dan.md", "interests/cycling.md"}


@pytest.mark.asyncio
async def test_write_file_rejects_traversal(temp_vault):
    with pytest.raises(ValueError):
        await write_file("../escape.md", "nope")


def test_registry_schemas_parse_as_valid_json():
    from pa.tools.registry import tool_schemas

    for s in tool_schemas():
        # Round-trip through JSON to confirm everything is JSON-serializable.
        json.dumps(s)
        assert s["type"] == "function"
        assert "name" in s["function"]


@pytest.mark.asyncio
async def test_update_section_replaces_only_target_heading(temp_vault):
    await write_file(
        "profile.md",
        "---\ntype: profile\nname: You\n---\n"
        "# You\n\n## Bio\n\nold bio\n\n## Current focus\n\nold focus\n\n## Values\n\nkeep me\n",
    )
    result = await update_section("profile.md", "Current focus", "Shipping Aleph.")
    assert result["updated"] is True

    content = (temp_vault.root / "profile.md").read_text()
    assert "old bio" in content
    assert "keep me" in content
    assert "old focus" not in content
    assert "Shipping Aleph." in content
    # Heading line itself is preserved.
    assert "## Current focus" in content
    # Frontmatter survives intact (type, name).
    note = Note.load(temp_vault.root / "profile.md")
    assert note.metadata.get("type") == "profile"
    assert note.metadata.get("name") == "You"


@pytest.mark.asyncio
async def test_update_section_handles_final_section(temp_vault):
    await write_file(
        "notes.md",
        "# Notes\n\n## First\n\none\n\n## Last\n\nold last\n",
    )
    await update_section("notes.md", "Last", "new last")
    content = (temp_vault.root / "notes.md").read_text()
    assert "one" in content
    assert "new last" in content
    assert "old last" not in content


@pytest.mark.asyncio
async def test_update_section_handles_trailing_empty_section_in_template(temp_vault):
    """Regression: the freshly-bootstrapped profile template ends with an
    empty `## Current focus` heading. `frontmatter.loads` strips the trailing
    newline from `post.content`, so without a separator we'd produce
    `## Current focusBody text` jammed onto the heading."""
    # temp_vault.bootstrap() already created profile.md from the template.
    await update_section(
        "profile.md", "Current focus", "Shipping Aleph."
    )
    content = (temp_vault.root / "profile.md").read_text()
    assert "## Current focus\n\nShipping Aleph." in content
    assert "## Current focusShipping" not in content
    # Other sections should still be intact (empty but present).
    assert "## Bio" in content
    assert "## Preferences" in content
    assert "## Values" in content


@pytest.mark.asyncio
async def test_update_section_handles_empty_section_with_no_trailing_newline(temp_vault):
    """A heading at the very end of the body with no trailing newline still
    gets a proper separator before the new content."""
    await write_file(
        "notes.md",
        "# Notes\n\n## First\n\none\n\n## Last",  # no \n after "Last"
    )
    # Re-read to confirm it landed exactly as written; write_file may add
    # trailing newlines, so this guards against the test going stale.
    raw = (temp_vault.root / "notes.md").read_text()
    if raw.endswith("## Last") or raw.endswith("## Last\n"):
        await update_section("notes.md", "Last", "fresh content")
        content = (temp_vault.root / "notes.md").read_text()
        assert "## Last\n\nfresh content" in content
        assert "## Lastfresh" not in content


@pytest.mark.asyncio
async def test_update_section_replaces_nested_subheadings(temp_vault):
    await write_file(
        "notes.md",
        "# Notes\n\n## Plans\n\n### A\nfirst\n\n### B\nsecond\n\n## Other\nkeep\n",
    )
    await update_section("notes.md", "Plans", "wiped")
    content = (temp_vault.root / "notes.md").read_text()
    assert "first" not in content
    assert "second" not in content
    assert "### A" not in content
    assert "wiped" in content
    assert "## Other" in content
    assert "keep" in content


@pytest.mark.asyncio
async def test_update_section_clears_with_empty_body(temp_vault):
    await write_file(
        "notes.md",
        "# Notes\n\n## A\n\nfilled\n\n## B\n\nalso\n",
    )
    await update_section("notes.md", "A", "")
    content = (temp_vault.root / "notes.md").read_text()
    assert "filled" not in content
    assert "## A" in content
    assert "## B" in content
    assert "also" in content


@pytest.mark.asyncio
async def test_update_section_errors_on_missing_heading(temp_vault):
    await write_file("notes.md", "# Notes\n\n## Real\n\nbody\n")
    result = await update_section("notes.md", "Missing", "nope")
    assert "error" in result
    # File untouched.
    assert (temp_vault.root / "notes.md").read_text().count("body") == 1


@pytest.mark.asyncio
async def test_update_section_errors_on_missing_file(temp_vault):
    result = await update_section("nope.md", "Anything", "...")
    assert "error" in result


@pytest.mark.asyncio
async def test_update_frontmatter_sets_key_and_preserves_body(temp_vault):
    await write_file(
        "people/alice.md",
        "---\ntype: person\nname: Alice\nlast_contact: null\n---\n"
        "# Alice\n\n## Background\n\nFriend from college.\n",
    )
    result = await update_frontmatter("people/alice.md", "last_contact", "2026-05-19")
    assert result["updated"] is True

    note = Note.load(temp_vault.root / "people" / "alice.md")
    assert note.metadata["last_contact"] == "2026-05-19"
    # Body preserved (modulo the frontmatter library's trailing-newline strip on load).
    assert note.body.rstrip("\n") == "# Alice\n\n## Background\n\nFriend from college."
    # `updated` was set by Note.save.
    assert "updated" in note.metadata


@pytest.mark.asyncio
async def test_update_frontmatter_accepts_int_and_list(temp_vault):
    await write_file(
        "people/bob.md",
        "---\ntype: person\nname: Bob\ntags: []\n---\n# Bob\n\nNotes.\n",
    )
    await update_frontmatter("people/bob.md", "cadence_weeks", 4)
    await update_frontmatter("people/bob.md", "tags", ["climbing", "rust"])
    note = Note.load(temp_vault.root / "people" / "bob.md")
    assert note.metadata["cadence_weeks"] == 4
    assert note.metadata["tags"] == ["climbing", "rust"]


@pytest.mark.asyncio
async def test_update_frontmatter_errors_on_missing_file(temp_vault):
    result = await update_frontmatter("nope.md", "k", "v")
    assert "error" in result


@pytest.mark.asyncio
async def test_update_section_rejects_traversal(temp_vault):
    with pytest.raises(ValueError):
        await update_section("../escape.md", "Heading", "body")


@pytest.mark.asyncio
async def test_update_frontmatter_rejects_traversal(temp_vault):
    with pytest.raises(ValueError):
        await update_frontmatter("../escape.md", "k", "v")


@pytest.mark.asyncio
async def test_update_frontmatter_blocks_premature_first_run_flip(temp_vault):
    """Flipping `first_run_complete=true` is refused while onboarding sections are blank."""
    # Bootstrap leaves Bio/Current focus/Preferences empty on profile.md.
    result = await update_frontmatter("profile.md", "first_run_complete", True)
    assert "error" in result
    assert "first_run_complete" in result["error"]
    # All three onboarding sections should be listed as missing.
    assert set(result["missing_sections"]) == {"Bio", "Current focus", "Preferences"}

    # And the marker on disk must still be False.
    note = Note.load(temp_vault.root / "profile.md")
    assert note.metadata["first_run_complete"] is False


@pytest.mark.asyncio
async def test_update_frontmatter_allows_first_run_flip_when_sections_filled(temp_vault):
    """Once all three onboarding sections have content, the flip succeeds."""
    await update_section("profile.md", "Bio", "I'm a person.")
    await update_section("profile.md", "Current focus", "Shipping Aleph.")
    await update_section("profile.md", "Preferences", "Tight responses.")

    result = await update_frontmatter("profile.md", "first_run_complete", True)
    assert "error" not in result
    note = Note.load(temp_vault.root / "profile.md")
    assert note.metadata["first_run_complete"] is True


@pytest.mark.asyncio
async def test_update_frontmatter_guard_only_applies_to_profile(temp_vault):
    """The onboarding guard must not interfere with other notes."""
    await write_file("people/x.md", "---\nname: X\n---\n\n# X\n", template=None)
    result = await update_frontmatter("people/x.md", "first_run_complete", True)
    # Sanity: nonsense key but tool should still accept it on a non-profile note.
    assert "error" not in result


@pytest.mark.asyncio
async def test_update_frontmatter_guard_handles_symlinked_vault_root(tmp_path, monkeypatch):
    """Regression: on macOS `/tmp -> /private/tmp`, so the resolved target path
    has a different prefix than `vault.root`. The earlier guard implementation
    called `target.relative_to(vault.root)` and raised `ValueError`, which
    aborted the tool before the section check could run — the marker silently
    failed to flip even with all sections populated."""
    from pathlib import Path

    import pa.vault.manager as vm
    from pa.vault.manager import VaultManager

    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "link"
    link_root.symlink_to(real_root, target_is_directory=True)

    vault = VaultManager(root=link_root, require_mount=False)
    vault.bootstrap()
    monkeypatch.setattr(vm, "_vault", vault)

    # Sanity-check the precondition: vault.root is unresolved.
    assert Path(link_root).resolve() != link_root

    await update_section("profile.md", "Bio", "I'm a person.")
    await update_section("profile.md", "Current focus", "Shipping Aleph.")
    await update_section("profile.md", "Preferences", "Tight responses.")

    result = await update_frontmatter("profile.md", "first_run_complete", True)
    # The guard must pass *without* throwing, and the flip must succeed.
    assert "error" not in result, result
    note = Note.load(link_root / "profile.md")
    assert note.metadata["first_run_complete"] is True
