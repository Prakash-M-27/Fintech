"""Tests for api_server.py — the always-on forex REST service.

WHY these tests exist:
    The forex service is what the frontend talks to, so the HTTP contract must
    be stable. These tests verify the endpoints exist, return the expected
    shapes, and that triggering a run persists a decision.
"""

from __future__ import annotations

import pytest

from api_server import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Very long loop interval so the background task doesn't spam during tests.
    app = create_app(loop_interval=99999)
    with TestClient(app) as c:
        yield c


def test_health(client):
    data = client.get("/api/forex/health").json()
    assert data["status"] == "running"
    assert data["trading_mode"] == "paper"
    assert "USDINR" in data["instruments"]


def test_rules_endpoint(client):
    rules = client.get("/api/forex/rules").json()
    assert isinstance(rules, list)
    assert len(rules) >= 1
    names = {r["name"] for r in rules}
    assert "oversold_bullish_news" in names


def test_run_then_decisions(client):
    r = client.post("/api/forex/run?instrument=USDINR")
    assert r.status_code == 200
    body = r.json()
    assert body["action"] in ("BUY", "SELL", "HOLD")
    assert body["instrument"] == "USDINR"
    assert "trace_id" in body

    decs = client.get("/api/forex/decisions").json()
    assert len(decs) >= 1
    d0 = decs[0]
    for key in ("trace_id", "instrument", "action", "risk_approved",
                "execution_status", "ts"):
        assert key in d0


def test_signals_only_buy_sell(client):
    # Signals endpoint should never return HOLD entries.
    signals = client.get("/api/forex/signals").json()
    for s in signals:
        assert s["action"] in ("BUY", "SELL")


def test_log_endpoint(client):
    log = client.get("/api/forex/log").json()
    assert isinstance(log, list) or "error" in log
