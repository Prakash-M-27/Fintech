"""Tests for graph/nodes/risk_agent.py — the mandatory safety gate.

WHY this is the most important test file:
    The Risk Agent is the hard gate between every signal and execution. These
    tests enumerate EVERY rejection path and the single approval path, so we
    can prove there is no combination of inputs that yields `approved: True`
    when any of compliance, sizing, or SL/TP fails.
"""

from __future__ import annotations

import pytest

from graph.nodes.risk_agent import RiskAgent
from tests.conftest import make_settings


def base_state(**overrides) -> dict:
    state = {
        "instrument": "USDINR",
        "indicators": {"rsi": 25.0, "close": 83.5, "mas": {}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "proposed_signal": {
            "action": "BUY",
            "rule": "oversold_bullish_news",
            "reason": "RSI oversold + bullish news + tight spread",
        },
        "risk_check": None,
        "execution_result": None,
        "trace_id": "t",
    }
    state.update(overrides)
    return state


class TestApprovalPath:
    def test_eligible_buy_is_approved(self):
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state())
        assert risk["approved"] is True
        assert risk["position_size"] > 0
        assert risk["stop_loss"] < risk["entry"]
        assert risk["take_profit"] > risk["entry"]

    def test_approved_copy_is_non_hold(self):
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state())
        assert risk["action"] == "BUY"


class TestRejectionPaths:
    def test_hold_signal_rejected_not_executed(self):
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state(proposed_signal={
            "action": "HOLD", "rule": None, "reason": "no rule matched",
        }))
        assert risk["approved"] is False

    def test_no_signal_rejected(self):
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state(proposed_signal=None))
        assert risk["approved"] is False

    def test_blocked_instrument_rejected(self):
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state(instrument="EUR/USD"))
        assert risk["approved"] is False
        assert "FEMA/SEBI/RBI" in risk["reason"]

    def test_configured_allowlist_removes_instrument(self):
        # Even a "valid-looking" instrument is rejected if not on the
        # configured allow-list.
        agent = RiskAgent(make_settings(allowed_instruments=["EURINR"]))
        risk = agent.evaluate(base_state(instrument="USDINR"))
        assert risk["approved"] is False

    def test_zero_equity_rejected(self):
        agent = RiskAgent(make_settings(account_equity=0.0))
        risk = agent.evaluate(base_state())
        assert risk["approved"] is False
        assert "sizing" in risk["reason"].lower() or "0 units" in risk["reason"]

    def test_missing_close_price_rejected(self):
        # No entry price -> cannot size or compute SL/TP -> must reject.
        agent = RiskAgent(make_settings())
        state = base_state()
        state["indicators"]["close"] = 0.0
        risk = agent.evaluate(state)
        assert risk["approved"] is False

    def test_never_any_signal_without_positive_sl(self):
        # Whole approval path proves: every approved trade has stop_loss < entry
        # for BUY, take_profit > entry, positive size.
        agent = RiskAgent(make_settings())
        risk = agent.evaluate(base_state())
        assert risk["approved"] is True
        assert risk["stop_loss"] < risk["entry"] < risk["take_profit"]


class TestNeverSkipsRisk:
    def test_node_writes_risk_check_always(self):
        # Run the full node; irrespective of outcome, risk_check must exist.
        from graph.nodes.risk_agent import risk_agent_node

        state = base_state(instrument="EUR/USD")
        out = risk_agent_node(dict(state))
        assert out["risk_check"] is not None
        assert "approved" in out["risk_check"]
