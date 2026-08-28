"""
services/decision_engine.py
────────────────────────────
Groq Call B — Decision Engine.

Only invoked when a news signal's combined score (confidence × |impact_score|)
clears SIGNAL_ACTION_THRESHOLD.  This call is more expensive than the classifier:
it assembles a rich prompt combining news signal, live technicals, open position
state, and capital ledger, then asks Groq for a BUY / SELL / HOLD / EXIT decision.

Server-side capital enforcement is applied AFTER the Groq response — we never
trust the LLM alone for money math.

Technical indicators are computed in Python here (not deferred to the TypeScript
lib/indicators.ts) so the server is self-contained and there's a single source
of truth for indicator logic.

IMPORTANT: This is a paper-trading simulation only.
No real brokerage integration exists. amount_inr is virtual capital, clamped
server-side before any position row is written.
"""

import json
import logging
import re
from typing import Optional

# pyrefly: ignore [missing-import]
import httpx

from config import GROQ_API_KEY, MAX_TRADE_AMOUNT, SIGNAL_ACTION_THRESHOLD

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "compound-beta"

# ── Python indicator implementations ──────────────────────────────────────
# Ported from client/lib/indicators.ts to keep indicator logic consistent
# between frontend visualisation and server-side decision making.

def calc_ema(prices: list[float], period: int) -> list[float]:
    """Exponential Moving Average — matches the TypeScript calcEMA implementation."""
    if not prices:
        return []
    k = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(round(p * k + result[-1] * (1 - k), 2))
    return result


def calc_rsi(prices: list[float], period: int = 14) -> list[float]:
    """RSI — matches the TypeScript calcRSI implementation."""
    if len(prices) <= period:
        return [50.0] * len(prices)
    result = [50.0] * period
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = prices[i] - prices[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period, len(prices)):
        d = prices[i] - prices[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        result.append(round(100 - 100 / (1 + rs), 2))
    return result


def calc_bollinger(prices: list[float], period: int = 20, mult: float = 2.0):
    """Bollinger Bands — matches the TypeScript calcBollinger implementation."""
    upper, lower, mid = [], [], []
    for i in range(len(prices)):
        if i < period - 1:
            upper.append(prices[i])
            lower.append(prices[i])
            mid.append(prices[i])
            continue
        window = prices[i - period + 1: i + 1]
        mean = sum(window) / period
        std = (sum((p - mean) ** 2 for p in window) / period) ** 0.5
        mid.append(round(mean, 2))
        upper.append(round(mean + mult * std, 2))
        lower.append(round(mean - mult * std, 2))
    return upper, lower, mid


def build_technical_snapshot(price_history: list[float]) -> dict:
    """
    Given an ordered list of recent prices (oldest first), compute a snapshot
    of all technical indicators used in the decision prompt.
    Returns a dict safe for JSON serialisation and DB storage.
    """
    if not price_history:
        return {}
    prices = [float(p) for p in price_history]

    ema20 = calc_ema(prices, 20)
    ema50 = calc_ema(prices, 50)
    rsi   = calc_rsi(prices, 14)
    bb_u, bb_l, bb_m = calc_bollinger(prices, 20)

    # MACD (12, 26, 9)
    ema12 = calc_ema(prices, 12)
    ema26 = calc_ema(prices, 26)
    macd_line  = [round(a - b, 2) for a, b in zip(ema12, ema26)]
    macd_sig   = calc_ema(macd_line, 9)
    macd_hist  = [round(a - b, 2) for a, b in zip(macd_line, macd_sig)]

    # Approximate VWAP as simple average of last N prices (no volume data available server-side)
    vwap = round(sum(prices[-20:]) / min(len(prices), 20), 2)

    last = len(prices) - 1
    return {
        "price":       round(prices[last], 2),
        "ema20":       ema20[last],
        "ema50":       ema50[last],
        "rsi":         rsi[last],
        "macd":        macd_line[last],
        "macd_signal": macd_sig[last],
        "macd_hist":   macd_hist[last],
        "bb_upper":    bb_u[last],
        "bb_lower":    bb_l[last],
        "bb_mid":      bb_m[last],
        "vwap":        vwap,
    }


# ── Prompt construction ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a risk-aware quantitative trading agent operating a PAPER-TRADING simulation for Indian financial markets.
You make decisions for three assets: NIFTY 50 (India equity index), GOLD (XAU/USD), USD/INR (forex).

CONSTRAINTS YOU MUST RESPECT (these are hard limits enforced server-side after your response):
- amount_inr must NEVER exceed the max_trade_amount shown below.
- amount_inr must NEVER exceed available_capital shown below.
- If an open position already exists for this asset, you may only recommend HOLD or EXIT (not BUY/SELL into an existing position).
- For HOLD actions, set amount_inr = 0.
- This is paper-trading only — no real money is involved.

Return ONLY valid JSON with no markdown fences, exactly these keys:
  "action"      : string  — "BUY", "SELL", "HOLD", or "EXIT"
  "amount_inr"  : number  — virtual INR amount for this trade (0 for HOLD)
  "confidence"  : number  — float in [0.0, 1.0]
  "reasoning"   : string  — 2–4 sentence explanation covering news signal, technicals, and risk
"""

_USER_TEMPLATE = """\
=== NEWS SIGNAL ===
Asset: {asset}
Sentiment: {sentiment}
Impact score: {impact_score} (range -1.0 to 1.0)
Signal confidence: {signal_confidence}
Article title: {article_title}
Classifier reasoning: {classifier_reasoning}

=== TECHNICAL INDICATORS (current) ===
Price: {price}
RSI(14): {rsi}
MACD: {macd} | Signal: {macd_signal} | Histogram: {macd_hist}
EMA20: {ema20} | EMA50: {ema50}
Bollinger Upper: {bb_upper} | Lower: {bb_lower}
VWAP (approx): {vwap}

=== OPEN POSITION ===
{open_position_text}

=== CAPITAL STATE (paper-trading, virtual INR) ===
Total capital:     ₹{total_capital}
Allocated capital: ₹{allocated_capital}
Available capital: ₹{available_capital}
Max trade amount:  ₹{max_trade_amount}
"""


def _format_position(open_position: Optional[dict]) -> str:
    if not open_position:
        return "None — no open position for this asset."
    return (
        f"Status: {open_position.get('status', 'open')}\n"
        f"Entry price: {open_position.get('entry_price')}\n"
        f"Entry amount: ₹{open_position.get('entry_amount_inr')}\n"
        f"Unrealized PnL: ₹{open_position.get('unrealized_pnl', 0)}"
    )


async def get_decision(
    signal: dict,
    technical_snapshot: dict,
    open_position: Optional[dict],
    capital_state: dict,
) -> dict:
    """
    Run Groq Call B to get a trading decision.

    Args:
        signal:             NewsSignal fields (asset, sentiment, impact_score,
                            confidence, reasoning, article title).
        technical_snapshot: Output of build_technical_snapshot().
        open_position:      Current open position dict for this asset (or None).
        capital_state:      {total_capital, allocated_capital, available_capital}.

    Returns:
        dict with keys: action, amount_inr, confidence, reasoning

    Raises:
        httpx.HTTPStatusError  — on non-2xx from Groq
        ValueError             — if GROQ_API_KEY unset or JSON parse fails
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured — set it in server/.env")

    snap = technical_snapshot or {}
    user_content = _USER_TEMPLATE.format(
        asset=signal.get("asset", "unknown"),
        sentiment=signal.get("sentiment", "neutral"),
        impact_score=signal.get("impact_score", 0.0),
        signal_confidence=signal.get("confidence", 0.0),
        article_title=signal.get("article_title", "(no title)")[:200],
        classifier_reasoning=signal.get("reasoning", "")[:300],
        price=snap.get("price", "N/A"),
        rsi=snap.get("rsi", "N/A"),
        macd=snap.get("macd", "N/A"),
        macd_signal=snap.get("macd_signal", "N/A"),
        macd_hist=snap.get("macd_hist", "N/A"),
        ema20=snap.get("ema20", "N/A"),
        ema50=snap.get("ema50", "N/A"),
        bb_upper=snap.get("bb_upper", "N/A"),
        bb_lower=snap.get("bb_lower", "N/A"),
        vwap=snap.get("vwap", "N/A"),
        open_position_text=_format_position(open_position),
        total_capital=capital_state.get("total_capital", 0),
        allocated_capital=capital_state.get("allocated_capital", 0),
        available_capital=capital_state.get("available_capital", 0),
        max_trade_amount=MAX_TRADE_AMOUNT,
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "max_tokens": 400,
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
        resp.raise_for_status()

    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
    result = _parse_decision_response(raw_text, signal.get("asset", "unknown"))

    logger.info(
        "Decision engine: asset=%s action=%s amount=%.0f conf=%.2f",
        signal.get("asset"), result["action"], result["amount_inr"], result["confidence"],
    )
    return result


def _parse_decision_response(raw_text: str, asset: str) -> dict:
    """Extract, parse, and validate the decision JSON from Groq's response."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError(
            f"Decision engine returned no JSON for asset={asset!r}. Raw: {raw_text[:200]}"
        )

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Decision engine JSON parse error for asset={asset!r}: {exc}. Raw: {raw_text[:200]}"
        ) from exc

    action = str(data.get("action", "HOLD")).upper()
    if action not in ("BUY", "SELL", "HOLD", "EXIT"):
        logger.warning("Decision engine returned unknown action %r — defaulting to HOLD", action)
        action = "HOLD"

    amount_raw = data.get("amount_inr", 0)
    try:
        amount_inr = float(amount_raw)
    except (TypeError, ValueError):
        amount_inr = 0.0
    amount_inr = max(0.0, amount_inr)   # must be non-negative; server clamps to MAX_TRADE_AMOUNT

    return {
        "action":     action,
        "amount_inr": amount_inr,
        "confidence": float(max(0.0, min(1.0, float(data.get("confidence", 0.5))))),
        "reasoning":  str(data.get("reasoning", ""))[:1000],
    }
