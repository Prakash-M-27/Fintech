# Axiom

**Autonomous AI Agents for Real-Time Financial Markets**
*Built for CSI ORIGIN 2026 — Problem Statement 3*

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-NeonDB-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-cache-DC382D?logo=redis&logoColor=white)
![Socket.IO](https://img.shields.io/badge/Socket.IO-realtime-010101?logo=socket.io&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

Axiom is a real-time financial intelligence platform that simulates an autonomous trading agent. It continuously ingests live market data, reasons over it with an LLM-driven decision pipeline, and — in its current build-out — is being extended into a fully closed **observe → interpret → reason → assess risk → allocate → execute → observe outcome → adapt** loop, evaluated against real financial news rather than price data alone.

No real capital is at risk. All trading is simulated (paper trading) against a fixed capital pool.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Data Flow](#data-flow)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Autonomous News Agent](#autonomous-news-agent)
- [Risk & Capital Rules](#risk--capital-rules)
- [Roadmap](#roadmap)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

Traditional trading systems fall into two camps: human-driven analysis, which is limited by attention and reaction speed, or fixed-rule algorithms, which execute quickly but can't reassess themselves when conditions change. Axiom targets the gap between them — an agent that perceives a changing market, reasons about competing signals (price action, technical indicators, and now news sentiment), and acts within explicit, code-enforced risk and capital constraints.

The platform has two working layers today:

1. **Live market data pipeline** — real-time price ingestion, persistence, caching, and broadcast, already in production for three asset classes.
2. **AI trade analysis** — an on-demand Groq-powered technical analyst that scores live indicator data and returns a structured trade recommendation.

It is being extended with a third layer — an **autonomous news-driven decision agent** — described in [Autonomous News Agent](#autonomous-news-agent) below.

---

## System Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │              EXTERNAL SOURCES                │
                        │                                              │
                        │  TwelveData WS   Yahoo Finance   Frankfurter │
                        │   (Gold, live)   (NIFTY, 5s)    (USD/INR,30s)│
                        │                                              │
                        │   NewsAPI (5min)      Tavily (planned)       │
                        └───────────────┬──────────────────────────────┘
                                        │
                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │              FASTAPI BACKEND                  │
                        │                                              │
                        │  ┌────────────┐   ┌───────────────────────┐ │
                        │  │  pipeline  │──▶│  PostgreSQL (NeonDB)  │ │
                        │  │  .price_   │   │  price + news +       │ │
                        │  │  handler() │   │  agent-decision tables│ │
                        │  └─────┬──────┘   └───────────────────────┘ │
                        │        │                                     │
                        │        ▼                                     │
                        │  ┌────────────┐   ┌───────────────────────┐ │
                        │  │   Redis    │   │   Socket.IO server    │ │
                        │  │  (60s TTL  │   │  emits market_update, │ │
                        │  │   cache)   │   │  news_signal,         │ │
                        │  └────────────┘   │  agent_decision       │ │
                        │                   └──────────┬─────────────┘ │
                        └──────────────────────────────┼───────────────┘
                                                        │  WebSocket
                                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │             NEXT.JS FRONTEND                  │
                        │                                              │
                        │  axiom-dashboard.tsx  (shell, socket client) │
                        │  live-trading.tsx     (agent pipeline view)  │
                        │  /markets /agent /positions /capital /news   │
                        │  /risk /execution /history /outcomes ...     │
                        └───────────────┬───────────────────────────────┘
                                        │  REST (page load / history)
                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │   GET /api/market · /api/market/{asset}      │
                        │   GET /api/market/{asset}/history            │
                        │   POST /api/groq-analysis  (Next.js route)   │
                        └─────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend framework | FastAPI + Uvicorn | Async REST API |
| Real-time transport | python-socketio | WebSocket broadcast to clients |
| Database | PostgreSQL (NeonDB) via SQLAlchemy (async) + asyncpg | Durable price / news / decision history |
| Cache | Redis (aioredis) | Sub-second reads for latest market snapshot |
| HTTP client | httpx | Polling external REST APIs |
| Market data | TwelveData (WS), Yahoo Finance, Frankfurter | Gold, NIFTY 50, USD/INR |
| News | NewsAPI, Tavily *(agent, in progress)* | Headline ingestion, targeted financial search |
| AI reasoning | Groq API — `gpt-oss-120B` | Technical analysis + news classification + decision engine |
| Frontend framework | Next.js 16 (App Router), React 19, TypeScript | Dashboard UI |
| Styling / UI | Tailwind CSS v4, shadcn/ui, @base-ui/react | Component system |
| Charts | Recharts | Price and indicator visualization |
| Realtime client | socket.io-client | Live UI updates |
| Analytics | @vercel/analytics | Usage tracking |
| Orchestration | Docker Compose | Redis + Postgres + backend services |

---

## Data Flow

**Live pricing (implemented):**

```
External APIs → pipeline.price_handler()
                       │
                       ├──▶ PostgreSQL   (persist every tick)
                       ├──▶ Redis        (market:{asset}:latest, TTL 60s)
                       └──▶ Socket.IO    (market_update)
                                │
                                ▼
                     Frontend (socket.io-client)
                                │
                                └──▶ every 30s → /api/groq-analysis → Groq → BUY/SELL/HOLD
```

**News-driven agent loop (in progress — see below):**

```
Tavily search (per tracked asset)
        │
        ▼
news_articles (deduped by URL)
        │
        ▼
Groq classifier → sentiment, impact_score, confidence
        │
        ▼ (if confidence × |impact| ≥ threshold)
Groq decision engine → BUY / SELL / HOLD / EXIT + amount
        │
        ▼
Server-side risk clamp (₹5,000 cap · capital ledger check)
        │
        ▼
portfolio_positions + capital_ledger updated → Socket.IO emit
```

---

## Project Structure

```
Fintech/
├── server/
│   ├── main.py                  # App bootstrap, background task startup
│   ├── config.py                # Env var loading
│   ├── database.py              # Async SQLAlchemy engine, init_db()
│   ├── models.py                # PriceModel base + nifty/gold/usd tables
│   ├── schemas.py                # Pydantic I/O schemas
│   ├── pipeline.py               # price_handler(), warm_up_from_db()
│   ├── socket_manager.py         # Socket.IO server, room events
│   ├── routers/
│   │   └── market.py             # /api/market REST endpoints
│   ├── services/
│   │   ├── cache.py               # Redis singleton client
│   │   ├── twelvedata.py          # Gold WS client
│   │   ├── frankfurter.py         # USD/INR poller
│   │   ├── nifty.py               # NIFTY poller
│   │   └── news.py                # NewsAPI poller
│   ├── docker-compose.yml         # redis · postgres · backend
│   └── .env
└── client/
    ├── app/
    │   ├── page.tsx                        # / (Command Center)
    │   ├── live/page.tsx                    # /live
    │   ├── markets/ agent/ scenarios/
    │   │   risk/ capital/ positions/
    │   │   execution/ history/ outcomes/
    │   │   news/ data-sources/ settings/    # dashboard sub-routes
    │   └── api/
    │       └── groq-analysis/route.ts        # Groq trade-analysis proxy
    ├── components/
    │   ├── axiom-dashboard.tsx               # Shared shell, Socket.IO client
    │   └── live-trading.tsx                  # Full trading room UI
    ├── lib/
    │   ├── axiom-data.ts                     # Seed/static data (being replaced)
    │   └── indicators.ts                     # EMA / RSI / MACD / Bollinger
    ├── package.json
    └── next.config.mjs
```

> Planned additions for the autonomous news agent (`services/tavily_client.py`, `services/news_classifier.py`, `services/decision_engine.py`, `routers/agent.py`, and the corresponding new tables) are tracked separately and not yet merged — see [Roadmap](#roadmap).

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- API keys: TwelveData, NewsAPI, Groq, Tavily *(for the agent)*

### Backend

```bash
cd server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in credentials
docker compose up -d redis postgres
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd client
npm install
npm run dev
```

The dashboard runs on `http://localhost:3000` and connects to the backend at `http://localhost:8000` via Socket.IO on mount.

---

## Environment Variables

**Backend (`server/.env`)**

| Variable | Description |
|---|---|
| `DATABASE_URL` | NeonDB PostgreSQL connection string (SSL) |
| `DB_SSL` | `require` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `TWELVEDATA_API_KEY` | Live Gold price WebSocket |
| `NEWS_API_KEY` | NewsAPI headlines |
| `FRANKFUTER_BASE_URL` | `https://api.frankfurter.dev/v2` |
| `USD_POLL_INTERVAL` | Seconds between USD/INR polls (default 30) |
| `CACHE_TTL` | Redis cache TTL in seconds (default 60) |
| `GROQ_API_KEY` | Groq inference (`gpt-oss-120B`) |
| `TAVILY_API_KEY` | *(agent)* Tavily search |
| `NEWS_AGENT_POLL_INTERVAL` | *(agent)* Seconds between Tavily sweeps (default 300) |
| `SIGNAL_ACTION_THRESHOLD` | *(agent)* Confidence × impact threshold to trigger a decision (default 0.6) |
| `TOTAL_CAPITAL` | *(agent)* Simulated capital pool (default 100000) |
| `MAX_TRADE_AMOUNT` | *(agent)* Per-decision cap (default 5000) |
| `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT` | *(agent)* Auto-exit thresholds |

---

## API Reference

### Market data (implemented)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/market` | Latest snapshot for all tracked assets (Redis-first, DB fallback) |
| `GET` | `/api/market/{asset}` | Latest snapshot for one asset (`nifty` / `gold` / `usd`) |
| `GET` | `/api/market/{asset}/history?limit=50` | Historical prices, capped at 500 rows |
| `GET` | `/api/health` | DB, Redis, and Socket.IO connection status |
| `POST` | `/api/groq-analysis` | (Next.js route) Live indicator snapshot → Groq trade recommendation |

### Agent endpoints (planned)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/agent/news` | Recent classified articles and signals |
| `GET` | `/api/agent/decisions` | Recent agent decisions with reasoning |
| `GET` | `/api/agent/portfolio` | Open/closed positions and capital ledger state |
| `GET` | `/api/agent/health` | Tavily/Groq connectivity for the agent loop |

### Socket.IO events

| Event | Status | Payload |
|---|---|---|
| `market_update` | Implemented | Latest price tick for a subscribed asset |
| `news_update` | Implemented | New NewsAPI headline |
| `news_signal` | Planned | Classified sentiment/impact for a news article |
| `agent_decision` | Planned | BUY/SELL/HOLD/EXIT decision with reasoning |

---

## Autonomous News Agent

This is the component being built to satisfy Problem Statement 3's requirement for a full autonomous decision loop, rather than a single price prediction:

1. **Observe** — Tavily continuously searches for financial news tied to each tracked asset.
2. **Interpret** — Groq (`gpt-oss-120B`) classifies each new article for relevance, sentiment, impact score, and confidence.
3. **Reason** — when a signal clears a defined threshold, a second Groq pass weighs it against live technical indicators, the asset's current position, and available capital.
4. **Assess risk & allocate** — the suggested action and amount are clamped server-side against hard caps before anything is persisted; capital math is never trusted from model output alone.
5. **Execute** — a simulated position is opened, closed, or adjusted, and the capital ledger updated.
6. **Observe outcome** — every open position is re-marked on each subsequent price tick.
7. **Adapt** — stop-loss / take-profit rules trigger autonomous exits based on those outcomes, without further human input.

All seven steps run continuously, asset by asset, as a background task alongside the existing market-data pollers.

---

## Risk & Capital Rules

- Total simulated capital: **₹100,000**
- Maximum allocation per decision: **₹5,000**
- Maximum concurrent open positions per asset: **1**
- No `BUY` is persisted if it would exceed available capital
- All capital mutations pass through a single serialized function per asset to prevent race conditions between concurrent signals

This is a **paper-trading simulation** — no real capital, brokerage account, or order routing is involved at any stage.

---

## Roadmap

- [x] Live multi-source price ingestion pipeline
- [x] Redis caching + Socket.IO real-time broadcast
- [x] On-demand Groq technical analysis
- [ ] Tavily-powered news ingestion
- [ ] Two-stage Groq news classification and decision engine
- [ ] Capital ledger and simulated position management
- [ ] Stop-loss / take-profit auto-adaptation loop
- [ ] Agent-facing REST endpoints and frontend wiring
- [ ] Decision audit log / outcome intelligence dashboard

---

## License

MIT — see `LICENSE`.

## Acknowledgments

Built for **CSI ORIGIN 2026**, Problem Statement 3 — *Autonomous AI Agents for Real-Time Financial Markets*, powered by Stitch / CodeCrafters / ElevenLabs / NexusX.

Market and reasoning infrastructure: TwelveData, Yahoo Finance, Frankfurter, NewsAPI, Tavily, Groq, NeonDB.