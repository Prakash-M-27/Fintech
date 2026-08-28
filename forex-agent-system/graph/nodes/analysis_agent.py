"""Analysis Agent — computes technical indicators and news sentiment.

WHY this node:
    It transforms raw ticks/news into the `indicators` dict and the
    `sentiment` label that the Strategy Agent's rule engine consumes. It is
    the ONLY place technical indicators are computed, and the ONLY place an
    LLM is used — and only to classify *news sentiment*, never to predict
    price.

WHY indicators are computed manually here (not a hard library dependency):
    Indicator libraries (e.g. pandas-ta → numba) are version-fragile and can
    break the whole graph with an environment change. We implement RSI, moving
    averages and support/resistance in pure pandas/numpy so the graph runs
    deterministically everywhere. The math is standard and unit-tested.

WHY sentiment uses a strict, low-temp LLM prompt:
    The model is constrained to return exactly one of bullish/bearish/neutral
    plus a one-sentence justification. It is explicitly told NOT to forecast,
    only to label the news tone. If no model is configured we fall back to a
    keyword heuristic so paper runs still work offline.
"""

from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

from graph.state import Sentiment, TradeState

logger = logging.getLogger(__name__)

SENTIMENT_MODEL = os.getenv("SENTIMENT_MODEL", "")


# --- Indicators (pure pandas/numpy) -----------------------------------------


def rsi(series: pd.Series, period: int = 14) -> float:
    """Relative Strength Index (Wilder smoothing). Returns latest value.

    Handles the degenerate extremes correctly:
      * every recent change is a gain (no losses)  -> RSI ~ 100
      * every recent change is a loss (no gains)   -> RSI ~ 0
    A pure monotonic series must not collapse to the 50 "no data" default,
    which would silently hide a strongly trending regime.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])

    # No losses at all -> trend is pure upside.
    if last_loss == 0:
        return 100.0
    # No gains at all -> trend is pure downside.
    if last_gain == 0:
        return 0.0

    rs = last_gain / last_loss
    value = 100.0 - (100.0 / (1.0 + rs))
    if np.isnan(value):
        return 50.0
    return float(value)



def simple_ma(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return float(series.mean())
    return float(series.iloc[-window:].mean())


def compute_indicators(ohlcv: list[dict]) -> dict:
    """Compute RSI, short/long MAs and support/resistance from OHLCV bars.

    Expects OHLCV bars ordered oldest→newest (the data agent returns them that
    way). Returns a dict with 'rsi', 'close', 'mas' and support/resistance.
    """
    if not ohlcv:
        raise ValueError("no OHLCV bars supplied to indicator computation")

    df = pd.DataFrame(ohlcv).sort_values("ts")
    close = df["close"].astype(float).reset_index(drop=True)

    ma_short = simple_ma(close, 20)
    ma_long = simple_ma(close, 50)

    support = float(df["low"].rolling(20).min().iloc[-1])
    resistance = float(df["high"].rolling(20).max().iloc[-1])

    return {
        "rsi": rsi(close, 14),
        "close": float(close.iloc[-1]),
        "mas": {"MA20": ma_short, "MA50": ma_long},
        "support": support,
        "resistance": resistance,
    }


# --- Sentiment (LLM, or keyword fallback when no model configured) -----------


_BULLISH_WORDS = ("strengthen", "rises", "rally", "hawkish", "cut", "ease",
                  "support", "gain", "bull")
_BEARISH_WORDS = ("weaken", "falls", "slump", "dovish", "pressure", "sell-off",
                  "bear", "decline", "drop")


def sentiment_proxy(closes: list[float]) -> Sentiment:
    """Deterministic trend-based sentiment PROXY used ONLY by the backtest.

    WHY this exists (and why it's not used in live):
        Historical OHLCV data has no news, so the LLM sentiment step cannot
        run in backtest. To exercise the SAME rule engine that production uses
        (rules with `sentiment` preconditions), we derive a deterministic
        sentiment label from the recent price trend. It is a stand-in for the
        news input only — the decision code (rule engine) is identical live and
        in backtest. The live path continues to use the real LLM/news sentiment.
    """
    if len(closes) < 2:
        return "neutral"
    short = closes[-5:]
    window = closes[-20:] if len(closes) >= 20 else closes
    short_avg = sum(short) / len(short)
    window_avg = sum(window) / len(window)
    if short_avg > window_avg * 1.001:
        return "bullish"
    if short_avg < window_avg * 0.999:
        return "bearish"
    return "neutral"


def _keyword_sentiment(news: list[dict]) -> tuple[Sentiment, str]:
    """Deterministic keyword heuristic used only when no LLM is configured."""
    text = " ".join(f"{n.get('headline','')} {n.get('summary','')}" for n in news).lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in text)
    bear = sum(1 for w in _BEARISH_WORDS if w in text)
    if bull > bear:
        return "bullish", "keyword heuristic: bullish tone in headlines"
    if bear > bull:
        return "bearish", "keyword heuristic: bearish tone in headlines"
    return "neutral", "keyword heuristic: no clear tone"


def sentiment_classify(news: list[dict], model: str = SENTIMENT_MODEL) -> dict:
    """Classify news sentiment to bullish/bearish/neutral + justification.

    Attempts a strict LangChain ChatModel call when `model` is configured.
    Falls back to `_keyword_sentiment` when it isn't (offline/paper runs).
    The LLM is instructed to label tone only — it is never asked to predict
    where price will go.
    """
    if not news:
        return {"sentiment": "neutral", "justification": "no news events"}

    if not model:
        senti, just = _keyword_sentiment(news)
        return {"sentiment": senti, "justification": just}

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.language_models.chat_models import BaseChatModel

    # Resolve the model via langchain's chat model factory if importable.
    try:
        from langchain.chat_models import init_chat_model

        llm: BaseChatModel = init_chat_model(model, temperature=0.0)
    except Exception as exc:  # noqa: BLE001 - no provider configured
        logger.warning("LLM unavailable (%s); using keyword sentiment", exc)
        senti, just = _keyword_sentiment(news)
        return {"sentiment": senti, "justification": just}

    system = (
        "You label the TONE of financial news for a single currency pair. "
        "Classify overall sentiment as exactly one of: bullish, bearish, or "
        "neutral. Do NOT predict price, give targets, or trade advice. "
        "Reply as JSON with keys 'sentiment' and 'justification'."
    )
    prompt = "\n".join(
        f"- {n.get('headline','')}: {n.get('summary','')}" for n in news
    )
    try:
        resp = llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)]
        )
        import json
        data = json.loads(resp.content)
        label = str(data.get("sentiment", "neutral")).lower()
        if label not in ("bullish", "bearish", "neutral"):
            label = "neutral"
        return {"sentiment": label, "justification": data.get("justification", "")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM sentiment call failed (%s); keyword fallback", exc)
        senti, just = _keyword_sentiment(news)
        return {"sentiment": senti, "justification": just}


def analysis_agent_node(state: TradeState) -> TradeState:
    """Compute indicators + sentiment and store them on the state."""
    ohlcv = state.get("_ohlcv") or []
    indicators = compute_indicators(ohlcv)

    # join latest spread from raw ticks if present
    ticks = state.get("raw_ticks") or []
    if ticks:
        indicators["spread_pips"] = float(ticks[-1].get("spread_pips", 1.0))

    senti = sentiment_classify(state.get("news_events") or [], model=SENTIMENT_MODEL)

    state["indicators"] = indicators
    state["sentiment"] = senti["sentiment"]
    state["sentiment_justification"] = senti["justification"]
    # drop transient OHLCV now that indicators are computed
    state.pop("_ohlcv", None)
    return state
