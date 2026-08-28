import os
from dotenv import load_dotenv

load_dotenv()

# ── Existing config ────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
DB_SSL = os.getenv("DB_SSL", "disable")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
FRANKFUTER_BASE_URL = os.getenv("FRANKFUTER_BASE_URL", "https://api.frankfurter.dev/v2")
USD_POLL_INTERVAL = int(os.getenv("USD_POLL_INTERVAL", 30))
CACHE_TTL = int(os.getenv("CACHE_TTL", 60))

# ── Agent / AI config ──────────────────────────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# How often the news-sentinel agent polls Tavily (seconds). Default 5 minutes.
NEWS_AGENT_POLL_INTERVAL = int(os.getenv("NEWS_AGENT_POLL_INTERVAL", 300))

# Combined score threshold (confidence × |impact_score|) to trigger a
# full decision-engine call.  Range 0.0–1.0.
SIGNAL_ACTION_THRESHOLD = float(os.getenv("SIGNAL_ACTION_THRESHOLD", 0.6))

# ── Paper-trading capital config ───────────────────────────────────────────
# IMPORTANT: All capital figures below are virtual (paper-trading simulation).
# No real brokerage integration exists; no real money is at risk.
TOTAL_CAPITAL = float(os.getenv("TOTAL_CAPITAL", 100000))
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", 5000))

# Stop-loss / take-profit as percentages (signed: -3 means -3%, +5 means +5%).
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", -3))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", 5))
