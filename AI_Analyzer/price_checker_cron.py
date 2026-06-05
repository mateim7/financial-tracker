"""
Signal Price Checker — runs via system cron independently of the main server.
Checks prices for pending signal outcomes at exact checkpoint intervals.

Setup (run once):
  crontab -e
  # Add this line to run every 30 minutes during market hours (Mon-Fri, 9:30-16:00 ET):
  */30 9-16 * * 1-5 cd /home/sergiu/Desktop/financial-tracker/AI_Analyzer && python3 price_checker_cron.py >> /tmp/price_checker.log 2>&1
"""

import os
import time
import datetime

# Checkpoint definitions: (column_prefix, seconds_after_entry)
CHECKPOINTS = [
    ("1h",  3600),       # 1 hour
    ("4h",  14400),      # 4 hours
    ("1d",  86400),      # 1 day
    ("1w",  604800),     # 1 week
]

# Thresholds for WIN/LOSS/FLAT
WIN_THRESHOLD = 0.5    # +0.5% or more = WIN for BUY
FLAT_THRESHOLD = 0.5   # within ±0.5% = FLAT


def get_current_price(ticker: str) -> float | None:
    """Fetch current price via yfinance."""
    try:
        import yfinance as yf
        # Handle dot-notation tickers (BRK.B → BRK-B for yfinance)
        yf_ticker = ticker.replace(".", "-")
        t = yf.Ticker(yf_ticker)
        data = t.history(period="1d")
        if not data.empty:
            return round(float(data["Close"].iloc[-1]), 2)
    except Exception as e:
        print(f"  [Price] Failed to fetch {ticker}: {e}")
    return None


def determine_outcome(signal: str, pct_change: float) -> str:
    """Determine WIN/LOSS/FLAT based on signal direction and price change."""
    if abs(pct_change) < FLAT_THRESHOLD:
        return "FLAT"
    if signal == "BUY":
        return "WIN" if pct_change > 0 else "LOSS"
    elif signal == "SELL":
        return "WIN" if pct_change < 0 else "LOSS"
    return "FLAT"


def run():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("[Cron] SUPABASE_URL/SUPABASE_KEY not set. Skipping.")
        return

    try:
        from supabase import create_client
    except ImportError:
        print("[Cron] supabase package not installed. Run: pip install supabase")
        return

    client = create_client(url, key)
    now = time.time()
    now_dt = datetime.datetime.now()
    print(f"\n[Cron] Price check at {now_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    # Fetch all pending (incomplete) signal outcomes
    result = client.table("signal_outcomes").select("*").eq("completed", 0).execute()
    pending = result.data or []

    if not pending:
        print("[Cron] No pending signals to check.")
        return

    print(f"[Cron] Found {len(pending)} pending signal(s)")

    updated_count = 0
    price_cache = {}  # Cache prices to avoid duplicate API calls

    for row in pending:
        event_id = row["event_id"]
        ticker = row["ticker"]
        signal = row.get("signal", "HOLD")
        entry_price = row.get("entry_price")
        entry_time = row.get("entry_time")

        if not entry_price or not entry_time:
            continue

        needs_update = False
        update_data = {}

        for cp, delay in CHECKPOINTS:
            price_col = f"price_{cp}"
            pct_col = f"pct_{cp}"
            outcome_col = f"outcome_{cp}"

            # Skip if already filled
            if row.get(price_col) is not None:
                continue

            # Check if enough time has passed
            if now < entry_time + delay:
                continue

            # Time has passed — fetch current price
            if ticker not in price_cache:
                price_cache[ticker] = get_current_price(ticker)

            current_price = price_cache[ticker]
            if current_price is None:
                continue

            # Calculate percentage change
            pct = round(((current_price - entry_price) / entry_price) * 100, 2)
            outcome = determine_outcome(signal, pct)

            update_data[price_col] = current_price
            update_data[pct_col] = pct
            update_data[outcome_col] = outcome
            needs_update = True

            print(f"  [{ticker}] {cp}: ${entry_price} → ${current_price} ({pct:+.2f}%) = {outcome}")

        # Check if all checkpoints are now filled
        all_filled = True
        for cp, _ in CHECKPOINTS:
            if row.get(f"price_{cp}") is None and f"price_{cp}" not in update_data:
                all_filled = False
                break

        if all_filled and needs_update:
            update_data["completed"] = 1
            print(f"  [{ticker}] All checkpoints filled — marking as completed")

        if needs_update:
            client.table("signal_outcomes").update(update_data).eq(
                "event_id", event_id
            ).eq("ticker", ticker).execute()
            updated_count += 1

    print(f"[Cron] Updated {updated_count} signal(s)")


if __name__ == "__main__":
    run()
