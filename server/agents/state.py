from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime

class AgentState(TypedDict):
    """
    Global state for the LangGraph orchestrator.
    Contains the entire structured understanding of the current market context.
    """
    # Event metadata
    trace_id: str
    asset: str
    event_type: str  # e.g., 'PRICE_CHANGED', 'NEWS_DETECTED', 'LIQUIDITY_BREAKDOWN'
    timestamp: datetime
    
    # Observation Layer
    market_data: Optional[Dict[str, Any]]
    technical_state: Optional[Dict[str, Any]]
    liquidity_state: Optional[Dict[str, Any]]
    news_state: Optional[Dict[str, Any]]
    cross_asset_state: Optional[Dict[str, Any]]
    data_quality: Optional[Dict[str, Any]]
    
    # Interpretation Layer
    market_regime: Optional[Dict[str, Any]]
    market_context: Optional[str]
    signal_fusion: Optional[Dict[str, Any]]
    
    # Reasoning Layer
    current_decision: Optional[Dict[str, Any]]
    decision_version: int
    decision_validity: Optional[Dict[str, Any]]
    scenarios: List[Dict[str, Any]]
    
    # Execution & Risk Layer
    risk_state: Optional[Dict[str, Any]]
    capital_state: Optional[Dict[str, Any]]
    execution_state: Optional[Dict[str, Any]]
    positions: List[Dict[str, Any]]
    
    # Outcome Layer
    outcomes: List[Dict[str, Any]]
    adaptation_state: Optional[Dict[str, Any]]
    
    # System routing & logs
    agent_events: List[Dict[str, Any]]
    next_action: Optional[str]
    error: Optional[str]
