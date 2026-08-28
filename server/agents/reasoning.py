import logging
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GROQ_API_KEY
from .state import AgentState

logger = logging.getLogger(__name__)

llm = ChatGroq(temperature=0.0, groq_api_key=GROQ_API_KEY, model_name="qwen/qwen3.6-27b")

async def decision_agent(state: AgentState) -> dict:
    """
    Decision Agent
    Generates a current action proposal.
    """
    logger.info(f"[{state['trace_id']}] Running Decision Agent for {state['asset']}")
    
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
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        decision = chain.invoke({
            "asset": state["asset"],
            "regime": json.dumps(state.get("market_regime", {})),
            "tech_state": json.dumps(state.get("technical_state", {})),
            "liquidity": json.dumps(state.get("liquidity_state", {})),
            "positions": json.dumps(state.get("positions", []))
        })
    except Exception as e:
        logger.error(f"Decision Agent failed: {e}")
        decision = {
            "action": "HOLD",
            "confidence": 0.0,
            "risk_level": "MODERATE",
            "amount_inr": 0.0,
            "reasoning": f"Decision agent error: {e}",
            "validity_conditions": [],
            "invalidation_conditions": []
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
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "asset": state["asset"],
            "regime": json.dumps(state.get("market_regime", {})),
            "tech_state": json.dumps(state.get("technical_state", {})),
            "news": json.dumps(state.get("news_state", {}))
        })
        scenarios = result.get("scenarios", [])
    except Exception as e:
        logger.error(f"Scenario Agent failed: {e}")
        scenarios = state.get("scenarios", [])
        
    return {"scenarios": scenarios}
