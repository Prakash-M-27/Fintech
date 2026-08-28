import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_SSL = os.getenv("DB_SSL", "disable")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
FRANKFUTER_BASE_URL = os.getenv("FRANKFUTER_BASE_URL", "https://api.frankfurter.dev/v2")
USD_POLL_INTERVAL = int(os.getenv("USD_POLL_INTERVAL", 30))
CACHE_TTL = int(os.getenv("CACHE_TTL", 60))