"""Declarative rule engine that turns signal_rules.yaml into predicates.

WHY a declarative engine:
    The whole point of a "rules-based" system is that the strategy is data,
    not code. By parsing YAML into small, individually-testable predicate
    functions we make every rule human-auditable, and we keep a SINGLE source
    of truth used identically by the production strategy node AND the backtest
    harness. Reimplementing rules separately for backtest vs. live is the #1
    cause of "works in backtest, fails live" — this module prevents that.

Output contract:
    evaluate() returns the first matching rule dict, or a HOLD signal with
    reason "no rule matched" when nothing fires.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

# Path resolution is relative to this file so imports work from anywhere.
DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "signal_rules.yaml"

# indicator key -> required threshold operand.
# Each predicate builder returns (indicator_key, comparator, threshold) that
# is evaluated against state["indicators"][key] and state["sentiment"].
_SENTIMENT = "sentiment"


def _rsi_below(threshold: float) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        rsi = state["indicators"].get("rsi")
        return rsi is not None and rsi < float(threshold)
    return _pred


def _rsi_above(threshold: float) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        rsi = state["indicators"].get("rsi")
        return rsi is not None and rsi > float(threshold)
    return _pred


def _price_above_ma(ma_key: str) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        close = state["indicators"].get("close")
        ma = state["indicators"].get("mas", {}).get(ma_key)
        return close is not None and ma is not None and close > ma
    return _pred


def _price_below_ma(ma_key: str) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        close = state["indicators"].get("close")
        ma = state["indicators"].get("mas", {}).get(ma_key)
        return close is not None and ma is not None and close < ma
    return _pred


def _sentiment(label: str) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        return (state.get("sentiment") or "").lower() == label.lower()
    return _pred


def _spread_below(threshold: float) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        spread = state["indicators"].get("spread_pips")
        return spread is not None and float(spread) < float(threshold)
    return _pred


def _spread_above(threshold: float) -> Callable[[dict], bool]:
    def _pred(state: dict) -> bool:
        spread = state["indicators"].get("spread_pips")
        return spread is not None and float(spread) > float(threshold)
    return _pred


# Map YAML predicate names to builder functions. Unknown predicates fail fast
# at load time so a typo can never silently disable a rule.
PREDICATE_BUILDERS: dict[str, Callable[..., Callable[[dict], bool]]] = {
    "rsi_below": _rsi_below,
    "rsi_above": _rsi_above,
    "price_above_ma": _price_above_ma,
    "price_below_ma": _price_below_ma,
    "sentiment": _sentiment,
    "spread_below_pips": _spread_below,
    "spread_above_pips": _spread_above,
}


class RuleEngine:
    """Loads rules from YAML and evaluates them against agent state."""

    def __init__(self, rules_path: Path = DEFAULT_RULES_PATH) -> None:
        self.rules: list[dict[str, Any]] = []
        self.rules_path = Path(rules_path)
        self._compiled: list[
            tuple[str, list[Callable[[dict], bool]], str, str]
        ] = []
        self.load()

    def load(self) -> None:
        """Read YAML, validate structure, precompile each rule's predicates.

        WHY precompile & validate:
            Catching a malformed rule (wrong predicate name, missing `then`)
            at import time means a config error can never sneak past the
            startup check and silently produce wrong signals in production.
        """
        with open(self.rules_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or []
        if not isinstance(raw, list):
            raise ValueError(f"rules file {self.rules_path} must be a YAML list")

        self.rules = []
        self._compiled = []
        for entry in raw:
            name = entry.get("name")
            when: dict = entry.get("when", {})
            then: dict = entry.get("then", {})
            if not name or not when or not then:
                raise ValueError(f"rule missing name/when/then: {entry}")
            action = then.get("action")
            if action not in ("BUY", "SELL"):
                raise ValueError(f"rule '{name}': action must be BUY/SELL")
            predicates: list[Callable[[dict], bool]] = []
            for pred_key, threshold in when.items():
                builder = PREDICATE_BUILDERS.get(pred_key)
                if builder is None:
                    raise ValueError(
                        f"rule '{name}': unknown predicate '{pred_key}'"
                    )
                predicates.append(builder(threshold))
            self._compiled.append((name, predicates, then.get("reason", ""), action))
            self.rules.append(entry)

    def evaluate(
        self,
        indicators: dict[str, Any],
        sentiment: str,
        spread_pips: float | None = None,
    ) -> dict[str, Any]:
        """Return the first matching rule's `then`, else a HOLD decision.

        The `indicators` dict must expose 'rsi', 'close', 'mas' and
        optionally 'spread_pips'. `spread_pips` may override the indicator's
        value and is applied to the state used for predicate evaluation.
        """
        state = {
            "indicators": indicators,
            "sentiment": sentiment,
        }
        if spread_pips is not None:
            state["indicators"]["spread_pips"] = float(spread_pips)

        for name, predicates, reason, action in self._compiled:
            if all(pred(state) for pred in predicates):
                logger.info("rule '%s' fired -> %s (%s)", name, action, reason)
                return {"action": action, "rule": name, "reason": reason}
        logger.debug("no rule matched -> HOLD")
        return {
            "action": "HOLD",
            "rule": None,
            "reason": "no rule matched",
        }
