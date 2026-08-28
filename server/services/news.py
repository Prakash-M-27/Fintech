import asyncio
import logging
from datetime import datetime

import httpx

from config import NEWS_API_KEY
from pipeline import price_handler

logger = logging.getLogger(__name__)

from services.tavily_client import fetch_all_asset_news

NEWS_POLL_INTERVAL = 300


async def fetch_financial_news() -> list[dict] | None:
    try:
        articles = await fetch_all_asset_news()
        return articles
    except Exception as exc:
        logger.error("Failed to fetch news from Tavily in news service: %s", exc)
        return None


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
                    source_name = a.get("source") if isinstance(a.get("source"), str) else (a.get("source") or {}).get("name", "Tavily")
                    filtered.append({
                        "title": a.get("title"),
                        "source": source_name,
                        "url": a.get("url"),
                        "published_at": a.get("published_at") or a.get("publishedAt"),
                        "description": a.get("raw_snippet") or a.get("description"),
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