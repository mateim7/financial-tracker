import re
from backend.algorithm.NYSEReferenceDB import NYSEReferenceDB
from backend.algorithm.StockAvailabilityChecker import StockAvailabilityChecker

class EntityExtractor:
    """
    Multi-pass entity extraction with supply chain propagation.

    Pass 1: Explicit ticker symbols ($NVDA, NYSE:NVDA)
    Pass 2: Company name / alias resolution
    Pass 3: Sector keyword detection for macro events
    Pass 4: Supply chain contagion graph traversal
    Pass 5: Sector â†’ ETF propagation
    """

    # Aliases that are common English words â€” always require word-boundary matching
    # regardless of length, to prevent false extraction from news text.
    AMBIGUOUS_ALIASES = {
        "ge", "arm", "lam", "ups", "citi", "chase", "visa", "coke", "now",
        "oxy", "all", "it", "on", "an", "key", "car", "run", "well",
        "lilly", "pioneer", "gold", "ford",
    }

    # Patterns to detect analyst/rater role and separate actor from target.
    # Group "actor" captures the firm performing the action (analyst).
    # These patterns match common headline structures for upgrades/downgrades.
    ANALYST_ACTION_PATTERNS = [
        # "VMC downgraded to Neutral by JPMorgan" / "VMC upgraded by Goldman Sachs"
        re.compile(
            r'(?:downgrade[sd]?|upgrade[sd]?|rated|cut|initiated?|reiterate[sd]?'
            r'|maintained?|raises?\s+(?:price\s+)?target|lowers?\s+(?:price\s+)?target'
            r'|overweight|underweight|outperform|underperform|neutral|sell\s+rating'
            r'|buy\s+rating)\s+.*?\bby\s+(?P<actor>.+?)(?:\s*[,;.\-â€”]|\s+(?:as|amid|after|on|citing|due|with|the|saying|over|ahead|following|here))',
            re.IGNORECASE,
        ),
        # "JPMorgan downgrades VMC" / "Goldman Sachs upgrades AAPL"
        re.compile(
            r'(?P<actor>.+?)\s+(?:downgrade[sd]?|upgrade[sd]?|initiate[sd]?'
            r'|reiterate[sd]?|maintain[sd]?|cut[sd]?|rate[sd]?'
            r'|raises?\s+(?:price\s+)?target|lowers?\s+(?:price\s+)?target'
            r'|starts?\s+coverage|begins?\s+coverage)\s',
            re.IGNORECASE,
        ),
        # "Goldman warns of..." / "Jack Dorsey praises..." / "Morgan Stanley expects..."
        # Person/firm is the COMMENTATOR or ENDORSER, not the subject of the news
        re.compile(
            r'(?P<actor>.+?)\s+(?:warns?|says?|expects?|predicts?|forecasts?'
            r'|sees?\b|projects?|estimates?|cautions?|flags?|notes?'
            r'|believes?|analysts?\s+at|strategists?\s+at|economists?\s+at'
            r'|research\s+from|according\s+to|report\s+from|reaffirms?'
            r'|highlights?|signals?|recommends?'
            r'|praises?|endorses?|backs?|supports?|touts?|applauds?'
            r'|criticizes?|slams?|blasts?|questions?|doubts?)\s',
            re.IGNORECASE,
        ),
        # "...warns Goldman" / "...says JPMorgan" / "...praises Jack Dorsey"
        re.compile(
            r'(?:warns?|says?|expects?|predicts?|forecasts?|sees?'
            r'|projects?|estimates?|cautions?|flags?|notes?'
            r'|believes?|according\s+to|report\s+(?:from|by)'
            r'|praises?|endorses?|backs?|supports?|touts?)\s+(?P<actor>.+?)(?:\s*[,;.\-â€”]|$)',
            re.IGNORECASE,
        ),
    ]

    def __init__(self, reference_db: NYSEReferenceDB):
        self.db = reference_db
        self.ticker_pattern = re.compile(
            r'(?:\$([A-Z]{1,5}))'                             # $VMC
            r'|(?:\((?:NYSE|NASDAQ)\s*:\s*([A-Z]{1,5})\))'    # (NYSE:VMC)
            r'|(?:\(([A-Z]{1,5})\))'                          # (VMC) â€” parenthesized ticker
        )
        # Combined set of all known tickers (detailed DB + broker lists)
        self._all_known_tickers = (
            set(self.db.tickers.keys())
            | StockAvailabilityChecker.REVOLUT_TICKERS
            | StockAvailabilityChecker.XTB_TICKERS
        )
        # Precompile word-boundary regex for short/ambiguous aliases
        self._alias_patterns: dict[str, tuple[re.Pattern, str]] = {}
        for alias, ticker in self.db.aliases.items():
            if len(alias) <= 3 or alias in self.AMBIGUOUS_ALIASES:
                self._alias_patterns[alias] = (
                    re.compile(r'\b' + re.escape(alias) + r'\b'),
                    ticker,
                )
            else:
                self._alias_patterns[alias] = (None, ticker)  # plain substring

        # â”€â”€ spaCy NER (Pass 0) â€” catches entities the alias DB misses â”€â”€
        self._nlp = None
        try:
            import spacy
            self._nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
            # Add custom entity ruler for financial institutions / central banks
            ruler = self._nlp.add_pipe("entity_ruler", before="ner")
            financial_patterns = [
                {"label": "ORG", "pattern": "the Fed"},
                {"label": "ORG", "pattern": "Federal Reserve"},
                {"label": "ORG", "pattern": "ECB"},
                {"label": "ORG", "pattern": "European Central Bank"},
                {"label": "ORG", "pattern": "PBOC"},
                {"label": "ORG", "pattern": "Bank of Japan"},
                {"label": "ORG", "pattern": "Bank of England"},
                {"label": "ORG", "pattern": "SEC"},
                {"label": "ORG", "pattern": "FTC"},
                {"label": "ORG", "pattern": "DOJ"},
                {"label": "ORG", "pattern": "OPEC"},
                {"label": "ORG", "pattern": "OPEC+"},
            ]
            ruler.add_patterns(financial_patterns)
            print("  [NER] spaCy en_core_web_sm loaded with financial entity ruler")
        except (ImportError, OSError) as e:
            print(f"  [NER] spaCy not available ({e}) â€” using keyword extraction only")

        # Build reverse lookup: lowercase company name â†’ ticker for NER resolution
        self._company_to_ticker: dict[str, str] = {}
        for ticker, info in self.db.tickers.items():
            if "name" in info:
                self._company_to_ticker[info["name"].lower()] = ticker
        # Also add aliases as company names
        for alias, ticker in self.db.aliases.items():
            if len(alias) > 4:  # only longer aliases to avoid false matches
                self._company_to_ticker[alias.lower()] = ticker

        # Sector keywords for macro events that don't mention specific companies.
        # Order matters: Crypto is checked first so "bitcoin" articles don't fall
        # through to Materials just because "gold" appears in comparison text.
        self.sector_keywords: dict[str, list[str]] = {
            "Crypto": ["bitcoin", "btc", "ethereum", "eth ", "crypto", "cryptocurrency",
                       "blockchain", "defi", "stablecoin", "digital asset", "microstrategy",
                       "bitcoin etf", "spot etf", "crypto regulation", "digital currency",
                       "altcoin", "memecoin", "nft"],
            "Semiconductors": ["chip", "semiconductor", "wafer", "fab ", "foundry", "gpu", "ai chip",
                               "hbm", "memory chip", "processor", "lithography"],
            "Energy": ["oil", "crude", "natural gas", "lng", "opec", "drilling", "refinery",
                       "pipeline", "barrel", "permian", "shale", "petroleum", "brent", "wti"],
            "Financials": ["banking", "interest rate", "loan", "mortgage", "credit card",
                           "lending", "deposit", "yield curve", "net interest"],
            "Healthcare": ["drug", "pharma", "clinical trial", "fda", "medicare", "medicaid",
                           "hospital", "vaccine", "biotech", "gene therapy", "obesity drug"],
            "Defense": ["defense contract", "pentagon", "military", "weapon", "missile",
                        "fighter jet", "nato", "defense spending", "arms"],
            "Utilities": ["power grid", "electricity", "nuclear", "renewable", "solar",
                          "wind farm", "data center power", "grid reliability"],
            "REITs": ["commercial real estate", "office vacancy", "data center",
                      "warehouse", "industrial real estate", "cell tower"],
            "Materials": ["copper", "gold price", "gold miner", "steel", "aluminum", "lithium",
                          "rare earth", "mining", "commodity", "iron ore", "gold futures",
                          "precious metal"],
        }

    def extract(self, headline: str, body: str = "") -> dict:
        text = f"{headline} {body}"
        found_tickers = set()
        found_sectors = set()
        found_etfs = set()
        found_supply_chain = set()
        found_contagion = set()

        # Pass 0: spaCy NER â€” catch company/org entities the alias DB misses
        if self._nlp:
            doc = self._nlp(headline)  # Only headline for speed â€” body is noisy
            for ent in doc.ents:
                if ent.label_ in ("ORG", "PRODUCT"):
                    ent_lower = ent.text.lower()
                    # Try direct company name â†’ ticker resolution
                    if ent_lower in self._company_to_ticker:
                        found_tickers.add(self._company_to_ticker[ent_lower])
                    else:
                        # Fuzzy: check if any known company name starts with or contains the entity
                        for name, ticker in self._company_to_ticker.items():
                            if len(ent_lower) >= 5 and (ent_lower in name or name in ent_lower):
                                found_tickers.add(ticker)
                                break

        # Pass 1: Explicit ticker symbols ($VMC, NYSE:VMC, or (VMC))
        for match in self.ticker_pattern.finditer(text):
            ticker = match.group(1) or match.group(2) or match.group(3)
            if ticker in self._all_known_tickers:
                found_tickers.add(ticker)

        # Pass 2: Company name / alias resolution (word-boundary safe)
        text_lower = text.lower()
        for alias, (pattern, ticker) in self._alias_patterns.items():
            if pattern is not None:
                # Short or ambiguous alias â€” require whole-word match
                if pattern.search(text_lower):
                    found_tickers.add(ticker)
            else:
                # Longer, unambiguous alias â€” substring is safe
                if alias in text_lower:
                    found_tickers.add(ticker)

        # Pass 2b: Analyst role detection â€” identify actor (analyst firm) tickers.
        # These will be removed AFTER all passes so that sector/supply-chain tickers
        # are available as targets. This fixes cases like "Goldman warns of GDP drag"
        # where GS is the only ticker at this point but oil/macro tickers come later.
        analyst_tickers = set()
        headline_lower = headline.lower()
        for pattern in self.ANALYST_ACTION_PATTERNS:
            m = pattern.search(headline_lower)
            if m:
                actor_text = m.group("actor").strip()
                # Resolve the actor text to a ticker via aliases
                for alias, (apatt, aticker) in self._alias_patterns.items():
                    if apatt is not None:
                        if apatt.search(actor_text):
                            analyst_tickers.add(aticker)
                    else:
                        if alias in actor_text:
                            analyst_tickers.add(aticker)
                # Also check explicit ticker symbols in the actor text
                for tmatch in self.ticker_pattern.finditer(actor_text):
                    t = tmatch.group(1) or tmatch.group(2) or tmatch.group(3)
                    if t in self._all_known_tickers:
                        analyst_tickers.add(t)
                break  # first matching pattern is enough

        # Pass 3: Sector keyword detection (for macro / broad events)
        detected_sectors_from_keywords = set()
        for sector, keywords in self.sector_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    detected_sectors_from_keywords.add(sector)
                    break

        # If no real target tickers found (empty or only analyst messengers),
        # use sector keywords to flag sector-wide impact
        real_tickers = found_tickers - analyst_tickers
        if not real_tickers and detected_sectors_from_keywords:
            for sector in detected_sectors_from_keywords:
                found_sectors.add(sector)
                found_etfs.update(self.db.sector_correlations.get(sector, []))

        # Pass 4: Supply chain contagion
        for ticker in list(found_tickers):
            chain = self.db.get_supply_chain_exposure(ticker)
            for role, related in chain.items():
                for t in related:
                    found_supply_chain.add(f"{t} ({role[:-1]})")  # "TSM (supplier)"
                    found_contagion.add(t)

        # Pass 5: Sector & ETF propagation from real target tickers only.
        # Exclude analyst/messenger tickers so their sectors don't pollute ETFs.
        # e.g. Jack Dorsey â†’ SQ â†’ Financials ETFs should NOT appear on an NVDA article.
        target_tickers = found_tickers - analyst_tickers
        for ticker in target_tickers:
            info = self.db.tickers.get(ticker, {})
            if "sector" in info:
                found_sectors.add(info["sector"])
            found_etfs.update(self.db.get_sector_etfs(ticker))

        # Also add sectors from keywords even if we have tickers
        found_sectors.update(detected_sectors_from_keywords)

        # Final pass: Remove analyst/messenger tickers identified in Pass 2b.
        # Always remove the messenger â€” even if it's the only ticker found.
        # The "Missing Main Character" fix downstream will promote the correct
        # ticker from Claude's correlated_moves/ticker_signals.
        # e.g. "Goldman warns of GDP drag" â†’ GS removed, Claude provides USO/XOM/SPY.
        if analyst_tickers:
            found_tickers -= analyst_tickers
            found_supply_chain -= analyst_tickers
            found_contagion -= analyst_tickers

        return {
            "tickers": sorted(found_tickers),
            "sectors": sorted(found_sectors),
            "etfs": sorted(found_etfs),
            "supply_chain": sorted(found_supply_chain),
            "contagion": sorted(found_contagion - found_tickers),  # Exclude direct hits
        }
