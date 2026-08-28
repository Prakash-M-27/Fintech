"""Tests for rules/rule_engine.py — declarative signal evaluation.

WHY these tests exist:
    The rule engine is the heart of the "decisions are data, not code"
    design. We verify (a) each starter rule fires only when its full
    precondition set holds, (b) HOLD is returned when nothing matches, and
    (c) malformed rules are rejected at load time rather than silently
    disabling a strategy.
"""

from __future__ import annotations

import textwrap

import pytest

from rules.rule_engine import RuleEngine


def make_engine(yaml_src: str) -> RuleEngine:
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(yaml_src)
        path = Path(fh.name)
    return RuleEngine(rules_path=path)


YAML = textwrap.dedent("""\
    - name: oversold_bullish_news
      when:
        rsi_below: 30
        sentiment: bullish
        spread_below_pips: 2
      then:
        action: BUY
        reason: "RSI oversold + bullish news + tight spread"

    - name: overbought_bearish_news
      when:
        rsi_above: 70
        sentiment: bearish
      then:
        action: SELL
        reason: "RSI overbought + bearish news"
""")


@pytest.fixture
def engine():
    return make_engine(YAML)


class TestRuleFiring:
    def test_oversold_bullish_fires_buy(self, engine):
        res = engine.evaluate(
            {"rsi": 25.0, "close": 80.0, "mas": {}, "spread_pips": 1.0},
            sentiment="bullish",
        )
        assert res["action"] == "BUY"

    def test_oversold_but_not_bullish_is_hold(self, engine):
        res = engine.evaluate(
            {"rsi": 25.0, "close": 80.0, "mas": {}}, sentiment="neutral"
        )
        assert res["action"] == "HOLD"

    def test_oversold_but_wide_spread_is_hold(self, engine):
        res = engine.evaluate(
            {"rsi": 25.0, "close": 80.0, "mas": {}}, sentiment="bullish",
            spread_pips=5.0,
        )
        assert res["action"] == "HOLD"

    def test_overbought_bearish_fires_sell(self, engine):
        res = engine.evaluate(
            {"rsi": 75.0, "close": 90.0, "mas": {}}, sentiment="bearish"
        )
        assert res["action"] == "SELL"

    def test_no_match_returns_hold(self, engine):
        res = engine.evaluate(
            {"rsi": 55.0, "close": 80.0, "mas": {}}, sentiment="neutral"
        )
        assert res["action"] == "HOLD"
        assert res["rule"] is None


class TestMalformedRulesRejectedAtLoad:
    def test_unknown_predicate_raises(self):
        with pytest.raises(ValueError):
            make_engine("- name: bad\n  when:\n    not_a_real_pred: 5\n"
                        "  then:\n    action: BUY\n    reason: x")

    def test_missing_then_raises(self):
        with pytest.raises(ValueError):
            make_engine("- name: bad\n  when:\n    rsi_below: 30\n")

    def test_invalid_action_raises(self):
        with pytest.raises(ValueError):
            make_engine("- name: bad\n  when:\n    rsi_below: 30\n"
                        "  then:\n    action: MOON\n    reason: x")
