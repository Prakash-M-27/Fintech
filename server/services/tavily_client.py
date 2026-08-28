"""
services/tavily_client.py
─────────────────────────
Thin async wrapper over the Tavily Search API.
Follows the same style as frankfurter.py and nifty.py:
  - async fetch_* function for a single call
  - async poll_* loop for continuous background operation

Tavily docs: https://docs.tavily.com/docs/rest-api/api-reference
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from config import TAVILY_API_KEY, NEWS_AGENT_POLL_INTERVAL

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# ── Query configuration ────────────────────────────────────────────────────
# Each entry is (asset_key, search_query).
# asset_key matches the identifiers used throughout the rest of the codebase:
#   nifty / gold / usd / general
ASSET_QUERIES: list[tuple[str, str]] = [
    ("nifty",   "NIFTY 50 India stock market news today"),
    ("gold",    "gold price XAU USD commodity news today"),
    ("usd",     "USD INR exchange rate rupee dollar news today"),
    ("general", "India financial markets economy news today"),
]

# Maximum results to request per query — Tavily free tier is generous at 5–10.
MAX_RESULTS_PER_QUERY = 5


async def search_news(query: str, asset: str) -> list[dict]:
    """
    Run a single Tavily search and return a normalised list of article dicts.
    Each dict has keys: url, title, source, published_at, raw_snippet, related_asset.

    Raises httpx.HTTPStatusError on non-2xx responses — callers should catch and log.
    """
    if not TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY is not configured — set it in .env")

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",      # "basic" is cheaper; "advanced" gives more content
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "max_results": MAX_RESULTS_PER_QUERY,
        "topic": "finance",           # Tavily finance topic filter
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    articles: list[dict] = []
    for r in results:
        url = r.get("url") or r.get("link")
        title = r.get("title") or ""
        if not url or not title:
            continue
        articles.append({
            "url": url,
            "title": title,
            "source": r.get("source") or _infer_source(url),
            "published_at": r.get("published_date"),   # ISO string or None
            "raw_snippet": (r.get("content") or r.get("snippet") or "")[:2000],
            "related_asset": asset,
            "fetched_at": datetime.utcnow().isoformat(),
        })

    logger.debug("Tavily [%s] returned %d results for query: %s", asset, len(articles), query)
    return articles


async def fetch_all_asset_news() -> list[dict]:
    """
    Run all ASSET_QUERIES sequentially and return a combined de-duplicated list.
    De-duplication here is by URL within a single fetch round; the caller is
    responsible for checking against the DB to avoid re-inserting across rounds.
    """
    seen_urls: set[str] = set()
    all_articles: list[dict] = []

    for asset, query in ASSET_QUERIES:
        try:
            articles = await search_news(query, asset)
            for article in articles:
                url = article["url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(article)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Tavily HTTP error for asset=%s query=%r: %s %s",
                asset, query, exc.response.status_code, exc.response.text[:200],
            )
        except httpx.RequestError as exc:
            logger.error("Tavily request error for asset=%s query=%r: %s", asset, query, exc)
        except ValueError as exc:
            # TAVILY_API_KEY missing — log once and bail out for this round
            logger.error("Tavily configuration error: %s", exc)
            break

    logger.info("Tavily fetch_all: collected %d unique articles", len(all_articles))
    return all_articles


async def check_tavily_health() -> bool:
    """
    Lightweight connectivity check used by /api/agent/health.
    Sends a minimal query and returns True if Tavily responds 200.
    """
    if not TAVILY_API_KEY:
        return False
    try:
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": "market news",
            "search_depth": "basic",
            "max_results": 1,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(TAVILY_SEARCH_URL, json=payload)
            return resp.status_code == 200
    except Exception:
        return False


# ── Helpers ────────────────────────────────────────────────────────────────

def _infer_source(url: str) -> Optional[str]:
    """Best-effort source name from URL domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        # strip www. prefix if present
        return host.removeprefix("www.")
    except Exception:
        return None
