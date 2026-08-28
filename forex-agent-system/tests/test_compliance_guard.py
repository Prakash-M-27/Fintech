"""Tests for risk/compliance_guard.py — the FEMA/SEBI/RBI allow-list.

WHY these tests exist:
    The allow-list is a regulatory gate. Every rejection path must be verified
    so that a blocked instrument can never slip through. We test the
    authorized set, case/whitespace normalisation, and clearly-rejected
    OTC/spot international pairs.
"""

from __future__ import annotations

import pytest

from risk.compliance_guard import (
    DEFAULT_ALLOWED,
    compliance_guard,
    is_allowed_instrument,
)


class TestIsAllowed:
    def test_authorized_exchange_instruments_allowed(self):
        for inst in DEFAULT_ALLOWED:
            assert is_allowed_instrument(inst) is True

    def test_lowercase_normalised(self):
        assert is_allowed_instrument("usdinr") is True

    def test_whitespace_normalised(self):
        assert is_allowed_instrument("  USDINR  ") is True

    @pytest.mark.parametrize("blocked", [
        "EUR/USD", "EURUSD", "GBP/USD", "GBPUSD", "USD/JPY", "USDJPY",
        "AUDUSD", "XAUUSD", "", "BTCUSD", "US30",
    ])
    def test_otc_and_spot_pairs_blocked(self, blocked):
        # Non-authorized, non exchange-traded cross / spot pairs must fail.
        assert is_allowed_instrument(blocked) is False


class TestComplianceGuard:
    def test_approved_instrument_reason(self):
        res = compliance_guard("USDINR")
        assert res["ok"] is True
        assert "USDINR" in res["reason"]

    def test_blocked_otc_pair(self):
        res = compliance_guard("EUR/USD")
        assert res["ok"] is False
        assert "FEMA/SEBI/RBI" in res["reason"]

    def test_empty_instrument_rejected(self):
        res = compliance_guard("")
        assert res["ok"] is False

    def test_none_instrument_rejected(self):
        res = compliance_guard(None)  # type: ignore[arg-type]
        assert res["ok"] is False

    def test_custom_allowlist_honoured(self):
        # A custom allow-list that excludes USDINR must reject it.
        res = compliance_guard("USDINR", allowed=("EURINR", "GBPINR"))
        assert res["ok"] is False
