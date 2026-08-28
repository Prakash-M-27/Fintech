"""Generate a deterministic multi-regime historical OHLCV CSV for backtesting.

WHY a synthetic generator:
    Backtesting requires a minimum window (default 2 years) across *multiple
    regimes* (trending up, trending down, choppy) so the reported metrics are
    meaningful. Without a real historical data vendor, this script synthesizes
    a realistic USDINR-style series covering several regimes using a seeded RNG
    (so runs are reproducible). Swap in a real vendor CSV by pointing
    BACKTEST_CSV_PATH at it — run_backtest.py only depends on the CSV columns,
    never on this generator.

Output columns (Backtrader-friendly): date, open, high, low, close, volume
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def generate_series(
    n_days: int = 3 * 365,
    seed: int = 42,
    start_price: float = 83.0,
) -> pd.DataFrame:
    """Return an OHLCV DataFrame with trending + choppy regimes."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=datetime.today().date(), periods=n_days, freq="B")

    # Regime schedule (drift per day) — mix of up, down, and sideways blocks.
    regime_pattern = [0.0004, -0.0003, 0.00006, -0.0005, 0.0007, -0.0001]
    block = n_days // len(regime_pattern)
    drift_arr = np.repeat(regime_pattern, block)
    # Extend to exactly n_days (repeat from the start) or trim.
    if len(drift_arr) < n_days:
        drift_arr = np.concatenate([drift_arr, np.tile(regime_pattern, n_days)])[:n_days]
    else:
        drift_arr = drift_arr[:n_days]
    drift_arr = np.asarray(drift_arr, dtype=float)

    daily_vol = 0.002
    rets = drift_arr + rng.normal(0, daily_vol, n_days)
    close = start_price * np.exp(np.cumsum(rets))

    open_ = np.concatenate([[start_price], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 0.1, n_days)
    low = np.minimum(open_, close) - rng.uniform(0, 0.1, n_days)
    volume = rng.integers(1000, 100000, n_days)

    return pd.DataFrame({
        "date": dates,
        "open": open_.round(4),
        "high": high.round(4),
        "low": low.round(4),
        "close": close.round(4),
        "volume": volume,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="backtest/data/historical_usdinr.csv")
    parser.add_argument("--days", type=int, default=3 * 365)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = generate_series(n_days=args.days, seed=args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
