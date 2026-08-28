from datetime import datetime
from decimal import Decimal
from typing import Optional
import enum

from sqlalchemy import (
    BigInteger, DateTime, Index, Numeric, Text, Boolean,
    ForeignKey, Float, JSON, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# Existing price tables (unchanged)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Agent system enums
# ---------------------------------------------------------------------------

class SentimentEnum(str, enum.Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class ActionEnum(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


class PositionStatusEnum(str, enum.Enum):
    open = "open"
    closed = "closed"


# ---------------------------------------------------------------------------
# news_articles — raw articles fetched from Tavily (deduped by url)
# ---------------------------------------------------------------------------

class NewsArticle(Base):
    """
    Stores every unique article retrieved by the Tavily search service.
    'processed' is flipped to True once the Groq classifier has run on it.
    'related_asset' is set by the classifier (nifty / gold / usd / general / None).
    """
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_news_articles_url"),
        Index("ix_news_articles_processed", "processed"),
        Index("ix_news_articles_fetched_at", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # ISO string from Tavily
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    raw_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_asset: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # set post-classification
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # relationships
    signals: Mapped[list["NewsSignal"]] = relationship(
        "NewsSignal", back_populates="article", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# news_signals — Groq Call-A output: one signal per article per asset
# ---------------------------------------------------------------------------

class NewsSignal(Base):
    """
    Result of Groq Call A (news classifier).  impact_score is on [-1.0, 1.0]:
    positive values are bullish for the related asset, negative are bearish.
    confidence is on [0.0, 1.0].
    """
    __tablename__ = "news_signals"
    __table_args__ = (Index("ix_news_signals_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset: Mapped[str] = mapped_column(Text, nullable=False)   # nifty / gold / usd / general
    sentiment: Mapped[SentimentEnum] = mapped_column(
        SAEnum(SentimentEnum, name="sentimentenum"), nullable=False
    )
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)   # -1.0 to 1.0
    confidence: Mapped[float] = mapped_column(Float, nullable=False)     # 0.0 to 1.0
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # relationships
    article: Mapped["NewsArticle"] = relationship("NewsArticle", back_populates="signals")
    decisions: Mapped[list["AgentDecision"]] = relationship(
        "AgentDecision", back_populates="triggering_signal"
    )


# ---------------------------------------------------------------------------
# agent_decisions — Groq Call-B output: one decision per signal that clears threshold
# ---------------------------------------------------------------------------

class AgentDecision(Base):
    """
    Paper-trading decision produced by the decision engine.
    Stores a full technical snapshot (RSI, MACD, EMA20, EMA50, BB, VWAP)
    alongside the Groq reasoning so every decision is self-contained for audit.

    IMPORTANT: This is a paper-trading simulation only.
    No real brokerage integration or real order routing exists.
    amount_inr is virtual capital, clamped server-side before this row is written.
    """
    __tablename__ = "agent_decisions"
    __table_args__ = (Index("ix_agent_decisions_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[ActionEnum] = mapped_column(
        SAEnum(ActionEnum, name="actionenum"), nullable=False
    )
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    triggering_signal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("news_signals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # JSON snapshot: { rsi, macd, macd_signal, ema20, ema50, bb_upper, bb_lower, vwap, price }
    technical_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # relationships
    triggering_signal: Mapped[Optional["NewsSignal"]] = relationship(
        "NewsSignal", back_populates="decisions"
    )
    positions: Mapped[list["PortfolioPosition"]] = relationship(
        "PortfolioPosition", back_populates="decision"
    )


# ---------------------------------------------------------------------------
# portfolio_positions — open / closed paper positions
# ---------------------------------------------------------------------------

class PortfolioPosition(Base):
    """
    Tracks a single paper-trade position lifecycle: open → (price ticks update
    unrealized_pnl) → closed (exit triggered by stop-loss, take-profit, or EXIT decision).

    IMPORTANT: Paper-trading simulation only. No real capital is at risk.
    """
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        Index("ix_portfolio_positions_asset_status", "asset", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PositionStatusEnum] = mapped_column(
        SAEnum(PositionStatusEnum, name="positionstatusenum"),
        default=PositionStatusEnum.open,
        nullable=False,
    )
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    entry_amount_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 8), nullable=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    realized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("agent_decisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # relationships
    decision: Mapped["AgentDecision"] = relationship(
        "AgentDecision", back_populates="positions"
    )


# ---------------------------------------------------------------------------
# capital_ledger — append-only audit log of every capital state change
# ---------------------------------------------------------------------------

class CapitalLedger(Base):
    """
    Append-only ledger — each row records the capital state *after* an event.
    The most-recent row (by id DESC) is the authoritative current state.

    total_capital is fixed (₹100,000 by default, set from TOTAL_CAPITAL env var).
    allocated_capital = sum of entry_amount_inr across all open positions.
    available_capital = total_capital - allocated_capital.

    IMPORTANT: Paper-trading simulation only. Figures are virtual INR amounts.
    """
    __tablename__ = "capital_ledger"
    __table_args__ = (Index("ix_capital_ledger_updated_at", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    total_capital: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    allocated_capital: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    available_capital: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )