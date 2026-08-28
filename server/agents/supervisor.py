import logging
from langgraph.graph import StateGraph, END
from .state import AgentState

from .observation import market_data_agent, technical_signal_agent, liquidity_agent
from .interpretation import news_agent, market_regime_agent
from .reasoning import decision_agent, scenario_agent
from .execution import risk_agent, capital_agent, execution_agent
from .outcome import outcome_agent, adaptation_agent

logger = logging.getLogger(__name__)

def should_reassess(state: AgentState) -> str:
    """
    Conditional edge: fast-path vs reasoning path.
    """
    event = state.get("event_type", "")
    liquidity = state.get("liquidity_state", {})
    
    # Fast path to Risk if liquidity breakdown
    if liquidity.get("event") == "LIQUIDITY_BREAKDOWN":
        logger.info(f"[{state.get('trace_id')}] Fast path triggered: LIQUIDITY_BREAKDOWN")
        return "risk"
        
    # Standard path for price ticks
    if event == "PRICE_CHANGED":
        return "outcome"
        
    # Reasoning path for News
    if event == "NEWS_DETECTED":
        return "interpretation"
        
    return "outcome"

# ── Build the Graph ──
graph_builder = StateGraph(AgentState)

# Add Nodes
graph_builder.add_node("observation_market", market_data_agent)
graph_builder.add_node("observation_technical", technical_signal_agent)
graph_builder.add_node("observation_liquidity", liquidity_agent)

graph_builder.add_node("interpretation_news", news_agent)
graph_builder.add_node("interpretation_regime", market_regime_agent)

graph_builder.add_node("reasoning_decision", decision_agent)
graph_builder.add_node("reasoning_scenario", scenario_agent)

graph_builder.add_node("risk", risk_agent)
graph_builder.add_node("capital", capital_agent)
graph_builder.add_node("execution", execution_agent)

graph_builder.add_node("outcome", outcome_agent)
graph_builder.add_node("adaptation", adaptation_agent)

# Add Edges
# Observation happens sequentially for now
graph_builder.set_entry_point("observation_market")
graph_builder.add_edge("observation_market", "observation_technical")
graph_builder.add_edge("observation_technical", "observation_liquidity")

# Conditional routing after observation
graph_builder.add_conditional_edges(
    "observation_liquidity",
    should_reassess,
    {
        "interpretation": "interpretation_news",
        "risk": "risk",
        "outcome": "outcome"
    }
)

# Reasoning Path
graph_builder.add_edge("interpretation_news", "interpretation_regime")
graph_builder.add_edge("interpretation_regime", "reasoning_decision")
graph_builder.add_edge("reasoning_decision", "reasoning_scenario")
graph_builder.add_edge("reasoning_scenario", "risk")

# Execution Path
graph_builder.add_edge("risk", "capital")
graph_builder.add_edge("capital", "execution")
graph_builder.add_edge("execution", "outcome")

# Outcome Path
graph_builder.add_edge("outcome", "adaptation")
graph_builder.add_edge("adaptation", END)

# Compile
app = graph_builder.compile()
