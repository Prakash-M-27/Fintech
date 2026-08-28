"""Local MCP connectivity package.

NOTE ON PACKAGE NAME (engineering decision):
    The official MCP SDK exposes *subpackages* named `mcp.client` and
    `mcp.server`. The original spec asked for local files `mcp/client.py` and
    `mcp/servers/` — but those names directly collide with the SDK's own
    `mcp.client` / `mcp.server` subpackages and break its internal imports
    (e.g. `from mcp.client._input_required import ...` resolving to our file).

    To keep the official SDK usable (a hard requirement — this wrapper wraps
    the SDK), this package is named `mcp_wrappers`. The files are otherwise
    identical to the spec (`client.py`, `servers/market_data_server.py`,
    `servers/news_calendar_server.py`, `servers/broker_server.py`). This is a
    documented, deliberate deviation to avoid a namespace collision.
"""

from mcp_wrappers.client import MCPClient, MCPClientError  # noqa: F401

__all__ = ["MCPClient", "MCPClientError"]
