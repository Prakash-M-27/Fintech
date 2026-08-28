import asyncio
import logging
from database import init_db
from services.graph_runner import run_langgraph_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

async def test_all_agents():
    await init_db()
    
    assets = [
        ("nifty", {"price": 24200.0, "change": "+120"}),
        ("gold", {"price": 2750.5, "change": "+15.2"}),
        ("usd_inr", {"price": 83.95, "change": "-0.05"})
    ]
    
    for asset_name, mkt in assets:
        payload = {
            "market_data": mkt,
            "news_state": {
                "articles": [
                    {
                        "title": f"Key macro developments affecting {asset_name}",
                        "source": "Reuters",
                        "sentiment": "positive",
                        "impact_score": 0.85,
                        "confidence": 0.9,
                        "reasoning": "Positive economic sentiment indicator."
                    }
                ],
                "aggregate_sentiment": "positive",
                "aggregate_impact": 0.85
            },
            "positions": []
        }
        
        print(f"\n🚀 [TEST] Running LangGraph multi-agent loop for {asset_name.upper()}...")
        try:
            res = await run_langgraph_cycle(asset_name, "TEST_RUN", payload)
            print(f"✅ [SUCCESS] Agent cycle completed for {asset_name.upper()}! Decision: {res.get('current_decision') if res else 'None'}")
        except Exception as e:
            print(f"❌ [ERROR] Failed cycle for {asset_name.upper()}: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_agents())
