"""Line-anchored reminder helpers used by the web UI."""

from __future__ import annotations

from pa.tools.reminders import (
    append_line,
    delete_at_line,
    list_active_items,
    set_done_at_line,
)
from pa.vault.conventions import REMINDERS_ACTIVE


def test_append_and_list(temp_vault):
    line = append_line("Call the dentist")
    items = list_active_items()
    assert any(it["line"] == line and it["text"] == "Call the dentist" for it in items)


def test_toggle_done_round_trip(temp_vault):
    line = append_line("Pick up dry cleaning")
    assert set_done_at_line(line, True) is True
    items = list_active_items()
    match = next(it for it in items if it["line"] == line)
    assert match["done"] is True

    assert set_done_at_line(line, False) is True
    items = list_active_items()
    match = next(it for it in items if it["line"] == line)
    assert match["done"] is False


def test_delete_removes_row(temp_vault):
    line = append_line("Renew library card")
    assert delete_at_line(line) is True
    assert all(it["line"] != line for it in list_active_items())


def test_set_done_returns_false_for_missing_line(temp_vault):
    # File exists (bootstrap created it) but no item lives at line 99.
    assert set_done_at_line(99, True) is False


def test_lines_are_one_based(temp_vault):
    # The reminders file starts with a heading line + blank line, then items.
    line_a = append_line("first")
    line_b = append_line("second")
    body = (temp_vault.root / REMINDERS_ACTIVE).read_text(encoding="utf-8").splitlines()
    assert body[line_a - 1].startswith("- [ ] first")
    assert body[line_b - 1].startswith("- [ ] second")
