"""Agent loop: bootstrap context → tool-calling iterations → streamed final reply.

Conversations are keyed by `thread_id` and persisted to the vault under
`threads/<id>.md` (see `pa.threads`). The in-memory cache mirrors what's on
disk so we don't re-read the file for every turn within an active session.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pa import threads as threads_mod
from pa.config import settings
from pa.llm import get_llm
from pa.prompts import render_bootstrap_context, render_system_prompt
from pa.threads import (
    DEFAULT_TITLE,
    Message,
    Thread,
    create_thread,
    load_thread,
    placeholder_title,
    save_thread,
    thread_exists,
)
from pa.tools import ToolCall, dispatch, tool_schemas
from pa.vault.manager import get_vault

log = logging.getLogger(__name__)


@dataclass
class ToolEvent:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None


@dataclass
class TurnEvent:
    """Event yielded during a streamed agent turn."""

    kind: str  # "thread" | "tool_start" | "tool_result" | "token" | "title" | "done"
    text: str | None = None
    tool: ToolEvent | None = None


@dataclass
class Conversation:
    """In-memory mirror of a persisted thread."""

    thread_id: str
    title: str = DEFAULT_TITLE
    messages: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_thread(cls, thread: Thread) -> Conversation:
        return cls(
            thread_id=thread.thread_id,
            title=thread.title,
            messages=[
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in thread.messages
            ],
        )

    def add_user(self, text: str, timestamp: str) -> dict[str, Any]:
        msg = {"role": "user", "content": text, "timestamp": timestamp}
        self.messages.append(msg)
        return msg

    def add_assistant(self, text: str, timestamp: str) -> dict[str, Any]:
        msg = {"role": "assistant", "content": text, "timestamp": timestamp}
        self.messages.append(msg)
        return msg

    def recent(self, n: int) -> list[dict[str, Any]]:
        # Strip the timestamp field — the LLM only needs role/content.
        return [
            {"role": m["role"], "content": m["content"]} for m in self.messages[-n:]
        ]


def _build_messages(conv: Conversation) -> list[dict[str, Any]]:
    vault = get_vault()
    system = render_system_prompt()
    bootstrap = render_bootstrap_context(vault)
    return [
        {"role": "system", "content": system},
        {"role": "system", "content": bootstrap},
        *conv.recent(settings.history_turns),
    ]


async def run_turn(conv: Conversation, user_message: str) -> AsyncIterator[TurnEvent]:
    """Drive one user→assistant exchange, yielding events for the UI.

    The loop alternates between non-streaming chat calls (which let us inspect
    `tool_calls`) and tool dispatch, then streams the final user-visible turn.
    Each user and assistant turn is appended to the thread file on disk.
    """
    vault = get_vault()
    user_ts = threads_mod.now_iso()
    conv.add_user(user_message, user_ts)
    threads_mod.append_message(
        vault, conv.thread_id, Message(role="user", content=user_message, timestamp=user_ts)
    )

    llm = get_llm()
    working_messages = _build_messages(conv)

    for _ in range(settings.max_tool_iterations):
        # Re-evaluate each iteration so the user can toggle a connector
        # off mid-conversation and have it take effect on the next call.
        schemas = tool_schemas()
        response = await llm.chat(messages=working_messages, tools=schemas)
        msg = response.get("message", {}) or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # No more tool use — stream the final answer with the same history.
            final_text = ""
            async for token in llm.chat_stream(messages=working_messages):
                final_text += token
                yield TurnEvent(kind="token", text=token)
            await _persist_assistant_turn(conv, final_text, user_message)
            async for ev in _maybe_generate_title(conv, user_message, final_text):
                yield ev
            yield TurnEvent(kind="done")
            return

        # Record the assistant's tool-call turn so subsequent calls see it.
        working_messages.append(
            {
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            }
        )

        for call in tool_calls:
            fn = call.get("function", {}) or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {}) or {}
            args = raw_args if isinstance(raw_args, dict) else _coerce_args(raw_args)

            tool_event = ToolEvent(name=name, arguments=args)
            yield TurnEvent(kind="tool_start", tool=tool_event)

            result_json = await dispatch(ToolCall(name=name, arguments=args))
            try:
                tool_event.result = json.loads(result_json)
            except json.JSONDecodeError:
                tool_event.result = {"raw": result_json}
            yield TurnEvent(kind="tool_result", tool=tool_event)

            working_messages.append(
                {"role": "tool", "name": name, "content": result_json}
            )

    log.warning("hit max_tool_iterations (%d); cutting loop", settings.max_tool_iterations)
    fallback = (
        "I hit the tool-use safety limit before reaching a final answer. "
        "Could you rephrase or give me a hint about what you're after?"
    )
    await _persist_assistant_turn(conv, fallback, user_message)
    yield TurnEvent(kind="token", text=fallback)
    yield TurnEvent(kind="done")


async def _persist_assistant_turn(
    conv: Conversation, text: str, _user_message: str
) -> None:
    ts = threads_mod.now_iso()
    conv.add_assistant(text, ts)
    threads_mod.append_message(
        get_vault(),
        conv.thread_id,
        Message(role="assistant", content=text, timestamp=ts),
    )


async def _maybe_generate_title(
    conv: Conversation, user_message: str, assistant_text: str
) -> AsyncIterator[TurnEvent]:
    """After the first user+assistant exchange, ask the LLM for a real title.

    Runs only on the very first exchange (message_count == 2). On subsequent
    turns the user keeps whatever title they have, including manual renames.
    """
    if len(conv.messages) != 2:
        return
    try:
        title = await generate_title(user_message, assistant_text)
    except Exception as exc:  # noqa: BLE001
        log.warning("title generation failed: %s", exc)
        return
    if not title:
        return
    conv.title = title
    # Reload from disk so we don't clobber messages persisted between turns.
    try:
        thread = load_thread(get_vault(), conv.thread_id)
        thread.title = title
        save_thread(get_vault(), thread)
    except FileNotFoundError:
        return
    yield TurnEvent(kind="title", text=title)


async def generate_title(user_message: str, assistant_text: str) -> str:
    """Ask the LLM for a short conversation title. Best-effort; trims punctuation."""
    prompt = (
        "Generate a short title (3-6 words) summarizing this conversation. "
        "Reply with only the title text — no quotes, no punctuation, no prefix.\n\n"
        f"User: {user_message[:600]}\n\nAssistant: {assistant_text[:600]}"
    )
    resp = await get_llm().chat(
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (resp.get("message", {}) or {}).get("content") or ""
    title = raw.strip().splitlines()[0] if raw.strip() else ""
    title = title.strip().strip('"').strip("'").strip("`").rstrip(".!?")
    return title[:80]


def _coerce_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


_conversations: dict[str, Conversation] = {}


def get_conversation(thread_id: str) -> Conversation:
    """Return the in-memory conversation for a thread, loading from disk if needed."""
    if thread_id in _conversations:
        return _conversations[thread_id]
    thread = load_thread(get_vault(), thread_id)
    conv = Conversation.from_thread(thread)
    _conversations[thread_id] = conv
    return conv


def ensure_thread(thread_id: str | None, first_message: str) -> Conversation:
    """Resolve a thread for an incoming chat request.

    - If `thread_id` is provided and exists, return its cached conversation.
    - If `thread_id` is None or missing on disk, create a new thread with a
      placeholder title and return its conversation.
    """
    vault = get_vault()
    if thread_id and thread_exists(vault, thread_id):
        return get_conversation(thread_id)
    thread = create_thread(
        vault,
        thread_id=thread_id if thread_id else None,
        title=placeholder_title(first_message),
    )
    conv = Conversation.from_thread(thread)
    _conversations[thread.thread_id] = conv
    return conv


def drop_conversation(thread_id: str) -> None:
    _conversations.pop(thread_id, None)


def reset_conversations() -> None:
    """Test helper: clear the in-memory cache."""
    _conversations.clear()
