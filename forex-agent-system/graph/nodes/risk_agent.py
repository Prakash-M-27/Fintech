"""Risk Agent — the mandatory safety gate between every signal and execution.

WHY this node exists (and why it's wired as a hard gate):
    No trade signal may reach execution without passing through this node.
    The graph's conditional edge after this node lets ONLY `approved: True`
    continue to the Execution Agent; a rejection short-circuits to the audit
    trail. There is deliberately NO code path that bypasses it. It combines
    three independent checks so that a single misconfiguration cannot disable
    safety:

      1. compliance_guard    — is the instrument RBI/SEBI authorized?
      2. position_sizing     — is size capped so worst-case loss ≤ 1–2% equity?
      3. stop_take_calculator— are mandatory SL/TP levels computable and sane?

    Each check can independently reject the signal; any rejection records a
    human-readable `reason` for the trace and Postgres audit trail.
"""

from __future__ import annotations

import logging

from config.settings import Settings, load_settings
from graph.state import TradeState
from risk.compliance_guard import (
    compliance_guard,
    settings_allowed_instruments,
)
from risk.position_sizing import position_size
from risk.stop_take_calculator import stop_take

logger = logging.getLogger(__name__)

# Sentinel used as the actual gate boolean. Risk Agent only ever sets
# approved True when every check passes. Nothing else in the graph writes this.
APPROVED = "approved"


class RiskAgent:
    """Encapsulates the risk checks so they're independently unit-testable."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def _compliance(self, instrument: str) -> tuple[bool, str]:
        allowed = settings_allowed_instruments(self.settings)
        result = compliance_guard(instrument, allowed=allowed)
        return bool(result["ok"]), result["reason"]

    def _sizing(self, entry: float) -> tuple[int, str]:
        try:
            size = position_size(
                equity=self.settings.account_equity,
                risk_pct=self.settings.risk_per_trade_pct,
                stop_distance_pips=self.settings.sl_pips,
            )
        except Exception as exc:  # noqa: BLE001
            return 0, f"position sizing failed: {exc}"
        if size <= 0:
            return 0, (
                "position sizing produced 0 units; the computed risk budget "
                "cannot cover even one unit at this stop distance."
            )
        return size, ""

    def _sl_tp(self, action: str, entry: float) -> tuple[dict | None, str]:
        try:
            levels = stop_take(
                action=action,
                entry=entry,
                sl_pips=self.settings.sl_pips,
                tp_pips=self.settings.tp_pips,
            )
            return levels, ""
        except Exception as exc:  # noqa: BLE001
            return None, f"stop/take calculation failed: {exc}"

    def evaluate(self, state: TradeState) -> dict:
        """Run all checks for the proposed signal. Returns the risk_check dict."""
        signal = state.get("proposed_signal")
        instrument = (state.get("instrument") or "").strip()

        # No signal, or HOLD: nothing to risk-check or execute. This is not a
        # rejection — it's a legitimate "do nothing" outcome that skips exec.
        if signal is None or signal.get("action") == "HOLD":
            return {
                APPROVED: False,
                "action": "HOLD",
                "reason": "no actionable signal to risk-check (HOLD/no-match)",
                "position_size": 0,
                "stop_loss": None,
                "take_profit": None,
            }

        action = signal.get("action")
        entry = float(state.get("indicators", {}).get("close") or 0.0)

        # --- Gate 1: compliance -------------------------------------------
        ok, reason = self._compliance(instrument)
        if not ok:
            return self._reject(reason, action)

        # --- Gate 2: position sizing --------------------------------------
        size, reason = self._sizing(entry)
        if size <= 0:
            return self._reject(reason, action)

        # --- Gate 3: mandatory SL/TP ---------------------------------------
        levels, reason = self._sl_tp(action, entry)
        if levels is None:
            return self._reject(reason, action)

        return {
            APPROVED: True,
            "action": action,
            "reason": (
                f"compliance OK ({instrument}); size {size} units keeps "
                f"worst-case loss <= {self.settings.risk_per_trade_pct}% of "
                f"equity; SL/TP computed. Rule: {signal.get('rule')} — {signal.get('reason')}"
            ),
            "position_size": size,
            "stop_loss": levels["stop_loss"],
            "take_profit": levels["take_profit"],
            "sl_pips": levels["sl_pips"],
            "tp_pips": levels["tp_pips"],
            "entry": entry,
        }

    @staticmethod
    def _reject(reason: str, action: str) -> dict:
        logger.warning("RISK REJECT %s: %s", action, reason)
        return {
            APPROVED: False,
            "action": action,
            "reason": f"RISK REJECTED: {reason}",
            "position_size": 0,
            "stop_loss": None,
            "take_profit": None,
        }


def risk_agent_node(state: TradeState) -> TradeState:
    """LangGraph node wrapper: runs the risk evaluation and stores the result."""
    agent = RiskAgent()
    state["risk_check"] = agent.evaluate(state)
    return state
