"""Thin async wrapper around the Ollama HTTP API for chat + embeddings."""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from ollama import AsyncClient

from pa.config import settings

log = logging.getLogger("pa.llm")

# Monotonic per-process call counter so log lines can be paired across the
# request/response boundary (e.g., "chat #17 start" → "chat #17 done").
_call_seq = itertools.count(1)


class LLM:
    def __init__(self, host: str | None = None) -> None:
        self._host = host or settings.ollama_host
        self._client = AsyncClient(host=self._host)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn. Returns Ollama's response dict.

        Used inside the tool-call loop where we need the structured `tool_calls`
        field. We only stream the final user-visible message (see `chat_stream`).
        """
        call_id = next(_call_seq)
        model_name = model or settings.chat_model
        log.info(
            "chat #%d start model=%s messages=%d tools=%d",
            call_id, model_name, len(messages), len(tools or []),
        )
        t0 = time.monotonic()
        try:
            resp = await self._client.chat(
                model=model_name,
                messages=messages,
                tools=tools,
                options=options or {},
                stream=False,
            )
        except Exception as exc:
            log.warning(
                "chat #%d FAILED after %.1fs: %s: %s",
                call_id, time.monotonic() - t0, type(exc).__name__, exc,
            )
            raise
        elapsed = time.monotonic() - t0
        msg = resp.get("message", {}) or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []
        log.info(
            "chat #%d done in %.1fs content=%dch tool_calls=%d",
            call_id, elapsed, len(content), len(tool_calls),
        )
        if not content and not tool_calls:
            # Empty response with no tool call — usually a model/tools mismatch
            # or a sampling collapse. Surface loudly because the agent loop will
            # then fall through to a streaming call that may also be empty.
            log.warning("chat #%d returned empty content and no tool_calls", call_id)
        return resp

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the assistant's text content chunk by chunk."""
        call_id = next(_call_seq)
        model_name = model or settings.chat_model
        log.info(
            "chat_stream #%d start model=%s messages=%d",
            call_id, model_name, len(messages),
        )
        t0 = time.monotonic()
        first_chunk_at: float | None = None
        chars = 0
        chunks = 0
        try:
            stream = await self._client.chat(
                model=model_name,
                messages=messages,
                options=options or {},
                stream=True,
            )
            async for chunk in stream:
                content = chunk.get("message", {}).get("content")
                if content:
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic() - t0
                        log.info(
                            "chat_stream #%d first chunk at %.1fs",
                            call_id, first_chunk_at,
                        )
                    chunks += 1
                    chars += len(content)
                    yield content
        except Exception as exc:
            log.warning(
                "chat_stream #%d FAILED after %.1fs (chunks=%d chars=%d): %s: %s",
                call_id, time.monotonic() - t0, chunks, chars, type(exc).__name__, exc,
            )
            raise
        log.info(
            "chat_stream #%d done in %.1fs chunks=%d chars=%d",
            call_id, time.monotonic() - t0, chunks, chars,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        resp = await self._client.embeddings(
            model=model or settings.embed_model,
            prompt=text,
        )
        return list(resp["embedding"])

    async def embed_many(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        # Ollama's /api/embeddings is single-prompt; loop for simplicity.
        return [await self.embed(t, model=model) for t in texts]

    async def list_models(self) -> Any:
        """Whatever `ollama list` returns — a ListResponse (ollama>=0.4) or dict."""
        return await self._client.list()

    async def running_models(self) -> Any:
        """Whatever `ollama ps` returns — currently loaded models."""
        return await self._client.ps()

    @property
    def host(self) -> str:
        return self._host


def installed_model_names(listed: Any) -> list[str]:
    """Extract model names from whatever shape `ollama.list()` returned.

    ollama>=0.4 returns a `ListResponse` (pydantic) with `.models: list[Model]`,
    where each `Model` exposes the name via `.model`. Older versions / mocks
    return a dict with `"models"` containing dicts that use either the `"model"`
    or `"name"` key. Walk both paths defensively.
    """
    models = getattr(listed, "models", None)
    if models is None and isinstance(listed, dict):
        models = listed.get("models")
    if not models:
        return []
    names: list[str] = []
    for entry in models:
        name = getattr(entry, "model", None) or getattr(entry, "name", None)
        if not name and isinstance(entry, dict):
            name = entry.get("model") or entry.get("name")
        if name:
            names.append(str(name))
    return names


def model_installed(required: str, installed: set[str] | list[str]) -> bool:
    """Whether `required` is in `installed`, treating bare names as `:latest`.

    Ollama appends `:latest` when a model is pulled without an explicit tag,
    so `nomic-embed-text` and `nomic-embed-text:latest` are the same model.
    """
    pool = installed if isinstance(installed, set) else set(installed)
    if required in pool:
        return True
    return ":" not in required and f"{required}:latest" in pool


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
