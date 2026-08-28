"""Shared LangGraph state schema for the forex multi-agent system.

WHY a single typed state:
    Every node reads & writes the same `TradeState` object. Keeping one
    canonical schema means no node can silently produce an untyped,
    untraceable side-channel of data — everything each downstream node (and
    the LangSmith trace) observes flows through this one object. This is what
    makes the whole signal chain auditable end-to-end.

The lifecycle of a signal through the graph:
    raw_ticks/news_events  --(data_agent)-->  indicators/sentiment
        --(analysis_agent)--> proposed_signal
        --(strategy_agent)--> risk_check
        --(risk_agent)--> execution_result  (only if risk_check.approved)
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# Possible signal actions. HOLD means no rule matched (or the only decision
# was "do nothing"); BUY/SELL are real, risk-gated candidate actions.
SignalAction = Literal["BUY", "SELL", "HOLD"]

# Sentiment produced by the LLM sentiment step. Deliberately coarse and
# bounded: the model is never asked to forecast price, only to label news.
Sentiment = Literal["bullish", "bearish", "neutral"]


class TradeState(TypedDict, total=False):
    """The single shared object threaded through every graph node.

    Fields are all optional (total=False) so that nodes can partially
    populate the state as they run and the graph still type-checks cleanly.
    """

    instrument: str
    raw_ticks: list[dict[str, Any]]
    news_events: list[dict[str, Any]]
    # Computed technicals (RSI, moving averages, support/resistance levels…)
    indicators: dict[str, Any]
    # LLM-produced news sentiment label + one-line justification.
    sentiment: Sentiment
    sentiment_justification: str
    # Strategy Agent output: the declarative rule engine's decision.
    proposed_signal: dict[str, Any] | None
    # Risk Agent output. `approved` MUST be True before execution is reached.
    risk_check: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    # Private transient slot for OHLCV bars consumed by the Analysis Agent.
    _ohlcv: list[dict[str, Any]]
    # Correlation id for LangSmith tracing / Postgres audit trail.
    trace_id: str
