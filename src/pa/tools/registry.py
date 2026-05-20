"""Tool registry: JSON schemas (for Ollama) + dispatch table (for the agent loop).

Built-in tools are static. MCP-provided tools are merged in at app startup once
the MCP manager has finished its handshake. The ToolGate filters tools whose
group is currently disabled — the model never sees a disabled tool, and a
dispatch attempt with one is rejected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pa.mcp import MCPManager, split_qualified
from pa.tool_gate import get_gate
from pa.tools import web_search

# Vault-dependent tools live behind a soft import: the `pa.vault` package is
# still being built out, and we want the agent (and its tests) to be able to
# load the registry — at least for the web/MCP tools — even when vault isn't
# importable yet.
try:
    from pa.tools import datetime_tool, files, reminders, search, threads_tool
    _HAS_VAULT_TOOLS = True
except ImportError:  # vault module not yet available
    _HAS_VAULT_TOOLS = False

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


ToolFn = Callable[..., Awaitable[Any]]

_TOOLS: dict[str, ToolFn] = {
    "web_search": web_search.web_search,
    "web_fetch": web_search.web_fetch,
}
if _HAS_VAULT_TOOLS:
    _TOOLS.update(
        {
            "list_files": files.list_files,
            "read_file": files.read_file,
            "write_file": files.write_file,
            "append_to_file": files.append_to_file,
            "update_section": files.update_section,
            "update_frontmatter": files.update_frontmatter,
            "semantic_search": search.semantic_search,
            "text_search": search.text_search,
            "list_reminders": reminders.list_reminders,
            "create_reminder": reminders.create_reminder,
            "complete_reminder": reminders.complete_reminder,
            "current_datetime": datetime_tool.current_datetime,
            "list_threads": threads_tool.list_threads,
            "read_thread": threads_tool.read_thread,
        }
    )


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_SCHEMAS: list[dict] = [
    _schema(
        "list_files",
        "List files and subdirectories inside the vault. Pass an empty string for the root.",
        {
            "directory": {
                "type": "string",
                "description": "Vault-relative directory, e.g. 'people' or ''.",
            }
        },
        [],
    ),
    _schema(
        "read_file",
        "Read a Markdown note from the vault.",
        {"path": {"type": "string", "description": "Vault-relative file path."}},
        ["path"],
    ),
    _schema(
        "write_file",
        "Create or replace a note. Use a template for new notes when one fits "
        "(profile, person, project, interest, journal). Replaces existing content "
        "fully — prefer append_to_file for additive edits.",
        {
            "path": {"type": "string", "description": "Vault-relative file path."},
            "content": {"type": "string", "description": "Markdown body."},
            "template": {
                "type": "string",
                "description": "Optional template name. Ignored if the file already exists.",
                "enum": ["profile", "person", "project", "interest", "journal"],
            },
        },
        ["path", "content"],
    ),
    _schema(
        "append_to_file",
        "Append content to the end of a note (creates the file if missing). "
        "Best for daily journal entries and adding interactions to a person note.",
        {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        ["path", "content"],
    ),
    _schema(
        "update_section",
        "Replace the body under a single Markdown heading in an existing note, "
        "leaving frontmatter and other sections untouched. Use this — not "
        "write_file — to edit one section of a longer note (e.g., the user's "
        "`## Current focus` in profile.md). Errors if the heading isn't there.",
        {
            "path": {"type": "string", "description": "Vault-relative file path."},
            "heading": {
                "type": "string",
                "description": (
                    "Heading text without leading '#'s, e.g. 'Current focus'. "
                    "Matches the first heading with this exact text at any level."
                ),
            },
            "new_body": {
                "type": "string",
                "description": (
                    "Replacement body for the section (no heading line). May be "
                    "empty to clear the section."
                ),
            },
        },
        ["path", "heading", "new_body"],
    ),
    _schema(
        "update_frontmatter",
        "Set a single YAML frontmatter key on an existing note (e.g., "
        "`last_contact`, `cadence_weeks`, `status`, `tags`). Body is preserved "
        "verbatim. Use this — not write_file — for durable structured fields.",
        {
            "path": {"type": "string", "description": "Vault-relative file path."},
            "key": {"type": "string", "description": "Frontmatter key, e.g. 'last_contact'."},
            "value": {
                "type": ["string", "number", "boolean", "null", "array"],
                "description": (
                    "New value. Use an ISO date string for dates (e.g. "
                    "'2026-05-19'); a number for counts; a JSON array for tags."
                ),
            },
        },
        ["path", "key", "value"],
    ),
    _schema(
        "semantic_search",
        "Search vault notes by meaning using local embeddings. Returns top-k chunks.",
        {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "How many hits.", "default": 5},
        },
        ["query"],
    ),
    _schema(
        "text_search",
        "Exact / regex text search across vault notes. Use when you know a phrase "
        "or proper noun and want every occurrence.",
        {
            "pattern": {"type": "string", "description": "Python regex (case-insensitive)."},
            "directory": {
                "type": "string",
                "description": "Vault-relative subdirectory to scope the search.",
            },
        },
        ["pattern"],
    ),
    _schema(
        "list_reminders",
        "List current open reminders (the checkbox list at reminders/active.md).",
        {"filter": {"type": "string", "description": "Optional substring filter."}},
        [],
    ),
    _schema(
        "create_reminder",
        "Add a new open reminder.",
        {
            "text": {"type": "string"},
            "due": {"type": "string", "description": "Optional ISO date or free-form."},
        },
        ["text"],
    ),
    _schema(
        "complete_reminder",
        "Mark a reminder complete and move it to the archive. Matches by substring.",
        {"text": {"type": "string", "description": "Substring of the reminder to complete."}},
        ["text"],
    ),
    _schema(
        "current_datetime",
        "Get the current local date, weekday, and timezone.",
        {},
        [],
    ),
    _schema(
        "list_threads",
        "List recent chat threads with the user, sorted by most recent activity. "
        "Use to find past conversations by title/timestamp before calling read_thread.",
        {
            "limit": {
                "type": "integer",
                "description": "Maximum threads to return (default 20).",
                "default": 20,
            }
        },
        [],
    ),
    _schema(
        "read_thread",
        "Read the full content of a past chat thread by id. Returns all messages "
        "with timestamps. Use after list_threads to look up what was discussed.",
        {
            "thread_id": {
                "type": "string",
                "description": "Thread id from list_threads (32-char hex).",
            }
        },
        ["thread_id"],
    ),
    _schema(
        "web_search",
        "Search the public web via DuckDuckGo. Use for questions about current events, "
        "external facts, or anything not in the vault. Never include vault content in queries.",
        {
            "query": {"type": "string", "description": "Search query in natural language."},
            "max_results": {"type": "integer", "description": "1–10, default 5.", "default": 5},
        },
        ["query"],
    ),
    _schema(
        "web_fetch",
        "Download a public web page and return its main text (no JS execution). "
        "Use after web_search to read a result in detail. Only http(s) URLs on public hosts.",
        {
            "url": {"type": "string", "description": "Full http(s) URL."},
            "max_chars": {
                "type": "integer",
                "description": "Truncate text to this length.",
                "default": 20000,
            },
        },
        ["url"],
    ),
]


_mcp_manager: MCPManager | None = None


def set_mcp_manager(manager: MCPManager | None) -> None:
    """Wire (or unwire) the MCP manager that supplies extra tool schemas."""
    global _mcp_manager
    _mcp_manager = manager


def tool_schemas() -> list[dict]:
    """All currently-allowed tool schemas, filtered by the gate.

    Drops static schemas for tools that didn't actually load (e.g., vault tools
    while `pa.vault` isn't yet implemented).
    """
    gate = get_gate()
    schemas = [s for s in _SCHEMAS if s["function"]["name"] in _TOOLS]
    if _mcp_manager is not None:
        schemas.extend(_mcp_manager.tool_schemas())
    return gate.filter_schemas(schemas)


async def dispatch(call: ToolCall) -> str:
    """Run a tool and return its result as a JSON string (Ollama tool-result form)."""
    gate = get_gate()
    if not gate.is_tool_allowed(call.name):
        return json.dumps(
            {"error": f"tool {call.name!r} is currently disabled by the user toggle"}
        )

    fn = _TOOLS.get(call.name)
    if fn is not None:
        try:
            result = await fn(**call.arguments)
        except TypeError as exc:
            return json.dumps({"error": f"bad arguments: {exc}"})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    # MCP-provided tool?
    if _mcp_manager is not None and split_qualified(call.name):
        try:
            result = await _mcp_manager.call_tool(call.name, call.arguments)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    return json.dumps({"error": f"unknown tool: {call.name}"})
