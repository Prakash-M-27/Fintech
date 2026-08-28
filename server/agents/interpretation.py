import logging
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GROQ_API_KEY
from .state import AgentState

logger = logging.getLogger(__name__)

from services.groq_helper import invoke_llm_json

async def news_agent(state: AgentState) -> dict:
    """
    News Intelligence Agent
    Parses unstructured news to extract entities and impact.
    """
    logger.info(f"[{state['trace_id']}] Running News Agent")
    
    news_data = state.get("news_state", {}) or {}
    if state.get("event_type") == "CONTINUOUS_MONITOR" and not news_data.get("title"):
        news_data.update({
            "event_type": "CONTINUOUS_MONITOR",
            "impact": "LOW",
            "sentiment": "NEUTRAL",
            "affected_assets": [state["asset"].upper()],
            "confidence": 0.85,
            "reasoning": "Routine continuous market monitoring tick."
        })
        return {"news_state": news_data}

    if not news_data.get("title"):
        return {"news_state": {"impact": "NONE", "confidence": 0.0}}
        
    title = news_data.get("title")
    snippet = news_data.get("raw_snippet", "")
    
    prompt = PromptTemplate(
        template="""
        Analyze the following financial news article and extract structured intelligence.
        Title: {title}
        Snippet: {snippet}
        
        Respond with valid JSON matching this schema:
        {{
            "event_type": "string",
            "impact": "HIGH" | "MEDIUM" | "LOW" | "NONE",
            "sentiment": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
            "affected_assets": ["NIFTY", "GOLD", "USD"],
            "confidence": float (0.0 to 1.0),
            "reasoning": "string"
        }}
        """,
        input_variables=["title", "snippet"]
    )
    
    try:
        result = invoke_llm_json(prompt, {"title": title, "snippet": snippet})
        news_data.update(result)
    except Exception as e:
        logger.warning(f"News Agent LLM fallback: {e}")
        news_data.update({"impact": "NONE", "confidence": 0.5, "sentiment": "NEUTRAL", "reasoning": "Market sentiment neutral."})
        
    return {"news_state": news_data}

async def market_regime_agent(state: AgentState) -> dict:
    """
    Market Regime Agent
    Interprets current market environment (Trend, Volatility, Risk-On/Off).
    """
    logger.info(f"[{state['trace_id']}] Running Market Regime Agent for {state['asset']}")
    
    tech_state = state.get("technical_state", {})
    liquidity = state.get("liquidity_state", {})
    news = state.get("news_state", {})

    if state.get("event_type") == "CONTINUOUS_MONITOR":
        return {
            "market_regime": {
                "regime": "RANGE_BOUND",
                "trend": "FLAT",
                "volatility": "MODERATE",
                "confidence": 0.85
            }
        }
    
    prompt = PromptTemplate(
        template="""
        Determine the current Market Regime based on the provided data.
        
        Technical State:
        {tech_state}
        
        Liquidity State:
        {liquidity}
        
        Recent News Impact:
        {news}
        
        Respond with valid JSON matching this schema:
        {{
            "regime": "RISK_ON" | "RISK_OFF" | "TRENDING_BULLISH" | "TRENDING_BEARISH" | "RANGE_BOUND" | "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "UNCERTAIN",
            "trend": "BULLISH" | "BEARISH" | "FLAT",
            "volatility": "HIGH" | "MODERATE" | "LOW",
            "confidence": float (0.0 to 1.0)
        }}
        """,
        input_variables=["tech_state", "liquidity", "news"]
    )
    
    try:
        result = invoke_llm_json(prompt, {
            "tech_state": json.dumps(tech_state),
            "liquidity": json.dumps(liquidity),
            "news": json.dumps(news)
        })
    except Exception as e:
        logger.warning(f"Regime Agent LLM fallback: {e}")
        result = {"regime": "RANGE_BOUND", "trend": "FLAT", "volatility": "MODERATE", "confidence": 0.7}
        
    return {"market_regime": result}
