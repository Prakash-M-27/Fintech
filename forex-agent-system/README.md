# forex-agent-system

A production-grade, **rules-based**, multi-agent trading-assistant system for
currency markets. It automates data collection, signal generation from explicit
declarative rules, backtesting, risk enforcement, and (optionally, gated) order
execution.

> **This system does NOT predict prices.** It applies deterministic rules to
> indicators + news sentiment, enforces risk on every signal, and routes orders
> through an explicit, multi-layer approval gate.

Stack: **LangGraph** (orchestration) · **LangChain** (tool/model layer) ·
**LangSmith** (tracing + evals) · **MCP** (external connectivity) ·
**Backtrader** (backtesting) · Postgres/SQLite (audit log) · Redis (hot state).

---

## 1. Non-negotiable safety constraints (how each is enforced)

| Constraint | Enforcement point |
|---|---|
| **No live order without human flip** | `TRADING_MODE` hardcodes to `"paper"` in `config/settings.py`. Live only if a human edits `.env` to `live` **and** `main.require_backtest_for_live` passes. |
| **Every signal passes Risk Agent** | `graph/build_graph.py` wires `strategy -> risk_agent -> (conditional)`. The conditional edge `_route_after_risk` sends **only** `approved is True` to execution; everything else → `audit_trail`. There is no bypass path. |
| **End-to-end traceability** | Every run is tagged in LangSmith (`trace_id`, instrument, `TRADING_MODE`) and every decision (approved **and** rejected) is written to the SQLite/Postgres `decisions` log. |
| **India: RBI/SEBI allow-list only** | `risk/compliance_guard.py` hard-rejects any instrument not on the `{USDINR, EURINR, GBPINR, JPYINR}` exchange-traded list. Also mirrored in the broker server. |

---

## 2. Repository layout

```
forex-agent-system/
├── graph/
│   ├── state.py            # shared TradeState (single source of truth)
│   ├── build_graph.py      # StateGraph wiring + risk conditional edge
│   └── nodes/
│       ├── data_agent.py       # pull & normalize market data + news via MCP
│       ├── analysis_agent.py   # indicators (RSI/MA/S-R) + LLM news sentiment
│       ├── strategy_agent.py   # declarative rule engine (NO LLM decisions)
│       ├── risk_agent.py       # the mandatory safety gate (compliance+size+SL/TP)
│       └── execution_agent.py  # order routing (paper by default; live gated)
├── mcp_wrappers/
│   ├── client.py            # thin async wrapper around the MCP SDK (retry/backoff)
│   ├── fastmcp_compat.py    # minimal FastMCP shim over mcp 2.x MCPServer
│   └── servers/
│       ├── market_data_server.py   # tick/OHLCV tools
│       ├── news_calendar_server.py # economic calendar/news tools
│       └── broker_server.py        # order routing (re-checks mode/allow-list)
├── rules/
│   ├── signal_rules.yaml    # declarative IF/THEN rules (change strategy = edit YAML)
│   └── rule_engine.py       # parses YAML -> predicates, first-match wins
├── risk/
│   ├── compliance_guard.py    # FEMA/SEBI/RBI instrument allow-list
│   ├── position_sizing.py     # cap risk at 1–2% of equity per trade
│   └── stop_take_calculator.py# mandatory SL/TP on every approved trade
├── backtest/
│   ├── generate_data.py       # synthetic multi-regime historical CSV
│   └── run_backtest.py        # Backtrader harness (reuses PRODUCTION rule engine)
├── eval/
│   └── langsmith_datasets.py  # golden cases + LangSmith regression eval
├── storage/
│   └── trade_log.py           # SQLite decision/audit log
├── config/settings.py         # pydantic-settings + .env (no hardcoded secrets)
├── main.py                    # entrypoint: run / live / backtest
├── pyproject.toml
└── requirements.txt
```

> **Naming note (deliberate deviation):** the official MCP SDK exposes *subpackages*
> named `mcp.client` and `mcp.server`. The spec's `mcp/client.py` and
> `mcp/servers/` would collide with the SDK and break its internal imports, so
> this local package is named **`mcp_wrappers`** (files otherwise identical:
> `client.py`, `servers/…`). See `mcp_wrappers/__init__.py`. Wherever you see
> `mcp_wrappers` in this repo it maps 1:1 onto the spec's `mcp` directory.

---

## 3. The five nodes & the signal path

```
START ─► data_agent ─► analysis_agent ─► strategy_agent ─► risk_agent
                                                                │
                                    approved is True ──────────┤ (execution_agent) ─► END
                                    anything else ────────────► audit_trail ─► END
```

1. **Data Agent** — calls MCP `get_latest_ticks` / `get_ohlcv` / `get_recent_news`;
   normalizes into `raw_ticks` / `news_events`.
2. **Analysis Agent** — computes RSI, MAs, support/resistance (pure pandas/numpy)
   and runs a strict, low-temperature LLM sentiment prompt (bullish/bearish/neutral
   + one-line justification). The LLM is **never asked to predict price**.
3. **Strategy Agent** — evaluates `rules/signal_rules.yaml` via `rule_engine.py`.
   No LLM decides the trade; decisions come from the declarative rules. LLMs are
   used only for sentiment and the human-readable reason string.
4. **Risk Agent** — the hard gate. Runs `compliance_guard` → `position_sizing`
   → `stop_take_calculator`. Sets `approved=False` on any violation with a reason.
5. **Execution Agent** — only reached if `approved`. Converts the signal to an
   order payload and calls the broker MCP tool (paper simulates; live only when
   `TRADING_MODE=live` **and** the backtest gate passed).

---

## 4. Rule engine format

Rules are declarative and human-auditable. Add a strategy by adding a YAML entry —
no agent code changes.

```yaml
- name: oversold_bullish_news
  when:
    rsi_below: 30
    sentiment: bullish
    spread_below_pips: 2
  then:
    action: BUY
    reason: "RSI oversold + bullish news + tight spread"
```

Supported predicates: `rsi_below`, `rsi_above`, `price_above_ma`, `price_below_ma`,
`sentiment`, `spread_below_pips`, `spread_above_pips`. The engine returns the first
matching rule, or `HOLD`. Malformed rules fail fast at load time.

---

## 5. MCP integration

- `mcp_wrappers/client.py` is a thin async wrapper over the official MCP SDK
  (retry with exponential backoff, connection pooling).
- Local stub servers in `mcp_wrappers/servers/` expose tools with strict schemas so
  the graph runs end-to-end without real market access.
- To use commercial MCP servers, point `MARKET_DATA_MCP_URL` / `NEWS_CALENDAR_MCP_URL`
  / `BROKER_MCP_URL` at them in `.env`. The graph nodes don't care which backend serves
  the tools.

---

## 6. LangSmith tracing & evals

- Set in `.env`: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=forex-multi-agent`
  and a valid `LANGCHAIN_API_KEY`.
- Every run is tagged with `trace_id`, `instrument`, and `TRADING_MODE`
  (`graph/build_graph.py::compile_graph`).
- Golden dataset + evaluator: `eval/langsmith_datasets.py`. It builds a dataset of
  `(indicators, sentiment) -> expected_signal` pairs from the starter rules and
  registers a `strategy_accuracy` evaluator. Re-run `python -m eval.langsmith_datasets`
  whenever the rule file or sentiment prompt changes to catch silent drift.
- The same golden cases run **offline** as pytest tests (`tests/test_golden_cases.py`)
  so drift is caught in CI even without LangSmith credentials.

---

## 7. Backtesting (required before switching away from paper)

`backtest/run_backtest.py` uses **Backtrader** and imports the **same**
`rules/rule_engine.py` and the **same** indicator functions (`analysis_agent.py`)
used in production — there is no second copy of the strategy, which is the #1
cause of "works in backtest, fails live".

- Generate data: `python -m backtest.generate_data`
- Run: `python -m backtest.run_backtest --csv backtest/data/historical_usdinr.csv`
- `main.py backtest` runs the gate.
- Minimum window: `BACKTEST_MIN_YEARS` (default 2). Reported metrics: max drawdown,
  win rate, Sharpe.

**Sentiment in backtest:** historical OHLCV has no news, so backtest uses
`sentiment_proxy()` (a deterministic trend proxy) to exercise the rule engine.
The live path uses real LLM/news sentiment. This divergence is limited to the
*input feed*, never the decision code. If your historical data has a `sentiment`
column it is preferred.

---

## 8. Going live — the documented sign-off process

Live trading is **off by default and intentionally hard**:

1. Make sure `rules/signal_rules.yaml` is the version you want (edit + run the
   golden eval in section 6).
2. Run `python -m backtest.generate_data` and `python -m backtest.run_backtest`.
   Confirm the metrics (max drawdown, win rate, Sharpe) are acceptable for the
   `BACKTEST_MIN_YEARS` window.
3. Add real historical/paper market data and, when ready, point `BROKER_MCP_URL`
   (or the broker server) at a real paper-trading broker. Keep `TRADING_MODE=paper`.
4. **Only after** steps 1–3, a human edits `.env` to `TRADING_MODE=live` and
   confirms the documented sign-off. `main.py` refuses to enter live mode unless
   `require_backtest_for_live` passes (it re-runs the backtest and requires a
   non-empty trade set). There is no flag or code path that places a live order
   without the Risk Agent's explicit approval.

---

## 9. Quick start

```bash
cd forex-agent-system
python -m venv .venv && source .venv/bin/activate   # or use pyproject
pip install -e ".[dev]"
cp .env.example .env                                # edit as needed
python -m backtest.generate_data                    # create historical CSV
python -m pytest -q                                 # run the test suite
python main.py run                                  # one paper evaluation cycle
python main.py backtest                             # run the backtest gate
```

> When using a local `.deps` install (no venv), run with `PYTHONPATH=.:.deps` and
> `TMPDIR=/tmp` (the rule-engine tests write temp YAML files).

## 10. Always-on REST service + frontend wiring

The forex engine ships as a **self-contained, always-on service** (`api_server.py`)
so the frontend can consume it without colliding with the existing `server/`
backend. **Why a separate process:** both systems own a top-level `config` Python
module; importing one into the other in-process would shadow `config` and break
one of them. Running forex-agent-system on its own port (default `8001`), on its
own working directory, keeps the two fully isolated with no shared mutable state.
The service is SQLite-based — no Postgres/Redis required.

The `#1` shared run logic lives in `runner.py` (`ForexRunner`), used by **both**
`main.py` and the service loop, so the two entrypoints never diverge.

```bash
# run the service (dev)
PYTHONPATH=.:.deps python -m api_server --port 8001 --loop 30

# or prod-style
uvicorn api_server:app --host 0.0.0.0 --port 8001
```

| Endpoint | Purpose |
|---|---|
| `GET /api/forex/health` | service + loop status, trading mode, last cycle |
| `GET /api/forex/decisions?limit=N` | most recent cycles (frontend feed) |
| `GET /api/forex/signals?limit=N` | only BUY/SELL, risk-relevant signals |
| `GET /api/forex/rules` | the loaded declarative rules |
| `POST /api/forex/run` | trigger one cycle on demand |
| `GET /api/forex/log` | raw SQLite decision log |

The `--loop N` background task round-robins across instruments on a cadence, so
REST consumers always have fresh data without polling the graph directly.

**Frontend wiring (Next.js `client/`):**
- Add a backend URL via `NEXT_PUBLIC_FOREX_URL` (default `http://localhost:8001`).
- `components/forex-dashboard.tsx` polls the endpoints above and renders health
  metrics, live signals, the decision pipeline, and the strategy rules.
- Route `/forex` renders the forex dashboard inside the shared chrome (nav entry
  + title added to `components/axiom-dashboard.tsx`). The pre-existing `/agent`
  route and the existing `server/` backend are untouched.

Both services can run together:
```
server/        (uvicorn, port 8000)  — existing agent, /api/agent/*
forex-agent-system/ (port 8001)      — forex graph, /api/forex/*
client/        (next dev)            — talks to both via NEXT_PUBLIC_*_URL
```

## 11. Test coverage

The suite (`tests/`) covers every risk-rejection path, the compliance allow-list,
position-sizing bounds, SL/TP correctness, the rule engine (incl. malformed rules),
the graph's risk routing contract, the live-authorization gate, the golden strategy
cases, and the audit log. Run with `python -m pytest`.
