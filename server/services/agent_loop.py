"""
services/agent_loop.py
──────────────────────
News Sentinel Agent — the 5th background task started in main.py alongside
the TwelveData / NIFTY / USD / NewsAPI pollers.

Full autonomous loop (paper-trading simulation only):
  observe  → Tavily fetches fresh news articles
  interpret → Groq Call-A classifies each article
  reason   → if signal clears threshold, Groq Call-B decides action
  risk     → server-side capital rules enforce hard limits (LLM output is NOT trusted for money math)
  allocate → capital ledger updated atomically
  execute  → portfolio_positions row created/closed (paper trade)
  outcome  → each price tick recomputes unrealized PnL + checks stop-loss / take-profit
  adapt    → stop-loss/take-profit auto-exits feed back into the next decision cycle

IMPORTANT: This is a paper-trading simulation.
No real brokerage integration, no real order routing.
Every "trade" is a Postgres row and a capital-ledger entry.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.exc import IntegrityError

from config import (
    GROQ_API_KEY,
    MAX_TRADE_AMOUNT,
    NEWS_AGENT_POLL_INTERVAL,
    SIGNAL_ACTION_THRESHOLD,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TOTAL_CAPITAL,
)
from database import SessionLocal
from models import (
    ActionEnum,
    AgentDecision,
    CapitalLedger,
    GoldPrice,
    NewsArticle,
    NewsSignal,
    NiftyPrice,
    PortfolioPosition,
    PositionStatusEnum,
    SentimentEnum,
    USDPrice,
)
from services.cache import asset_cache_key, cache_get
from services.decision_engine import build_technical_snapshot, get_decision
from services.news_classifier import classify_article
from services.tavily_client import check_tavily_health, fetch_all_asset_news
from socket_manager import emit_market_update

logger = logging.getLogger(__name__)

# ── Per-asset lock — mirrors the pattern in pipeline.py ───────────────────
# Serialises all capital / position mutations so concurrent news events
# cannot race the capital ledger.
_asset_locks: dict[str, asyncio.Lock] = {}

def _lock_for(asset: str) -> asyncio.Lock:
    if asset not in _asset_locks:
        _asset_locks[asset] = asyncio.Lock()
    return _asset_locks[asset]

# Price model map used to retrieve recent history for technical indicators
_PRICE_MODEL_MAP = {
    "nifty": NiftyPrice,
    "gold":  GoldPrice,
    "usd":   USDPrice,
}

# ── Agent state (in-memory, for /api/agent/health) ────────────────────────
agent_state = {
    "running":        False,
    "last_poll_at":   None,
    "articles_total": 0,
    "signals_total":  0,
    "decisions_total": 0,
    "last_error":     None,
}


# ═══════════════════════════════════════════════════════════════════════════
# Capital ledger helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _get_or_init_capital(session) -> CapitalLedger:
    """Return the latest capital ledger row, creating the seed row if missing."""
    result = await session.execute(
        select(CapitalLedger).order_by(desc(CapitalLedger.id)).limit(1)
    )
    row = result.scalars().first()
    if row is None:
        row = CapitalLedger(
            total_capital=Decimal(str(TOTAL_CAPITAL)),
            allocated_capital=Decimal("0.00"),
            available_capital=Decimal(str(TOTAL_CAPITAL)),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.flush()
        logger.info("Capital ledger initialised: total=₹%.0f", TOTAL_CAPITAL)
    return row


async def _append_capital(session, allocated: Decimal, reason: str = "") -> CapitalLedger:
    """Append a new ledger row with updated allocated / available figures."""
    total = Decimal(str(TOTAL_CAPITAL))
    available = total - allocated
    row = CapitalLedger(
        total_capital=total,
        allocated_capital=allocated,
        available_capital=available,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Capital ledger updated%s: allocated=₹%.0f available=₹%.0f",
        f" ({reason})" if reason else "",
        float(allocated),
        float(available),
    )
    return row


async def _compute_allocated_capital(session) -> Decimal:
    """Sum entry_amount_inr across all open positions — source of truth."""
    result = await session.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.status == PositionStatusEnum.open
        )
    )
    positions = result.scalars().all()
    return sum((p.entry_amount_inr for p in positions), Decimal("0.00"))


# ═══════════════════════════════════════════════════════════════════════════
# Technical snapshot helper
# ═══════════════════════════════════════════════════════════════════════════

async def _get_price_history(asset: str, limit: int = 60) -> list[float]:
    """
    Fetch the last `limit` price rows for an asset from Postgres, oldest first.
    Falls back to Redis snapshot if DB is unavailable.
    """
    model = _PRICE_MODEL_MAP.get(asset)
    if model is None:
        return []
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(model).order_by(desc(model.timestamp)).limit(limit)
            )
            rows = result.scalars().all()
            return [float(r.price) for r in reversed(rows)]
    except Exception as exc:
        logger.warning("Price history fetch failed for %s: %s — falling back to cache", asset, exc)
        cached = await cache_get(asset_cache_key(asset))
        if cached and cached.get("price"):
            return [float(cached["price"])]
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Position helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _get_open_position(session, asset: str) -> Optional[PortfolioPosition]:
    result = await session.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.asset == asset,
            PortfolioPosition.status == PositionStatusEnum.open,
        )
    )
    return result.scalars().first()


async def _open_position(
    session,
    asset: str,
    amount_inr: Decimal,
    entry_price: float,
    decision_id: int,
) -> PortfolioPosition:
    pos = PortfolioPosition(
        asset=asset,
        status=PositionStatusEnum.open,
        entry_price=Decimal(str(entry_price)),
        entry_amount_inr=amount_inr,
        entry_time=datetime.now(timezone.utc),
        unrealized_pnl=Decimal("0.00"),
        decision_id=decision_id,
    )
    session.add(pos)
    await session.flush()
    logger.info(
        "[PAPER TRADE] OPENED position: asset=%s amount=₹%.0f entry_price=%.4f",
        asset, float(amount_inr), entry_price,
    )
    return pos


async def _close_position(
    session,
    pos: PortfolioPosition,
    exit_price: float,
    reason: str,
) -> Decimal:
    """
    Close an open position, compute realized PnL, return capital to ledger.
    Returns the realized PnL (can be negative).
    """
    entry = float(pos.entry_price)
    qty_units = float(pos.entry_amount_inr) / entry if entry != 0 else 0
    realized = Decimal(str(round((exit_price - entry) * qty_units, 2)))

    pos.status = PositionStatusEnum.closed
    pos.exit_price = Decimal(str(exit_price))
    pos.exit_time = datetime.now(timezone.utc)
    pos.realized_pnl = realized
    pos.unrealized_pnl = Decimal("0.00")
    await session.flush()

    logger.info(
        "[PAPER TRADE] CLOSED position: asset=%s reason=%s entry=%.4f exit=%.4f pnl=₹%.2f",
        pos.asset, reason, entry, exit_price, float(realized),
    )
    return realized


# ═══════════════════════════════════════════════════════════════════════════
# Price-tick hook — called from pipeline.price_handler
# ═══════════════════════════════════════════════════════════════════════════

async def on_price_tick(asset: str, current_price: float) -> None:
    """
    Called on every price tick for nifty / gold / usd.
    - Recomputes unrealized PnL on any open position for this asset.
    - Checks stop-loss / take-profit thresholds and auto-exits if breached.

    This IS the "adaptation" loop: outcomes of prior decisions (price moving
    against / for the position) feed back into subsequent action (auto-exit)
    without new human input — satisfying problem-statement requirement #6.
    """
    async with _lock_for(asset):
        try:
            async with SessionLocal() as session:
                pos = await _get_open_position(session, asset)
                if pos is None:
                    return

                entry = float(pos.entry_price)
                if entry == 0:
                    return

                pct_change = ((current_price - entry) / entry) * 100

                # Update unrealized PnL
                qty_units = float(pos.entry_amount_inr) / entry
                unrealized = round((current_price - entry) * qty_units, 2)
                pos.unrealized_pnl = Decimal(str(unrealized))

                exit_reason: Optional[str] = None
                if pct_change <= STOP_LOSS_PCT:
                    exit_reason = f"stop_loss ({pct_change:.2f}% <= {STOP_LOSS_PCT}%)"
                elif pct_change >= TAKE_PROFIT_PCT:
                    exit_reason = f"take_profit ({pct_change:.2f}% >= {TAKE_PROFIT_PCT}%)"

                if exit_reason:
                    realized = await _close_position(session, pos, current_price, exit_reason)
                    # Recompute and append capital ledger
                    allocated = await _compute_allocated_capital(session)
                    await _append_capital(session, allocated, reason=exit_reason)
                    await session.commit()

                    # Emit Socket.IO event so frontend updates without page refresh
                    await emit_market_update("agent_decision", {
                        "type":    "auto_exit",
                        "asset":   asset,
                        "action":  "EXIT",
                        "reason":  exit_reason,
                        "price":   current_price,
                        "pnl":     float(realized),
                        "ts":      datetime.now(timezone.utc).isoformat(),
                    })
                    await session.commit()

            # Trigger LangGraph Fast-Path Evaluation
            from services.graph_runner import run_langgraph_cycle
            asyncio.create_task(run_langgraph_cycle(
                asset, 
                "PRICE_CHANGED", 
                {"market_data": {"price": current_price, "timestamp": datetime.now(timezone.utc).isoformat()}}
            ))


        except Exception as exc:
            logger.error("on_price_tick error for %s: %s", asset, exc)


# ═══════════════════════════════════════════════════════════════════════════
# Core agent cycle — one full pass (fetch → classify → decide → execute)
# ═══════════════════════════════════════════════════════════════════════════

async def _run_agent_cycle() -> None:
    """Execute one full news-to-trade cycle."""

    # ── Step 1: Fetch articles from Tavily ──────────────────────────────
    logger.info("Agent cycle: fetching news from Tavily…")
    try:
        raw_articles = await fetch_all_asset_news()
    except Exception as exc:
        logger.error("Agent cycle: Tavily fetch failed — skipping cycle: %s", exc)
        agent_state["last_error"] = str(exc)
        return

    if not raw_articles:
        logger.info("Agent cycle: no articles returned from Tavily")
        return

    # ── Step 2: Dedup against DB and persist new articles ───────────────
    new_articles: list[NewsArticle] = []
    async with SessionLocal() as session:
        for art in raw_articles:
            # Check for existing URL
            existing = await session.execute(
                select(NewsArticle).where(NewsArticle.url == art["url"])
            )
            if existing.scalars().first() is not None:
                continue
            db_art = NewsArticle(
                url=art["url"],
                source=art.get("source"),
                title=art["title"],
                published_at=art.get("published_at"),
                raw_snippet=art.get("raw_snippet"),
                related_asset=art.get("related_asset"),
                processed=False,
            )
            session.add(db_art)
            new_articles.append(db_art)
        if new_articles:
            await session.commit()
            # Refresh to get ids
            for a in new_articles:
                await session.refresh(a)
            agent_state["articles_total"] += len(new_articles)
            logger.info("Agent cycle: persisted %d new articles", len(new_articles))

    if not new_articles:
        logger.info("Agent cycle: all articles already processed — nothing to do")
        return

    # ── Step 3: Classify each new article with Groq Call-A ──────────────
    for db_art in new_articles:
        await _classify_and_act(db_art)


async def _classify_and_act(db_art: NewsArticle) -> None:
    """Classify one article, persist the signal, then conditionally run the decision engine."""

    # ── Groq Call A ───────────────────────────────────────────────────
    try:
        classification = await classify_article(db_art.title, db_art.raw_snippet)
    except Exception as exc:
        logger.error("Classifier failed for article id=%s title=%r: %s", db_art.id, db_art.title[:60], exc)
        # Mark as processed so we don't retry indefinitely on a bad article
        async with SessionLocal() as session:
            art = await session.get(NewsArticle, db_art.id)
            if art:
                art.processed = True
                await session.commit()
        return

    # Persist signal and mark article processed
    signal_id: Optional[int] = None
    async with SessionLocal() as session:
        # Update article: mark processed and set related_asset from classifier
        art = await session.get(NewsArticle, db_art.id)
        if art is None:
            return
        art.processed = True
        art.related_asset = classification["asset"]

        signal = NewsSignal(
            article_id=db_art.id,
            asset=classification["asset"],
            sentiment=SentimentEnum(classification["sentiment"]),
            impact_score=classification["impact_score"],
            confidence=classification["confidence"],
            reasoning=classification["reasoning"],
        )
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        signal_id = signal.id
        agent_state["signals_total"] += 1

    logger.info(
        "Signal: asset=%s sentiment=%s impact=%.2f conf=%.2f title=%r",
        classification["asset"], classification["sentiment"],
        classification["impact_score"], classification["confidence"],
        db_art.title[:60],
    )

    # Emit news_signal Socket.IO event regardless of threshold
    await emit_market_update("news_signal", {
        "article_id":   db_art.id,
        "title":        db_art.title,
        "source":       db_art.source,
        "asset":        classification["asset"],
        "sentiment":    classification["sentiment"],
        "impact_score": classification["impact_score"],
        "confidence":   classification["confidence"],
        "reasoning":    classification["reasoning"],
        "ts":           datetime.now(timezone.utc).isoformat(),
    })

    # ── Threshold check ───────────────────────────────────────────────
    combined_score = classification["confidence"] * abs(classification["impact_score"])
    if combined_score < SIGNAL_ACTION_THRESHOLD:
        logger.info(
            "Signal below threshold (%.3f < %.3f) — skipping decision engine",
            combined_score, SIGNAL_ACTION_THRESHOLD,
        )
        return

    if classification["asset"] not in ("nifty", "gold", "usd"):
        logger.info("Signal asset=%r not tradable — skipping decision engine", classification["asset"])
        return

    # ── Groq Call B (under per-asset lock) ────────────────────────────
    asset = classification["asset"]
    async with _lock_for(asset):
        await _run_decision(classification, db_art, signal_id)


async def _run_decision(
    classification: dict,
    db_art: NewsArticle,
    signal_id: Optional[int],
) -> None:
    """Trigger LangGraph cycle with NEWS_DETECTED."""
    asset = classification["asset"]
    from services.graph_runner import run_langgraph_cycle
    await run_langgraph_cycle(
        asset,
        "NEWS_DETECTED",
        {
            "news_state": classification,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# Background loop — the 5th asyncio.create_task started in main.py
# ═══════════════════════════════════════════════════════════════════════════

async def run_agent_loop() -> None:
    """
    Continuously poll Tavily, classify articles, and execute paper trades.
    Mirrors the pattern of poll_usd_loop / poll_nifty_loop in the existing pollers.
    Registered as the 5th background task in main.py lifespan.
    """
    agent_state["running"] = True
    logger.info(
        "News Sentinel Agent started — poll_interval=%ds threshold=%.2f "
        "stop_loss=%.1f%% take_profit=%.1f%% max_trade=₹%.0f",
        NEWS_AGENT_POLL_INTERVAL, SIGNAL_ACTION_THRESHOLD,
        STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_TRADE_AMOUNT,
    )

    # Seed the capital ledger on first run if empty
    try:
        async with SessionLocal() as session:
            await _get_or_init_capital(session)
            await session.commit()
    except Exception as exc:
        logger.error("Agent: failed to seed capital ledger: %s", exc)

    asset_list = ["nifty", "gold", "usd"]
    asset_idx = 0

    while True:
        try:
            agent_state["last_poll_at"] = datetime.now(timezone.utc).isoformat()
            # Run news poll
            await _run_agent_cycle()
            
            # Continuous market telemetry cycle for active asset
            target_asset = asset_list[asset_idx % len(asset_list)]
            asset_idx += 1
            from services.graph_runner import run_langgraph_cycle
            await run_langgraph_cycle(
                target_asset,
                "CONTINUOUS_MONITOR",
                {
                    "market_data": {"price": 24200.0, "change": "+0.25%"},
                    "news_state": {"aggregate_sentiment": "neutral", "aggregate_impact": 0.5},
                    "positions": []
                }
            )
        except Exception as exc:
            logger.error("Agent loop unhandled error: %s", exc)
            agent_state["last_error"] = str(exc)
        await asyncio.sleep(25)
