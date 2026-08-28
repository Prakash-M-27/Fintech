from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import json
import os

from database import get_db
from models import NiftyPrice, GoldPrice, USDPrice, PriceModel
from schemas import MarketSnapshot, PriceOut, CandleOut
from services.cache import asset_cache_key, cache_get, cache_set, CACHE_TTL
from config import TWELVEDATA_API_KEY

router = APIRouter(prefix="/api", tags=["market"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

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


SYMBOL_MAP = {
    "gold": "XAU/USD",
    "usd": "USD/INR",
}

SYNTHETIC_ASSETS = {"nifty", "banknifty", "sensex"}

VALID_TIMEFRAMES = ["1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week", "1month"]


def _load_synthetic_candles(asset: str, timeframe: str) -> list[CandleOut]:
    filepath = os.path.join(DATA_DIR, f"{asset}_{timeframe}.json")
    if not os.path.exists(filepath):
        raise HTTPException(404, detail=f"No synthetic data for {asset}/{timeframe}. Run generate_synthetic_data.py first.")
    with open(filepath, "r") as f:
        data = json.load(f)
    return [
        CandleOut(
            time=c["time"], open=c["open"], high=c["high"],
            low=c["low"], close=c["close"], volume=c["volume"],
        )
        for c in data
    ]


@router.get("/market/{asset}/candles", response_model=list[CandleOut])
async def get_candles(
    asset: str,
    timeframe: str = Query("1min", description="Candle timeframe"),
    limit: int = Query(200, description="Number of candles"),
):
    asset = asset.lower()
    if timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(400, detail=f"Valid timeframes: {', '.join(VALID_TIMEFRAMES)}")

    if asset in SYNTHETIC_ASSETS:
        candles = _load_synthetic_candles(asset, timeframe)
        return candles[:limit]

    symbol = SYMBOL_MAP.get(asset)
    if not symbol:
        raise HTTPException(400, detail="Valid assets: nifty, banknifty, sensex, gold, usd")

    limit = max(1, min(limit, 500))
    cache_key = f"candles:{asset}:{timeframe}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": timeframe,
        "outputsize": limit,
        "apikey": TWELVEDATA_API_KEY,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    values = data.get("values", [])
    candles = [
        CandleOut(
            time=v["datetime"],
            open=float(v["open"]),
            high=float(v["high"]),
            low=float(v["low"]),
            close=float(v["close"]),
            volume=int(v.get("volume", 0)),
        )
        for v in values
    ]

    candles.reverse()
    await cache_set(cache_key, [c.model_dump() for c in candles], ttl=30)
    return candles