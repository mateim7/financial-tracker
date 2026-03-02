# Financial Tracker

Real-time market-moving news screener with AI-powered buy/sell signals and stock availability checks.

## What it does

- Polls 11+ financial RSS feeds every 60 seconds (CNBC, MarketWatch, Yahoo Finance, etc.)
- Scores each article by market impact (0–100)
- Uses **Claude Sonnet** to generate BUY / SELL / HOLD signals with 1–100% confidence
- Checks if affected stocks are available on **Revolut** and **XTB** (via yfinance)
- Streams events in real-time to this React dashboard via WebSocket

## Requirements

- Python 3.10+
- Node.js 18+
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)

## Setup

### 1. Install Python dependencies

```bash
pip install aiohttp feedparser anthropic websockets yfinance
```

### 2. Set your Anthropic API key

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

**Mac / Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

> The key is never stored in code. You must set it each terminal session, or add it to your system environment variables permanently.

### 3. Start the Python backend

```bash
python AI_Analyzer/nyse_impact_screener.py
```

### 4. Start the React dashboard (separate terminal)

```bash
cd AI_Analyzer/nyse-screener
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Architecture

```
RSS Feeds (11 sources)
       ↓
Python backend  →  Entity extraction  →  Impact scoring
       ↓
Claude Sonnet (score ≥ 40 only)  →  BUY/SELL/HOLD + confidence %
       ↓
yfinance  →  Revolut / XTB availability check
       ↓
WebSocket (ws://localhost:8765)
       ↓
React dashboard
```

## Notes

- LOW impact events (score < 40) skip Claude to save tokens (~60% of articles)
- BUY signals above 50% confidence are cross-checked against other RSS sources before finalizing
- API key security: the key is read from environment variables only — never commit `.env` files
