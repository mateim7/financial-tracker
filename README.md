# Financial Tracker

Real-time market-moving news screener with AI-powered buy/sell signals and stock availability checks.

## What it does

- Polls 90+ financial RSS feeds every 60 seconds (CNBC, MarketWatch, Yahoo Finance, Reuters, etc.)
- Connects to **real-time WebSocket news feeds** (Finnhub, Benzinga, Polygon.io) for instant alerts
- Scores each article by market impact (0-100)
- Uses **Claude Sonnet** to generate BUY / SELL / HOLD signals with 1-100% confidence
- Generates **per-ticker signals** (different directions for different assets in the same event)
- Checks if affected stocks are available on **Revolut** and **XTB** (via yfinance)
- Streams events in real-time to the React dashboard via WebSocket

## Requirements

- Python 3.10+
- Node.js 18+
- An Anthropic API key (required)
- Finnhub / Benzinga / Polygon.io API keys (optional, for real-time WebSocket feeds)

## API Keys Setup

All API keys are set as **environment variables** — never commit them to code or `.env` files.

### 1. Anthropic (required)

Powers the Claude Sonnet AI analysis. Get a key at [console.anthropic.com](https://console.anthropic.com).

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### 2. WebSocket News Feeds (optional, recommended)

These give you **real-time news** (1-3 second latency) instead of waiting for RSS polls (60 seconds). You can use one, two, or all three — they run simultaneously.

| Provider | Tier | Cost | Sign up |
|----------|------|------|---------|
| **Finnhub** | Free tier available | Free (60 calls/min) | [finnhub.io](https://finnhub.io/register) |
| **Polygon.io** | Free tier available | Free (5 calls/min) | [polygon.io](https://polygon.io/dashboard/signup) |
| **Benzinga** | Professional | Paid | [benzinga.com/apis](https://www.benzinga.com/apis) |

```bash
# Set whichever keys you have — any combination works
export FINNHUB_API_KEY="your_finnhub_key"
export POLYGON_API_KEY="your_polygon_key"
export BENZINGA_API_KEY="your_benzinga_key"
```

### Make keys permanent (persist across terminal sessions)

Add the export lines to your shell profile so you don't have to set them every time:

**Linux / Mac:**
```bash
# Add to the end of ~/.bashrc (or ~/.zshrc for Mac)
echo 'export ANTHROPIC_API_KEY="your_key"' >> ~/.bashrc
echo 'export FINNHUB_API_KEY="your_key"' >> ~/.bashrc
echo 'export POLYGON_API_KEY="your_key"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "your_key", "User")
[System.Environment]::SetEnvironmentVariable("FINNHUB_API_KEY", "your_key", "User")
[System.Environment]::SetEnvironmentVariable("POLYGON_API_KEY", "your_key", "User")
```

### Verify your API keys

Run the built-in health check to confirm everything is working:

```bash
python3 AI_Analyzer/test_api_keys.py
```

Output (all keys configured):
```
══════════════════════════════════════════════════════════
  API Key Health Check
══════════════════════════════════════════════════════════

  Anthropic (Claude Sonnet)
    ✓ Anthropic API key is valid!

  Finnhub (News WebSocket)
    ✓ Working!

  Benzinga Pro (News WebSocket)
    ✓ Working!

  Polygon.io (News WebSocket)
    ✓ Working!

  Summary
  ✓ Anthropic
  ✓ Finnhub
  ✓ Benzinga
  ✓ Polygon

  WebSocket news feeds ready: 3/3
```

| Symbol | Meaning |
|--------|---------|
| `✓` | API key is valid and working |
| `✗` | API key is set but invalid — double-check you copied it correctly |
| `○` | API key not set (optional — system works without it) |

## Setup

### Option A: Docker (recommended)

The easiest way to run everything with a single command.

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

```bash
# Make sure your API keys are exported (see above), then:
docker compose up --build
```

This starts:
- **Backend** (Python) on ports `8765` (WebSocket) and `8766` (HTTP API)
- **Frontend** (React via Nginx) on port `3000`

Open [http://localhost:3000](http://localhost:3000) in your browser.

To run in the background:
```bash
docker compose up --build -d
```

To stop:
```bash
docker compose down
```

### Option B: Manual setup

#### 1. Install Python dependencies

```bash
pip install aiohttp feedparser anthropic websockets yfinance
```

#### 2. Set your API keys

See the [API Keys Setup](#api-keys-setup) section above.

#### 3. Start the Python backend

```bash
python3 AI_Analyzer/nyse_impact_screener.py
```

#### 4. Start the React dashboard (separate terminal)

```bash
cd AI_Analyzer/nyse-screener
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Architecture

```
News Sources
├── RSS Feeds (90+ sources, polled every 60s)
└── WebSocket Feeds (Finnhub, Benzinga, Polygon — real-time push)
            ↓
   Python backend
            ↓
   Entity Extraction (5-pass: tickers, aliases, sectors, supply chain, ETFs)
            ↓
   Impact Scoring (55+ event types, VIX regime, market cap, beta)
            ↓
   Claude Sonnet (score ≥ 40 only — saves ~60% tokens)
   → BUY/SELL/HOLD + per-ticker signals + confidence %
            ↓
   yfinance → Revolut / XTB availability check
            ↓
   WebSocket broadcast (ws://localhost:8765)
            ↓
   React dashboard (http://localhost:3000)
```

## Notes

- LOW impact events (score < 40) skip Claude to save tokens (~60% of articles)
- BUY signals above 50% confidence are cross-checked against other sources before finalizing
- WebSocket feeds auto-detect which API keys are configured — no code changes needed
- If no WebSocket keys are set, the system runs in RSS-only mode (still fully functional, just slower)
- API key security: keys are read from environment variables only — never stored in project files
