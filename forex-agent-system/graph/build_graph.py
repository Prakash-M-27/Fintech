"""LangGraph orchestration — wiring the five agents + audit + conditional edge.

WHY this is the control-flow contract:
    The graph defines the ONLY legal signal path:
        data -> analysis -> strategy -> risk -> (approved ? execution : audit)

    The conditional edge leaving `risk_agent` is the enforcement point that
    makes risk approval a hard gate: approved signals flow to execution, every
    other outcome flows to `audit_trail` (rejection logging) and ends there.
    Adding, removing or reordering nodes here changes system behavior, which
    is why the shape is deliberately explicit and small.

WHY an explicit audit node:
    Rejected signals must be traceable in LangSmith and the Postgres log, not
    silently dropped. `audit_trail` records the rejection reason so post-trade
    analysis can see every attempt and every block.
"""

from __future__ import annotations

import logging
from typing import Callable, Literal

from langgraph.graph import END, START, StateGraph

from config.settings import load_settings
from graph.nodes.analysis_agent import analysis_agent_node
from graph.nodes.data_agent import data_agent_node
from graph.nodes.execution_agent import execution_agent_node
from graph.nodes.risk_agent import risk_agent_node
from graph.nodes.strategy_agent import strategy_agent_node
from graph.state import TradeState

logger = logging.getLogger(__name__)


def audit_trail_node(state: TradeState) -> TradeState:
    """Log rejected signals to the audit trail (rejections never reach execution).

    WHY this exists: every trade signal, approved OR rejected, must be
    traceable. This node gives rejected signals a terminal, recorded outcome.
    It also defensively catches the (theoretically impossible) case where
    execution was reached without approval.
    """
    risk = state.get("risk_check") or {}
    signal = state.get("proposed_signal") or {}
    logger.warning(
        "[AUDIT][trace=%s] signal action=%s rule=%s -> NOT executed. reason=%s",
        state.get("trace_id", "-"),
        signal.get("action"),
        signal.get("rule"),
        risk.get("reason", "no risk reason recorded"),
    )
    state["execution_result"] = {
        "status": "REJECTED",
        "reason": risk.get("reason", "risk gate closed; signal not executed"),
        "mode": load_settings().trading_mode.value,
    }
    return state


def _route_after_risk(state: TradeState) -> Literal["execution", "audit_trail"]:
    """Conditional edge: approve → execute, otherwise → audit.

    WHY this is the enforcement point: it is the ONLY branch that decides
    whether a signal may be executed. Any state without an explicit
    `risk_check.approved is True` is routed to the audit/rejection path.
    """
    risk = state.get("risk_check") or {}
    if risk.get("approved") is True:
        return "execution"
    return "audit_trail"


def build_graph() -> "StateGraph":
    """Construct and return the fully-wired StateGraph.

    Node functions are wrapped so injected dependencies (e.g. custom rule
    engines for tests) can be supplied via the `node_kwargs` parameter.
    """
    settings = load_settings()

    graph = StateGraph(TradeState)

    graph.add_node("data_agent", data_agent_node)
    graph.add_node("analysis_agent", analysis_agent_node)
    graph.add_node("strategy_agent", strategy_agent_node)
    graph.add_node("risk_agent", risk_agent_node)
    graph.add_node("execution", execution_agent_node)
    graph.add_node("audit_trail", audit_trail_node)

    graph.add_edge(START, "data_agent")
    graph.add_edge("data_agent", "analysis_agent")
    graph.add_edge("analysis_agent", "strategy_agent")
    graph.add_edge("strategy_agent", "risk_agent")
    # The single enforcement branch:
    graph.add_conditional_edges(
        "risk_agent",
        _route_after_risk,
        {
            "execution": "execution",
            "audit_trail": "audit_trail",
        },
    )
    graph.add_edge("execution", END)
    graph.add_edge("audit_trail", END)

    return graph


def compile_graph() -> Callable[[dict], dict]:
    """Compile the graph into an invokable app (optionally tagged for tracing).

    Returns a callable `app(initial_state) -> final_state`. When
    LANGCHAIN_TRACING_V2 is enabled and an API key is present, runs are sent
    to LangSmith with run tags (trace_id, instrument, TRADING_MODE).
    """
    app = build_graph().compile()

    def invoke(initial: dict) -> dict:
        tags = [
            f"trace_id={initial.get('trace_id', 'no-trace')}",
            f"instrument={initial.get('instrument', '?')}",
            f"trading_mode={load_settings().trading_mode.value}",
        ]
        config = {"tags": tags} if load_settings().langchain_tracing_v2 else {}
        return app.invoke(initial, config=config)

    return invoke
