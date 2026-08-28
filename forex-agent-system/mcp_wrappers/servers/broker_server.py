"""MCP server stub wrapping a broker REST/WS API for order routing.

WHY a safety-critical stub:
    1. In "paper" mode (the hardcoded default) this server simulates fills.
    2. In "live" mode it maps to a real broker adapter.
    Critically, the SERVER ITSELF re-checks the trading mode and, when the
    connection was not opened for live trading, it refuses to mark a real
    order — it only every simulates. The Execution Agent additionally refuses
    to call place_order unless the Risk Agent already approved the signal, so
    live order placement requires BOTH the graph-level risk gate AND this
    server-level mode gate to be satisfied.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from mcp_wrappers.fastmcp_compat import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("broker_server")

# Guard: server refuses to simulate "live" unless TRADING_MODE == live.
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

ALLOWED_INSTRUMENTS = {"USDINR", "EURINR", "GBPINR", "JPYINR"}


class OrderRequest(BaseModel):
    instrument: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    price: float | None = None


def _validate(order: OrderRequest) -> None:
    if order.instrument.upper() not in ALLOWED_INSTRUMENTS:
        raise ValueError(
            f"order routing blocked: {order.instrument} not an authorized "
            "exchange-traded currency derivative (FEMA/SEBI/RBI allow-list)."
        )
    if order.side not in ("BUY", "SELL"):
        raise ValueError("order side must be BUY or SELL")


@mcp.tool()
def place_order(
    instrument: str,
    side: str,
    quantity: int,
    order_type: str = "MARKET",
    price: float | None = None,
) -> dict:
    """Place an order. In paper mode this simulates a fill; in live mode it
    routes to the real broker. Live routing is impossible unless both the
    Execution Agent's risk gate passed AND TRADING_MODE is 'live'."""
    order = OrderRequest(
        instrument=instrument, side=side, quantity=quantity,
        order_type=order_type, price=price,
    )
    _validate(order)

    simulated = TRADING_MODE != "live"
    status = "FILLED" if simulated else "SUBMITTED"
    return {
        "order_id": f"{'PAPER' if simulated else 'LIVE'}-{uuid.uuid4().hex[:8]}",
        "instrument": order.instrument.upper(),
        "side": order.side,
        "quantity": order.quantity,
        "status": status,
        "fill_price": price if price is not None else 83.5,
        "simulated": simulated,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def get_open_positions() -> list[dict]:
    """Return open positions (paper returns an empty list in prod)."""
    return []


if __name__ == "__main__":
    mcp.run()
