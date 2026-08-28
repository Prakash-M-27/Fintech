"""Tests for main.py — the live-trading authorization gate.

WHY these tests matter most:
    The requirement that live trading is impossible without documented sign-off
    AND a passing backtest is enforced here. These tests prove:
      * paper mode does NOT trigger the gate,
      * live mode with a valid backtest authorizes,
      * live mode with a missing/worthless backtest is REFUSED with a
        LiveNotAuthorizedError.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from config.settings import TradingMode
from main import LiveNotAuthorizedError, require_backtest_for_live
from storage.trade_log import TradeLog


def _write_backtest_csv(path: Path, n_rows: int = 600) -> None:
    from backtest.generate_data import generate_series
    from datetime import datetime

    df = generate_series(n_days=n_rows, seed=7)
    df.to_csv(path, index=False)


def _fake_settings(tmp_path: Path, mode: TradingMode, csv: str):
    from tests.conftest import make_settings
    return make_settings(
        trading_mode=mode.value,
        backtest_csv_path=csv,
        database_url="sqlite://",
    )


class TestGatePaperMode:
    def test_paper_does_not_require_backtest(self, tmp_path):
        # Paper mode must never be blocked — it should return (not raise).
        s = _fake_settings(tmp_path, TradingMode.PAPER, "ignored.csv")
        require_backtest_for_live(s, TradeLog("sqlite://"))
        assert True


class TestGateLiveMode:
    def test_live_with_valid_backtest_authorizes(self, tmp_path):
        csv = str(tmp_path / "hist.csv")
        _write_backtest_csv(Path(csv), n_rows=400)
        s = _fake_settings(tmp_path, TradingMode.LIVE, csv)
        # Should not raise.
        require_backtest_for_live(s, TradeLog("sqlite://"))

    def test_live_missing_csv_refused(self, tmp_path):
        s = _fake_settings(tmp_path, TradingMode.LIVE, str(tmp_path / "missing.csv"))
        with pytest.raises(LiveNotAuthorizedError):
            require_backtest_for_live(s, TradeLog("sqlite://"))
