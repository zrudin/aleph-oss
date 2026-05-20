"""Persistent chat threads, stored as markdown notes in `<vault>/threads/`.

Each thread is one `.md` file with YAML frontmatter (metadata) and a body of
alternating `## user · <iso-ts>` and `## assistant · <iso-ts>` sections. The
file lives inside the encrypted vault, so no app-level crypto is needed.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pa.vault.conventions import THREADS_DIR
from pa.vault.manager import VaultManager
from pa.vault.note import Note

DEFAULT_TITLE = "New chat"
_THREAD_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_SECTION_RE = re.compile(
    r"^## (user|assistant) · (\S+)\s*$",
    re.MULTILINE,
)


@dataclass
class Message:
    role: str
    content: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Thread:
    thread_id: str
    title: str = DEFAULT_TITLE
    created: str = ""
    updated: str = ""
    last_message_at: str = ""
    messages: list[Message] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass
class ThreadSummary:
    thread_id: str
    title: str
    last_message_at: str
    message_count: int

    def to_dict(self) -> dict:
        return {
            "id": self.thread_id,
            "title": self.title,
            "last_message_at": self.last_message_at,
            "message_count": self.message_count,
        }


def now_iso() -> str:
    # Microsecond precision so concurrent threads sort deterministically.
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_thread_id() -> str:
    return uuid.uuid4().hex


def _validate_id(thread_id: str) -> None:
    if not _THREAD_ID_RE.match(thread_id):
        raise ValueError(f"invalid thread_id: {thread_id!r}")


def thread_path(vault: VaultManager, thread_id: str) -> Path:
    _validate_id(thread_id)
    return vault.root / THREADS_DIR / f"{thread_id}.md"


def _serialize_messages(messages: list[Message]) -> str:
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        parts.append(f"## {m.role} · {m.timestamp}\n\n{m.content.rstrip()}")
    return "\n\n".join(parts) + "\n"


def _parse_messages(body: str) -> list[Message]:
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return []
    messages: list[Message] = []
    for i, m in enumerate(matches):
        role = m.group(1)
        ts = m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip("\n")
        messages.append(Message(role=role, content=content, timestamp=ts))
    return messages


def _thread_from_note(note: Note) -> Thread:
    meta = note.metadata
    return Thread(
        thread_id=str(meta.get("thread_id") or note.path.stem),
        title=str(meta.get("title") or DEFAULT_TITLE),
        created=str(meta.get("created") or ""),
        updated=str(meta.get("updated") or ""),
        last_message_at=str(meta.get("last_message_at") or meta.get("updated") or ""),
        messages=_parse_messages(note.body),
    )


def save_thread(vault: VaultManager, thread: Thread) -> None:
    path = thread_path(vault, thread.thread_id)
    metadata = {
        "type": "thread",
        "thread_id": thread.thread_id,
        "title": thread.title,
        "last_message_at": thread.last_message_at or thread.updated or now_iso(),
        "message_count": thread.message_count,
    }
    if thread.created:
        metadata["created"] = thread.created
    body = _serialize_messages(thread.messages)
    note = Note(path=path, metadata=metadata, body=body)
    note.save()
    # Note.save() sets `updated` to now and `created` to now if missing.
    thread.created = str(note.metadata.get("created", thread.created))
    thread.updated = str(note.metadata.get("updated", thread.updated))


def load_thread(vault: VaultManager, thread_id: str) -> Thread:
    path = thread_path(vault, thread_id)
    if not path.exists():
        raise FileNotFoundError(f"thread not found: {thread_id}")
    return _thread_from_note(Note.load(path))


def thread_exists(vault: VaultManager, thread_id: str) -> bool:
    try:
        return thread_path(vault, thread_id).exists()
    except ValueError:
        return False


def delete_thread(vault: VaultManager, thread_id: str) -> None:
    path = thread_path(vault, thread_id)
    if path.exists():
        path.unlink()


def rename_thread(vault: VaultManager, thread_id: str, new_title: str) -> Thread:
    title = new_title.strip()
    if not title:
        raise ValueError("title cannot be empty")
    thread = load_thread(vault, thread_id)
    thread.title = title[:200]
    save_thread(vault, thread)
    return thread


def append_message(vault: VaultManager, thread_id: str, message: Message) -> Thread:
    thread = load_thread(vault, thread_id)
    thread.messages.append(message)
    thread.last_message_at = message.timestamp
    save_thread(vault, thread)
    return thread


def create_thread(
    vault: VaultManager,
    *,
    thread_id: str | None = None,
    title: str = DEFAULT_TITLE,
) -> Thread:
    """Create and persist an empty thread."""
    tid = thread_id or new_thread_id()
    _validate_id(tid)
    ts = now_iso()
    thread = Thread(
        thread_id=tid,
        title=title,
        created=ts,
        updated=ts,
        last_message_at=ts,
        messages=[],
    )
    save_thread(vault, thread)
    return thread


def list_threads(vault: VaultManager, limit: int | None = None) -> list[ThreadSummary]:
    """Return thread summaries sorted by `last_message_at` descending."""
    base = vault.root / THREADS_DIR
    if not base.is_dir():
        return []
    summaries: list[ThreadSummary] = []
    for path in base.glob("*.md"):
        if not _THREAD_ID_RE.match(path.stem):
            continue
        try:
            note = Note.load(path)
        except OSError:
            continue
        thread = _thread_from_note(note)
        summaries.append(
            ThreadSummary(
                thread_id=thread.thread_id,
                title=thread.title,
                last_message_at=thread.last_message_at or thread.updated,
                message_count=thread.message_count,
            )
        )
    summaries.sort(key=lambda s: s.last_message_at, reverse=True)
    if limit is not None:
        return summaries[:limit]
    return summaries


def placeholder_title(user_message: str, max_len: int = 40) -> str:
    """First-line, length-capped fallback used until the LLM generates a real title."""
    first_line = user_message.strip().splitlines()[0] if user_message.strip() else ""
    if len(first_line) <= max_len:
        return first_line or DEFAULT_TITLE
    return first_line[:max_len].rstrip() + "…"
