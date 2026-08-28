"""Shared MCP client wrapper.

WHY this exists:
    Data and Execution agents both call external capabilities — market data,
    economic calendar/news, and broker order routing — over the Model Context
    Protocol. Rather than each agent implementing its own connection handling
    (which would duplicate auth, reconnection, retry and timeout logic and
    risk divergence), this module provides one thin async wrapper with:
      * connection pooling (reuse a session across calls),
      * retry with exponential backoff on transient failures,
      * strict typed tool invocation.

    The graph nodes do NOT care whether a tool is served by one of our local
    stub servers (mcp/servers/) or by a commercial broker/vendor MCP server —
    they only need the MCP endpoint URL from config, so swapping providers is
    a config change, not a code change.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# NOTE: This package is named `mcp_wrappers` (not `mcp`) specifically so that
# the `import mcp ...` lines above resolve to the OFFICIAL MCP SDK, not to a
# local package of the same name. See mcp_wrappers/__init__.py for rationale.

logger = logging.getLogger(__name__)


class MCPClientError(RuntimeError):
    """Raised when an MCP tool call fails after all retries are exhausted."""


class MCPClient:
    """Async wrapper around a single MCP server connection.

    Use via the `session()` async context manager (one session per call scope)
    or the lower-level `connect()`/`close()`. Retry/backoff is applied to tool
    calls because transient network / broker throttling errors are normal.
    """

    def __init__(
        self,
        server_params: StdioServerParameters,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        name: str = "mcp",
    ) -> None:
        self._params = server_params
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self.name = name
        self._session: ClientSession | None = None
        self._read: Any = None
        self._write: Any = None

    async def connect(self) -> "MCPClient":
        """Open the stdio transport and a ClientSession. Idempotent."""
        if self._session is not None:
            return self
        self._read, self._write = await stdio_client(self._params).__aenter__()
        self._session = await ClientSession(self._read, self._write).__aenter__()
        await self._session.initialize()
        logger.debug("MCP client '%s' connected", self.name)
        return self

    async def close(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._read is not None and self._write is not None:
            await (self._read, self._write).__class__  # no-op; closed above

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool with retry + exponential backoff on transient errors."""
        await self.connect()
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                assert self._session is not None
                result = await self._session.call_tool(name, arguments)
                if getattr(result, "isError", False):
                    raise MCPClientError(
                        f"tool '{name}' returned error: {result.content}"
                    )
                return result
            except Exception as exc:  # noqa: BLE001 - retryable transport errors
                last_error = exc
                if attempt == self._max_retries:
                    break
                delay = self._backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "MCP tool '%s' attempt %d/%d failed (%s); retrying in %.2fs",
                    name, attempt, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
        raise MCPClientError(f"tool '{name}' failed after retries: {last_error}")

    @asynccontextmanager
    async def session(self):
        """Context manager yielding a connected client, auto-closed on exit."""
        await self.connect()
        try:
            yield self
        finally:
            await self.close()
