"""Thread storage: round-trip, append, list ordering, rename, delete."""

from __future__ import annotations

import time

import pytest

from pa import threads as threads_mod
from pa.threads import (
    DEFAULT_TITLE,
    Message,
    append_message,
    create_thread,
    delete_thread,
    list_threads,
    load_thread,
    new_thread_id,
    placeholder_title,
    rename_thread,
    save_thread,
    thread_exists,
    thread_path,
)
from pa.vault.conventions import THREADS_DIR


def test_threads_dir_bootstrapped(temp_vault):
    assert (temp_vault.root / THREADS_DIR).is_dir()


def test_create_and_load_thread(temp_vault):
    thread = create_thread(temp_vault, title="Project kickoff")
    assert thread.thread_id
    assert thread.title == "Project kickoff"
    assert thread_exists(temp_vault, thread.thread_id)

    reloaded = load_thread(temp_vault, thread.thread_id)
    assert reloaded.title == "Project kickoff"
    assert reloaded.messages == []
    assert reloaded.created
    assert reloaded.updated


def test_append_message_round_trip(temp_vault):
    thread = create_thread(temp_vault, title="Test")
    ts1 = threads_mod.now_iso()
    append_message(
        temp_vault,
        thread.thread_id,
        Message(role="user", content="Hello, what time is it?", timestamp=ts1),
    )
    time.sleep(0.01)
    ts2 = threads_mod.now_iso()
    append_message(
        temp_vault,
        thread.thread_id,
        Message(
            role="assistant",
            content="It's 2pm.\n\nAnything else?",
            timestamp=ts2,
        ),
    )

    reloaded = load_thread(temp_vault, thread.thread_id)
    assert len(reloaded.messages) == 2
    assert reloaded.messages[0].role == "user"
    assert reloaded.messages[0].content == "Hello, what time is it?"
    assert reloaded.messages[0].timestamp == ts1
    assert reloaded.messages[1].role == "assistant"
    assert "Anything else?" in reloaded.messages[1].content
    assert reloaded.messages[1].timestamp == ts2
    assert reloaded.last_message_at == ts2


def test_parse_handles_multiline_and_markdown(temp_vault):
    thread = create_thread(temp_vault, title="Markdown")
    ts = threads_mod.now_iso()
    body = "Here is code:\n\n```python\nprint('hi')\n```\n\nAnd a list:\n\n- one\n- two"
    append_message(
        temp_vault,
        thread.thread_id,
        Message(role="assistant", content=body, timestamp=ts),
    )
    reloaded = load_thread(temp_vault, thread.thread_id)
    assert reloaded.messages[0].content == body


def test_list_threads_sorted_by_last_message(temp_vault):
    a = create_thread(temp_vault, title="A")
    time.sleep(0.01)
    b = create_thread(temp_vault, title="B")
    time.sleep(0.01)
    c = create_thread(temp_vault, title="C")

    # Push A to the top by appending a fresh message.
    time.sleep(0.01)
    append_message(
        temp_vault,
        a.thread_id,
        Message(role="user", content="bump", timestamp=threads_mod.now_iso()),
    )

    summaries = list_threads(temp_vault)
    ids = [s.thread_id for s in summaries]
    assert ids[0] == a.thread_id
    assert set(ids[1:]) == {b.thread_id, c.thread_id}


def test_list_threads_respects_limit(temp_vault):
    for _ in range(5):
        create_thread(temp_vault)
        time.sleep(0.005)
    assert len(list_threads(temp_vault, limit=3)) == 3


def test_rename_thread_preserves_messages(temp_vault):
    thread = create_thread(temp_vault, title="Old name")
    ts = threads_mod.now_iso()
    append_message(
        temp_vault,
        thread.thread_id,
        Message(role="user", content="hi", timestamp=ts),
    )

    rename_thread(temp_vault, thread.thread_id, "Better title")

    reloaded = load_thread(temp_vault, thread.thread_id)
    assert reloaded.title == "Better title"
    assert len(reloaded.messages) == 1
    assert reloaded.messages[0].content == "hi"


def test_rename_rejects_empty_title(temp_vault):
    thread = create_thread(temp_vault)
    with pytest.raises(ValueError):
        rename_thread(temp_vault, thread.thread_id, "   ")


def test_delete_thread(temp_vault):
    thread = create_thread(temp_vault)
    assert thread_exists(temp_vault, thread.thread_id)
    delete_thread(temp_vault, thread.thread_id)
    assert not thread_exists(temp_vault, thread.thread_id)


def test_delete_missing_is_noop(temp_vault):
    delete_thread(temp_vault, new_thread_id())  # no error


def test_invalid_thread_id_rejected(temp_vault):
    with pytest.raises(ValueError):
        thread_path(temp_vault, "../etc/passwd")
    with pytest.raises(ValueError):
        thread_path(temp_vault, "not-a-uuid")


def test_load_missing_thread_raises(temp_vault):
    with pytest.raises(FileNotFoundError):
        load_thread(temp_vault, new_thread_id())


def test_placeholder_title_truncates():
    assert placeholder_title("short") == "short"
    long = "this is a really long message that should be truncated for the title"
    title = placeholder_title(long, max_len=20)
    assert len(title) <= 21  # +1 for the ellipsis char
    assert title.endswith("…")
    assert placeholder_title("") == DEFAULT_TITLE
    assert placeholder_title("first line\nsecond line", max_len=80) == "first line"


def test_save_thread_overwrites_in_place(temp_vault):
    thread = create_thread(temp_vault, title="V1")
    thread.title = "V2"
    save_thread(temp_vault, thread)
    reloaded = load_thread(temp_vault, thread.thread_id)
    assert reloaded.title == "V2"
