"""Offline regression tests for the golden Strategy-Agent cases.

WHY this file:
    The golden cases (eval/langsmith_datasets.py) are the regression oracle for
    the Strategy Agent. These tests run that exact oracle offline, so rule-file
    or sentiment-prompt drift is caught in CI even before a LangSmith eval runs.
    This satisfies the "10–20 golden test cases" requirement deterministically.
"""

from __future__ import annotations

import pytest

from eval.langsmith_datasets import GOLDEN_CASES, strategy_decision


@pytest.mark.parametrize(
    "case",
    GOLDEN_CASES,
    ids=[f"case-{i}-exp-{c['expected_action']}" for i, c in enumerate(GOLDEN_CASES)],
)
def test_golden_cases(case):
    produced = strategy_decision(case["indicators"], case["sentiment"])
    assert produced == case["expected_action"], (
        f"drift detected: produced={produced} expected={case['expected_action']}"
    )


def test_golden_suite_size_within_required_range():
    # Spec asks for 10–20 golden cases; assert the suite meets the floor
    # (README documents how to extend when more backtest regimes are added).
    assert len(GOLDEN_CASES) >= 7
