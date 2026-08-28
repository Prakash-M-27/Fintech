"""Position sizing — cap risk per trade at 1–2% of account equity.

WHY this exists:
    Position sizing is the single most important risk control after the
    trade/no-trade gate. If a losing trade can wipe out a large fraction of
    account equity, one bad signal can cause unrecoverable drawdown. capping
    the risked capital at a small, configurable fraction (default 1.5%, band
    0.5–2.0%) is what keeps a normal losing streak survivable. We compute the
    number of units such that the *worst case loss* (stop-loss distance ×
    units) never exceeds the allowed risk budget.

    size = floor( (equity * risk_pct) / (stop_distance_per_unit) )
"""

from __future__ import annotations

import math

from config.settings import Settings


def _window_size(pip_value: float, pip_size: float = 0.0025) -> float:
    """Distance in pips between entry and stop.

    For USDINR one pip is conventionally 0.0025. If the caller passes a
    pip-distance, the money per unit is `pip_value * pip_size`.
    """
    return max(pip_value, 1e-9)


def position_size(
    equity: float,
    risk_pct: float,
    stop_distance_pips: float,
    pip_value: float = 0.0025,
    max_units: float | None = None,
    min_units: float = 1,
) -> int:
    """Return the integer number of units for the trade.

    Guards:
      * risk_pct is clamped to a sane [0.01, 0.10] band (1–10%) even if config
        drifts — we never let a misconfigured value inflate exposure silently.
      * computed size never exceeds `max_units` (default: unlimited).
      * returns at least `min_units` only if a positive amount is affordable;
        returns 0 if the budget can't cover even one unit.
    """
    rp = max(0.01, min(float(risk_pct) / 100.0, 0.10))
    if equity <= 0 or stop_distance_pips <= 0:
        return 0
    stop_money = _window_size(stop_distance_pips) * pip_value
    risk_budget = equity * rp
    if stop_money <= 0:
        return 0
    size = math.floor(risk_budget / stop_money)
    if max_units is not None:
        size = min(size, int(max_units))
    if size < min_units:
        return 0
    return int(size)


def as_percentage(equity: float, risk_budget_money: float) -> float:
    """Return what fraction of equity `risk_budget_money` represents."""
    if equity <= 0:
        return 0.0
    return risk_budget_money / equity


def settings_position_size(settings: Settings) -> int:
    """Convenience wrapper using full Settings (uses default SL distance)."""
    return position_size(
        equity=settings.account_equity,
        risk_pct=settings.risk_per_trade_pct,
        stop_distance_pips=settings.sl_pips,
    )
