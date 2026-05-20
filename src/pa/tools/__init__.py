"""Tools the agent can call.

Each tool is a plain async function. `registry.py` wires them up with the JSON
schemas Ollama needs and the dispatch table used by the agent loop.
"""

from pa.tools.registry import ToolCall, dispatch, tool_schemas

__all__ = ["ToolCall", "dispatch", "tool_schemas"]
