import asyncio
import logging
from datetime import datetime

import httpx

from config import NEWS_API_KEY
from pipeline import price_handler

logger = logging.getLogger(__name__)

NEWS_URL = "https://newsapi.org/v2/top-headlines"
NEWS_POLL_INTERVAL = 300


async def fetch_financial_news() -> list[dict] | None:
    params = {
        "category": "business",
        "language": "en",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(NEWS_URL, params=params)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("articles", [])


async def poll_news_loop() -> None:
    while True:
        try:
            articles = await fetch_financial_news()
            if not articles:
                continue
            filtered = []
            for a in articles:
                title = (a.get("title") or "").lower()
                if any(k in title for k in ("stock", "market", "nifty", "gold", "usd", "inr", "rupee", "trading", "equity", "sensex", "forex", "currency", "commodity", "inflation", "rate", "fed", "rbi")):
                    filtered.append({
                        "title": a.get("title"),
                        "source": a.get("source", {}).get("name"),
                        "url": a.get("url"),
                        "published_at": a.get("publishedAt"),
                        "description": a.get("description"),
                    })
            if filtered:
                payload = {
                    "asset": "news",
                    "price": 0,
                    "change": None,
                    "change_pct": None,
                    "volume": len(filtered),
                    "timestamp": datetime.now().isoformat() + "Z",
                    "meta": {"articles": filtered[:10]},
                }
                await price_handler("news", payload)
                logger.info("News updated: %d articles", len(filtered))
        except Exception as exc:
            logger.warning("News poll failed: %s", exc)
        await asyncio.sleep(NEWS_POLL_INTERVAL)