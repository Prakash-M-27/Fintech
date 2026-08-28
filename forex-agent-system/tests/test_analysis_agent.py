"""Tests for graph/nodes/analysis_agent.py — indicators & sentiment.

WHY these tests exist:
    The Analysis Agent produces the `indicators` and `sentiment` that drive
    the rule engine. Wrong indicators -> wrong but confident signals. We test
    the pure math (RSI bounds, MA correctness, support/resistance) and the
    sentiment fallback (keyword heuristic when no LLM configured), so the
    downstream decision input is trustworthy.
"""

from __future__ import annotations

import pytest

from graph.nodes.analysis_agent import (
    _keyword_sentiment,
    compute_indicators,
    rsi,
    sentiment_classify,
    simple_ma,
)


def make_ohlcv(closes):
    import pandas as pd
    from datetime import datetime, timedelta, timezone

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    prev = 80.0
    for i, c in enumerate(closes):
        prev = c
        rows.append({
            "ts": (base + timedelta(days=i)).isoformat(),
            "open": c, "high": c + 0.1, "low": c - 0.1,
            "close": c, "volume": 1000,
        })
    return rows


class TestRsi:
    def test_bound_0_to_100(self):
        px = list(range(50, 100))
        val = rsi(
            __import__("pandas").Series(px, dtype=float)
        )
        assert 0.0 <= val <= 100.0

    def test_uptrend_high_rsi(self):
        px = [100 + i for i in range(30)]
        s = __import__("pandas").Series(px, dtype=float)
        assert rsi(s) > 50


class TestSimpleMA:
    def test_window_average(self):
        s = __import__("pandas").Series([1.0, 2.0, 3.0, 4.0])
        assert simple_ma(s, 3) == pytest.approx((2 + 3 + 4) / 3)

    def test_short_data_uses_mean(self):
        s = __import__("pandas").Series([5.0, 6.0])
        assert simple_ma(s, 10) == pytest.approx(5.5)


class TestComputeIndicators:
    def test_structure_and_mas(self):
        closes = [100.0, 101.0, 102.0, 103.0, 104.0] * 15
        ind = compute_indicators(make_ohlcv(closes))
        assert "rsi" in ind and "close" in ind
        assert "MA20" in ind["mas"] and "MA50" in ind["mas"]
        assert "support" in ind and "resistance" in ind
        assert ind["close"] == pytest.approx(closes[-1])
        assert ind["support"] <= ind["close"]
        assert ind["resistance"] >= ind["close"]

    def test_no_data_raises(self):
        with pytest.raises(ValueError):
            compute_indicators([])


class TestSentimentKeyword:
    def test_bullish_dominant(self):
        senti, just = _keyword_sentiment([
            {"headline": "Rupee strengthens, rally on rate-cut hopes"},
        ])
        assert senti == "bullish"

    def test_bearish_dominant(self):
        senti, just = _keyword_sentiment([
            {"headline": "Rupee weakens as sell-off pressures exporters"},
        ])
        assert senti == "bearish"

    def test_neutral_when_no_signal(self):
        senti, just = _keyword_sentiment([
            {"headline": "Flat session in quiet trade"},
        ])
        assert senti == "neutral"

    def test_empty_news_is_neutral(self):
        senti, just = _keyword_sentiment([])
        assert senti == "neutral"


class TestSentimentClassify:
    def test_empty_news_neutral(self):
        res = sentiment_classify([], model="")
        assert res["sentiment"] == "neutral"

    def test_no_model_uses_keyword(self):
        res = sentiment_classify(
            [{"headline": "Rupee strengthens on hawkish RBI outlook"}], model=""
        )
        assert res["sentiment"] in ("bullish", "bearish", "neutral")

    def test_always_bounded_label(self):
        # Even with arbitrary news, label must be one of the three.
        res = sentiment_classify(
            [{"headline": "zqxwy", "summary": "noise"}], model=""
        )
        assert res["sentiment"] in ("bullish", "bearish", "neutral")
