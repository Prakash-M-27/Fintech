"""Tests for storage/trade_log.py — the decision/rejection audit log.

WHY these tests exist:
    The traceability requirement depends on every decision (approved AND
    rejected) being durably recorded. These tests verify the log captures a
    full signal lifecycle, that rejections are not dropped, and that the
    sqlite-url path parsing is correct.
"""

from __future__ import annotations

import pytest

from storage.trade_log import TradeLog, _sqlite_path_from_url


class TestPathParsing:
    def test_sqlite_relative(self):
        assert _sqlite_path_from_url("sqlite:///forex_trades.db") == "forex_trades.db"

    def test_sqlite_absolute(self):
        assert _sqlite_path_from_url("sqlite:////abs/path/x.db") == "/abs/path/x.db"

    def test_in_memory(self):
        assert _sqlite_path_from_url("sqlite://") == ":memory:"

    def test_postgres_rejected(self):
        with pytest.raises(ValueError):
            _sqlite_path_from_url("postgresql://user:pw@host/db")


class TestTradeLog:
    def test_log_and_query_approved(self):
        log = TradeLog("sqlite://")
        log.log_decision({
            "trace_id": "t1", "instrument": "USDINR",
            "proposed_signal": {"action": "BUY", "rule": "r1"},
            "sentiment": "bullish", "indicators": {"rsi": 25},
            "risk_check": {"approved": True, "reason": "ok"},
            "execution_result": {"status": "FILLED"},
        }, mode="paper")
        rows = log.query(approved_only=True)
        assert len(rows) == 1
        assert rows[0]["signal_action"] == "BUY"
        assert rows[0]["risk_approved"] == 1

    def test_rejection_is_logged_not_dropped(self):
        log = TradeLog("sqlite://")
        log.log_decision({
            "trace_id": "t2", "instrument": "USDINR",
            "proposed_signal": {"action": "BUY", "rule": "r1"},
            "sentiment": "bearish", "indicators": {"rsi": 25},
            "risk_check": {"approved": False, "reason": "FEMA/SEBI/RBI block"},
            "execution_result": {"status": "REJECTED"},
        }, mode="paper")
        rows = log.query(approved_only=False)
        assert len(rows) == 1
        assert rows[0]["risk_approved"] == 0
        assert "FEMA/SEBI/RBI" in rows[0]["risk_reason"]

    def test_filter_by_instrument(self):
        log = TradeLog("sqlite://")
        for inst in ("USDINR", "EURINR"):
            log.log_decision({
                "trace_id": "x", "instrument": inst,
                "proposed_signal": {"action": "HOLD", "rule": None},
                "risk_check": {"approved": False, "reason": "hold"},
                "execution_result": {"status": "REJECTED"},
            }, mode="paper")
        assert len(log.query(instrument="EURINR")) == 1
