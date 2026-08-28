import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import socketio

from database import init_db
from services.cache import close_redis, get_redis
from services.frankfurter import poll_usd_loop
from services.news import poll_news_loop
from services.nifty import poll_nifty_loop
from services.twelvedata import connect_twelvedata
from services.agent_loop import run_agent_loop
from services.synthetic_price import run_synthetic_price_loop
from socket_manager import sio, register_socket_events
from pipeline import warm_up_from_db
from routers.market import router as market_router
from routers.agent import router as agent_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    register_socket_events()
    try:
        r = await get_redis()
        await r.ping()
        logger.info("Redis connected")
    except Exception:
        logger.warning("Redis unavailable")

    import asyncio

    # Background tasks 1–4: existing market data pollers
    asyncio.create_task(connect_twelvedata())
    asyncio.create_task(poll_usd_loop())
    asyncio.create_task(poll_nifty_loop())
    asyncio.create_task(poll_news_loop())
    # Background task 5: News Sentinel Agent (news → classify → decide → paper trade)
    asyncio.create_task(run_agent_loop())
    # Background task 6: Synthetic live prices for nifty/banknifty/sensex (1.5s ticks)
    asyncio.create_task(run_synthetic_price_loop())

    await warm_up_from_db()
    logger.info("Axiom backend started — 6 background tasks running")
    yield
    await close_redis()


app = FastAPI(title="Axiom Market Data Backend", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router)
app.include_router(agent_router)


@app.get("/")
async def root():
    return {
        "service": "Axiom Market Backend",
        "status": "running",
        "endpoints": [
            "/api/market", "/api/market/{asset}", "/api/market/{asset}/history",
            "/api/agent/health", "/api/agent/news", "/api/agent/decisions", "/api/agent/portfolio",
            "/api/health",
        ],
    }


@app.get("/api/health")
async def health():
    from services.cache import ping as redis_ping
    from services.agent_loop import agent_state
    from services.tavily_client import check_tavily_health

    db_ok = "ok"
    try:
        from database import SessionLocal
        from sqlalchemy import text
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"

    return {
        "status": "ok",
        "database": db_ok,
        "redis": "ok" if await redis_ping() else "error",
        "realtime_connected": sio is not None,
        "agent": {
            "running":       agent_state["running"],
            "last_poll_at":  agent_state.get("last_poll_at"),
            "tavily":        "ok" if await check_tavily_health() else "error",
            "signals_total": agent_state.get("signals_total", 0),
            "decisions_total": agent_state.get("decisions_total", 0),
        },
    }


socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
