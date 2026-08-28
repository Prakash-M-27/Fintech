"""
Background task that generates live-updating synthetic prices
for Indian indices (nifty, banknifty, sensex) and emits via Socket.IO.
"""

import asyncio
import logging
import random
import time
from datetime import datetime

from socket_manager import emit_market_update

logger = logging.getLogger(__name__)

SYMBOLS = {
    "nifty": {"price": 26800, "min": 24150, "max": 29500, "vol": 0.0008, "mr": 0.003},
    "banknifty": {"price": 54000, "min": 48000, "max": 62000, "vol": 0.001, "mr": 0.003},
    "sensex": {"price": 88500, "min": 79000, "max": 98000, "vol": 0.0007, "mr": 0.003},
}

INTERVAL = 1.5


async def _tick(symbol: str, cfg: dict) -> None:
    mid = (cfg["min"] + cfg["max"]) / 2
    drift = cfg["mr"] * (mid - cfg["price"]) / mid
    noise = random.gauss(0, cfg["vol"])
    pct = drift + noise

    old_price = cfg["price"]
    new_price = old_price * (1 + pct)
    new_price = max(cfg["min"], min(cfg["max"], new_price))
    cfg["price"] = new_price

    change = new_price - old_price
    change_pct = (change / old_price) * 100

    await emit_market_update("market_update", {
        "asset": symbol,
        "price": round(new_price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 4),
        "volume": random.randint(50, 300),
        "timestamp": datetime.now().isoformat() + "Z",
        "cached": False,
    })


async def run_synthetic_price_loop() -> None:
    """Continuously emit synthetic price ticks every INTERVAL seconds."""
    logger.info("Synthetic price loop started (interval=%.1fs)", INTERVAL)
    while True:
        start = time.monotonic()
        tasks = [_tick(sym, cfg) for sym, cfg in SYMBOLS.items()]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start
        sleep_time = max(0, INTERVAL - elapsed)
        await asyncio.sleep(sleep_time)
