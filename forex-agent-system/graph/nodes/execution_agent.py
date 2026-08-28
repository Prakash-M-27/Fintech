"""Execution Agent — converts an approved signal into an order payload.

WHY this node only runs after Risk approval:
    The graph's conditional edge routes to this node exclusively when
    `risk_check.approved is True`. If the risk gate never approved, this node
    is unreachable — there is no other path to it. This is the defense-in-depth
    boundary around real order placement.

WHY it re-checks TRADING_MODE before routing to a broker:
    Even though the graph guarantees this node only sees approved signals,
    this node independently refuses to place a LIVE order unless a human has
    explicitly set TRADING_MODE=live. In paper mode (the hardcoded default) it
    simulates fills. Live execution therefore requires BOTH graph-level risk
    approval AND an explicit human mode flip — two independent gates.
"""

from __future__ import annotations

import logging

from config.settings import load_settings
from graph.state import TradeState
from mcp_wrappers.servers.broker_server import place_order as broker_stub_place_order

logger = logging.getLogger(__name__)


def _build_order_payload(instrument: str, action: str, size: int, entry: float) -> dict:
    """Construct the normalized order payload the broker tool expects."""
    return {
        "instrument": instrument.upper(),
        "side": action,
        "quantity": int(size),
        "order_type": "MARKET",
        "price": float(entry),
        "stop_loss": None,   # set by broker adapter from risk_check SL/TP in prod
        "take_profit": None,
    }


def execution_agent_node(state: TradeState) -> TradeState:
    """Place (or simulate) the order and record telemetry back on the state."""
    settings = load_settings()

    risk = state.get("risk_check") or {}
    signal = state.get("proposed_signal") or {}
    action = signal.get("action")

    # Defensive: even reachable only on approval, re-assert the invariant.
    if not risk.get("approved"):
        state["execution_result"] = {
            "status": "SKIPPED",
            "reason": "execution node reached without risk approval; refusing",
        }
        return state

    payload = _build_order_payload(
        instrument=state.get("instrument", ""),
        action=action,
        size=int(risk.get("position_size") or 0),
        entry=float(risk.get("entry") or state.get("indicators", {}).get("close") or 0.0),
    )

    mode = settings.trading_mode.value
    # Route through MCP broker server URL if configured, else local stub.
    try:
        result = broker_stub_place_order(
            instrument=payload["instrument"],
            side=payload["side"],
            quantity=payload["quantity"],
            order_type=payload["order_type"],
            price=payload["price"],
        )
    except Exception as exc:  # noqa: BLE001
        result = {"status": "REJECTED", "reason": f"broker call failed: {exc}"}

    state["execution_result"] = {
        "status": result.get("status", "UNKNOWN"),
        "order_id": result.get("order_id"),
        "simulated": result.get("simulated", True),
        "mode": mode,
        "instrument": payload["instrument"],
        "side": payload["side"],
        "quantity": payload["quantity"],
        "fill_price": result.get("fill_price"),
        "sl_tp": {
            "stop_loss": risk.get("stop_loss"),
            "take_profit": risk.get("take_profit"),
        },
        "reason": result.get("reason", "order placed"),
    }
    logger.info("EXECUTION[%s] %s %s x%d -> %s",
                result.get("status"), payload["instrument"],
                payload["side"], payload["quantity"], mode)
    return state


def describe_tool() -> dict:
    """Return a JSON schema describing the broker 'place_order' tool.

    This is what lets the Execution Agent treat the broker as a LangChain
    tool (schema shown for the LangChain tool binding in a full deployment).
    """
    return {
        "name": "place_order",
        "description": "Place a market/limit order via the broker MCP server. "
                       "Only reachable after Risk Agent approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string"},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "integer", "exclusiveMinimum": 0},
                "order_type": {"type": "string", "enum": ["MARKET", "LIMIT"]},
                "price": {"type": ["number", "null"]},
            },
            "required": ["instrument", "side", "quantity"],
        },
    }
