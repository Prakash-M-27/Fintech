from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, BigInteger, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PriceModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    change: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class NiftyPrice(PriceModel):
    __tablename__ = "nifty_prices"
    __table_args__ = (Index("ix_nifty_timestamp", "timestamp"),)


class GoldPrice(PriceModel):
    __tablename__ = "gold_prices"
    __table_args__ = (Index("ix_gold_timestamp", "timestamp"),)


class USDPrice(PriceModel):
    __tablename__ = "usd_prices"
    __table_args__ = (Index("ix_usd_timestamp", "timestamp"),)