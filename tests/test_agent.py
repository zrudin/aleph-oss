"""Agent loop with a mocked LLM. Verifies tool dispatch, history, and exit."""

from __future__ import annotations

from typing import Any

import pytest

import pa.agent as agent_mod
import pa.llm as llm_mod
from pa.threads import list_threads, load_thread


class FakeLLM:
    """Programmable Ollama replacement.

    `chat_responses` is a list of dicts in Ollama's `response` shape; the loop
    consumes them in order. `stream_text` is yielded by `chat_stream` at the end.
    Any extra `chat` calls (e.g. title generation) get a canned empty response
    so the loop doesn't crash.
    """

    def __init__(self, chat_responses: list[dict[str, Any]], stream_text: str = "ok") -> None:
        self._responses = list(chat_responses)
        self._stream_text = stream_text
        self.chat_calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools=None, model=None, options=None):
        self.chat_calls.append(list(messages))
        if not self._responses:
            return {"message": {"content": "Generated title", "tool_calls": []}}
        return self._responses.pop(0)

    async def chat_stream(self, messages, model=None, options=None):
        for ch in self._stream_text:
            yield ch

    async def embed(self, text, model=None):
        return [0.0] * 8


@pytest.mark.asyncio
async def test_agent_dispatches_tool_then_streams_final(temp_vault, monkeypatch):
    fake = FakeLLM(
        chat_responses=[
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "list_files",
                                "arguments": {"directory": ""},
                            }
                        }
                    ],
                }
            },
            {"message": {"content": "", "tool_calls": []}},
        ],
        stream_text="Here is what I found.",
    )

    monkeypatch.setattr(llm_mod, "_llm", fake)
    agent_mod.reset_conversations()

    conv = agent_mod.ensure_thread(None, "what's in the vault?")
    events = []
    async for ev in agent_mod.run_turn(conv, "what's in the vault?"):
        events.append(ev)

    kinds = [e.kind for e in events]
    assert "tool_start" in kinds
    assert "tool_result" in kinds
    assert "done" in kinds
    tokens = "".join(e.text for e in events if e.kind == "token" and e.text)
    assert tokens == "Here is what I found."

    assert conv.messages[-2]["role"] == "user"
    assert conv.messages[-1]["role"] == "assistant"
    assert conv.messages[-1]["content"] == "Here is what I found."

    # The turn was persisted to disk.
    reloaded = load_thread(temp_vault, conv.thread_id)
    assert len(reloaded.messages) == 2
    assert reloaded.messages[0].role == "user"
    assert reloaded.messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_agent_handles_no_tool_call(temp_vault, monkeypatch):
    fake = FakeLLM(
        chat_responses=[{"message": {"content": "", "tool_calls": []}}],
        stream_text="hi.",
    )
    monkeypatch.setattr(llm_mod, "_llm", fake)
    agent_mod.reset_conversations()

    conv = agent_mod.ensure_thread(None, "hi")
    events = [e async for e in agent_mod.run_turn(conv, "hi")]
    assert events[-1].kind == "done"
    assert any(e.kind == "token" for e in events)


@pytest.mark.asyncio
async def test_agent_generates_title_after_first_exchange(temp_vault, monkeypatch):
    fake = FakeLLM(
        chat_responses=[{"message": {"content": "", "tool_calls": []}}],
        stream_text="Sure, here is the plan.",
    )
    monkeypatch.setattr(llm_mod, "_llm", fake)
    agent_mod.reset_conversations()

    conv = agent_mod.ensure_thread(None, "Plan my week")
    events = [e async for e in agent_mod.run_turn(conv, "Plan my week")]

    title_events = [e for e in events if e.kind == "title"]
    assert title_events, "expected a title event after first exchange"
    assert title_events[0].text == "Generated title"

    reloaded = load_thread(temp_vault, conv.thread_id)
    assert reloaded.title == "Generated title"


@pytest.mark.asyncio
async def test_agent_reuses_existing_thread(temp_vault, monkeypatch):
    fake = FakeLLM(
        chat_responses=[
            {"message": {"content": "", "tool_calls": []}},
            {"message": {"content": "", "tool_calls": []}},
        ],
        stream_text="ack",
    )
    monkeypatch.setattr(llm_mod, "_llm", fake)
    agent_mod.reset_conversations()

    conv = agent_mod.ensure_thread(None, "first")
    async for _ in agent_mod.run_turn(conv, "first"):
        pass

    same = agent_mod.ensure_thread(conv.thread_id, "second")
    assert same.thread_id == conv.thread_id
    async for _ in agent_mod.run_turn(same, "second"):
        pass

    summaries = list_threads(temp_vault)
    assert len(summaries) == 1
    assert summaries[0].message_count == 4
