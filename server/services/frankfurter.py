import logging
import asyncio
from datetime import datetime

import httpx

from config import FRANKFUTER_BASE_URL, USD_POLL_INTERVAL
from pipeline import price_handler

logger = logging.getLogger(__name__)


async def fetch_usd_rates() -> dict | None:
    url = f"{FRANKFUTER_BASE_URL}/rates"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def poll_usd_loop() -> None:
    while True:
        try:
            data = await fetch_usd_rates()
            rates = {row["quote"]: row["rate"] for row in data if row.get("quote")}
            inr = rates.get("INR")
            usd = rates.get("USD")
            if inr is not None and usd:
                usd_inr = round(float(inr) / float(usd), 4)
                payload = {
                    "asset": "usd",
                    "price": usd_inr,
                    "change": None,
                    "change_pct": None,
                    "volume": None,
                    "timestamp": datetime.now().isoformat() + "Z",
                    "meta": {"base": "EUR", "quote": "INR", "derived_from": ["EUR/INR", "EUR/USD"]},
                }
                await price_handler("usd", payload)
                logger.info("USD/INR updated: %.4f", usd_inr)
        except Exception as exc:
            logger.warning("USD poll failed: %s", exc)
        await asyncio.sleep(USD_POLL_INTERVAL)