"""Shared pytest helpers / fixtures for the forex-agent-system test suite."""

from __future__ import annotations

import pytest

from config.settings import Settings
from risk.compliance_guard import DEFAULT_ALLOWED


def make_settings(**overrides) -> Settings:
    """Build a Settings with test-friendly overrides (all in-memory, no .env)."""
    base = dict(
        trading_mode="paper",
        default_instrument="USDINR",
        account_equity=100_000.0,
        risk_per_trade_pct=1.5,
        sl_pips=30.0,
        tp_pips=60.0,
        allowed_instruments=list(DEFAULT_ALLOWED),
        langchain_tracing_v2=False,
    )
    base.update(overrides)
    return Settings(**base)


def approved_signal_state(**overrides) -> dict:
    """A fully-formed state whose proposed_signal is an approved BUY.

    Used to test nodes downstream of risk (execution) in isolation.
    """
    state = {
        "instrument": "USDINR",
        "raw_ticks": [],
        "news_events": [],
        "indicators": {"rsi": 25.0, "close": 83.5, "mas": {}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "proposed_signal": {
            "action": "BUY",
            "rule": "oversold_bullish_news",
            "reason": "RSI oversold + bullish news + tight spread",
        },
        "risk_check": {
            "approved": True,
            "action": "BUY",
            "position_size": 2000,
            "stop_loss": 83.425,
            "take_profit": 83.65,
            "entry": 83.5,
            "reason": "all checks passed",
        },
        "execution_result": None,
        "trace_id": "test-trace",
    }
    state.update(overrides)
    return state


@pytest.fixture
def settings_fixture():
    return make_settings()


@pytest.fixture
def approved_state():
    return approved_signal_state()
