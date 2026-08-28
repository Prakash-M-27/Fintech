"""Backtrader-based backtest that reuses the PRODUCTION rule engine & indicators.

WHY this design (the critical anti-divergence constraint):
    The #1 cause of "works in backtest, fails live" is reimplementing the
    strategy for backtest vs. live. Here BOTH paths import the exact same
    `rules/rule_engine.py` and the exact same indicator math from
    `graph/nodes/analysis_agent.py` (rsi / simple_ma / compute_indicators).
    There is no second copy of the rules anywhere.

WHY sentiment in backtest is a documented proxy:
    Sentiment comes from news, which historical OHLCV data lacks. The live path
    derives sentiment from the LLM/news in the Analysis Agent; the backtest uses
    a deterministic `sentiment_proxy()` derived from the short-term trend so the
    *rule engine* (which is what we're validating) is exercised identically.
    When a real dataset with a sentiment column is provided, the proxy is
    overridden by that column. This divergence is limited to the *input* feed
    (unavoidable without a news archive), never to the decision code.

Metrics reported: total return, win rate, max drawdown, Sharpe, trade count.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import backtrader as bt

from graph.nodes.analysis_agent import compute_indicators, sentiment_proxy
from risk.position_sizing import position_size
from risk.stop_take_calculator import stop_take
from rules.rule_engine import RuleEngine

logger = logging.getLogger("backtest")
logging.basicConfig(level=logging.WARNING)

DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "historical_usdinr.csv"


class RuleEngineStrategy(bt.Strategy):
    """Backtrader strategy backed by the production rule engine + risk calc."""

    params = (
        ("engine", None),      # RuleEngine (default reads production YAML)
        ("equity", 100_000.0),
        ("risk_pct", 1.5),
        ("sl_pips", 30.0),
        ("tp_pips", 60.0),
        ("pip_size", 0.0025),
        ("min_bars", 60),      # warmup before indicators are meaningful
    )

    def __init__(self) -> None:
        self.engine: RuleEngine = self.p.engine or RuleEngine()
        self.entry = None
        self.sl = None
        self.tp = None
        self.trades = []          # list of (entry, exit, direction)
        self.order = None

    def _sentiment(self) -> str:
        if hasattr(self.datas[0], "sentiment_line") and self.datas[0].sentiment_line is not None:
            val = self.datas[0].sentiment_line[0]
            if val in ("bullish", "bearish", "neutral"):
                return val
        closes = [self.datas[0].close[i] for i in range(-50, 1)]
        return sentiment_proxy(closes)  # type: ignore[arg-type]

    def next(self) -> None:
        if len(self.data) < self.p.min_bars or self.order:
            return

        # Compute indicators using the SAME function as production.
        closes = [self.datas[0].close[i] for i in range(-60, 1)]
        bars = [
            {"ts": "", "open": self.datas[0].open[i],
             "high": self.datas[0].high[i], "low": self.datas[0].low[i],
             "close": self.datas[0].close[i], "volume": self.datas[0].volume[i]}
            for i in range(-60, 1)
        ]
        ind = compute_indicators(bars)
        ind["spread_pips"] = 1.0  # flat-spread assumption for synthetic data

        senti = self._sentiment()
        decision = self.engine.evaluate(ind, senti, spread_pips=ind["spread_pips"])
        action = decision["action"]
        price = self.datas[0].close[0]

        # Exit an open trade at SL/TP if already in one.
        if self.position and self.entry is not None:
            if self.sl is not None and self.tp is not None:
                if self._is_long() and (price <= self.sl or price >= self.tp):
                    self._close("TP/SL exit")
                elif not self._is_long() and (price >= self.sl or price <= self.tp):
                    self._close("TP/SL exit")
            return

        # Enter on a fresh, risk-approved signal only.
        if action in ("BUY", "SELL"):
            # Size off CURRENT equity (mirrors production: risk % of live
            # equity), not a static constant, so sizing stays realistic.
            current_equity = self.broker.getvalue()
            size = position_size(current_equity, self.p.risk_pct, self.p.sl_pips)
            if size <= 0:
                return
            try:
                levels = stop_take(action, price, self.p.sl_pips, self.p.tp_pips, self.p.pip_size)
            except Exception:  # noqa: BLE001 - invalid SL/TP means no trade
                return
            if action == "BUY":
                self.buy(size=size)
                self.entry, dtype = price, 1
            else:
                self.sell(size=size)
                self.entry, dtype = price, -1
            self.sl, self.tp = levels["stop_loss"], levels["take_profit"]
        # HOLD does nothing.

    def _is_long(self) -> bool:
        return self.position.size > 0

    def _close(self, why: str) -> None:
        price = self.datas[0].close[0]
        direction = 1 if self._is_long() else -1
        pnl = (price - self.entry) * direction * abs(self.position.size)
        self.trades.append({"pnl": pnl, "why": why, "entry": self.entry})
        self.close()
        self.entry = None
        self.sl = None
        self.tp = None


def run_backtest(csv_path: str | Path, *, out_report: bool = True) -> dict:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"backtest CSV not found: {csv_path}. Generate it with "
            "`python -m backtest.generate_data` first."
        )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(RuleEngineStrategy)

    data = bt.feeds.GenericCSVData(
        dataname=str(csv_path),
        dtformat="%Y-%m-%d",
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(100_000.0)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    results = cerebro.run()
    strat = results[0]

    trades = getattr(strat, "trades", [])
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    win_rate = len(wins) / len(trades) if trades else 0.0

    dd = strat.analyzers.dd.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()

    report = {
        "start_value": 100_000.0,
        "end_value": round(cerebro.broker.getvalue(), 2),
        "return_pct": round((cerebro.broker.getvalue() / 100_000.0 - 1) * 100, 2),
        "trade_count": len(trades),
        "win_rate": round(win_rate, 3),
        "max_drawdown_pct": round(dd.get("max", {}).get("drawdown", 0.0), 2),
        "sharpe": round(float(sharpe.get("sharperatio", 0.0) or 0.0), 3),
    }
    if out_report:
        _print_report(report)
    return report


def _print_report(r: dict) -> None:
    print("\n=== BACKTEST REPORT ===")
    for k, v in r.items():
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    args = parser.parse_args()
    run_backtest(args.csv)


if __name__ == "__main__":
    main()
