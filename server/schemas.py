from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    price: Decimal
    change: Optional[Decimal] = None
    change_pct: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: datetime


class MarketSnapshot(BaseModel):
    asset: str
    price: Decimal
    change: Optional[Decimal] = None
    change_pct: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: datetime
    cached: bool = False


class CandleOut(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class HealthOut(BaseModel):
    status: str
    database: str
    redis: str
    realtime_connected: bool
    last_updated: Optional[dict] = None