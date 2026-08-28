import logging
from datetime import datetime, timezone

from .state import AgentState
from services.decision_engine import build_technical_snapshot

logger = logging.getLogger(__name__)

async def market_data_agent(state: AgentState) -> dict:
    """
    Market Data Agent (Deterministic)
    Updates the market data state and checks data freshness.
    """
    logger.info(f"[{state['trace_id']}] Running Market Data Agent for {state['asset']}")
    
    # In Phase 1, we pull the snapshot that was passed in via the pipeline
    market_data = state.get("market_data", {})
    
    if not market_data:
        return {"data_quality": {"status": "STALE", "reason": "No market data provided"}}
        
    ts_str = market_data.get("timestamp")
    freshness = "UNKNOWN"
    if ts_str:
        try:
            # handle 'Z' or timezone offsets depending on DB format
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1] + '+00:00'
            ts = datetime.fromisoformat(ts_str)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age < 5:
                freshness = "LIVE"
            elif age < 60:
                freshness = "FRESH"
            else:
                freshness = "DELAYED"
        except Exception:
            freshness = "UNKNOWN"
            
    data_quality = {
        "status": "DEGRADED" if freshness in ("DELAYED", "UNKNOWN", "STALE") else "OK",
        "market_price": freshness,
    }
    
    # Do not mutate input state, return the state updates
    return {
        "data_quality": data_quality
    }

async def technical_signal_agent(state: AgentState) -> dict:
    """
    Technical Signal Agent (Deterministic)
    Calculates technical indicators from recent price history.
    """
    logger.info(f"[{state['trace_id']}] Running Technical Signal Agent for {state['asset']}")
    
    # Normally we would fetch the history here or have it injected.
    # We will assume pipeline/supervisor injects `price_history` into technical_state
    # for simplicity in Phase 1 if it's not already there.
    tech_state = state.get("technical_state", {})
    price_history = tech_state.get("price_history", [])
    
    if not price_history:
        # Fallback to current price if no history
        market_data = state.get("market_data", {})
        if "price" in market_data:
            price_history = [market_data["price"]]
            
    snapshot = build_technical_snapshot(price_history)
    
    # Add back the history for later use
    snapshot["price_history"] = price_history
    
    return {
        "technical_state": snapshot
    }

async def liquidity_agent(state: AgentState) -> dict:
    """
    Liquidity Agent (Deterministic)
    Evaluates whether the market is suitable for proposed action.
    Phase 1: Approximates liquidity using volume and recent volatility since orderbook isn't available.
    """
    logger.info(f"[{state['trace_id']}] Running Liquidity Agent for {state['asset']}")
    
    market_data = state.get("market_data", {})
    tech_state = state.get("technical_state", {})
    
    volume = market_data.get("volume", 0) or 0
    volatility = tech_state.get("volatility", "MODERATE")
    
    # Simple deterministic liquidity heuristic for Phase 1
    liquidity_score = 70
    if volume < 100000:
        liquidity_score -= 20
    if volatility == "HIGH":
        liquidity_score -= 10
        
    liquidity_state = {
        "score": liquidity_score,
        "state": "ACCEPTABLE" if liquidity_score >= 50 else "POOR",
        "trend": "STABLE",
        "execution_suitability": "ACCEPTABLE" if liquidity_score >= 50 else "POOR",
    }
    
    # Check for breakdown
    if liquidity_score < 40:
        liquidity_state["event"] = "LIQUIDITY_BREAKDOWN"
        
    return {
        "liquidity_state": liquidity_state
    }
