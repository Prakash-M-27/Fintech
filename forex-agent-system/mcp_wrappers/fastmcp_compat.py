"""Small FastMCP-style compatibility shim over the mcp 2.x server API.

WHY this exists:
    The stub MCP servers are written against the familiar `FastMCP` API
    (`@mcp.tool()` decorator + `mcp.run()`). The installed official SDK is
    mcp 2.x, which renamed `FastMCP` to `MCPServer`. Rather than pinning to a
    legacy SDK or rewriting the servers, this module provides a tiny
    drop-in `FastMCP` that wraps `MCPServer`, so the server files stay clean,
    readable and valid against current and (largely) future SDK versions.

    This shim is only needed for the LOCAL stub servers. In production, the
    same wrapped `MCPClient` connects to whatever commercial MCP server the
    operator configures — it never assumes FastMCP on the far side.
"""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.mcpserver import MCPServer


class FastMCP:
    """Minimal FastMCP-compatible decorator/run wrapper over MCPServer."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._server = MCPServer(name=name)

    def tool(self, name: str | None = None, **kwargs: Any) -> Callable:
        """Decorator registering a tool with the underlying MCPServer."""

        def decorator(fn: Callable) -> Callable:
            self._server.add_tool(fn, name=name, **kwargs)
            return fn

        return decorator

    def run(self, *args: Any, **kwargs: Any) -> None:
        self._server.run(*args, **kwargs)
