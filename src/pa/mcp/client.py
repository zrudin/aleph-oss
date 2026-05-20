"""Thin MCP stdio client wrapper.

We spawn each external MCP server as a subprocess, hold its session open for
the life of the FastAPI app, and expose its tools to the agent under a
namespaced name like ``notion__search`` so they can't collide with built-ins.

Imports of the `mcp` SDK are lazy so the rest of the package stays importable
even if mcp isn't installed (useful in tests and in CI without a Node runtime).
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

_NAMESPACE_SEP = "__"


def qualified_name(server: str, tool: str) -> str:
    return f"{server}{_NAMESPACE_SEP}{tool}"


def split_qualified(name: str) -> tuple[str, str] | None:
    if _NAMESPACE_SEP not in name:
        return None
    server, _, tool = name.partition(_NAMESPACE_SEP)
    if not server or not tool:
        return None
    return server, tool


@dataclass
class MCPServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class _LiveServer:
    spec: MCPServer
    session: Any  # mcp.ClientSession
    tools: list[dict]  # OpenAI/Ollama-shaped schemas


class MCPManager:
    """Owns spawned MCP servers for the app's lifetime."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._servers: dict[str, _LiveServer] = {}
        self._started = False

    async def start(self, servers: list[MCPServer]) -> None:
        if self._started:
            return
        self._started = True
        for spec in servers:
            try:
                await self._spawn(spec)
            except Exception as exc:  # noqa: BLE001
                log.warning("MCP server %r failed to start: %s", spec.name, exc)

    async def _spawn(self, spec: MCPServer) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env)
        transport = await self._stack.enter_async_context(stdio_client(params))
        read, write = transport
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listing = await session.list_tools()
        schemas: list[dict] = []
        for tool in listing.tools:
            schemas.append(_to_function_schema(spec.name, tool))
        self._servers[spec.name] = _LiveServer(spec=spec, session=session, tools=schemas)
        log.info("MCP server %r ready (%d tools)", spec.name, len(schemas))

    def server_names(self) -> list[str]:
        return list(self._servers.keys())

    def tool_schemas(self) -> list[dict]:
        out: list[dict] = []
        for live in self._servers.values():
            out.extend(live.tools)
        return out

    async def call_tool(self, qname: str, arguments: dict) -> Any:
        parts = split_qualified(qname)
        if parts is None:
            raise ValueError(f"not a namespaced MCP tool name: {qname!r}")
        server, tool = parts
        live = self._servers.get(server)
        if live is None:
            raise ValueError(f"unknown MCP server: {server!r}")
        result = await live.session.call_tool(tool, arguments)
        return _flatten_result(result)

    async def stop(self) -> None:
        if not self._started:
            return
        await self._stack.aclose()
        self._servers.clear()
        self._started = False


def _to_function_schema(server: str, tool: Any) -> dict:
    """Convert an mcp.types.Tool into the Ollama/OpenAI function-call schema."""
    schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": qualified_name(server, tool.name),
            "description": getattr(tool, "description", "") or "",
            "parameters": schema,
        },
    }


def _flatten_result(result: Any) -> Any:
    """Collapse an mcp.types.CallToolResult into plain Python the agent can JSON-serialize."""
    is_error = getattr(result, "isError", False)
    content = getattr(result, "content", None) or []
    pieces: list[str] = []
    structured: list[Any] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            pieces.append(text)
            continue
        data = getattr(item, "data", None)
        if data is not None:
            structured.append({"type": getattr(item, "type", "data"), "data": "<omitted-binary>"})
    payload: dict[str, Any] = {}
    if pieces:
        payload["text"] = "\n".join(pieces)
    if structured:
        payload["attachments"] = structured
    if is_error:
        payload["error"] = True
    return payload or {"text": ""}
