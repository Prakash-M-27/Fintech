"""Tests for risk/position_sizing.py — the per-trade risk cap.

WHY these tests exist:
    Position sizing caps worst-case loss at a small fraction of equity. Every
    boundary case (zero/negative equity, huge risk, zero stop distance, tiny
    budget) must be covered so a misconfiguration can never silently balloon
    exposure.
"""

from __future__ import annotations

import pytest

from risk.position_sizing import as_percentage, position_size


class TestPositionSize:
    def test_caps_loss_to_risk_pct(self):
        # equity 100k, risk 1.5%, stop 30 pips * 0.0025 = 0.075 per unit.
        # budget = 1500; units = floor(1500 / 0.075) = 20000.
        size = position_size(100_000.0, 1.5, 30.0)
        assert size == 20000

    def test_risk_pct_clamped_above_ten_percent(self):
        # Even if config passes 50%, clamp to 10% max — never exceed 10% risk.
        size = position_size(100_000.0, 50.0, 30.0)
        assert size == int((0.10 * 100_000.0) / (30 * 0.0025))

    def test_risk_pct_clamped_below_one_percent(self):
        size = position_size(100_000.0, 0.01, 30.0)
        # clamped up to 1%
        assert size == int((0.01 * 100_000.0) / (30 * 0.0025))

    @pytest.mark.parametrize("kwargs", [
        {"equity": 0.0, "risk_pct": 1.5, "stop_distance_pips": 30},
        {"equity": -100, "risk_pct": 1.5, "stop_distance_pips": 30},
        {"equity": 100_000, "risk_pct": 1.5, "stop_distance_pips": 0},
        {"equity": 100_000, "risk_pct": 1.5, "stop_distance_pips": -5},
    ])
    def test_invalid_inputs_return_zero(self, kwargs):
        assert position_size(**kwargs) == 0

    def test_max_units_respected(self):
        size = position_size(100_000.0, 1.5, 30.0, max_units=500)
        assert size == 500

    def test_tiny_budget_returns_zero(self):
        # Budget can't cover even one unit.
        assert position_size(1.0, 1.5, 30.0) == 0


class TestAsPercentage:
    def test_basic(self):
        assert as_percentage(100_000.0, 1_500.0) == pytest.approx(0.015)

    def test_zero_equity(self):
        assert as_percentage(0.0, 100.0) == 0.0
