"""
routers/agent.py
────────────────
REST endpoints for the News Sentinel Agent.
Follows the same style as routers/market.py:
  - FastAPI APIRouter with /api prefix
  - Redis-first, DB fallback where applicable
  - Pydantic response models for clean serialisation

Endpoints:
  GET /api/agent/health      — Tavily/Groq connectivity + agent loop status
  GET /api/agent/news        — recent classified articles + signals
  GET /api/agent/decisions   — recent agent decisions with full reasoning
  GET /api/agent/portfolio   — open+closed positions + current capital ledger
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import GROQ_API_KEY, TAVILY_API_KEY
from database import get_db
from models import (
    AgentDecision,
    CapitalLedger,
    NewsArticle,
    NewsSignal,
    PortfolioPosition,
)
from services.tavily_client import check_tavily_health

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Pydantic response schemas ──────────────────────────────────────────────

class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset: str
    sentiment: str
    impact_score: float
    confidence: float
    reasoning: str
    created_at: datetime


class ArticleWithSignal(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    source: Optional[str]
    url: str
    published_at: Optional[str]
    related_asset: Optional[str]
    fetched_at: datetime
    processed: bool
    signal: Optional[SignalOut] = None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset: str
    action: str
    amount_inr: Decimal
    confidence: float
    reasoning: str
    technical_snapshot: Optional[dict]
    triggering_signal_id: Optional[int]
    created_at: datetime


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asset: str
    status: str
    entry_price: Decimal
    entry_amount_inr: Decimal
    entry_time: datetime
    exit_price: Optional[Decimal]
    exit_time: Optional[datetime]
    realized_pnl: Optional[Decimal]
    unrealized_pnl: Optional[Decimal]
    decision_id: int


class CapitalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total_capital: Decimal
    allocated_capital: Decimal
    available_capital: Decimal
    updated_at: datetime


class PortfolioOut(BaseModel):
    open_positions: list[PositionOut]
    closed_positions: list[PositionOut]
    capital: Optional[CapitalOut]
    summary: dict


class AgentHealthOut(BaseModel):
    status: str
    agent_running: bool
    last_poll_at: Optional[str]
    articles_total: int
    signals_total: int
    decisions_total: int
    tavily_connected: bool
    groq_configured: bool
    last_error: Optional[str]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/health", response_model=AgentHealthOut)
async def agent_health():
    """Connectivity check for Tavily/Groq plus agent loop status."""
    from services.agent_loop import agent_state

    tavily_ok = await check_tavily_health()
    groq_configured = bool(GROQ_API_KEY)

    status = "ok" if (tavily_ok and groq_configured and agent_state["running"]) else "degraded"

    return AgentHealthOut(
        status=status,
        agent_running=agent_state["running"],
        last_poll_at=agent_state.get("last_poll_at"),
        articles_total=agent_state.get("articles_total", 0),
        signals_total=agent_state.get("signals_total", 0),
        decisions_total=agent_state.get("decisions_total", 0),
        tavily_connected=tavily_ok,
        groq_configured=groq_configured,
        last_error=agent_state.get("last_error"),
    )


@router.get("/news", response_model=list[ArticleWithSignal])
async def get_news(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """
    Return the most recent classified news articles with their signals.
    limit is capped at 100.
    """
    limit = max(1, min(limit, 100))

    result = await db.execute(
        select(NewsArticle)
        .order_by(desc(NewsArticle.fetched_at))
        .limit(limit)
    )
    articles = result.scalars().all()

    output: list[ArticleWithSignal] = []
    for art in articles:
        # Fetch the most recent signal for this article (there should be at most one)
        sig_result = await db.execute(
            select(NewsSignal)
            .where(NewsSignal.article_id == art.id)
            .order_by(desc(NewsSignal.created_at))
            .limit(1)
        )
        sig = sig_result.scalars().first()

        output.append(ArticleWithSignal(
            id=art.id,
            title=art.title,
            source=art.source,
            url=art.url,
            published_at=art.published_at,
            related_asset=art.related_asset,
            fetched_at=art.fetched_at,
            processed=art.processed,
            signal=SignalOut.model_validate(sig) if sig else None,
        ))

    return output


@router.get("/decisions", response_model=list[DecisionOut])
async def get_decisions(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """
    Return the most recent agent decisions with full reasoning and technical snapshots.
    limit is capped at 100.
    """
    limit = max(1, min(limit, 100))
    result = await db.execute(
        select(AgentDecision)
        .order_by(desc(AgentDecision.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [DecisionOut.model_validate(r) for r in rows]


@router.get("/portfolio", response_model=PortfolioOut)
async def get_portfolio(db: AsyncSession = Depends(get_db)):
    """
    Return all open and closed positions plus the current capital ledger state.
    """
    # Open positions
    open_result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.status == "open")
        .order_by(desc(PortfolioPosition.entry_time))
    )
    open_positions = open_result.scalars().all()

    # Closed positions (last 50)
    closed_result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.status == "closed")
        .order_by(desc(PortfolioPosition.exit_time))
        .limit(50)
    )
    closed_positions = closed_result.scalars().all()

    # Latest capital ledger row
    capital_result = await db.execute(
        select(CapitalLedger).order_by(desc(CapitalLedger.id)).limit(1)
    )
    capital = capital_result.scalars().first()

    # Summary stats
    total_unrealized = sum(
        float(p.unrealized_pnl or 0) for p in open_positions
    )
    total_realized = sum(
        float(p.realized_pnl or 0) for p in closed_positions
    )

    summary = {
        "open_count":        len(open_positions),
        "closed_count":      len(closed_positions),
        "total_unrealized":  round(total_unrealized, 2),
        "total_realized":    round(total_realized, 2),
        "total_pnl":         round(total_unrealized + total_realized, 2),
        "capital_available": float(capital.available_capital) if capital else None,
        "capital_allocated": float(capital.allocated_capital) if capital else None,
    }

    return PortfolioOut(
        open_positions=[PositionOut.model_validate(p) for p in open_positions],
        closed_positions=[PositionOut.model_validate(p) for p in closed_positions],
        capital=CapitalOut.model_validate(capital) if capital else None,
        summary=summary,
    )


@router.get("/telemetry")
async def get_telemetry():
    """Returns cached node completion events."""
    from services.graph_runner import get_telemetry_cache
    return get_telemetry_cache()


@router.post("/trigger")
async def trigger_agent(asset: str = "nifty"):
    """Manually triggers a full LangGraph agent cycle for the specified asset."""
    from services.graph_runner import run_langgraph_cycle
    payload = {
        "market_data": {"price": 24200.0, "change": "+0.5%"},
        "news_state": {
            "articles": [
                {
                    "title": f"Manual trigger market update for {asset}",
                    "source": "Axiom Real-Time Sentinel",
                    "sentiment": "positive",
                    "impact_score": 0.85,
                    "confidence": 0.9,
                    "reasoning": "Real-time decision update requested by user."
                }
            ],
            "aggregate_sentiment": "positive",
            "aggregate_impact": 0.85
        },
        "positions": []
    }
    
    import asyncio
    asyncio.create_task(run_langgraph_cycle(asset, "MANUAL_TRIGGER", payload))
    return {"status": "triggered", "asset": asset}

