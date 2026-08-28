"""
services/news_classifier.py
───────────────────────────
Groq Call A — News Classifier.

Given a single article (title + snippet), asks Groq to classify:
  - Is it relevant to any tracked asset?
  - Which asset (nifty / gold / usd / none)?
  - What is the sentiment and impact score?
  - How confident is the model?

This call is intentionally narrow and cheap — it runs on EVERY unprocessed
article, so the prompt is short and max_tokens is kept low.

IMPORTANT: This is part of a paper-trading simulation only.
No real money decisions are made solely on this output.
"""

import json
import logging
import re
from typing import Optional

import httpx

from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "compound-beta"    # same model as the frontend groq-analysis route

# System prompt kept tight to minimise tokens and hallucination risk.
_SYSTEM_PROMPT = """\
You are a financial news classifier for an Indian markets trading system.
You track three assets: NIFTY 50 (India equity index), GOLD (XAU/USD commodity), USD/INR (forex).

Given a news article title and snippet, return ONLY valid JSON with no markdown fences.
The JSON must have exactly these keys:
  "relevant"     : boolean — is this article relevant to any of the three tracked assets?
  "asset"        : string  — "nifty", "gold", "usd", or "none" (if not relevant or ambiguous general macro)
  "sentiment"    : string  — "positive", "negative", or "neutral" (for the named asset)
  "impact_score" : number  — float in [-1.0, 1.0]; +1.0 = extremely bullish, -1.0 = extremely bearish
  "confidence"   : number  — float in [0.0, 1.0]; your confidence in this classification
  "reasoning"    : string  — 1–2 sentence explanation (keep under 100 words)

Rules:
- If the article is about India equities / Sensex / Nifty / FII flows → asset = "nifty"
- If the article is about gold, precious metals, XAU → asset = "gold"
- If the article is about dollar, rupee, USD, INR, forex rates → asset = "usd"
- If general macro / RBI / inflation with no specific asset → asset = "none", relevant = true (general market signal)
- If completely unrelated to finance → relevant = false, asset = "none", impact_score = 0.0, confidence = 0.0
"""

_USER_TEMPLATE = """\
Title: {title}
Snippet: {snippet}
"""


async def classify_article(
    title: str,
    snippet: Optional[str],
) -> dict:
    """
    Classify a single news article via Groq.

    Returns a dict with keys:
        relevant, asset, sentiment, impact_score, confidence, reasoning

    Raises:
        httpx.HTTPStatusError  — on non-2xx from Groq
        ValueError             — if GROQ_API_KEY is unset or JSON parse fails after retries
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured — set it in server/.env")

    user_content = _USER_TEMPLATE.format(
        title=title.strip(),
        snippet=(snippet or "").strip()[:500],   # cap snippet at 500 chars for this cheap call
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "max_tokens": 250,
        "temperature": 0.1,   # low temperature → deterministic classification
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
        resp.raise_for_status()

    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
    return _parse_classifier_response(raw_text, title)


def _parse_classifier_response(raw_text: str, title: str) -> dict:
    """
    Extract and validate the JSON blob from Groq's text response.
    Groq occasionally wraps JSON in markdown fences despite instructions — strip them.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    # Find the first {...} block
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError(
            f"Groq classifier returned no JSON for title={title!r}. Raw: {raw_text[:200]}"
        )

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Groq classifier JSON parse error for title={title!r}: {exc}. Raw: {raw_text[:200]}"
        ) from exc

    # Validate and coerce required fields to prevent downstream crashes
    result = {
        "relevant":     bool(data.get("relevant", False)),
        "asset":        str(data.get("asset", "none")).lower(),
        "sentiment":    str(data.get("sentiment", "neutral")).lower(),
        "impact_score": float(_clamp(data.get("impact_score", 0.0), -1.0, 1.0)),
        "confidence":   float(_clamp(data.get("confidence", 0.0), 0.0, 1.0)),
        "reasoning":    str(data.get("reasoning", ""))[:500],
    }

    # Normalise asset names that Groq might mangle
    asset_map = {
        "nifty 50": "nifty", "nifty50": "nifty",
        "gold": "gold", "xau": "gold", "xauusd": "gold",
        "usd": "usd", "usd/inr": "usd", "inr": "usd", "usdinr": "usd",
        "none": "none", "general": "none",
    }
    result["asset"] = asset_map.get(result["asset"], result["asset"])

    # Normalise sentiment
    if result["sentiment"] not in ("positive", "negative", "neutral"):
        result["sentiment"] = "neutral"

    logger.debug(
        "Classifier: asset=%s sentiment=%s impact=%.2f conf=%.2f title=%r",
        result["asset"], result["sentiment"],
        result["impact_score"], result["confidence"],
        title[:60],
    )
    return result


def _clamp(value, lo, hi):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo
