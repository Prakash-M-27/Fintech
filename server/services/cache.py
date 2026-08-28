import json
from typing import Any, Optional

import redis.asyncio as aioredis

from config import REDIS_URL, CACHE_TTL

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def ping() -> bool:
    try:
        r = await get_redis()
        return bool(await r.ping())
    except Exception:
        return False


async def cache_set(key: str, value: Any, ttl: int = CACHE_TTL) -> None:
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


async def cache_get(key: str) -> Optional[Any]:
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception:
        pass


def asset_cache_key(asset: str) -> str:
    return f"market:{asset}:latest"