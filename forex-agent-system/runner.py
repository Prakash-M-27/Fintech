"""Reusable forex-agent cycle runner (shared by CLI and the API server).

WHY this module exists:
    Both the CLI (`main.py`) and the always-on API server (`api_server.py`)
    must run the exact same graph and persist the exact same outcome. Putting
    the run logic here once guarantees the two entrypoints never diverge — the
    same single source of truth used by `main.py run` is reused by the service
    loop, so live/server behavior matches local CLI behavior.

This runner is self-contained (SQLite + the LangGraph pipeline) and does not
depend on the pre-existing `server/` package at all, so there are no Python
module-name collisions between the two systems.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config.settings import load_settings
from graph.build_graph import compile_graph
from storage.trade_log import TradeLog

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """A snapshot of one executed forex-agent cycle plus in-memory history."""

    result: dict  # the final TradeState
    trace_id: str
    instrument: str
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def signal_action(self) -> str:
        return (self.result.get("proposed_signal") or {}).get("action", "HOLD")

    @property
    def risk_approved(self) -> bool:
        return bool((self.result.get("risk_check") or {}).get("approved"))

    @property
    def execution_status(self) -> str:
        return (self.result.get("execution_result") or {}).get("status", "NONE")


class ForexRunner:
    """Runs forex-agent cycles, persists outcomes, and keeps recent history.

    `history` is an in-memory ring used by the API for fast reads; point-in-time
    ground truth lives in the SQLite `TradeLog`.
    """

    def __init__(self, history_limit: int = 200) -> None:
        self.settings = load_settings()
        self.log = TradeLog(self.settings.database_url)
        self.history_limit = history_limit
        self.history: list[RunSummary] = []
        self.continuous_running = False
        self.last_cycle_ts: str | None = None
        self.cycles_total = 0
        self.last_error: str | None = None

    def instruments(self) -> list[str]:
        return list(self.settings.allowed_instruments) or ["USDINR"]

    def run_cycle(self, instrument: str | None = None) -> RunSummary:
        """Execute one full graph cycle for an instrument and persist it.

        WHY this is the single entrypoint: it wraps `compile_graph().invoke()`
        (which applies LangSmith tracing tags + the risk conditional edge),
        then records the trace in SQLite and keeps an in-memory snapshot.
        """
        instrument = (instrument or self.settings.default_instrument).upper()
        trace_id = uuid.uuid4().hex
        invoke = compile_graph()
        final = invoke({"instrument": instrument, "trace_id": trace_id})

        try:
            self.log.log_decision(final, mode=self.settings.trading_mode.value)
        except Exception as exc:  # noqa: BLE001 - persistence must not crash the loop
            logger.warning("failed to persist decision: %s", exc)

        summary = RunSummary(
            result=final,
            trace_id=trace_id,
            instrument=instrument,
        )
        self.history.insert(0, summary)
        if len(self.history) > self.history_limit:
            self.history = self.history[: self.history_limit]

        self.last_cycle_ts = summary.executed_at
        self.cycles_total += 1
        logger.info(
            "[cycle] instrument=%s signal=%s risk_approved=%s exec=%s trace=%s",
            instrument, summary.signal_action, summary.risk_approved,
            summary.execution_status, trace_id,
        )
        return summary

    async def continuous_loop(self, interval_seconds: float) -> None:
        """Run cycles forever on a round-robin schedule across instruments.

        WHY continuous: the frontend needs a live agent feed; this task keeps
        the forex engine producing decisions on a cadence (one instrument at a
        time) so both REST reads and any polling UI always have fresh data.
        """
        self.continuous_running = True
        instruments = self.instruments()
        idx = 0
        logger.info("forex-agent continuous loop started (interval=%.0fs, instruments=%s)",
                    interval_seconds, instruments)
        while self.continuous_running:
            try:
                inst = instruments[idx % len(instruments)]
                idx += 1
                self.run_cycle(inst)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                logger.error("forex-agent loop error: %s", exc)
            await __import__("asyncio").sleep(interval_seconds)

    def stop(self) -> None:
        self.continuous_running = False

    def health(self) -> dict:
        return {
            "status": "running" if self.continuous_running else "idle",
            "trading_mode": self.settings.trading_mode.value,
            "cycles_total": self.cycles_total,
            "last_cycle_at": self.last_cycle_ts,
            "last_error": self.last_error,
            "instruments": self.instruments(),
        }


_runner: ForexRunner | None = None


def get_runner() -> ForexRunner:
    """Return a process-wide singleton runner (used by the API server)."""
    global _runner
    if _runner is None:
        _runner = ForexRunner()
    return _runner
