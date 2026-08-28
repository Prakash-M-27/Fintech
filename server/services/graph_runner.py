import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from database import SessionLocal
from agents.state import AgentState
from agents.supervisor import app as langgraph_app

from models import AgentDecision, ActionEnum
from services.agent_loop import (
    _open_position,
    _close_position,
    _get_open_position,
    _compute_allocated_capital,
    _append_capital,
    emit_market_update,
    _get_price_history
)

logger = logging.getLogger(__name__)

async def run_langgraph_cycle(asset: str, event_type: str, payload: dict):
    """
    Invokes the LangGraph orchestrator and applies resulting state mutations.
    """
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] Starting LangGraph cycle for {asset} on {event_type}")

    price_history = await _get_price_history(asset)
    
    initial_state: AgentState = {
        "trace_id": trace_id,
        "asset": asset,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc),
        "market_data": payload.get("market_data"),
        "news_state": payload.get("news_state"),
        "technical_state": {"price_history": price_history},
        "liquidity_state": None,
        "cross_asset_state": None,
        "data_quality": None,
        "market_regime": None,
        "market_context": None,
        "signal_fusion": None,
        "current_decision": None,
        "decision_version": payload.get("decision_version", 0),
        "decision_validity": None,
        "scenarios": [],
        "risk_state": None,
        "capital_state": None,
        "execution_state": None,
        "positions": payload.get("positions", []),
        "outcomes": [],
        "adaptation_state": None,
        "agent_events": [],
        "next_action": None,
        "error": None
    }

    try:
        final_state = initial_state.copy()
        async for chunk in langgraph_app.astream(initial_state):
            for node_name, state_update in chunk.items():
                logger.info(f"[{trace_id}] Node completed: {node_name}")
                
                # Emit Telemetry Event
                await emit_market_update("agent_node_complete", {
                    "trace_id": trace_id,
                    "asset": asset,
                    "node": node_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "state_update": state_update
                })
                
                # Accumulate state
                final_state.update(state_update)
                
    except Exception as e:
        logger.error(f"[{trace_id}] LangGraph failed: {e}")
        return

    # Process Execution
    execution = final_state.get("execution_state", {})
    if execution and execution.get("filled"):
        action = execution.get("action")
        amount_inr = Decimal(str(execution.get("amount_inr", 0.0)))
        decision_dict = final_state.get("current_decision", {})
        
        async with SessionLocal() as session:
            # Persist Decision
            db_decision = AgentDecision(
                asset=asset,
                action=ActionEnum(action),
                amount_inr=amount_inr,
                confidence=decision_dict.get("confidence", 0.0),
                triggering_signal_id=None,
                technical_snapshot=final_state.get("technical_state", {}),
                reasoning=decision_dict.get("reasoning", "")
            )
            session.add(db_decision)
            await session.flush()
            decision_id = db_decision.id
            
            # Execute Paper Trade
            if action in ("BUY", "SELL") and amount_inr > 0:
                current_price = final_state.get("technical_state", {}).get("price") or (price_history[-1] if price_history else 0)
                await _open_position(session, asset, amount_inr, current_price, decision_id)
            elif action == "EXIT":
                pos = await _get_open_position(session, asset)
                if pos:
                    current_price = final_state.get("technical_state", {}).get("price") or (price_history[-1] if price_history else float(pos.entry_price))
                    await _close_position(session, pos, current_price, "agent_decision_exit")
            
            # Update Ledger
            allocated = await _compute_allocated_capital(session)
            await _append_capital(session, allocated, reason=f"{action}_{asset}_graph")
            await session.commit()
            
            await emit_market_update("agent_decision", {
                "decision_id": decision_id,
                "asset": asset,
                "action": action,
                "amount_inr": float(amount_inr),
                "confidence": decision_dict.get("confidence", 0.0),
                "reasoning": decision_dict.get("reasoning", ""),
                "technical": final_state.get("technical_state", {}),
                "ts": datetime.now(timezone.utc).isoformat(),
            })

    # Optional: Handle Outcome (e.g., auto-exit PnL in Outcome Node)
    # The Outcome agent processes auto-exits based on PRICE_CHANGED events
