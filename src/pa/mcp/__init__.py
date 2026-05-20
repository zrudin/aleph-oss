"""MCP client: spawn external MCP servers, expose their tools to the agent."""

from pa.mcp.client import MCPManager, MCPServer, qualified_name, split_qualified

__all__ = ["MCPManager", "MCPServer", "qualified_name", "split_qualified"]
