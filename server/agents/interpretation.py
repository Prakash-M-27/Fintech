import logging
import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GROQ_API_KEY
from .state import AgentState

logger = logging.getLogger(__name__)

# Initialize Groq LLM
llm = ChatGroq(temperature=0.0, groq_api_key=GROQ_API_KEY, model_name="qwen/qwen3.6-27b")

async def news_agent(state: AgentState) -> dict:
    """
    News Intelligence Agent
    Parses unstructured news to extract entities and impact.
    """
    logger.info(f"[{state['trace_id']}] Running News Agent")
    
    news_data = state.get("news_state", {})
    if not news_data or not news_data.get("title"):
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
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({"title": title, "snippet": snippet})
        news_data.update(result)
    except Exception as e:
        logger.error(f"News Agent failed: {e}")
        news_data.update({"impact": "UNKNOWN", "confidence": 0.0})
        
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
    
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "tech_state": json.dumps(tech_state),
            "liquidity": json.dumps(liquidity),
            "news": json.dumps(news)
        })
    except Exception as e:
        logger.error(f"Regime Agent failed: {e}")
        result = {"regime": "UNCERTAIN", "trend": "FLAT", "volatility": "MODERATE", "confidence": 0.0}
        
    return {"market_regime": result}
