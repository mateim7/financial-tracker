"""
RSS Feed source for the NYSE Impact Screener.
"""

import asyncio
import re
import time
import hashlib


RSS_SOURCES = [
    # ── Tier 1: Wire Services & Institutional (fastest, most reliable) ──────
    {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",     "name": "MarketWatch DJ",    "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",                "name": "WSJ Business",      "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                  "name": "WSJ Markets",       "tier": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",                    "name": "WSJ World",         "tier": 1},
    {"url": "https://feeds.reuters.com/reuters/businessNews",                  "name": "Reuters Business",  "tier": 1},
    {"url": "https://feeds.reuters.com/reuters/companyNews",                   "name": "Reuters Companies", "tier": 1},
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml",                 "name": "BBC Business",      "tier": 1},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",      "name": "NYT Business",      "tier": 1},
    {"url": "https://feeds.ft.com/rss/companies/us",                          "name": "FT US Companies",   "tier": 1},
    {"url": "https://feeds.bloomberg.com/markets/news.rss",                   "name": "Bloomberg Mkts",    "tier": 1},

    # ── Tier 2: Professional Financial Media ─────────────────────────────────
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",          "name": "CNBC",              "tier": 2},
    {"url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",           "name": "CNBC Markets",      "tier": 2},
    {"url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",           "name": "CNBC Finance",      "tier": 2},
    {"url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",           "name": "CNBC Tech",         "tier": 2},
    {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",           "name": "CNBC Economy",      "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/",          "name": "MarketWatch",       "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/marketpulse/",         "name": "MW Pulse",          "tier": 2},
    {"url": "https://www.investing.com/rss/news.rss",                         "name": "Investing.com",     "tier": 2},
    {"url": "https://www.investing.com/rss/market_overview.rss",              "name": "Investing Mkt",     "tier": 2},
    {"url": "https://finance.yahoo.com/news/rssindex",                        "name": "Yahoo Finance",     "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EGSPC",          "name": "Yahoo S&P News",    "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EDJI",           "name": "Yahoo DJIA News",   "tier": 2},
    {"url": "https://finance.yahoo.com/rss/2.0/headline?s=%5EIXIC",          "name": "Yahoo Nasdaq News", "tier": 2},
    {"url": "https://seekingalpha.com/feed.xml",                              "name": "Seeking Alpha",     "tier": 2},
    {"url": "https://seekingalpha.com/feed/market-news.xml",                  "name": "SA Market News",    "tier": 2},
    {"url": "https://www.benzinga.com/feed",                                  "name": "Benzinga",          "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=Markets",       "name": "Nasdaq Markets",    "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=Earnings",      "name": "Nasdaq Earnings",   "tier": 2},
    {"url": "https://www.nasdaq.com/feed/rssoutbound?category=IPOs",          "name": "Nasdaq IPOs",       "tier": 2},
    {"url": "https://www.barrons.com/feed",                                   "name": "Barron's",          "tier": 2},

    # ── Tier 2: Wire / PR (earnings releases, M&A, FDA) ─────────────────────
    {"url": "https://feeds.businesswire.com/rss/home/?rss=G1&rssid=1",       "name": "Business Wire",     "tier": 2},
    {"url": "https://www.globenewswire.com/RssFeed/subjectcode/17-Financial%20Markets", "name": "GlobeNewsWire", "tier": 2},
    {"url": "https://www.prnewswire.com/rss/news-releases-list.rss",          "name": "PR Newswire",       "tier": 2},
    {"url": "https://www.accesswire.com/rss/feed.aspx",                       "name": "AccessWire",        "tier": 2},

    # ── Tier 2: Macro / Geopolitical / Commodities ───────────────────────────
    {"url": "https://feeds.reuters.com/reuters/world-news",                    "name": "Reuters World",     "tier": 2},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",       "name": "NYT Economy",       "tier": 2},
    {"url": "https://feeds.feedburner.com/zaborskaya/oil-price",              "name": "Oil Price",         "tier": 2},
    {"url": "https://www.federalreserve.gov/feeds/press_all.xml",             "name": "Fed Reserve",       "tier": 1},

    # ── Tier 3: Sector-specific ──────────────────────────────────────────────
    {"url": "https://techcrunch.com/feed/",                                    "name": "TechCrunch",        "tier": 3},
    {"url": "https://www.theverge.com/rss/index.xml",                          "name": "The Verge",         "tier": 3},
    {"url": "https://arstechnica.com/feed/",                                   "name": "Ars Technica",      "tier": 3},
    {"url": "https://www.statnews.com/feed/",                                  "name": "STAT News",         "tier": 3},
    {"url": "https://www.fiercepharma.com/rss/xml",                            "name": "Fierce Pharma",     "tier": 3},
    {"url": "https://electrek.co/feed/",                                       "name": "Electrek",          "tier": 3},
    {"url": "https://www.spglobal.com/commodityinsights/en/rss-feed/oil",     "name": "S&P Oil",           "tier": 3},
]

# ── Per-ticker Yahoo Finance RSS — watches these stocks specifically ─────────
_TICKER_WATCH = [
    # Mega-cap (Big 7)
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA",
    # Semis
    "AMD", "INTC", "TSM", "AVGO", "QCOM", "ARM", "MU", "ASML",
    # AI / Cloud / SaaS
    "PLTR", "CRWD", "PANW", "NET", "SNOW", "DDOG", "NOW", "CRM", "ORCL",
    # Crypto-adjacent
    "COIN", "MSTR", "RIOT", "MARA", "HOOD", "SOFI",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "SQ", "SCHW",
    # Healthcare / Pharma
    "LLY", "MRNA", "ABBV", "UNH", "REGN", "VRTX",
    # Energy
    "XOM", "CVX", "OXY",
    # Consumer / Media
    "NFLX", "DIS", "NKE", "SBUX", "MCD",
    # EVs
    "RIVN", "LCID", "GM", "F",
    # Popular high-volume trades
    "SMCI", "SHOP", "SNAP", "RBLX", "LYFT", "DASH", "ROKU",
]
RSS_SOURCES += [
    {"url": f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US",
     "name": f"Yahoo/{t}", "tier": 2}
    for t in _TICKER_WATCH
]

class RSSFeed:
    def __init__(self):
        self._seen_ids: set = set()
        self._seen_headline_hashes: set = set()
        self._recent_articles: list = []

    @staticmethod
    def _headline_hash(headline: str) -> str:
        """Normalize headline and return an MD5 hash for cross-source deduplication."""
        normalized = re.sub(r'[^a-z0-9]', '', headline.lower())
        return hashlib.md5(normalized.encode()).hexdigest()

    async def fetch(self) -> list[dict]:
        import feedparser
        import aiohttp
        import email.utils

        cutoff = time.time() - 3600  # only articles from last 1 hour
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FinanceScreener/1.0)"}
        connector = aiohttp.TCPConnector(ssl=False)  # skip SSL cert verify for some feeds

        async def fetch_source(session: aiohttp.ClientSession, source: dict) -> list[dict]:
            items = []
            try:
                async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    text = await resp.text()
                feed = feedparser.parse(text)
                for entry in feed.entries:
                    uid = entry.get("id") or entry.get("link") or entry.get("title")
                    if not uid or uid in self._seen_ids:
                        continue
                    # ── 60-Minute Hard Stop: only process articles published within last hour ──
                    # Rule 1: Articles older than 60 minutes are discarded immediately
                    # Rule 2: Use the ORIGINAL publication timestamp, not scrape/index time
                    # Rule 3: If no valid publication date can be determined, discard the article
                    pub_ts = None
                    published = entry.get("published") or entry.get("updated")
                    if published:
                        try:
                            pub_ts = email.utils.parsedate_to_datetime(published).timestamp()
                        except Exception:
                            # Try feedparser's parsed time tuple as fallback
                            pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                            if pub_struct:
                                try:
                                    import calendar
                                    pub_ts = calendar.timegm(pub_struct)
                                except Exception:
                                    pass
                    else:
                        # No date string — try parsed structs directly
                        pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                        if pub_struct:
                            try:
                                import calendar
                                pub_ts = calendar.timegm(pub_struct)
                            except Exception:
                                pass

                    # STRICT: No valid publication timestamp → skip entirely
                    if pub_ts is None:
                        continue
                    # STRICT: Article older than 60 minutes → discard
                    if pub_ts < cutoff:
                        continue
                    # Guard against future timestamps (clock skew) — clamp to now
                    if pub_ts > time.time() + 300:  # allow 5min tolerance
                        continue
                    raw_title = entry.get("title", "").strip()
                    if not raw_title:
                        continue
                    # Strip HTML tags from title and body (some feeds embed raw HTML)
                    headline = re.sub(r'<[^>]+>', '', raw_title).strip()
                    headline = headline.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
                    if not headline:
                        continue
                    raw_body = entry.get("summary", entry.get("description", ""))
                    body = re.sub(r'<[^>]+>', '', raw_body).strip() if raw_body else ""
                    items.append({
                        "uid": uid,
                        "source": source["name"],
                        "source_tier": source["tier"],
                        "headline": headline,
                        "body": body,
                        "link": entry.get("link", ""),
                        "pub_ts": pub_ts,  # original publication timestamp
                    })
            except Exception as e:
                print(f"  [RSS] Failed to fetch {source['name']}: {e}")
            return items

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            results = await asyncio.gather(
                *[fetch_source(session, source) for source in RSS_SOURCES]
            )

        new_items = []
        for source_items in results:
            for item in source_items:
                uid = item.pop("uid")
                if uid in self._seen_ids:
                    continue
                self._seen_ids.add(uid)
                h = self._headline_hash(item["headline"])
                if h in self._seen_headline_hashes:
                    continue
                self._seen_headline_hashes.add(h)
                new_items.append(item)

        self._recent_articles.extend(new_items)
        self._recent_articles = self._recent_articles[-600:]
        return new_items
