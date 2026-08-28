"""Tests for risk/stop_take_calculator.py — mandatory SL/TP on every trade.

WHY these tests exist:
    A trade without a valid exit plan must be rejected, not guessed. We verify
    SL/TP direction for long/short, and that every invalid input raises so the
    Risk Agent can convert it into a clean rejection.
"""

from __future__ import annotations

import pytest

from risk.stop_take_calculator import StopTakeError, stop_take


class TestStopTakeBuy:
    def test_buy_stop_below_entry_profit_above(self):
        r = stop_take("BUY", entry=83.5, sl_pips=30, tp_pips=60)
        assert r["stop_loss"] == pytest.approx(83.5 - 30 * 0.0025)
        assert r["take_profit"] == pytest.approx(83.5 + 60 * 0.0025)
        assert r["stop_loss"] < 83.5
        assert r["take_profit"] > 83.5


class TestStopTakeSell:
    def test_sell_stop_above_entry_profit_below(self):
        r = stop_take("SELL", entry=83.5, sl_pips=30, tp_pips=60)
        assert r["stop_loss"] == pytest.approx(83.5 + 30 * 0.0025)
        assert r["take_profit"] == pytest.approx(83.5 - 60 * 0.0025)


@pytest.mark.parametrize("bad_kwargs", [
    {"action": "HOLD"},                       # HOLD can't carry SL/TP
    {"action": "HODL"},                       # unknown side
    {"action": "BUY", "sl_pips": 0},          # zero SL
    {"action": "BUY", "sl_pips": -5},         # negative SL
    {"action": "BUY", "tp_pips": 0},          # zero TP
    {"action": "BUY", "tp_pips": -5},         # negative TP
    {"action": "BUY", "entry": 0},            # zero entry
    {"action": "BUY", "entry": -10},          # negative entry
])
def test_invalid_inputs_raise(bad_kwargs):
    kwargs = {"action": "BUY", "entry": 83.5, "sl_pips": 30, "tp_pips": 60}
    kwargs.update(bad_kwargs)
    with pytest.raises(StopTakeError):
        stop_take(**kwargs)
