import asyncio
import logging
from datetime import datetime

import httpx

from pipeline import price_handler

logger = logging.getLogger(__name__)

NIFTY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
NIFTY_POLL_INTERVAL = 5


async def fetch_nifty() -> dict | None:
    params = {"range": "1d", "interval": "1m"}
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        resp = await client.get(NIFTY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        change = round(price - prev, 2) if prev else None
        change_pct = round((price - prev) / prev * 100, 3) if prev else None
        return {
            "price": float(price),
            "change": change,
            "change_pct": change_pct,
            "volume": meta.get("regularMarketVolume"),
            "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", 0)).isoformat() + "Z",
        }


async def poll_nifty_loop() -> None:
    while True:
        try:
            data = await fetch_nifty()
            if not data:
                continue
            payload = {
                "asset": "nifty",
                "price": data["price"],
                "change": data.get("change"),
                "change_pct": data.get("change_pct"),
                "volume": data.get("volume"),
                "timestamp": data.get("timestamp", datetime.now().isoformat() + "Z"),
                "meta": {"source": "yahoo-finance", "symbol": "^NSEI"},
            }
            await price_handler("nifty", payload)
            logger.info("NIFTY updated: %s", data["price"])
        except Exception as exc:
            logger.warning("NIFTY poll failed: %s", exc)
        await asyncio.sleep(NIFTY_POLL_INTERVAL)