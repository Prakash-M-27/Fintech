"""LangSmith golden datasets + evals for the Strategy Agent.

WHY this exists:
    The goal is to catch *silent behavior drift*: if someone edits
    `rules/signal_rules.yaml` or the sentiment prompt, the system might change
    what signals it produces without anyone noticing. This module builds a
    LangSmith dataset of golden (indicators, sentiment) -> expected-signal
    pairs and registers an evaluator that compares the Strategy Agent's
    decision to the expected label. It is meant to run whenever the rule file
    or sentiment prompt changes.

DESIGN NOTE:
    `strategy_decision()` is the production function under test. It is kept
    dependency-free (pure rule-engine call) so the *golden-case logic* is
    unit-testable offline, and the LangSmith wiring merely wraps it.

    Dataset creation / eval execution require LANGCHAIN_API_KEY and a network.
    This module degrades gracefully to an explicit message when unavailable,
    so importing it never breaks an offline run.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

REQUIRED_ENV = ("LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2")

# --- Golden cases ------------------------------------------------------------
# Derived deterministically from rules/signal_rules.yaml so the oracle is
# stable. Fields: indicators, sentiment, expected_action.
GOLDEN_CASES: list[dict] = [
    # oversold_bullish_news: rsi<30 + bullish + spread<2  -> BUY
    {
        "indicators": {"rsi": 25.0, "close": 83.5, "mas": {"MA20": 84.0, "MA50": 84.5}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "expected_action": "BUY",
    },
    # fails the tight-spread guard -> HOLD
    {
        "indicators": {"rsi": 25.0, "close": 83.5, "mas": {"MA20": 84.0, "MA50": 84.5}, "spread_pips": 5.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    # overbought_bearish_news: rsi>70 + bearish -> SELL
    {
        "indicators": {"rsi": 78.0, "close": 90.0, "mas": {"MA20": 88.0, "MA50": 87.0}, "spread_pips": 1.5},
        "sentiment": "bearish",
        "expected_action": "SELL",
    },
    # strong_uptrend: price>MA20 + neutral -> BUY
    {
        "indicators": {"rsi": 55.0, "close": 85.0, "mas": {"MA20": 84.0, "MA50": 83.0}, "spread_pips": 1.0},
        "sentiment": "neutral",
        "expected_action": "BUY",
    },
    # strong_downtrend: price<MA20 + neutral -> SELL
    {
        "indicators": {"rsi": 55.0, "close": 82.0, "mas": {"MA20": 84.0, "MA50": 85.0}, "spread_pips": 1.0},
        "sentiment": "neutral",
        "expected_action": "SELL",
    },
    # no rule matches -> HOLD
    {
        "indicators": {"rsi": 55.0, "close": 85.0, "mas": {"MA20": 85.0, "MA50": 86.0}, "spread_pips": 3.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    {
        "indicators": {"rsi": 60.0, "close": 86.0, "mas": {"MA20": 85.0, "MA50": 84.0}, "spread_pips": 1.0},
        "sentiment": "bearish",
        "expected_action": "HOLD",
    },
    # Price exactly at MA20 + neutral -> neither above nor below -> HOLD
    {
        "indicators": {"rsi": 55.0, "close": 85.0, "mas": {"MA20": 85.0, "MA50": 86.0}, "spread_pips": 1.0},
        "sentiment": "neutral",
        "expected_action": "HOLD",
    },
    # Bullish sentiment but neither oversold nor overbought and price==MA -> HOLD
    {
        "indicators": {"rsi": 50.0, "close": 84.0, "mas": {"MA20": 84.0, "MA50": 85.0}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    # Downtrend rule: price below MA20 + NEUTRAL sentiment -> SELL
    {
        "indicators": {"rsi": 55.0, "close": 82.0, "mas": {"MA20": 84.0, "MA50": 85.0}, "spread_pips": 1.2},
        "sentiment": "neutral",
        "expected_action": "SELL",
    },
    # Oversold but with spread exactly at threshold (2) -> NOT < 2 -> HOLD
    {
        "indicators": {"rsi": 28.0, "close": 83.0, "mas": {"MA20": 84.0, "MA50": 84.5}, "spread_pips": 2.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    # Overbought but bullish sentiment: needs bearish to fire SELL -> HOLD
    {
        "indicators": {"rsi": 78.0, "close": 91.0, "mas": {"MA20": 88.0, "MA50": 87.0}, "spread_pips": 1.5},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    # RSI exactly 30 (not <30) + bullish + tight spread -> HOLD
    {
        "indicators": {"rsi": 30.0, "close": 83.5, "mas": {"MA20": 84.0, "MA50": 84.5}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
    # Uptrend + bullish (sentiment not neutral, downtrend rule skipped) -> HOLD
    {
        "indicators": {"rsi": 60.0, "close": 85.0, "mas": {"MA20": 83.0, "MA50": 82.0}, "spread_pips": 1.0},
        "sentiment": "bullish",
        "expected_action": "HOLD",
    },
]


def strategy_decision(indicators: dict, sentiment: str) -> str:
    """Production decision function under eval: run the rule engine.

    Kept standalone (no LangChain / no state object dependency) so it is easy
    to drive both from the LangSmith harness AND from offline golden tests.
    """
    from graph.nodes.strategy_agent import strategy_agent_node

    state = {
        "instrument": "USDINR",
        "indicators": dict(indicators),
        "sentiment": sentiment,
        "proposed_signal": None,
    }
    strategy_agent_node(state)
    return state["proposed_signal"]["action"]


def accuracy_evaluator(run: object, example: object) -> dict:
    """LangSmith evaluator: compare produced action to expected action."""
    inputs = run.inputs  # type: ignore[attr-defined]
    produced = strategy_decision(inputs["indicators"], inputs["sentiment"])
    expected = example.outputs["expected_action"]  # type: ignore[attr-defined]
    return {
        "key": "strategy_accuracy",
        "score": int(produced == expected),
        "comment": f"produced={produced!r} expected={expected!r}",
    }


def _ready() -> tuple[bool, str]:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        return False, f"missing env vars: {missing}"
    return True, "ok"


def create_dataset(name: str = "forex-strategy-golden") -> None:
    """Create/refresh the LangSmith golden dataset from GOLDEN_CASES."""
    ok, why = _ready()
    if not ok:
        logger.warning("LangSmith dataset not created: %s", why)
        return
    from langsmith import Client

    client = Client()
    dataset = client.create_dataset(
        dataset_name=name,
        description="Golden (indicators, sentiment) -> expected signal for the Strategy Agent",
    )
    for case in GOLDEN_CASES:
        client.create_example(
            inputs={
                "indicators": case["indicators"],
                "sentiment": case["sentiment"],
            },
            outputs={"expected_action": case["expected_action"]},
            dataset_id=dataset.id,
        )
    logger.info("Created LangSmith dataset '%s' with %d examples", name, len(GOLDEN_CASES))


def run_eval(
    dataset: str | None = None,
    experiment_prefix: str = "strategy",
) -> None:
    """Run a regression eval of the strategy decision over the golden dataset."""
    ok, why = _ready()
    if not ok:
        logger.warning("LangSmith eval not run: %s", why)
        return
    from langsmith import Client, evaluate

    client = Client()
    dataset_name = dataset or "forex-strategy-golden"

    def predict(inputs: dict) -> dict:
        return {"predicted_action": strategy_decision(inputs["indicators"], inputs["sentiment"])}

    evaluate(
        predict,
        data=dataset_name,
        evaluators=[accuracy_evaluator],
        experiment_prefix=experiment_prefix,
        client=client,
    )


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    if cmd == "create":
        create_dataset()
    else:
        run_eval()
