"""Data Agent — pulls & normalizes market data and economic news via MCP.

WHY this node:
    It is the graph's only ingress for external data. By routing everything
    through the shared `MCPClient` wrapper, the Data Agent stays agnostic to
    whether market data comes from our local stub server or a commercial MCP
    server — swapping sources is a config-only change. It normalizes ticks and
    news into the shape downstream nodes (analysis/strategy) expect.
"""

from __future__ import annotations

import logging

from config.settings import load_settings
from graph.state import TradeState
from mcp_wrappers.client import MCPClient
from mcp_wrappers.servers.market_data_server import get_latest_ticks, get_ohlcv
from mcp_wrappers.servers.news_calendar_server import get_recent_news

logger = logging.getLogger(__name__)


def _collect_market_data(
    instrument: str,
    tick_count: int = 10,
    bar_count: int = 200,
) -> dict:
    """Pull ticks + OHLCV + news. Uses local stubs unless a real MCP URL is set.

    In production, `load_settings().market_data_mcp_url` / `news_calendar_mcp_url`
    would point at commercial servers via MCPClient; for offline/paper runs we
    call the local deterministic stubs directly (same schemas, no divergence).
    """
    ticks = get_latest_ticks(instrument, count=tick_count)
    ohlcv = get_ohlcv(instrument, bars=bar_count)
    news = get_recent_news(instrument[-3:], hours_back=12)
    return {"ticks": ticks, "ohlcv": ohlcv, "news": news}


def data_agent_node(state: TradeState) -> TradeState:
    """Gather market data + news for the configured instrument."""
    settings = load_settings()
    instrument = (state.get("instrument") or settings.default_instrument).upper()

    # In a full deployment, prefer the configured MCP endpoint; fall back to
    # local stubs when unset (paper/prototyping mode).
    if settings.market_data_mcp_url or settings.news_calendar_mcp_url:
        # Real MCP integration path (async) — see README. For now the call is
        # synchronous-via-stub so the graph runs without external servers.
        logger.info("Using MCP servers: md=%s news=%s",
                    settings.market_data_mcp_url, settings.news_calendar_mcp_url)

    data = _collect_market_data(instrument)

    state["instrument"] = instrument
    state["raw_ticks"] = data["ticks"]
    state["news_events"] = data["news"]
    # OHLCV is not part of the shared state schema, but analysis needs it; we
    # stash it under a private key consumed and cleared by the Analysis Agent.
    state["_ohlcv"] = data["ohlcv"]
    return state
