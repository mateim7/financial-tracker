# Financial Impact Screener - Architecture & Backend Documentation

## Overview

The **Financial Impact Screener** is a real-time market intelligence dashboard that ingests financial news from 90+ RSS sources and WebSocket feeds, extracts stock tickers, fetches live market momentum data (price, RVOL), cross-references SEC Form 4 insider filings, and uses Claude AI to generate actionable BUY/SELL/HOLD signals with conviction scores.

**Tech Stack:**
- **Backend:** Python 3.11 (asyncio) — monolith in `nyse_impact_screener.py` (~4,700 lines)
- **Frontend:** React (Create React App) — served via nginx in Docker
- **Database:** Supabase (PostgreSQL) — cloud-hosted, replaces original SQLite
- **AI Models:** Claude Sonnet 4.6 (primary scoring) + Claude Haiku 4.5 (validation layer)
- **Market Data:** Finnhub (real-time quotes including pre/post-market + SEC Form 4 insider data), yfinance (RVOL calculation, fallback prices)
- **News Feeds:** 90+ RSS sources + WebSocket feeds (Finnhub, Benzinga Pro, Polygon.io)
- **Deployment:** Docker Compose (2 services: backend + frontend)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DOCKER COMPOSE                                  │
│                                                                         │
│  ┌─────────────────────────────┐     ┌───────────────────────────────┐  │
│  │  BACKEND (Python 3.11)      │     │  FRONTEND (React + nginx)     │  │
│  │  Port 8765: WebSocket       │◄────│  Port 3000 → nginx → :80     │  │
│  │  Port 8766: HTTP API        │     │  Connects to ws://host:8765   │  │
│  └──────────┬──────────────────┘     └───────────────────────────────┘  │
│             │                                                           │
└─────────────┼───────────────────────────────────────────────────────────┘
              │
    ┌─────────▼─────────┐
    │ External Services  │
    ├────────────────────┤
    │ • Anthropic API    │ ← Claude Sonnet + Haiku
    │ • Finnhub API      │ ← Real-time quotes (pre/post-market) + SEC Form 4
    │ • yfinance         │ ← RVOL calculation, fallback prices
    │ • 90+ RSS feeds    │ ← MarketWatch, Reuters, CNBC, etc.
    │ • Supabase         │ ← PostgreSQL database
    └────────────────────┘
```

---

## Backend Classes (nyse_impact_screener.py)

| Line | Class | Purpose |
|------|-------|---------|
| ~312 | `RSSFeed` | Fetches news from 90+ RSS sources every 60 seconds with 1-hour freshness cutoff and 30-minute headline deduplication |
| ~461 | `WebSocketNewsFeed` | Real-time news from Finnhub, Benzinga Pro, Polygon.io with auto-reconnect |
| ~698 | `Direction` (Enum) | BULLISH, BEARISH, NEUTRAL |
| ~704 | `Urgency` (Enum) | FLASH, HIGH, STANDARD, LOW |
| ~711 | `EventType` (Enum) | 55+ event types (EARNINGS_BEAT, FDA_APPROVAL, CEO_DEPARTURE, CYBER_BREACH, etc.) |
| ~781 | `RawNewsEvent` | Normalized event dataclass: timestamp, headline, body, source, tickers |
| ~795 | `ScoredEvent` | Fully processed event with all fields: impact_score, buy_signal, price_data, insider_activity, momentum_context, etc. |
| ~834 | `ClaudeScorer` | Calls Claude Sonnet for enhanced scoring, includes prompt injection (prices, RVOL, insiders, historical context) and post-Claude enforcement |
| ~1448 | `StockAvailabilityChecker` | Fetches real-time prices via Finnhub (includes pre/post-market), calculates RVOL via yfinance, checks broker availability (Revolut/XTB) |
| ~1854 | `InsiderActivityChecker` | Fetches SEC Form 4 filings via Finnhub API, filters noise (option exercises, 10% beneficial owners, 10b5-1 plans) |
| ~2019 | `LiveMarketState` | Tracks VIX, SPY daily change, pre-market detection, earnings season heuristic |
| ~2181 | `SignalOutcomeTracker` | Records BUY/SELL signals and tracks performance at +1h, +4h, +1d, +1w checkpoints |
| ~2331 | `EventDatabase` | SQLite fallback with tables: `events`, `signal_outcomes` |
| ~2609 | `NYSEReferenceDB` | 300+ ticker database with sector/beta/ETF mappings and supply chain relationships |
| ~3365 | `EntityExtractor` | 5-pass pipeline: explicit symbols → aliases → sector keywords → supply chain → ETF propagation |
| ~3587 | `MarketImpactScoringEngine` | Keyword-based pre-scoring with 55+ event type patterns and VIX regime weighting |
| ~3893 | `AlertDispatcher` | Console alerts with severity color coding |
| ~4312 | `NYSEImpactScreener` | Main orchestrator: combines all components, runs event loop, manages WebSocket server |

---

## Event Processing Pipeline

This is the core data flow, from raw news to the user's screen:

```
RSS Fetch (every 60s)  ──┐
                          ├──► process_event()
WebSocket drain ─────────┘         │
                                   ▼
                         ┌─────────────────┐
                    1.   │  Ingest Raw      │  Normalize headline, body, source, timestamp
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    2.   │ Entity Extract   │  5-pass ticker extraction (see below)
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    3.   │ Keyword Score    │  Automated pattern matching → impact_score
                         │                 │  Events < 40 score → DROPPED (saves AI tokens)
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    4.   │ Price + RVOL     │  Finnhub: real-time price (pre/post-market)
                         │ (primary only)   │  yfinance: RVOL (30-day volume history)
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    5.   │ SEC Form 4      │  Finnhub: insider buys/sells in last 14 days
                         │ Insider Check    │  Filters: option exercises, 10% owners, 10b5-1
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    6.   │ Claude Sonnet   │  Full LLM analysis with injected context:
                         │ Enhanced Score   │  headline + prices + RVOL + insiders + history
                         │                 │  Returns: signal, confidence, reasoning, risk
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    7.   │ Post-Claude     │  FIRST PASS enforcement:
                         │ Enforcement (1)  │  • Insider Red Flag (sells > $500K → cap 60)
                         │                 │  • C-Suite Multiplier (buys > $250K → boost 85)
                         │                 │  • Tape Contradiction (SELL on green → HOLD)
                         │                 │  • Symmetrical Volume Veto (RVOL < 0.8 → HOLD)
                         │                 │  • Global Score Aggregator (avg of ticker scores)
                         │                 │  • Sinking + dead vol → downgrade to HOLD
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    8.   │ Haiku Validate  │  Only for BUY signals with confidence > 50%
                         │ (if BUY > 50%)   │  Cross-references with corroborating sources
                         │                 │  ~20x cheaper than Sonnet
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                    9.   │ Correlated      │  Fetch prices for Claude's correlated_moves
                         │ Ticker Prices    │  and ticker_signals (tickers not already checked)
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                   10.   │ Post-Claude     │  SECOND PASS enforcement:
                         │ Enforcement (2)  │  Re-runs tape checks on correlated tickers
                         │                 │  that didn't have price data during first pass
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                   11.   │ Store + Alert   │  Insert into Supabase, record signal outcomes,
                         │ + Broadcast      │  dispatch alerts, broadcast to WebSocket clients
                         └─────────────────┘
```

---

## Entity Extraction (5-Pass Pipeline)

The `EntityExtractor` identifies which stocks a news article is about. This is critical — wrong tickers = wrong signals.

### Pass 1: Explicit Ticker Symbols
Regex patterns match `$NVDA`, `(NYSE:NVDA)`, `(NVDA)` against 3,000+ known tickers (Revolut + XTB broker lists combined).

### Pass 2: Company Name / Alias Resolution
150+ aliases map company names to tickers:
- "nvidia" → NVDA, "exxon" → XOM, "jpmorgan" → JPM
- Short/ambiguous aliases (≤3 chars) use word-boundary regex to avoid false matches
- Example: "TSMC" → TSM, "Lockheed" → LMT

### Pass 2b: Analyst Role Detection
Identifies the "messenger" vs. the "target" in analyst reports:
- "JPMorgan downgrades VMware" → actor=JPM (removed), subject=VMW (kept)
- Prevents "shooting the messenger" bug where the analyst firm's ticker contaminates the signal

### Pass 3: Sector Keyword Detection
If no tickers found, scans for sector keywords:
- "chip shortage" → Semiconductors → NVDA, AMD, INTC, SMH, SOXX
- "oil prices" → Energy → XOM, CVX, XLE, OIH
- 9 sector categories: Crypto, Semiconductors, Energy, Financials, Healthcare, Defense, Utilities, REITs, Materials

### Pass 4: Supply Chain Contagion
For each found ticker, queries the reference database for suppliers, customers, and competitors:
- AAPL found → adds TSM (supplier), QCOM (supplier)

### Pass 5: Sector & ETF Propagation
Adds sector ETFs for found tickers:
- NVDA → adds SMH, SOXX, PSI, XSD (semiconductor ETFs)
- LMT → adds ITA, PPA, XAR (defense ETFs)

---

## Claude AI Integration

### Primary Scoring (Claude Sonnet 4.6)

The LLM receives a structured prompt with all available data:

```
[HEADLINE]: Raw news headline
[BODY]: Article body (truncated to 400 chars)
[AFFECTED TICKERS]: Extracted tickers or "MACRO"
[LIVE MARKET DATA]: For each ticker:
   ${price} ({change_pct}% today), RVOL: {rvol}x (SURGING/HIGH/NORMAL/LOW)
[SEC FORM 4 INSIDER ACTIVITY]: Grouped by [TICKER]:
   Name (Title) — Open-Market Buy/Sale — $value — X days ago — [C-SUITE]
[HISTORICAL CONTEXT]: Prior 30-day events for same tickers
[AUTOMATED SCORING]: Pre-computed event_type, sentiment, impact_score
```

### Prompt Rules (Hard Constraints for Claude)

1. **"Don't shoot the messenger"** — Never include the ticker of the firm making an analyst report
2. **"No hallucinated associations"** — Only use tickers explicitly mentioned or directly impacted
3. **"Respect the tape"** — Don't issue SELL on stocks up >3% or BUY on stocks down >3%
4. **"Tape Validation Matrix"** — 8 scenarios cross-referencing news sentiment vs price action vs RVOL
5. **"C-Suite Multiplier"** — C-level open-market buys > $250K aligned with bullish news → boost confidence to 85-100
6. **"Contrarian Red Flag"** — Insider sells > $500K during bullish news → cap confidence at 60, warn of "Insider Exit Divergence"
7. **"No Insider Cross-Contamination"** — Each insider filing is strictly tied to its ticker, never attributed to others
8. **"Symmetrical Volume Veto"** — If RVOL < 0.8x (Dead Tape), cap score between 20-45 and default to HOLD. Exception: Tier-1 hard catalysts (earnings, M&A, FDA, bankruptcy)
9. **"Global Score Aggregator"** — The global headline score (top-right circle) must be the mathematical average of all per-ticker confidence scores, not a qualitative mood score

### Claude Response Format
```json
{
  "event_type": "EARNINGS_BEAT",
  "sentiment": 0.75,
  "impact_score": 82,
  "direction": "BULLISH",
  "brief": "One-sentence market impact summary",
  "buy_signal": "BUY",
  "buy_confidence": 78,
  "reasoning": ["Reason 1", "Reason 2", "Reason 3"],
  "risk": "Single biggest risk to this thesis",
  "time_horizon": "swing (1-3d)",
  "correlated_moves": ["TICKER1", "TICKER2"],
  "ticker_signals": {
    "NVDA": {"signal": "BUY", "confidence": 82},
    "AMD": {"signal": "HOLD", "confidence": 45}
  },
  "momentum_context": "How RVOL and price action align with the signal",
  "insider_context": "How SEC Form 4 data influenced the score"
}
```

### Validation Layer (Claude Haiku 4.5)
- Triggered only for BUY signals with confidence > 50%
- Cross-references the signal with up to 3 corroborating news sources
- ~20x cheaper than Sonnet ($0.80/$4.00 per 1M tokens vs $3/$15)
- Can adjust confidence up or down based on multi-source validation

---

## Post-Claude Enforcement (Programmatic Safety Nets)

These rules **override Claude's output** when market data contradicts the signal. The LLM can be persuaded by compelling narratives; the enforcement layer cannot.

### First Pass (runs immediately after Claude responds)

| Rule | Trigger | Action |
|------|---------|--------|
| **Insider Red Flag** | BUY + insider sells > $500K | Cap confidence at 60, add divergence warning |
| **Massive Insider Dump** | BUY + insider sells > $2M | Downgrade to HOLD, cap confidence at 45 |
| **C-Suite Multiplier** | BUY + C-level buys > $250K | Boost confidence to 85+ |
| **SELL on green stock** | SELL + price > 0% | Override to HOLD (cap: 30/40/50 based on magnitude) |
| **Symmetrical Volume Veto** | Any signal + RVOL < 0.8x | Force HOLD, cap at 45, floor at 20. Exempt: Tier-1 hard catalysts (earnings, M&A, FDA, bankruptcy) |
| **BUY on sinking + low vol** | BUY + price < 0% + RVOL < 0.8x | Downgrade to HOLD, cap confidence at 40 |
| **Global Score Aggregator** | Always (post-scoring) | Global impact_score = mathematical average of all per-ticker confidence scores |

### Second Pass (runs after correlated ticker prices are fetched)
Re-applies the same tape enforcement rules to all tickers in `ticker_signals`, catching correlated tickers that didn't have price data during the first pass.

---

## SEC Form 4 Insider Trading Integration

### Data Source
Finnhub API: `GET /api/v1/stock/insider-transactions?symbol={TICKER}`

### Noise Filters (Critical)
The raw SEC data is extremely noisy. The following are filtered out:
1. **Transaction code filter** — Keep only: P (Purchase) and S (Sale). Skip: A (grant), M (option exercise), G (gift), F (tax withholding)
2. **10% Beneficial Owner filter** — Removes institutional investors (Vanguard, hedge funds) doing accounting transfers
3. **10b5-1 Planned Sales** — Pre-scheduled automated selling, not a bearish signal
4. **Sanity check** — Individual transactions > $50M are flagged as institutional noise
5. **C-Suite detection** — Tags CEO, CFO, COO, CTO, President with `is_csuite: true` for multiplier rules

### Cache
30-minute TTL per ticker to avoid hitting Finnhub rate limits.

---

## Momentum Scanner (RVOL)

**RVOL (Relative Volume)** measures today's trading volume against the 30-day average:

```
RVOL = Today's Volume / 30-Day Average Volume
```

| RVOL | Label | Interpretation |
|------|-------|----------------|
| >= 2.0x | SURGING | Institutional event — high conviction moves |
| >= 1.5x | HIGH | Above-average interest, likely catalyst-driven |
| >= 0.8x | NORMAL | Typical trading day |
| < 0.8x | LOW | Below average — price moves are drift, not conviction |
| < 0.5x | DEAD | No institutional participation — signals unreliable |

**RVOL Data Source:** yfinance 1-month daily history (free, no API key required).

**Price Data Source:** Finnhub `/quote` endpoint (real-time, includes pre-market and after-hours). Falls back to yfinance if Finnhub is unavailable.

**5-minute cache TTL** to avoid redundant API calls for the same ticker within a scoring cycle.

---

## Database (Supabase PostgreSQL)

### Table: `events`
Stores every scored event that passes the impact threshold (>= 40).

| Column | Type | Description |
|--------|------|-------------|
| event_id | TEXT PK | UUID |
| timestamp | FLOAT | Unix timestamp |
| headline | TEXT | Raw headline |
| source | TEXT | Feed name |
| source_tier | INT | 1 (institutional) to 3 (sector-specific) |
| event_type | TEXT | One of 55+ EventType values |
| direction | TEXT | BULLISH / BEARISH / NEUTRAL |
| sentiment | FLOAT | -1.0 to 1.0 |
| impact_score | INT | 1-100 |
| buy_signal | TEXT | BUY / HOLD / SELL |
| buy_confidence | INT | 1-100 |
| affected_tickers | TEXT (JSON) | Primary tickers |
| affected_sectors | TEXT (JSON) | Affected sectors |
| affected_etfs | TEXT (JSON) | Related ETFs |
| stock_availability | TEXT (JSON) | Broker availability + price data |

### Table: `signal_outcomes`
Tracks signal performance over time (populated by `price_checker_cron.py`).

| Column | Type | Description |
|--------|------|-------------|
| event_id | TEXT | FK to events |
| ticker | TEXT | Stock ticker |
| signal | TEXT | BUY / SELL / HOLD |
| confidence | INT | Signal confidence at time of issuance |
| entry_price | FLOAT | Price when signal was issued |
| entry_time | FLOAT | Unix timestamp |
| price_1h / 4h / 1d / 1w | FLOAT | Price at each checkpoint |
| pct_1h / 4h / 1d / 1w | FLOAT | % change at each checkpoint |
| outcome_1h / 4h / 1d / 1w | TEXT | WIN / LOSS / FLAT |
| completed | INT | 1 when all checkpoints filled |

---

## Price Checker Cron Job (price_checker_cron.py)

Runs independently via system cron every 30 minutes during market hours:

```bash
*/30 9-16 * * 1-5 cd /path && python3 price_checker_cron.py >> /tmp/price_checker.log 2>&1
```

**Logic:**
1. Query Supabase for all pending signals (completed = 0)
2. For each signal, check if enough time has elapsed for each checkpoint (+1h, +4h, +1d, +1w)
3. Fetch current price via Finnhub (real-time, pre/post-market), fallback to yfinance
4. Calculate % change from entry price
5. Determine outcome: WIN (>+0.5% for BUY, <-0.5% for SELL), LOSS (opposite), FLAT (within ±0.5%)
6. Update the signal_outcomes row
7. Mark completed = 1 when all 4 checkpoints are filled

This runs independently of the main server — signals are tracked even when Docker is down.

---

## Backtesting API (backtesting_api.py)

HTTP API served on port 8766 alongside the main backend.

| Endpoint | Description |
|----------|-------------|
| `GET /api/backtesting/overview` | Total signals, win rates at each checkpoint, stats by signal type |
| `GET /api/backtesting/by-event-type?checkpoint=1d` | Win rates grouped by event type |
| `GET /api/backtesting/confidence-calibration?checkpoint=1d` | Predicted confidence vs actual win rate (10% buckets) |
| `GET /api/backtesting/pnl-curve?checkpoint=1d` | Cumulative P&L curve over time |
| `GET /api/backtesting/by-ticker` | Win rates per individual ticker |
| `GET /api/backtesting/signal-history?limit=100` | Recent signal outcomes with headlines |

---

## Frontend (App.js)

React single-page application connecting to the backend via WebSocket.

### WebSocket Connection
Connects to `ws://localhost:8765`. On message, parses JSON and renders event cards.

### Event Card Anatomy
```
┌──────────────────────────────────────────────────────────────────┐
│ ↑ Bullish   EARNINGS_BEAT   📋 SEC Form 4  • Reuters    5m ago (85) │  ← Header: direction, type, insider badge, source, score
│                                                                       │
│ Company X Reports Record Q3 Revenue                                   │  ← Headline
│ Summary of the market impact...                                       │  ← Brief (Claude-generated)
│                                                                       │
│ › Reason 1 from Claude                                               │  ← Reasoning bullets
│ › Reason 2 from Claude                                               │
│ › Reason 3 from Claude                                               │
│                                                                       │
│ swing (1-3d)  ⚠ Risk scenario warning...                             │  ← Time horizon + risk
│                                                                       │
│ ⚡ Momentum context: RVOL 2.3x confirms institutional buying...       │  ← Momentum (yellow box)
│                                                                       │
│ 👔 CEO bought $2.5M of $TICKER                                3d ago │  ← Insider rows (green=buy, red=sell)
│ 👔 CFO sold $1.2M of $TICKER                                 10d ago │
│                                                                       │
│ 📄 Insider context: C-suite buy confirms bullish thesis...            │  ← Insider context (purple box)
│                                                                       │
│ Also moves: TICKER2 ▲  TICKER3 —                                     │  ← Correlated moves
│                                                                       │
│ ● BUY 78% Moderate Buy   BUY $NVDA 82%   BUY $AMD 71%              │  ← Signal badges
│ ● HOLD 45% Hold          $INTC 45%                                   │  ← Per-ticker signals
│                                                                       │
│ ✓ NVDA on Revolut  ✓ NVDA on XTB  ✓ AMD on Revolut  ✓ AMD on XTB  │  ← Broker availability
│                                                                       │
│ $NVDA 875.30 +2.4% 1.8x🔥  $AMD 165.20 +1.1% 0.92x → SMH, SOXX   │  ← Ticker pills + ETFs
└──────────────────────────────────────────────────────────────────┘
```

### Ticker Pill Features
- Price + daily change % (green/red)
- RVOL value with fire icon (🔥) when >= 1.5x
- Amber highlight when RVOL >= 2.0x (surging)

### Filter Tabs
- All Events / Bullish / Bearish / Buy Signals / High Impact
- Time-based: Intraday / Swing / Medium-term

---

## Environment Variables

| Variable | Required | Source | Purpose |
|----------|----------|--------|---------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic Console | Claude Sonnet + Haiku API calls |
| `FINNHUB_API_KEY` | Yes | Finnhub.io | Real-time quotes (pre/post-market) + SEC Form 4 insider data |
| `SUPABASE_URL` | Yes | Supabase Dashboard | PostgreSQL database URL |
| `SUPABASE_KEY` | Yes | Supabase Dashboard | Database service role key |
| `BENZINGA_API_KEY` | No | Benzinga Pro | Real-time WebSocket news (optional) |
| `POLYGON_API_KEY` | No | Polygon.io | Real-time WebSocket news (optional) |

All variables are stored in `.env` at the project root. Docker Compose reads them via `env_file: .env`.

---

## API Cost Tracking

The backend tracks token usage and cost per API call:

| Model | Input Cost | Output Cost | Usage |
|-------|-----------|-------------|-------|
| Claude Sonnet 4.6 | $3.00 / 1M tokens | $15.00 / 1M tokens | Primary scoring (every event) |
| Claude Haiku 4.5 | $0.80 / 1M tokens | $4.00 / 1M tokens | Validation (BUY signals > 50% only) |
| Finnhub | Free tier (250 calls/min) | Free | Real-time quotes (pre/post-market), SEC Form 4 insider data |
| yfinance | Free | Free | RVOL calculation (30-day volume history), fallback prices |

Cost is logged per call with running totals visible in backend console output.

---

## Docker Deployment

### Start
```bash
docker compose up --build -d
```

### Stop
```bash
docker compose down
```

### View Logs
```bash
docker compose logs -f backend
```

### Services
| Service | Port | Image |
|---------|------|-------|
| backend | 8765 (WS), 8766 (HTTP) | python:3.11-slim |
| frontend | 3000 → nginx:80 | node:20-alpine (build) → nginx:alpine |

### Note on Environment Variables
The `docker-compose.yml` uses `env_file: .env` to load variables. This means Docker always reads from the `.env` file directly, ignoring shell environment variables. To update an API key, edit `.env` and restart Docker.
