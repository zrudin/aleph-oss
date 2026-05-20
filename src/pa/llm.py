"""Thin async wrapper around the Ollama HTTP API for chat + embeddings."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ollama import AsyncClient

from pa.config import settings


class LLM:
    def __init__(self, host: str | None = None) -> None:
        self._client = AsyncClient(host=host or settings.ollama_host)

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
        return await self._client.chat(
            model=model or settings.chat_model,
            messages=messages,
            tools=tools,
            options=options or {},
            stream=False,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the assistant's text content chunk by chunk."""
        stream = await self._client.chat(
            model=model or settings.chat_model,
            messages=messages,
            options=options or {},
            stream=True,
        )
        async for chunk in stream:
            content = chunk.get("message", {}).get("content")
            if content:
                yield content

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        resp = await self._client.embeddings(
            model=model or settings.embed_model,
            prompt=text,
        )
        return list(resp["embedding"])

    async def embed_many(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        # Ollama's /api/embeddings is single-prompt; loop for simplicity.
        return [await self.embed(t, model=model) for t in texts]


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
