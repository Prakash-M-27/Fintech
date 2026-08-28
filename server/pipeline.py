import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from database import SessionLocal, init_db
from models import GoldPrice, NiftyPrice, USDPrice
from services.cache import asset_cache_key, cache_set
from socket_manager import emit_market_update

logger = logging.getLogger(__name__)

MODEL_MAP = {
    "nifty": NiftyPrice,
    "gold": GoldPrice,
    "usd": USDPrice,
    "news": None,
}

_locks: dict[str, asyncio.Lock] = {}


async def price_handler(asset: str, payload: dict) -> None:
    asset = asset.lower()
    model = MODEL_MAP.get(asset)
    if model is None and asset != "news":
        logger.warning("Unknown asset: %s", asset)
        return

    if asset != "news":
        lock = _locks.setdefault(asset, asyncio.Lock())
        async with lock:
            try:
                async with SessionLocal() as session:
                    row = model(
                        price=payload["price"],
                        change=payload.get("change"),
                        change_pct=payload.get("change_pct"),
                        volume=payload.get("volume"),
                        timestamp=datetime.now(),
                    )
                    session.add(row)
                    await session.commit()
                    row_id = row.id
                    ts = row.timestamp.isoformat()
            except Exception as exc:
                logger.error("DB insert failed for %s: %s", asset, exc)
                row_id, ts = None, None

            snapshot = {
                "asset": asset,
                "price": payload["price"],
                "change": payload.get("change"),
                "change_pct": payload.get("change_pct"),
                "volume": payload.get("volume"),
                "timestamp": ts,
                "cached": False,
            }
            await cache_set(asset_cache_key(asset), snapshot)
            await emit_market_update("market_update", snapshot)

            # ── Agent price-tick hook ─────────────────────────────────────
            # Recomputes unrealized PnL and checks stop-loss / take-profit
            # on any open paper position for this asset.
            # Import is deferred to avoid circular import at module load time.
            try:
                from services.agent_loop import on_price_tick
                await on_price_tick(asset, float(payload["price"]))
            except Exception as exc:
                logger.error("Agent on_price_tick error for %s: %s", asset, exc)
    else:
        await emit_market_update("news_update", payload)
        await emit_market_update("market_update", payload)


async def warm_up_from_db() -> None:
    """Load most recent row per asset into cache + socket at startup."""
    for asset, model in MODEL_MAP.items():
        if model is None:
            continue
        try:
            async with SessionLocal() as session:
                result = await session.execute(select(model).order_by(model.id.desc()).limit(1))
                row = result.scalars().first()
                if row is None:
                    continue
                snapshot = {
                    "asset": asset,
                    "price": float(row.price),
                    "change": float(row.change) if row.change is not None else None,
                    "change_pct": float(row.change_pct) if row.change_pct is not None else None,
                    "volume": row.volume,
                    "timestamp": row.timestamp.isoformat(),
                    "cached": True,
                }
                await cache_set(asset_cache_key(asset), snapshot)
                await emit_market_update("market_update", snapshot)
        except Exception as exc:
            logger.warning("Warm-up failed for %s: %s", asset, exc)
