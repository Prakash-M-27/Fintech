"""Always-on REST service for the forex-agent-system.

WHY this is a separate process (and why that is safe/correct):
    The pre-existing `server/` package owns the top-level Python module name
    `config` (and the frontend talks to it via `/api/agent/*`). The forex
    system ALSO owns a top-level `config` package. Importing one into the
    other in-process would collide and break both. Running forex-agent-system
    as its own FastAPI service (default port 8001) on its own working directory
    keeps the two systems fully isolated while letting the frontend consume
    BOTH backends cleanly.

    The forex service is self-contained: SQLite audit log + the LangGraph
    pipeline. No external Postgres/Redis required.

Run:
    PYTHONPATH=.:.deps python -m api_server            # dev (port 8001)
    uvicorn api_server:app --host 0.0.0.0 --port 8001  # prod

Endpoints:
    GET  /api/forex/health     — service + loop status
    GET  /api/forex/decisions  — recent cycles (most recent first)
    GET  /api/forex/signals    — normalized signals for the UI
    GET  /api/forex/rules      — the loaded declarative rules
    POST /api/forex/run        — trigger one cycle on demand
    GET  /api/forex/log        — raw SQLite decision log
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from runner import ForexRunner, get_runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _normalize_signal(summary) -> dict:
    """Map a RunSummary into the shape the frontend forex page expects."""
    result = summary.result
    sig = result.get("proposed_signal") or {}
    risk = result.get("risk_check") or {}
    exec_ = result.get("execution_result") or {}
    ind = result.get("indicators") or {}
    return {
        "trace_id": summary.trace_id,
        "ts": summary.executed_at,
        "instrument": summary.instrument,
        "action": sig.get("action", "HOLD"),
        "rule": sig.get("rule"),
        "reason": sig.get("reason", ""),
        "sentiment": result.get("sentiment", "neutral"),
        "rsi": ind.get("rsi"),
        "close": ind.get("close"),
        "risk_approved": risk.get("approved", False),
        "risk_reason": risk.get("reason", ""),
        "stop_loss": risk.get("stop_loss"),
        "take_profit": risk.get("take_profit"),
        "position_size": risk.get("position_size", 0),
        "execution_status": exec_.get("status", "NONE"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner: ForexRunner = get_runner()
    loop_interval = float(app.state.loop_interval)
    task = asyncio.create_task(runner.continuous_loop(loop_interval))
    logger.info("forex-agent service started (loop interval=%.0fs)", loop_interval)
    yield
    runner.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app(loop_interval: float = 30.0) -> FastAPI:
    app = FastAPI(title="forex-agent-system service", version="0.1.0", lifespan=lifespan)
    app.state.loop_interval = loop_interval

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/forex/health")
    async def health():
        runner = get_runner()
        return runner.health()

    @app.get("/api/forex/decisions")
    async def decisions(limit: int = 50):
        runner = get_runner()
        limit = max(1, min(limit, 500))
        return [
            _normalize_signal(s)
            for s in runner.history[:limit]
        ]

    @app.get("/api/forex/signals")
    async def signals(limit: int = 50):
        # Same data as /decisions but only non-HOLD, risk-relevant signals.
        runner = get_runner()
        limit = max(1, min(limit, 500))
        out = []
        for s in runner.history:
            if s.signal_action in ("BUY", "SELL"):
                out.append(_normalize_signal(s))
            if len(out) >= limit:
                break
        return out

    @app.get("/api/forex/rules")
    async def rules():
        from rules.rule_engine import RuleEngine

        engine = RuleEngine()
        return engine.rules

    @app.post("/api/forex/run")
    async def run(instrument: str | None = None):
        runner = get_runner()
        summary = runner.run_cycle(instrument)
        return _normalize_signal(summary)

    @app.get("/api/forex/log")
    async def log(limit: int = 50):
        runner = get_runner()
        try:
            rows = runner.log.query(limit=limit)
            return rows
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--loop", type=float, default=30.0, help="seconds between cycles")
    args = parser.parse_args()

    app = create_app(loop_interval=args.loop)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


app = create_app()

if __name__ == "__main__":
    main()
