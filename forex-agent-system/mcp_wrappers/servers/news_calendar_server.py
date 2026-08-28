"""MCP server stub exposing economic-calendar / news tools.

WHY this server:
    Provides the news/calendar input used by the Analysis Agent's sentiment
    step. Offline deterministic stubs let the graph run before a real news
    feed (e.g. a vendor's MCP news server) is wired in. The Analysis Agent
    only consumes the exported schema, so the source can be swapped freely.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mcp_wrappers.fastmcp_compat import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("news_calendar_server")


class NewsItem(BaseModel):
    id: str
    ts: str
    headline: str
    summary: str
    impact: str = Field(pattern="^(high|medium|low)$")
    currency: str


@mcp.tool()
def get_upcoming_events(hours_ahead: int = 24) -> list[dict]:
    """Return high-impact economic events in the next `hours_ahead` hours."""
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "evt-rbi-rate",
            "ts": (now + timedelta(hours=6)).isoformat(),
            "headline": "RBI Monetary Policy Decision",
            "summary": "Reserve Bank of India announces policy rate decision.",
            "impact": "high",
            "currency": "INR",
        },
        {
            "id": "evt-cpi",
            "ts": (now + timedelta(hours=18)).isoformat(),
            "headline": "US CPI Inflation Report",
            "summary": "US consumer price index release; USD volatility expected.",
            "impact": "high",
            "currency": "USD",
        },
    ]


@mcp.tool()
def get_recent_news(currency: str, hours_back: int = 12) -> list[dict]:
    """Return recent headlines for a currency (used for sentiment scoring)."""
    items = [
        NewsItem(
            id="n1",
            ts=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            headline="Rupee strengthens on expected RBI rate cut",
            summary="Traders position for easing; INR support near multi-year high.",
            impact="high",
            currency="INR",
        ),
        NewsItem(
            id="n2",
            ts=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            headline="USD pressured as rate-cut odds rise",
            summary="Market prices higher probability of near-term Fed easing.",
            impact="medium",
            currency="USD",
        ),
    ]
    return [n.model_dump() for n in items if n.currency.upper() == currency.upper()]


if __name__ == "__main__":
    mcp.run()
