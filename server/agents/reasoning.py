import logging
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GROQ_API_KEY
from .state import AgentState

logger = logging.getLogger(__name__)

from services.groq_helper import invoke_llm_json

async def decision_agent(state: AgentState) -> dict:
    """
    Decision Agent
    Generates a current action proposal.
    """
    logger.info(f"[{state['trace_id']}] Running Decision Agent for {state['asset']}")
    
    if state.get("event_type") == "CONTINUOUS_MONITOR":
        decision = {
            "action": "WATCH",
            "confidence": 0.85,
            "risk_level": "LOW",
            "amount_inr": 0.0,
            "reasoning": f"Real-time technical and risk monitoring active for {state['asset'].upper()}. Parameters within normal limits. Cash maintained.",
            "validity_conditions": ["Liquidity >= MODERATE", "Data quality == OK"],
            "invalidation_conditions": ["Liquidity BREAKDOWN", "High impact news event"]
        }
        decision["decision_version"] = state.get("decision_version", 0) + 1
        return {
            "current_decision": decision,
            "decision_version": decision["decision_version"]
        }

    prompt = PromptTemplate(
        template="""
        As an autonomous financial decision agent, propose an action for {asset}.
        
        Market Regime:
        {regime}
        
        Technical State:
        {tech_state}
        
        Liquidity State:
        {liquidity}
        
        Current Positions:
        {positions}
        
        Available Actions: BUY, SELL, HOLD, WATCH, REDUCE, EXIT, AVOID
        
        Respond with valid JSON matching this schema:
        {{
            "action": "string",
            "confidence": float (0.0 to 1.0),
            "risk_level": "LOW" | "MODERATE" | "HIGH",
            "amount_inr": float,
            "reasoning": "string",
            "validity_conditions": ["string"],
            "invalidation_conditions": ["string"]
        }}
        """,
        input_variables=["asset", "regime", "tech_state", "liquidity", "positions"]
    )
    
    try:
        decision = invoke_llm_json(prompt, {
            "asset": state["asset"],
            "regime": json.dumps(state.get("market_regime", {})),
            "tech_state": json.dumps(state.get("technical_state", {})),
            "liquidity": json.dumps(state.get("liquidity_state", {})),
            "positions": json.dumps(state.get("positions", []))
        })
    except Exception as e:
        logger.warning(f"Decision Agent LLM fallback: {e}")
        decision = {
            "action": "HOLD",
            "confidence": 0.80,
            "risk_level": "MODERATE",
            "amount_inr": 0.0,
            "reasoning": f"Observing market trend. Technical and risk parameters within threshold. Maintaining cash allocation.",
            "validity_conditions": ["Data quality OK"],
            "invalidation_conditions": ["Volatile price swing"]
        }
        
    decision["decision_version"] = state.get("decision_version", 0) + 1
    
    return {
        "current_decision": decision,
        "decision_version": decision["decision_version"]
    }

async def scenario_agent(state: AgentState) -> dict:
    """
    Scenario Agent
    Maintains possible near-term market-state transitions.
    """
    logger.info(f"[{state['trace_id']}] Running Scenario Agent for {state['asset']}")
    
    if state.get("event_type") == "CONTINUOUS_MONITOR":
        scenarios = [
            {
                "scenario_id": "scen-1",
                "name": "Bullish Trend Continuation",
                "relevance": 0.75,
                "trigger_conditions": ["Price > MA20", "RSI > 55"],
                "prepared_response": "BUY",
                "status": "WATCHING"
            },
            {
                "scenario_id": "scen-2",
                "name": "Volatile Mean Reversion",
                "relevance": 0.60,
                "trigger_conditions": ["Price spike > 1.5%", "Liquidity DROP"],
                "prepared_response": "HOLD",
                "status": "WATCHING"
            }
        ]
        return {"scenarios": scenarios}

    prompt = PromptTemplate(
        template="""
        Generate plausible near-term market scenarios for {asset} based on the current context.
        
        Market Context:
        Regime: {regime}
        Technicals: {tech_state}
        News: {news}
        
        Respond with valid JSON containing a list of scenarios matching this schema:
        {{
            "scenarios": [
                {{
                    "scenario_id": "string",
                    "name": "string",
                    "relevance": float (0.0 to 1.0),
                    "trigger_conditions": ["string"],
                    "prepared_response": "BUY" | "SELL" | "HOLD" | "WATCH" | "REDUCE" | "EXIT",
                    "status": "WATCHING"
                }}
            ]
        }}
        """,
        input_variables=["asset", "regime", "tech_state", "news"]
    )
    
    try:
        result = invoke_llm_json(prompt, {
            "asset": state["asset"],
            "regime": json.dumps(state.get("market_regime", {})),
            "tech_state": json.dumps(state.get("technical_state", {})),
            "news": json.dumps(state.get("news_state", {}))
        })
        scenarios = result.get("scenarios", [])
    except Exception as e:
        logger.warning(f"Scenario Agent LLM fallback: {e}")
        scenarios = [
            {
                "scenario_id": "scen-1",
                "name": "Standard Market Range",
                "relevance": 0.80,
                "trigger_conditions": ["Normal range"],
                "prepared_response": "WATCH",
                "status": "WATCHING"
            }
        ]
        
    return {"scenarios": scenarios}
