"""
SEC Form 4 Insider Activity Checker for the NYSE Impact Screener.
"""

import time
import os
import asyncio
from datetime import datetime, timedelta


class InsiderActivityChecker:
    """
    Fetches recent SEC Form 4 filings for tickers via Finnhub.
    Filters out noise (option exercises, 10b5-1 planned sales) and keeps
    only open-market buys/sells by officers and directors within the last 14 days.
    Results are cached for 30 minutes per ticker to avoid rate limits.
    """

    # Finnhub transactionCode mapping:
    #   P = Open-Market Purchase, S = Open-Market Sale
    #   A = Grant/Award, M = Option Exercise, G = Gift, F = Tax withholding
    # We only care about P and S — genuine open-market intent.
    _SIGNAL_CODES = {"P": "Open-Market Buy", "S": "Open-Market Sale"}

    # C-suite titles that trigger the multiplier/red-flag rules
    _CSUITE_TITLES = {"ceo", "cfo", "coo", "cto", "president", "chief executive officer",
                      "chief financial officer", "chief operating officer", "chief technology officer"}

    # 10% beneficial owners are institutional holders (hedge funds, Vanguard, etc.)
    # whose filings are accounting transfers, not conviction trades. Filter them out.
    _INSTITUTIONAL_NOISE = {"10% owner", "10% beneficial owner", "10 percent owner",
                            "beneficial owner", "10%"}

    # Individual open-market purchases rarely exceed $50M. Anything above is almost
    # certainly an institutional block trade, secondary offering, or data error.
    _MAX_SANE_VALUE = 50_000_000

    def __init__(self):
        self._api_key = os.environ.get("FINNHUB_API_KEY", "")
        self._cache: dict[str, dict] = {}  # {ticker: {"data": [...], "ts": float}}
        self._cache_ttl = 1800  # 30 minutes

    def _is_fresh(self, ticker: str) -> bool:
        entry = self._cache.get(ticker)
        return entry is not None and (time.time() - entry["ts"]) < self._cache_ttl

    async def check_tickers(self, tickers: list[str]) -> dict[str, list[dict]]:
        """
        Returns {ticker: [insider_tx, ...]} where each insider_tx is:
        {
            "name": str, "title": str, "type": "Open-Market Buy" | "Open-Market Sale",
            "shares": int, "value": float, "date": str (YYYY-MM-DD), "days_ago": int,
            "is_csuite": bool
        }
        Only includes transactions from the last 14 days with transaction codes P or S.
        """
        if not self._api_key:
            return {t: [] for t in tickers}

        results = {t: self._cache[t]["data"] for t in tickers if self._is_fresh(t)}
        uncached = [t for t in tickers if not self._is_fresh(t)]

        if uncached:
            fetched = await asyncio.gather(*[asyncio.to_thread(self._fetch_one, t) for t in uncached])
            for ticker, data in fetched:
                self._cache[ticker] = {"data": data, "ts": time.time()}
                results[ticker] = data

        return results

    def _fetch_one(self, ticker: str) -> tuple[str, list[dict]]:
        import requests
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=14)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/stock/insider-transactions",
                params={"symbol": ticker, "from": cutoff_str, "token": self._api_key},
                timeout=8,
            )
            if resp.status_code != 200:
                print(f"  [SEC] Finnhub {resp.status_code} for {ticker}")
                return ticker, []

            raw = resp.json().get("data", [])
            transactions = []

            for tx in raw:
                code = (tx.get("transactionCode") or "").upper()
                if code not in self._SIGNAL_CODES:
                    continue  # skip option exercises, grants, gifts, tax withholding

                # Filter out 10b5-1 planned sales (flagged in Finnhub data)
                if tx.get("is10b51"):
                    continue

                filing_date = tx.get("filingDate", "")
                if not filing_date or filing_date < cutoff_str:
                    continue

                filer_name = (tx.get("name", "") or "").strip()

                # ── CRITICAL: Filter out 10% Beneficial Owners ──
                # These are institutional holders (hedge funds, Vanguard, BlackRock, etc.)
                # whose Form 4 filings represent internal fund transfers, options conversions,
                # or secondary offerings — NOT genuine conviction trades.
                filer_lower = filer_name.lower()
                is_10pct_owner = any(noise in filer_lower for noise in self._INSTITUTIONAL_NOISE)
                if is_10pct_owner:
                    print(f"  [SEC] Filtered out 10% Owner filing: {filer_name} ({ticker})")
                    continue

                shares = abs(tx.get("share", 0) or 0)
                price = tx.get("transactionPrice") or 0
                value = round(shares * price, 2) if price else 0

                # ── Value sanity check ──
                # Individual officers don't buy/sell $50M+ on open market.
                # If value exceeds threshold, it's likely institutional noise that
                # slipped past the 10% owner filter.
                if value > self._MAX_SANE_VALUE:
                    print(f"  [SEC] Filtered suspiciously large tx: {filer_name} "
                          f"${value:,.0f} ({ticker}) — likely institutional")
                    continue

                # Extract title — Finnhub puts role info in the name field
                insider_title = ""
                for label in ["CEO", "CFO", "COO", "CTO", "President", "Director",
                              "VP", "SVP", "EVP", "General Counsel", "Secretary",
                              "Chief Executive", "Chief Financial", "Chief Operating",
                              "Chief Technology", "Officer"]:
                    if label.lower() in filer_lower:
                        insider_title = label
                        break

                days_ago = (datetime.now() - datetime.strptime(filing_date, "%Y-%m-%d")).days

                is_csuite = any(t in filer_lower for t in self._CSUITE_TITLES)

                transactions.append({
                    "name": filer_name,
                    "title": insider_title or "Insider",
                    "type": self._SIGNAL_CODES[code],
                    "shares": shares,
                    "value": value,
                    "date": filing_date,
                    "days_ago": days_ago,
                    "is_csuite": is_csuite,
                })

            # Sort by value descending — most significant trades first
            transactions.sort(key=lambda x: x["value"], reverse=True)

            if transactions:
                total_buy = sum(t["value"] for t in transactions if t["type"] == "Open-Market Buy")
                total_sell = sum(t["value"] for t in transactions if t["type"] == "Open-Market Sale")
                buy_count = sum(1 for t in transactions if t["type"] == "Open-Market Buy")
                sell_count = sum(1 for t in transactions if t["type"] == "Open-Market Sale")
                print(f"  [SEC] {ticker}: {len(transactions)} insider tx (14d) — "
                      f"{buy_count} buys ${total_buy:,.0f} / {sell_count} sells ${total_sell:,.0f}")

            return ticker, transactions[:5]  # cap at top 5 by value

        except Exception as e:
            print(f"  [SEC] Error fetching insider data for {ticker}: {e}")
            return ticker, []
