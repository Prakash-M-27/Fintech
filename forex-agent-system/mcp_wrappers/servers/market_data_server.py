"""MCP server stub exposing tick / OHLCV market-data tools.

WHY a stub server:
    It lets the full graph run end-to-end with deterministic, offline data so
    we can validate wiring, rules and risk behavior *before* pointing the same
    client at a real (broker/vendor) market-data MCP server. The tool names and
    Pydantic schemas are the contract — production servers keep them identical
    so the Data Agent's code never changes.

Run with:  PYTHONPATH=. python -m mcp_wrappers.servers.market_data_server
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from mcp_wrappers.fastmcp_compat import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("market_data_server")

ALLOWED_INSTRUMENTS = {"USDINR", "EURINR", "GBPINR", "JPYINR"}


class Tick(BaseModel):
    ts: str = Field(description="ISO-8601 timestamp")
    bid: float
    ask: float
    spread_pips: float = Field(gt=0)


class OhlcvBar(BaseModel):
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def _rand_price(base: float) -> float:
    return round(base + random.uniform(-0.05, 0.05), 4)


def _validate_instrument(instrument: str) -> None:
    if instrument.upper() not in ALLOWED_INSTRUMENTS:
        raise ValueError(
            f"instrument '{instrument}' not in allowed set {sorted(ALLOWED_INSTRUMENTS)}"
        )


@mcp.tool()
def get_latest_ticks(instrument: str, count: int = 5) -> list[dict]:
    """Return the `count` most recent ticks for an allowed instrument."""
    _validate_instrument(instrument)
    base = {"USDINR": 83.5, "EURINR": 90.2, "GBPINR": 105.4, "JPYINR": 0.56}[
        instrument.upper()
    ]
    now = datetime.now(timezone.utc)
    ticks: list[dict] = []
    for i in range(count):
        bid = _rand_price(base)
        spread = round(random.uniform(0.5, 1.8), 1)
        ticks.append(
            Tick(
                ts=(now - timedelta(seconds=15 * i)).isoformat(),
                bid=bid,
                ask=round(bid + spread / 1000, 4),
                spread_pips=spread,
            ).model_dump()
        )
    return ticks


@mcp.tool()
def get_ohlcv(instrument: str, bars: int = 200, period: str = "1d") -> list[dict]:
    """Return OHLCV bars (random-walk) for an allowed instrument."""
    _validate_instrument(instrument)
    base = {"USDINR": 83.5, "EURINR": 90.2, "GBPINR": 105.4, "JPYINR": 0.56}[
        instrument.upper()
    ]
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    price = base
    for i in range(bars):
        drift = random.uniform(-0.15, 0.15)
        open_ = price
        close = round(open_ + drift, 4)
        high = round(max(open_, close) + random.uniform(0, 0.1), 4)
        low = round(min(open_, close) - random.uniform(0, 0.1), 4)
        out.append(
            OhlcvBar(
                ts=(now - timedelta(days=i)).isoformat(),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=random.randint(1000, 100000),
            ).model_dump()
        )
        price = close
    return out


if __name__ == "__main__":
    mcp.run()
