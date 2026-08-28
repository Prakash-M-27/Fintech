from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import NiftyPrice, GoldPrice, USDPrice, PriceModel
from schemas import MarketSnapshot, PriceOut
from services.cache import asset_cache_key, cache_get, cache_set, CACHE_TTL

router = APIRouter(prefix="/api", tags=["market"])

MODEL_MAP = {
    "nifty": NiftyPrice,
    "gold": GoldPrice,
    "usd": USDPrice,
}


async def _latest_or_db(asset: str, model: type[PriceModel], db: AsyncSession) -> MarketSnapshot:
    cached = await cache_get(asset_cache_key(asset))
    if cached is not None:
        return MarketSnapshot(**cached)

    result = await db.execute(select(model).order_by(desc(model.timestamp)).limit(1))
    row = result.scalars().first()
    if row is None:
        raise HTTPException(404, detail=f"No data available yet for {asset}. Waiting for live feed...")

    snapshot = MarketSnapshot(
        asset=asset,
        price=row.price,
        change=row.change,
        change_pct=row.change_pct,
        volume=row.volume,
        timestamp=row.timestamp,
        cached=True,
    )
    await cache_set(asset_cache_key(asset), snapshot.model_dump(mode="json"), ttl=CACHE_TTL)
    return snapshot


@router.get("/market/{asset}", response_model=MarketSnapshot)
async def get_market(asset: str, db: AsyncSession = Depends(get_db)):
    asset = asset.lower()
    model = MODEL_MAP.get(asset)
    if model is None:
        raise HTTPException(400, detail="Valid assets: nifty, gold, usd")
    return await _latest_or_db(asset, model, db)


@router.get("/market/{asset}/history", response_model=list[PriceOut])
async def get_history(asset: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    asset = asset.lower()
    model = MODEL_MAP.get(asset)
    if model is None:
        raise HTTPException(400, detail="Valid assets: nifty, gold, usd")
    limit = max(1, min(limit, 500))
    result = await db.execute(select(model).order_by(desc(model.timestamp)).limit(limit))
    rows = result.scalars().all()
    return [PriceOut.model_validate(r) for r in rows]


@router.get("/market", response_model=list[MarketSnapshot])
async def get_all_markets(db: AsyncSession = Depends(get_db)):
    snapshots = []
    for asset, model in MODEL_MAP.items():
        try:
            snapshots.append(await _latest_or_db(asset, model, db))
        except HTTPException:
            continue
    return snapshots