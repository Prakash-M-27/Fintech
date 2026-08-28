"""Application configuration loaded from environment variables (.env).

WHY this layer exists:
    Every externally-configurable knob (trading mode, risk limits, MCP
    endpoints, model names, secrets) is centralised here via pydantic-settings.
    This guarantees no broker API key or endpoint is ever hardcoded in source,
    satisfies the "config/secrets via pydantic-settings + .env" constraint, and
    makes the whole system auditable from a single file.

    A separate immutable `TradingMode` gate lives here precisely because the
    most dangerous transition in the system (paper -> live) must be *explicit
    and verifiable*, never accidental.
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Trading mode ------------------------------------------------------
    # HARDCODED default to "paper" on purpose: a human must explicitly flip
    # this to "live" (after the documented sign-off + backtest gate). There is
    # no other code path that enables real orders.
    trading_mode: TradingMode = TradingMode.PAPER

    # --- Instrument / compliance -------------------------------------------
    default_instrument: str = "USDINR"
    account_equity: float = 100_000.0
    risk_per_trade_pct: float = Field(default=1.5, ge=0.5, le=2.0)
    sl_pips: float = Field(default=30.0, gt=0)
    tp_pips: float = Field(default=60.0, gt=0)
    allowed_instruments: list[str] = ["USDINR", "EURINR", "GBPINR", "JPYINR"]

    @field_validator("allowed_instruments", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [x.strip().upper() for x in v.split(",") if x.strip()]
        return v

    # --- Backtest gate ------------------------------------------------------
    backtest_min_years: float = 2.0
    backtest_csv_path: str = "backtest/data/historical_usdinr.csv"

    # --- MCP endpoints -------------------------------------------------------
    market_data_mcp_url: str | None = None
    news_calendar_mcp_url: str | None = None
    broker_mcp_url: str | None = None
    broker_api_key: str | None = None
    broker_base_url: str | None = None

    # --- Sentiment model (LLM used ONLY for news sentiment, never decisions) --
    sentiment_model: str = "groq/llama-3.1-8b-instant"
    sentiment_temperature: float = 0.0

    # --- Observability --------------------------------------------------------
    langchain_tracing_v2: bool = True
    langchain_project: str = "forex-multi-agent"
    langchain_api_key: str | None = None
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # --- Storage ---------------------------------------------------------------
    database_url: str = "sqlite:///forex_trades.db"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def is_live(self) -> bool:
        """True only when a human has explicitly opted into live trading."""
        return self.trading_mode == TradingMode.LIVE


settings = Settings()


def load_settings() -> Settings:
    """Return the (singleton) settings; callable for test injection."""
    global settings
    settings = Settings()
    return settings
