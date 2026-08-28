import logging

from .state import AgentState

logger = logging.getLogger(__name__)

async def outcome_agent(state: AgentState) -> dict:
    """
    Outcome Agent
    Observes what happened after a decision. Recomputes PnL.
    """
    logger.info(f"[{state['trace_id']}] Running Outcome Agent for {state['asset']}")
    
    # In Phase 1, PnL is tracked in the pipeline via price ticks. 
    # Here we just record that an outcome assessment was made.
    outcomes = state.get("outcomes") or []
    
    current_decision = state.get("current_decision")
    if current_decision and (state.get("execution_state") or {}).get("filled"):
        outcomes.append({
            "decision_version": state.get("decision_version"),
            "action": current_decision["action"],
            "expected_conditions": current_decision.get("validity_conditions", []),
            "status": "TRACKING"
        })
        
    return {"outcomes": outcomes}

async def adaptation_agent(state: AgentState) -> dict:
    """
    Adaptation Agent
    Learns from observed outcomes.
    """
    logger.info(f"[{state['trace_id']}] Running Adaptation Agent for {state['asset']}")
    
    adaptation_state = state.get("adaptation_state") or {}
    
    # Placeholder for Phase 1 adaptation logic
    # Real implementation would adjust signal reliability based on outcome success.
    adaptation_state["last_adapted_version"] = state.get("decision_version")
    
    return {"adaptation_state": adaptation_state}
