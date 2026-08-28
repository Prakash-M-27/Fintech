"""Trade / decision audit-log persistence.

WHY this exists:
    Every trade signal — approved OR rejected — must be recorded for the
    traceability requirement (end-to-end in LangSmith AND a durable trade/decision
    log). Postgres is the production target; SQLite is used for local
    prototyping. To keep that swap trivial, this module exposes a small,
    storage-agnostic repository interface so the rest of the system never
    talks to a DB driver directly.

    The `decisions` table captures: the trace id, instrument, the raw signal,
    indicator snapshot, sentiment, risk decision, and the execution outcome.
    Rejections are logged here (not dropped) so post-trade analysis can see
    every attempt that was blocked.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sqlite_path_from_url(database_url: str) -> str:
    """Extract a filesystem path from a SQLite SQLAlchemy-ish URL.

    WHY parse instead of treating the string as a path:
        config `database_url` is a SQLAlchemy URL (e.g.
        `sqlite:///forex_trades.db`). Passing that whole string to
        sqlite3.connect() creates a bogus file literally named
        `sqlite:///forex_trades.db`. We strip the `sqlite:///` prefix (and any
        `?params`) to get the real path. Non-sqlite schemes are rejected loudly
        so a mis-configured Postgres URL can't silently fall back to sqlite.
    """
    url = database_url.strip()
    if url == "sqlite://" or url.startswith("sqlite::memory:"):
        return ":memory:"
    m = re.match(r"^sqlite:///(.+)$", url)
    if m:
        return m.group(1).split("?", 1)[0]
    if url.startswith(("postgres", "postgresql")):
        raise ValueError(
            "TradeLog currently supports sqlite only (local prototyping). "
            "For Postgres, use a Postgres adapter (see README)."
        )
    # Plain relative/absolute path without scheme.
    return url


class TradeLog:
    """SQLite-backed decision log. Swap `self._conn` for asyncpg/Postgres in prod.

    WHY minimal dependencies here: relying on the stdlib sqlite3 keeps local
    prototyping dependency-light while the repository API (log_decision /
    query) matches what a Postgres adapter would implement.
    """

    def __init__(self, database_url: str = "sqlite:///forex_trades.db") -> None:
        path = _sqlite_path_from_url(database_url)
        self.db_path = Path(path) if path != ":memory:" else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
        else:
            self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                instrument TEXT NOT NULL,
                signal_action TEXT,
                signal_rule TEXT,
                sentiment TEXT,
                indicators_json TEXT,
                risk_approved INTEGER,
                risk_reason TEXT,
                execution_status TEXT,
                execution_json TEXT,
                mode TEXT
            )
            """
        )
        self._conn.commit()

    def log_decision(self, state: dict[str, Any], mode: str) -> None:
        """Persist one graph run's final outcome.

        WHY capture both approved and rejected signals: the audit trail must
        show every attempt, including those blocked by the risk gate, so we
        never lose visibility into what the system *considered* doing.
        """
        signal = state.get("proposed_signal") or {}
        risk = state.get("risk_check") or {}
        exec_ = state.get("execution_result") or {}

        self._conn.execute(
            """
            INSERT INTO decisions (
                ts, trace_id, instrument, signal_action, signal_rule,
                sentiment, indicators_json, risk_approved, risk_reason,
                execution_status, execution_json, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                state.get("trace_id", ""),
                state.get("instrument", ""),
                signal.get("action"),
                signal.get("rule"),
                state.get("sentiment"),
                json.dumps(state.get("indicators", {}), default=str),
                1 if risk.get("approved") is True else 0,
                risk.get("reason", ""),
                exec_.get("status"),
                json.dumps(exec_, default=str),
                mode,
            ),
        )
        self._conn.commit()

    def query(
        self,
        *,
        instrument: str | None = None,
        approved_only: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch decision records (for reports/eval/analysis)."""
        sql = "SELECT * FROM decisions WHERE 1=1"
        params: list[Any] = []
        if instrument:
            sql += " AND instrument = ?"
            params.append(instrument.upper())
        if approved_only is not None:
            sql += " AND risk_approved = ?"
            params.append(1 if approved_only else 0)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
