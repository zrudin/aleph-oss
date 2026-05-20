"""Tools the agent uses to read past chat threads."""

from __future__ import annotations

from pa import threads as threads_mod
from pa.vault.manager import get_vault


async def list_threads(limit: int = 20) -> dict:
    """Return recent threads (id, title, last_message_at, message_count)."""
    vault = get_vault()
    summaries = threads_mod.list_threads(vault, limit=limit)
    return {"threads": [s.to_dict() for s in summaries]}


async def read_thread(thread_id: str) -> dict:
    """Return the full content of a thread by id."""
    vault = get_vault()
    try:
        thread = threads_mod.load_thread(vault, thread_id)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}
    return {
        "id": thread.thread_id,
        "title": thread.title,
        "created": thread.created,
        "last_message_at": thread.last_message_at,
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in thread.messages
        ],
    }
