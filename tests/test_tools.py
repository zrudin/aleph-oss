"""Tools (the parts that don't require Ollama)."""

from __future__ import annotations

import json

import pytest

from pa.tools.files import append_to_file, list_files, read_file, write_file
from pa.tools.reminders import complete_reminder, create_reminder, list_reminders
from pa.tools.search import text_search


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
