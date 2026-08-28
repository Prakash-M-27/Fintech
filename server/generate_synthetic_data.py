"""
Generate synthetic OHLC candle data for Indian market indices.
Prices move realistically within a defined range using random walk with mean reversion.
"""

import json
import math
import random
import os
from datetime import datetime, timedelta

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")

SYMBOLS = {
    "nifty": {
        "name": "NIFTY 50",
        "base_price": 26800,
        "min_price": 24150,
        "max_price": 29500,
        "volatility": 0.0012,
        "mean_reversion": 0.002,
    },
    "banknifty": {
        "name": "BANKNIFTY",
        "base_price": 54000,
        "min_price": 48000,
        "max_price": 62000,
        "volatility": 0.0014,
        "mean_reversion": 0.002,
    },
    "sensex": {
        "name": "SENSEX",
        "base_price": 88500,
        "min_price": 79000,
        "max_price": 98000,
        "volatility": 0.0011,
        "mean_reversion": 0.002,
    },
}

TIMEFRAMES = {
    "1min":   {"candles": 300, "interval_minutes": 1},
    "5min":   {"candles": 250, "interval_minutes": 5},
    "15min":  {"candles": 200, "interval_minutes": 15},
    "30min":  {"candles": 200, "interval_minutes": 30},
    "1h":     {"candles": 200, "interval_minutes": 60},
    "4h":     {"candles": 150, "interval_minutes": 240},
    "1day":   {"candles": 200, "interval_minutes": 1440},
    "1week":  {"candles": 100, "interval_minutes": 10080},
    "1month": {"candles": 60,  "interval_minutes": 43200},
}


def generate_candles(symbol: str, config: dict, timeframe: str, tf_config: dict) -> list[dict]:
    random.seed(hash(f"{symbol}_{timeframe}"))

    base = config["base_price"]
    min_p = config["min_price"]
    max_p = config["max_price"]
    vol = config["volatility"]
    mr = config["mean_reversion"]
    mid = (min_p + max_p) / 2
    num_candles = tf_config["candles"]
    interval = tf_config["interval_minutes"]

    now = datetime.utcnow()
    start_time = now - timedelta(minutes=num_candles * interval)

    price = base
    candles = []

    for i in range(num_candles):
        t = start_time + timedelta(minutes=i * interval)

        drift = mr * (mid - price) / mid
        noise = random.gauss(0, vol)
        change_pct = drift + noise

        open_p = price
        intra_vol = vol * 1.5

        highs = [open_p * (1 + abs(random.gauss(0, intra_vol))) for _ in range(3)]
        lows = [open_p * (1 - abs(random.gauss(0, intra_vol))) for _ in range(3)]

        high_p = max(max(highs), open_p)
        low_p = min(min(lows), open_p)

        close_p = open_p * (1 + change_pct)
        close_p = max(min_p, min(max_p, close_p))

        if close_p > open_p:
            high_p = max(high_p, close_p)
        else:
            low_p = min(low_p, close_p)

        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)
        low_p = max(low_p, min_p * 0.99)
        high_p = min(high_p, max_p * 1.01)

        volume = int(random.uniform(50, 500) * (1 + abs(change_pct) * 50))

        candles.append({
            "time": t.strftime("%Y-%m-%dT%H:%M:%S"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": volume,
        })

        price = close_p

    return candles


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for symbol, config in SYMBOLS.items():
        for tf, tf_config in TIMEFRAMES.items():
            candles = generate_candles(symbol, config, tf, tf_config)
            filepath = os.path.join(OUTPUT_DIR, f"{symbol}_{tf}.json")
            with open(filepath, "w") as f:
                json.dump(candles, f)
            print(f"  Generated {len(candles):>4} candles  {symbol:>10} / {tf:<8} -> {filepath}")

    print(f"\nDone. Files saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
