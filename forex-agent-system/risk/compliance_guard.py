"""Instrument allow-list compliance guard for Indian forex regulations.

WHY this check exists:
    Operating from India, only RBI/SEBI-authorized *exchange-traded* currency
    derivatives (USDINR/EURINR/GBPINR/JPYINR futures & options on NSE/BSE/MSE)
    are lawful to trade. OTC/spot international forex pairs (EUR/USD, GBP/USD,
    and any non-INR cross) fall outside the authorized scope and must never be
    routed. This guard is a hard allow-list enforced in the Risk Agent — the
    gate that sits between every trade signal and execution — and is also
    mirrored in the broker server. It cannot be bypassed by any other node.
"""

from __future__ import annotations

from config.settings import Settings

# Default RBI/SEBI authorized exchange-traded currency derivative CCY pairs.
DEFAULT_ALLOWED = ("USDINR", "EURINR", "GBPINR", "JPYINR")


def is_allowed_instrument(instrument: str) -> bool:
    """Return True iff `instrument` is on the authorized exchange allow-list.

    Normalises to uppercase and strips whitespace so 'usdinr ' / 'USDINR'
    are treated identically. Any instrument not literally present is rejected.
    """
    key = (instrument or "").strip().upper()
    return key in DEFAULT_ALLOWED


def compliance_guard(
    instrument: str,
    allowed: tuple[str, ...] = DEFAULT_ALLOWED,
) -> dict:
    """Evaluate the instrument against the compliance allow-list.

    Returns a dict with `ok` and a human-readable `reason`. This is the
    regulatory gate — a non-allowed instrument hard-rejects the signal with
    FEMA/SEBI/RBI rationale that is also logged to the audit trail.
    """
    key = (instrument or "").strip().upper()
    if not key:
        return {
            "ok": False,
            "reason": "no instrument supplied; cannot route an empty instrument.",
        }
    if key in allowed:
        return {
            "ok": True,
            "reason": f"{key} is an authorized exchange-traded currency "
                      "derivative (NSE/BSE/MSE).",
        }
    return {
        "ok": False,
        "reason": (f"instrument {instrument!r} is NOT on the FEMA/SEBI/RBI "
                   "authorized exchange-traded currency-derivative allow-list. "
                   "OTC/spot international forex routing is blocked and logged."),
    }


def settings_allowed_instruments(settings: Settings) -> tuple[str, ...]:
    """Return the configured allow-list (normalised/upper-cased)."""
    return tuple(i.strip().upper() for i in settings.allowed_instruments)
