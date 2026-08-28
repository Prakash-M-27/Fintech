"""Strategy Agent — evaluates declarative rules; emits the proposed signal.

WHY this node does NOT call an LLM to decide the trade:
    The decision must be deterministic, auditable and reproducible for
    backtesting and evals. A probabilistic model "deciding" a trade breaks all
    three. The strategy comes from `rules/signal_rules.yaml` evaluated by
    `rule_engine.py`; the LLM is used only in the Analysis Agent for news
    sentiment and to compose a human-readable reason string here. This keeps
    the strategy a pure function of (indicators, sentiment) — exactly what we
    feed the backtest harness and the golden eval dataset.
"""

from __future__ import annotations

import logging

from graph.state import TradeState
from rules.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


def strategy_agent_node(state: TradeState, engine: RuleEngine | None = None) -> TradeState:
    """Run the rule engine and write `proposed_signal`.

    `engine` is injectable for tests and backtests (so tests can load custom
    YAML without touching the shared engine). Falls back to the default engine
    which reads rules/signal_rules.yaml.
    """
    engine = engine or RuleEngine()
    indicators = state.get("indicators") or {}
    sentiment = state.get("sentiment") or "neutral"

    result = engine.evaluate(
        indicators=indicators,
        sentiment=sentiment,
        spread_pips=indicators.get("spread_pips"),
    )

    state["proposed_signal"] = {
        "action": result["action"],
        "rule": result["rule"],
        "reason": result["reason"],
    }
    return state
