import logging
from decimal import Decimal

from .state import AgentState
from config import MAX_TRADE_AMOUNT, TOTAL_CAPITAL

logger = logging.getLogger(__name__)

async def risk_agent(state: AgentState) -> dict:
    """
    Risk Agent (Deterministic)
    Enforces hard risk rules on the proposed decision.
    """
    logger.info(f"[{state['trace_id']}] Running Risk Agent for {state['asset']}")
    
    decision = state.get("current_decision", {})
    action = decision.get("action", "HOLD")
    
    risk_state = {
        "status": "APPROVED",
        "overridden": False,
        "reason": ""
    }
    
    # Example hard rules:
    if action in ("BUY", "SELL"):
        if state.get("data_quality", {}).get("status") != "OK":
            risk_state["status"] = "REJECTED"
            risk_state["overridden"] = True
            risk_state["reason"] = "Data quality is degraded (STALE/DELAYED)"
            decision["action"] = "HOLD"
            decision["amount_inr"] = 0.0
            
        liquidity = state.get("liquidity_state", {})
        if liquidity.get("state") == "POOR":
            risk_state["status"] = "REJECTED"
            risk_state["overridden"] = True
            risk_state["reason"] = "Liquidity is POOR"
            decision["action"] = "HOLD"
            decision["amount_inr"] = 0.0
            
    return {
        "risk_state": risk_state,
        "current_decision": decision
    }

async def capital_agent(state: AgentState) -> dict:
    """
    Capital Allocation Agent (Deterministic)
    Determines how much capital can be assigned safely.
    """
    logger.info(f"[{state['trace_id']}] Running Capital Agent for {state['asset']}")
    
    decision = state.get("current_decision", {})
    action = decision.get("action", "HOLD")
    amount_inr = Decimal(str(decision.get("amount_inr", 0.0)))
    
    capital_state = state.get("capital_state", {})
    available = Decimal(str(capital_state.get("available_capital", TOTAL_CAPITAL)))
    
    if action in ("BUY", "SELL"):
        max_allowed = Decimal(str(MAX_TRADE_AMOUNT))
        amount_inr = min(amount_inr, max_allowed)
        
        if amount_inr > available:
            logger.warning(f"Insufficient capital: requested {amount_inr}, available {available}")
            decision["action"] = "HOLD"
            amount_inr = Decimal("0.0")
            capital_state["status"] = "REJECTED_INSUFFICIENT_FUNDS"
        else:
            capital_state["status"] = "APPROVED"
            
    decision["amount_inr"] = float(amount_inr)
    
    return {
        "current_decision": decision,
        "capital_state": capital_state
    }

async def execution_agent(state: AgentState) -> dict:
    """
    Execution Agent (Deterministic)
    Simulates paper trading fill and records it to DB.
    """
    logger.info(f"[{state['trace_id']}] Running Execution Agent for {state['asset']}")
    
    decision = state.get("current_decision", {})
    action = decision.get("action", "HOLD")
    
    execution_state = {
        "status": "NO_ACTION",
        "filled": False
    }
    
    if state.get("event_type") == "CONTINUOUS_MONITOR":
        execution_state["status"] = "REALTIME_MONITOR_EXEMPT"
        execution_state["filled"] = False
        return {"execution_state": execution_state}

    if action in ("BUY", "SELL", "EXIT"):
        execution_state["status"] = "PENDING_DB_FLUSH"
        execution_state["filled"] = True
        execution_state["action"] = action
        execution_state["amount_inr"] = decision.get("amount_inr", 0.0)
        # Note: Actual DB flush will be done synchronously in a wrapper or in the graph callback
        # For LangGraph Phase 1, we set the execution state, and pipeline.py will handle DB mutations.
        
    return {
        "execution_state": execution_state
    }
