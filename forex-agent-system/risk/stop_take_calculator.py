"""Stop-loss / take-profit calculator — mandatory SL/TP on every approved trade.

WHY this exists:
    A trade without an exit plan is a trade that must eventually be closed by
    panic. Every approved signal MUST carry an explicit stop-loss (capped
    downside) and take-profit (defined upside). Mandating both up front, at
    signal time, removes the temptation and the failure mode of "deciding to
    cut losses" after the market has already moved against us. SL and TP are
    expressed in price terms (entry +/− distance) so the execution layer and
    broker receive crisp levels.

WHY SL/TP are refused if invalid:
    If we cannot compute a sane loss limit or a sane profit target from the
    given data, the trade is deemed un-riskable and rejected rather than
    proceeding with a guess.
"""

from __future__ import annotations


class StopTakeError(ValueError):
    """Raised when SL/TP cannot be computed safely."""


def _validate_entry(entry: float) -> None:
    if entry is None or entry <= 0:
        raise StopTakeError(f"entry price must be positive, got {entry!r}")


def stop_take(
    action: str,
    entry: float,
    sl_pips: float,
    tp_pips: float,
    pip_size: float = 0.0025,
) -> dict:
    """Compute mandatory SL/TP levels for a BUY or SELL signal.

    For a BUY (long):  stop = entry - sl_pips*pip_size, take = entry + tp_pips*pip_size
    For a SELL (short): stop = entry + sl_pips*pip_size, take = entry - tp_pips*pip_size

    Returns {"stop_loss": float, "take_profit": float}. Raises StopTakeError
    for invalid inputs (negative/zero distance, unknown side) so the Risk
    Agent can turn any failure into `approved: False` with a clear reason.
    """
    _validate_entry(entry)
    side = (action or "").upper()
    if side not in ("BUY", "SELL"):
        raise StopTakeError(f"unknown action '{action}' for SL/TP calc")

    if sl_pips is None or tp_pips is None or sl_pips <= 0 or tp_pips <= 0:
        raise StopTakeError("SL and TP distances must be positive")

    sl_delta = sl_pips * pip_size
    tp_delta = tp_pips * pip_size

    if side == "BUY":
        stop_loss = entry - sl_delta
        take_profit = entry + tp_delta
    else:  # SELL
        stop_loss = entry + sl_delta
        take_profit = entry - tp_delta

    if stop_loss <= 0:
        raise StopTakeError("computed stop-loss is non-positive; refusing trade")

    return {
        "stop_loss": round(float(stop_loss), 4),
        "take_profit": round(float(take_profit), 4),
        "sl_pips": float(sl_pips),
        "tp_pips": float(tp_pips),
    }
