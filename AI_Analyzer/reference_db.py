"""
NYSE Reference Database for the NYSE Impact Screener.
"""

from typing import Optional

from market_state import LiveMarketState


class NYSEReferenceDB:
    """
    Comprehensive in-memory ticker resolution database.
    Covers: Semiconductors, Mega-cap Tech, Cloud/SaaS, Cybersecurity, Crypto,
    Energy (upstream/midstream/downstream/refining), Financials, Fintech,
    Healthcare/Pharma/Biotech, Defense/Aerospace, Industrials, Autos/EVs,
    Consumer, Airlines, Utilities, REITs, Materials, Transportation, Telecom,
    and Broad Market ETFs.

    Production version uses SQLite FTS5 for fuzzy matching + Redis hot cache.
    """

    def __init__(self):
        self.tickers: dict[str, dict] = {
            # ── SEMICONDUCTORS ──────────────────────────────────────────────
            "NVDA": {"name": "NVIDIA", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "GPU/AI Chips", "beta_30d": 1.8},
            "AMD":  {"name": "Advanced Micro Devices", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "GPU/CPU", "beta_30d": 1.7},
            "INTC": {"name": "Intel", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "CPU/Foundry", "beta_30d": 1.3},
            "TSM":  {"name": "Taiwan Semiconductor", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Foundry", "beta_30d": 1.4},
            "AVGO": {"name": "Broadcom", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Networking/Custom", "beta_30d": 1.3},
            "QCOM": {"name": "Qualcomm", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Mobile/RF", "beta_30d": 1.4},
            "ASML": {"name": "ASML Holding", "sector": "Semiconductors", "mcap": "mega", "etf": "SMH",
                     "sub_sector": "Lithography Equipment", "beta_30d": 1.5},
            "MU":   {"name": "Micron Technology", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Memory", "beta_30d": 1.6},
            "LRCX": {"name": "Lam Research", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Equipment", "beta_30d": 1.5},
            "AMAT": {"name": "Applied Materials", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Equipment", "beta_30d": 1.4},
            "TXN":  {"name": "Texas Instruments", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Analog", "beta_30d": 1.1},
            "ARM":  {"name": "Arm Holdings", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "IP/Architecture", "beta_30d": 1.9},
            "MRVL": {"name": "Marvell Technology", "sector": "Semiconductors", "mcap": "large", "etf": "SMH",
                     "sub_sector": "Data Infrastructure", "beta_30d": 1.6},

            # ── ENERGY — Upstream (E&P) ────────────────────────────────────
            "XOM":  {"name": "Exxon Mobil", "sector": "Energy", "mcap": "mega", "etf": "XLE",
                     "sub_sector": "Integrated", "beta_30d": 0.9},
            "CVX":  {"name": "Chevron", "sector": "Energy", "mcap": "mega", "etf": "XLE",
                     "sub_sector": "Integrated", "beta_30d": 0.9},
            "COP":  {"name": "ConocoPhillips", "sector": "Energy", "mcap": "large", "etf": "XLE",
                     "sub_sector": "E&P", "beta_30d": 1.1},
            "EOG":  {"name": "EOG Resources", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.2},
            "PXD":  {"name": "Pioneer Natural Resources", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P Permian", "beta_30d": 1.3},
            "OXY":  {"name": "Occidental Petroleum", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.5},
            # ── Energy — Midstream ─────────────────────────────────────────
            "WMB":  {"name": "Williams Companies", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.8},
            "KMI":  {"name": "Kinder Morgan", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.7},
            "ET":   {"name": "Energy Transfer", "sector": "Energy", "mcap": "large", "etf": "AMLP",
                     "sub_sector": "Midstream/Pipelines", "beta_30d": 0.9},
            # ── Energy — Services ──────────────────────────────────────────
            "SLB":  {"name": "Schlumberger", "sector": "Energy", "mcap": "large", "etf": "OIH",
                     "sub_sector": "Oilfield Services", "beta_30d": 1.3},
            "HAL":  {"name": "Halliburton", "sector": "Energy", "mcap": "large", "etf": "OIH",
                     "sub_sector": "Oilfield Services", "beta_30d": 1.4},
            # ── Energy — Renewables ────────────────────────────────────────
            "NEE":  {"name": "NextEra Energy", "sector": "Utilities", "mcap": "mega", "etf": "XLU",
                     "sub_sector": "Renewable Utilities", "beta_30d": 0.7},
            "ENPH": {"name": "Enphase Energy", "sector": "Energy", "mcap": "mid", "etf": "TAN",
                     "sub_sector": "Solar", "beta_30d": 2.0},
            "FSLR": {"name": "First Solar", "sector": "Energy", "mcap": "mid", "etf": "TAN",
                     "sub_sector": "Solar", "beta_30d": 1.8},

            # ── FINANCIALS ─────────────────────────────────────────────────
            "JPM":  {"name": "JPMorgan Chase", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.1},
            "GS":   {"name": "Goldman Sachs", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Investment Banking", "beta_30d": 1.3},
            "BAC":  {"name": "Bank of America", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.2},
            "MS":   {"name": "Morgan Stanley", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Investment Banking", "beta_30d": 1.3},
            "C":    {"name": "Citigroup", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.3},
            "WFC":  {"name": "Wells Fargo", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Money Center Banks", "beta_30d": 1.1},
            "BRK.B": {"name": "Berkshire Hathaway", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                      "sub_sector": "Diversified", "beta_30d": 0.6},
            "V":    {"name": "Visa", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Payments", "beta_30d": 0.9},
            "MA":   {"name": "Mastercard", "sector": "Financials", "mcap": "mega", "etf": "XLF",
                     "sub_sector": "Payments", "beta_30d": 0.9},
            "BLK":  {"name": "BlackRock", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Asset Management", "beta_30d": 1.1},

            # ── HEALTHCARE / PHARMA / BIOTECH ──────────────────────────────
            "JNJ":  {"name": "Johnson & Johnson", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Diversified Pharma", "beta_30d": 0.6},
            "PFE":  {"name": "Pfizer", "sector": "Healthcare", "mcap": "large", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.7},
            "UNH":  {"name": "UnitedHealth Group", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Managed Care", "beta_30d": 0.8},
            "LLY":  {"name": "Eli Lilly", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.9},
            "ABBV": {"name": "AbbVie", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.7},
            "MRK":  {"name": "Merck", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Big Pharma", "beta_30d": 0.6},
            "TMO":  {"name": "Thermo Fisher", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Life Sciences Tools", "beta_30d": 0.9},
            "AMGN": {"name": "Amgen", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.7},
            "GILD": {"name": "Gilead Sciences", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.6},

            # ── DEFENSE / AEROSPACE ────────────────────────────────────────
            "LMT":  {"name": "Lockheed Martin", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Prime", "beta_30d": 0.7},
            "RTX":  {"name": "RTX (Raytheon)", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense/Aero", "beta_30d": 0.8},
            "NOC":  {"name": "Northrop Grumman", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Prime", "beta_30d": 0.6},
            "GD":   {"name": "General Dynamics", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Defense Diversified", "beta_30d": 0.7},
            "BA":   {"name": "Boeing", "sector": "Defense", "mcap": "large", "etf": "ITA",
                     "sub_sector": "Commercial Aero/Defense", "beta_30d": 1.4},

            # ── TECHNOLOGY ─────────────────────────────────────────────────
            "IBM":  {"name": "IBM", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Enterprise IT", "beta_30d": 0.9},
            "CRM":  {"name": "Salesforce", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Cloud/SaaS", "beta_30d": 1.2},
            "ORCL": {"name": "Oracle", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Cloud/Enterprise", "beta_30d": 1.1},
            "NOW":  {"name": "ServiceNow", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Cloud/SaaS", "beta_30d": 1.2},
            "PLTR": {"name": "Palantir", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "AI/Data Analytics", "beta_30d": 2.1},

            # ── INDUSTRIALS ────────────────────────────────────────────────
            "CAT":  {"name": "Caterpillar", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Heavy Equipment", "beta_30d": 1.1},
            "DE":   {"name": "Deere & Company", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Agriculture Equipment", "beta_30d": 1.0},
            "GE":   {"name": "GE Aerospace", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Jet Engines/Power", "beta_30d": 1.1},
            "HON":  {"name": "Honeywell", "sector": "Industrials", "mcap": "large", "etf": "XLI",
                     "sub_sector": "Diversified Industrial", "beta_30d": 0.9},
            "UNP":  {"name": "Union Pacific", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Railroads", "beta_30d": 0.9},
            "UPS":  {"name": "United Parcel Service", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Logistics", "beta_30d": 1.0},
            "FDX":  {"name": "FedEx", "sector": "Transportation", "mcap": "large", "etf": "IYT",
                     "sub_sector": "Logistics", "beta_30d": 1.2},

            # ── CONSUMER STAPLES ───────────────────────────────────────────
            "WMT":  {"name": "Walmart", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Big Box Retail", "beta_30d": 0.5},
            "KO":   {"name": "Coca-Cola", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Beverages", "beta_30d": 0.5},
            "PEP":  {"name": "PepsiCo", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Beverages/Snacks", "beta_30d": 0.5},
            "PG":   {"name": "Procter & Gamble", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Household Products", "beta_30d": 0.4},
            "COST": {"name": "Costco", "sector": "Consumer Staples", "mcap": "mega", "etf": "XLP",
                     "sub_sector": "Warehouse Retail", "beta_30d": 0.7},

            # ── CONSUMER DISCRETIONARY ─────────────────────────────────────
            "NKE":  {"name": "Nike", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Apparel/Footwear", "beta_30d": 1.1},
            "HD":   {"name": "Home Depot", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "Home Improvement", "beta_30d": 1.0},
            "MCD":  {"name": "McDonald's", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "QSR", "beta_30d": 0.6},
            "SBUX": {"name": "Starbucks", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "QSR/Coffee", "beta_30d": 0.9},
            "ULTA": {"name": "Ulta Beauty", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Specialty Beauty Retail", "beta_30d": 1.3},
            "ELF":  {"name": "e.l.f. Beauty", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "Specialty Beauty", "beta_30d": 1.8},
            "COTY": {"name": "Coty", "sector": "Consumer Staples", "mcap": "mid", "etf": "XLP",
                     "sub_sector": "Beauty/Personal Care", "beta_30d": 1.4},
            "EL":   {"name": "Estée Lauder", "sector": "Consumer Staples", "mcap": "large", "etf": "XLP",
                     "sub_sector": "Beauty/Personal Care", "beta_30d": 1.2},
            "TGT":  {"name": "Target", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Big Box Retail", "beta_30d": 1.0},
            "LOW":  {"name": "Lowe's", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Home Improvement", "beta_30d": 1.0},
            "TJX":  {"name": "TJX Companies", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Off-Price Retail", "beta_30d": 0.9},
            "ROST": {"name": "Ross Stores", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Off-Price Retail", "beta_30d": 0.9},
            "DG":   {"name": "Dollar General", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Discount Retail", "beta_30d": 0.8},
            "DLTR": {"name": "Dollar Tree", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "Discount Retail", "beta_30d": 1.0},
            "DIS":  {"name": "Walt Disney", "sector": "Communication", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Media/Entertainment", "beta_30d": 1.1},

            # ── UTILITIES ──────────────────────────────────────────────────
            "DUK":  {"name": "Duke Energy", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.4},
            "SO":   {"name": "Southern Company", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.4},
            "AEP":  {"name": "American Electric Power", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Regulated Electric", "beta_30d": 0.5},
            "VST":  {"name": "Vistra", "sector": "Utilities", "mcap": "large", "etf": "XLU",
                     "sub_sector": "Power Generation/Nuclear", "beta_30d": 1.6},

            # ── REITs ──────────────────────────────────────────────────────
            "AMT":  {"name": "American Tower", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Cell Tower REITs", "beta_30d": 0.8},
            "PLD":  {"name": "Prologis", "sector": "REITs", "mcap": "mega", "etf": "VNQ",
                     "sub_sector": "Industrial/Logistics REITs", "beta_30d": 0.9},
            "EQIX": {"name": "Equinix", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Data Center REITs", "beta_30d": 0.9},
            "SPG":  {"name": "Simon Property Group", "sector": "REITs", "mcap": "large", "etf": "VNQ",
                     "sub_sector": "Retail REITs", "beta_30d": 1.2},

            # ── MATERIALS / MINING ─────────────────────────────────────────
            "FCX":  {"name": "Freeport-McMoRan", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Copper/Gold Mining", "beta_30d": 1.5},
            "NEM":  {"name": "Newmont Mining", "sector": "Materials", "mcap": "large", "etf": "GDX",
                     "sub_sector": "Gold Mining", "beta_30d": 0.5},
            "NUE":  {"name": "Nucor", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Steel", "beta_30d": 1.3},
            "APD":  {"name": "Air Products", "sector": "Materials", "mcap": "large", "etf": "XLB",
                     "sub_sector": "Industrial Gases", "beta_30d": 0.8},
            "LIN":  {"name": "Linde", "sector": "Materials", "mcap": "mega", "etf": "XLB",
                     "sub_sector": "Industrial Gases", "beta_30d": 0.7},

            # ── TELECOM ────────────────────────────────────────────────────
            "T":    {"name": "AT&T", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.7},
            "VZ":   {"name": "Verizon", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.6},
            "TMUS": {"name": "T-Mobile", "sector": "Telecom", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Telecom/Wireless", "beta_30d": 0.7},

            # ── MEGA-CAP TECH (Big 7) ───────────────────────────────────────
            "AAPL": {"name": "Apple", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Consumer Electronics/Software", "beta_30d": 1.2},
            "MSFT": {"name": "Microsoft", "sector": "Technology", "mcap": "mega", "etf": "XLK",
                     "sub_sector": "Cloud/Enterprise Software", "beta_30d": 1.1},
            "GOOGL": {"name": "Alphabet", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Search/Cloud/AI", "beta_30d": 1.2},
            "GOOG":  {"name": "Alphabet (Class C)", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Search/Cloud/AI", "beta_30d": 1.2},
            "META":  {"name": "Meta Platforms", "sector": "Communication", "mcap": "mega", "etf": "XLC",
                      "sub_sector": "Social Media/AI", "beta_30d": 1.4},
            "AMZN": {"name": "Amazon", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "E-Commerce/Cloud", "beta_30d": 1.3},
            "NFLX": {"name": "Netflix", "sector": "Communication", "mcap": "large", "etf": "XLC",
                     "sub_sector": "Streaming", "beta_30d": 1.5},
            "TSLA": {"name": "Tesla", "sector": "Consumer Disc.", "mcap": "mega", "etf": "XLY",
                     "sub_sector": "EV/Autonomous", "beta_30d": 2.0},

            # ── MORE TECHNOLOGY / SOFTWARE ──────────────────────────────────
            "ADBE": {"name": "Adobe", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Creative/AI Software", "beta_30d": 1.3},
            "INTU": {"name": "Intuit", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Financial Software", "beta_30d": 1.2},
            "SNPS": {"name": "Synopsys", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "EDA Software", "beta_30d": 1.3},
            "CDNS": {"name": "Cadence Design", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "EDA Software", "beta_30d": 1.3},
            "WDAY": {"name": "Workday", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/HR Software", "beta_30d": 1.2},
            "TEAM": {"name": "Atlassian", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/Dev Tools", "beta_30d": 1.4},
            "HUBS": {"name": "HubSpot", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "Cloud/CRM", "beta_30d": 1.3},
            "UBER": {"name": "Uber", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "Ride-Sharing/Logistics", "beta_30d": 1.5},
            "SMCI": {"name": "Super Micro Computer", "sector": "Technology", "mcap": "large", "etf": "XLK",
                     "sub_sector": "AI Servers", "beta_30d": 2.5},
            "SHOP": {"name": "Shopify", "sector": "Technology", "mcap": "large", "etf": "IGV",
                     "sub_sector": "E-Commerce Platform", "beta_30d": 1.8},

            # ── CYBERSECURITY ───────────────────────────────────────────────
            "PANW": {"name": "Palo Alto Networks", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity", "beta_30d": 1.4},
            "CRWD": {"name": "CrowdStrike", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/EDR", "beta_30d": 1.6},
            "FTNT": {"name": "Fortinet", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/Firewall", "beta_30d": 1.3},
            "ZS":   {"name": "Zscaler", "sector": "Technology", "mcap": "large", "etf": "CIBR",
                     "sub_sector": "Cloud Security", "beta_30d": 1.6},
            "S":    {"name": "SentinelOne", "sector": "Technology", "mcap": "mid", "etf": "CIBR",
                     "sub_sector": "Cybersecurity/AI", "beta_30d": 1.8},

            # ── CLOUD / DATA ────────────────────────────────────────────────
            "SNOW": {"name": "Snowflake", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Data Platform", "beta_30d": 1.7},
            "DDOG": {"name": "Datadog", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Monitoring", "beta_30d": 1.6},
            "NET":  {"name": "Cloudflare", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Networking/Security", "beta_30d": 1.7},
            "MDB":  {"name": "MongoDB", "sector": "Technology", "mcap": "large", "etf": "WCLD",
                     "sub_sector": "Cloud Database", "beta_30d": 1.8},
            "RBLX": {"name": "Roblox", "sector": "Technology", "mcap": "mid", "etf": "WCLD",
                     "sub_sector": "Gaming/Metaverse", "beta_30d": 1.9},
            "SNAP": {"name": "Snap", "sector": "Communication", "mcap": "mid", "etf": "XLC",
                     "sub_sector": "Social Media", "beta_30d": 2.2},
            "ROKU": {"name": "Roku", "sector": "Communication", "mcap": "mid", "etf": "XLC",
                     "sub_sector": "Streaming Platform", "beta_30d": 2.0},

            # ── CRYPTO-ADJACENT ─────────────────────────────────────────────
            "COIN": {"name": "Coinbase", "sector": "Financials", "mcap": "large", "etf": "BKCH",
                     "sub_sector": "Crypto Exchange", "beta_30d": 3.0},
            "MSTR": {"name": "MicroStrategy", "sector": "Technology", "mcap": "large", "etf": "BKCH",
                     "sub_sector": "Bitcoin Treasury", "beta_30d": 3.5},
            "RIOT": {"name": "Riot Platforms", "sector": "Technology", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Bitcoin Mining", "beta_30d": 3.2},
            "MARA": {"name": "Marathon Digital", "sector": "Technology", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Bitcoin Mining", "beta_30d": 3.3},
            "HOOD": {"name": "Robinhood", "sector": "Financials", "mcap": "mid", "etf": "BKCH",
                     "sub_sector": "Retail Brokerage/Crypto", "beta_30d": 2.5},

            # ── FINTECH ─────────────────────────────────────────────────────
            "PYPL": {"name": "PayPal", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Digital Payments", "beta_30d": 1.4},
            "SQ":   {"name": "Block (Square)", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Fintech/Payments", "beta_30d": 1.8},
            "SOFI": {"name": "SoFi Technologies", "sector": "Financials", "mcap": "mid", "etf": "XLF",
                     "sub_sector": "Digital Banking", "beta_30d": 2.0},
            "SCHW": {"name": "Charles Schwab", "sector": "Financials", "mcap": "large", "etf": "XLF",
                     "sub_sector": "Retail Brokerage", "beta_30d": 1.2},
            "AFRM": {"name": "Affirm", "sector": "Financials", "mcap": "mid", "etf": "XLF",
                     "sub_sector": "BNPL/Fintech", "beta_30d": 2.3},
            "DASH": {"name": "DoorDash", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Food Delivery", "beta_30d": 1.7},
            "LYFT": {"name": "Lyft", "sector": "Technology", "mcap": "mid", "etf": "XLK",
                     "sub_sector": "Ride-Sharing", "beta_30d": 2.0},

            # ── BIOTECH / PHARMA (additional) ───────────────────────────────
            "MRNA": {"name": "Moderna", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "mRNA Biotech", "beta_30d": 1.8},
            "BNTX": {"name": "BioNTech", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "mRNA Biotech", "beta_30d": 1.7},
            "REGN": {"name": "Regeneron", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Biotech", "beta_30d": 0.8},
            "VRTX": {"name": "Vertex Pharmaceuticals", "sector": "Healthcare", "mcap": "large", "etf": "IBB",
                     "sub_sector": "Rare Disease Biotech", "beta_30d": 0.9},
            "NVO":  {"name": "Novo Nordisk", "sector": "Healthcare", "mcap": "mega", "etf": "XLV",
                     "sub_sector": "Diabetes/GLP-1 Pharma", "beta_30d": 0.8},

            # ── EVs / AUTOS ──────────────────────────────────────────────────
            "GM":   {"name": "General Motors", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Autos/EV", "beta_30d": 1.3},
            "F":    {"name": "Ford Motor", "sector": "Consumer Disc.", "mcap": "large", "etf": "XLY",
                     "sub_sector": "Autos/EV", "beta_30d": 1.4},
            "RIVN": {"name": "Rivian", "sector": "Consumer Disc.", "mcap": "mid", "etf": "XLY",
                     "sub_sector": "EV Trucks", "beta_30d": 2.3},
            "LCID": {"name": "Lucid Group", "sector": "Consumer Disc.", "mcap": "small", "etf": "XLY",
                     "sub_sector": "EV Luxury", "beta_30d": 2.5},
            "DVN":  {"name": "Devon Energy", "sector": "Energy", "mcap": "large", "etf": "XOP",
                     "sub_sector": "E&P", "beta_30d": 1.4},
        }

        # ── ALIAS RESOLUTION: Common Names → Tickers ──────────────────────
        self.aliases: dict[str, str] = {
            "nvidia": "NVDA", "nvda": "NVDA", "jensen huang": "NVDA",
            "amd": "AMD", "advanced micro": "AMD", "lisa su": "AMD",
            "intel": "INTC", "pat gelsinger": "INTC",
            "tsmc": "TSM", "taiwan semi": "TSM", "taiwan semiconductor": "TSM",
            "broadcom": "AVGO", "hock tan": "AVGO",
            "qualcomm": "QCOM", "asml": "ASML", "micron": "MU",
            "lam research": "LRCX", "lam": "LRCX",
            "applied materials": "AMAT", "texas instruments": "TXN",
            "arm": "ARM", "arm holdings": "ARM", "softbank arm": "ARM",
            "marvell": "MRVL",
            "exxon": "XOM", "exxon mobil": "XOM", "exxonmobil": "XOM",
            "chevron": "CVX", "conocophillips": "COP", "conoco": "COP",
            "eog": "EOG", "eog resources": "EOG",
            "pioneer": "PXD", "pioneer natural": "PXD",
            "occidental": "OXY", "oxy": "OXY",
            "williams": "WMB", "williams companies": "WMB",
            "kinder morgan": "KMI", "energy transfer": "ET",
            "schlumberger": "SLB", "halliburton": "HAL",
            "nextera": "NEE", "nextera energy": "NEE",
            "enphase": "ENPH", "first solar": "FSLR",
            "jpmorgan": "JPM", "jp morgan": "JPM", "chase": "JPM", "jamie dimon": "JPM",
            "goldman": "GS", "goldman sachs": "GS", "david solomon": "GS",
            "bank of america": "BAC", "bofa": "BAC",
            "morgan stanley": "MS", "citigroup": "C", "citi": "C",
            "wells fargo": "WFC",
            "berkshire": "BRK.B", "berkshire hathaway": "BRK.B", "warren buffett": "BRK.B", "buffett": "BRK.B",
            "visa": "V", "mastercard": "MA",
            "blackrock": "BLK", "larry fink": "BLK",
            "columbia banking": "COLB", "columbia banking system": "COLB",
            "zions": "ZION", "zions bancorporation": "ZION", "zions bancorp": "ZION",
            "regions financial": "RF", "regions bank": "RF",
            "keycorp": "KEY", "key bank": "KEY", "keybank": "KEY",
            "comerica": "CMA", "first republic": "FRC",
            "western alliance": "WAL", "east west bancorp": "EWBC",
            "johnson & johnson": "JNJ", "j&j": "JNJ",
            "pfizer": "PFE", "unitedhealth": "UNH", "united health": "UNH",
            "eli lilly": "LLY", "lilly": "LLY",
            "abbvie": "ABBV", "merck": "MRK", "thermo fisher": "TMO",
            "amgen": "AMGN", "gilead": "GILD",
            "lockheed": "LMT", "lockheed martin": "LMT",
            "raytheon": "RTX", "rtx": "RTX",
            "northrop": "NOC", "northrop grumman": "NOC",
            "general dynamics": "GD", "boeing": "BA",
            "ibm": "IBM", "salesforce": "CRM", "oracle": "ORCL",
            "servicenow": "NOW", "palantir": "PLTR",
            "freightcar america": "RAIL", "freightcar": "RAIL",
            "trinity industries": "TRN", "trinity": "TRN",
            "greenbrier": "GBX", "greenbrier companies": "GBX",
            "caterpillar": "CAT", "deere": "DE", "john deere": "DE",
            "ge": "GE", "ge aerospace": "GE", "honeywell": "HON",
            "union pacific": "UNP", "ups": "UPS", "fedex": "FDX",
            "walmart": "WMT", "wal-mart": "WMT",
            "coca-cola": "KO", "coca cola": "KO", "coke": "KO",
            "pepsi": "PEP", "pepsico": "PEP",
            "procter": "PG", "procter & gamble": "PG", "p&g": "PG",
            "costco": "COST", "nike": "NKE", "home depot": "HD",
            "lowe's": "LOW", "lowes": "LOW",
            "mcdonald's": "MCD", "mcdonalds": "MCD",
            "starbucks": "SBUX", "disney": "DIS", "walt disney": "DIS",
            "target": "TGT",
            "tjx": "TJX", "tj maxx": "TJX", "t.j. maxx": "TJX", "marshalls": "TJX",
            "ross stores": "ROST", "ross": "ROST",
            "dollar general": "DG", "dollar tree": "DLTR",
            "ulta": "ULTA", "ulta beauty": "ULTA",
            "elf beauty": "ELF", "e.l.f.": "ELF", "e.l.f. beauty": "ELF",
            "coty": "COTY",
            "estee lauder": "EL", "estée lauder": "EL", "lauder": "EL",
            "duke energy": "DUK", "southern company": "SO", "vistra": "VST",
            "american tower": "AMT", "prologis": "PLD",
            "equinix": "EQIX", "simon property": "SPG",
            "freeport": "FCX", "freeport-mcmoran": "FCX", "freeport mcmoran": "FCX",
            "newmont": "NEM", "nucor": "NUE",
            "air products": "APD", "linde": "LIN",
            "at&t": "T", "att": "T", "verizon": "VZ", "t-mobile": "TMUS",
            "apple": "AAPL", "iphone": "AAPL", "tim cook": "AAPL",
            "microsoft": "MSFT", "satya nadella": "MSFT", "azure": "MSFT",
            "alphabet": "GOOGL", "google": "GOOGL", "sundar pichai": "GOOGL", "gemini": "GOOGL",
            "meta": "META", "facebook": "META", "mark zuckerberg": "META", "instagram": "META", "whatsapp": "META",
            "amazon": "AMZN", "aws": "AMZN", "andy jassy": "AMZN",
            "netflix": "NFLX",
            "tesla": "TSLA", "elon musk": "TSLA", "elon": "TSLA",
            "adobe": "ADBE", "intuit": "INTU", "turbotax": "INTU",
            "synopsys": "SNPS", "cadence": "CDNS",
            "workday": "WDAY", "atlassian": "TEAM", "jira": "TEAM",
            "hubspot": "HUBS", "uber": "UBER",
            "super micro": "SMCI", "supermicro": "SMCI",
            "shopify": "SHOP",
            "palo alto": "PANW", "palo alto networks": "PANW",
            "crowdstrike": "CRWD", "fortinet": "FTNT",
            "zscaler": "ZS", "sentinelone": "S",
            "snowflake": "SNOW", "datadog": "DDOG",
            "cloudflare": "NET", "mongodb": "MDB",
            "roblox": "RBLX", "snap": "SNAP", "snapchat": "SNAP",
            "roku": "ROKU",
            "coinbase": "COIN", "microstrategy": "MSTR",
            "riot": "RIOT", "riot platforms": "RIOT",
            "marathon digital": "MARA", "robinhood": "HOOD",
            "paypal": "PYPL",
            "block": "SQ", "square": "SQ", "cash app": "SQ", "jack dorsey": "SQ",
            "sofi": "SOFI", "schwab": "SCHW", "charles schwab": "SCHW",
            "affirm": "AFRM", "doordash": "DASH", "lyft": "LYFT",
            "moderna": "MRNA", "biontech": "BNTX",
            "regeneron": "REGN", "vertex": "VRTX",
            "novo nordisk": "NVO", "ozempic": "NVO", "wegovy": "NVO",
            "structure therapeutics": "GPCR", "structure therap": "GPCR",
            "viking therapeutics": "VKTX", "revolution medicines": "RVMD",
            "luminar": "LAZR", "luminar technologies": "LAZR",
            "velodyne": "VLDR",
            "innoviz": "INVZ", "innoviz technologies": "INVZ",
            "aeva": "AEVA", "aeva technologies": "AEVA",
            "microvision": "MVIS", "ouster": "OUST",
            "cepton": "CPTN", "mobileye": "MBLY",
            "aurora innovation": "AUR", "aurora": "AUR",
            "waymo": "GOOGL",
            "globalfoundries": "GFS", "global foundries": "GFS",
            "wolfspeed": "WOLF",
            "on semiconductor": "ON", "onsemi": "ON",
            "nxp": "NXPI", "nxp semiconductors": "NXPI",
            "stmicroelectronics": "STM", "stmicro": "STM",
            "microchip technology": "MCHP", "microchip": "MCHP",
            "lattice semiconductor": "LSCC", "lattice": "LSCC",
            "monolithic power": "MPWR", "silicon labs": "SLAB",
            "rambus": "RMBS",
            "amkor": "AMKR", "amkor technology": "AMKR",
            "umc": "UMC", "united micro": "UMC",
            "skyworks": "SWKS", "skyworks solutions": "SWKS",
            "indie semiconductor": "INDI", "coherent": "COHR",
            "cyberark": "CYBR", "qualys": "QLYS",
            "varonis": "VRNS", "rapid7": "RPD",
            "toast": "TOST", "upstart": "UPST",
            "lightspeed": "LSPD",
            "bill.com": "BILL", "bill holdings": "BILL",
            "marqeta": "MQ",
            "chargepoint": "CHPT", "sunrun": "RUN",
            "array technologies": "ARRY", "shoals": "SHLS", "maxeon": "MAXN",
            "general motors": "GM",
            "ford": "F", "ford motor": "F",
            "rivian": "RIVN", "lucid": "LCID",
            "devon": "DVN", "devon energy": "DVN",
        }

        # ── SECTOR → ETF CONTAGION MAP ─────────────────────────────────────
        self.sector_correlations: dict[str, list[str]] = {
            "Crypto":            ["IBIT", "BITO", "WGMI", "BITQ"],
            "Semiconductors":    ["SMH", "SOXX", "XSD", "PSI"],
            "Energy":            ["XLE", "XOP", "OIH", "AMLP", "TAN"],
            "Financials":        ["XLF", "KRE", "KBE", "IAI"],
            "Healthcare":        ["XLV", "IBB", "XBI", "IHI"],
            "Defense":           ["ITA", "PPA", "XAR"],
            "Technology":        ["XLK", "IGV", "WCLD"],
            "Industrials":       ["XLI", "IYT"],
            "Transportation":    ["IYT", "XLI"],
            "Consumer Staples":  ["XLP", "KXI"],
            "Consumer Disc.":    ["XLY", "FDIS"],
            "Communication":     ["XLC", "VOX"],
            "Utilities":         ["XLU", "IDU"],
            "REITs":             ["VNQ", "IYR", "XLRE"],
            "Materials":         ["XLB", "GDX", "SLV"],
            "Telecom":           ["XLC", "VOX"],
        }

        # ── SUPPLY CHAIN & DEPENDENCY GRAPH ─────────────────────────────────
        self.supply_chain: dict[str, dict[str, list[str]]] = {
            "NVDA": {
                "suppliers": ["TSM", "ASML", "LRCX", "AMAT", "MU"],
                "customers": ["ORCL", "EQIX", "VST"],
                "peers": ["AMD", "INTC", "AVGO", "ARM"],
            },
            "AMD": {
                "suppliers": ["TSM", "ASML"],
                "customers": ["ORCL"],
                "peers": ["NVDA", "INTC"],
            },
            "TSM": {
                "suppliers": ["ASML", "LRCX", "AMAT"],
                "customers": ["NVDA", "AMD", "QCOM", "AVGO", "ARM"],
                "peers": ["INTC"],
            },
            "ASML": {
                "suppliers": [],
                "customers": ["TSM", "INTC"],
                "peers": ["LRCX", "AMAT"],
            },
            "XOM": {
                "suppliers": ["SLB", "HAL"],
                "customers": [],
                "peers": ["CVX", "COP", "OXY"],
            },
            "BA": {
                "suppliers": ["GE", "RTX", "HON"],
                "customers": [],
                "peers": ["LMT", "RTX"],
            },
            "LMT": {
                "suppliers": ["RTX", "NOC", "GD"],
                "customers": [],
                "peers": ["RTX", "NOC", "GD", "BA"],
            },
            "JPM": {
                "suppliers": [],
                "customers": [],
                "peers": ["GS", "BAC", "MS", "C", "WFC"],
            },
            "WMT": {
                "suppliers": ["PG", "KO", "PEP"],
                "customers": [],
                "peers": ["COST", "HD"],
            },
            "UNH": {
                "suppliers": [],
                "customers": [],
                "peers": ["LLY", "JNJ", "PFE"],
            },
            "EQIX": {
                "suppliers": [],
                "customers": ["NVDA", "CRM", "ORCL"],
                "peers": ["AMT", "PLD"],
            },
            "FCX": {
                "suppliers": [],
                "customers": [],
                "peers": ["NEM", "NUE"],
            },
            "ULTA": {
                "suppliers": ["EL", "COTY", "ELF"],
                "customers": [],
                "peers": ["ELF", "COTY", "EL", "TGT"],
            },
            "ELF": {
                "suppliers": [],
                "customers": ["ULTA", "TGT", "WMT"],
                "peers": ["COTY", "EL"],
            },
            "TGT": {
                "suppliers": ["PG", "KO"],
                "customers": [],
                "peers": ["WMT", "COST", "DG"],
            },
        }

        # ── MARKET STATE (live via yfinance — VIX, SPY, pre-market, earnings) ──
        self.live_market = LiveMarketState()
        self.market_state = self.live_market.state  # shared reference — updates in-place

    def resolve_ticker(self, text: str) -> Optional[str]:
        """Resolve a company name or alias to its NYSE ticker."""
        text_lower = text.lower().strip()
        text_upper = text.upper().strip()
        if text_upper in self.tickers:
            return text_upper
        if text_lower in self.aliases:
            return self.aliases[text_lower]
        return None

    def get_sector_etfs(self, ticker: str) -> list[str]:
        info = self.tickers.get(ticker, {})
        sector = info.get("sector", "")
        return self.sector_correlations.get(sector, [])

    def get_market_cap_bucket(self, ticker: str) -> str:
        return self.tickers.get(ticker, {}).get("mcap", "unknown")

    def get_beta(self, ticker: str) -> float:
        return self.tickers.get(ticker, {}).get("beta_30d", 1.0)

    def get_supply_chain_exposure(self, ticker: str) -> dict[str, list[str]]:
        return self.supply_chain.get(ticker, {"suppliers": [], "customers": [], "peers": []})

    def get_sector_peers(self, ticker: str) -> list[str]:
        """Get all tickers in the same sub-sector."""
        info = self.tickers.get(ticker, {})
        sub = info.get("sub_sector", "")
        if not sub:
            return []
        return [t for t, d in self.tickers.items() if d.get("sub_sector") == sub and t != ticker]

    def get_vix_regime_multiplier(self) -> float:
        """Higher VIX = news has amplified impact."""
        vix = self.market_state["vix"]
        if vix < 15:
            return 0.9
        elif vix < 20:
            return 1.0
        elif vix < 30:
            return 1.15
        elif vix < 40:
            return 1.30
        return 1.50  # Crisis

    def get_time_of_day_multiplier(self) -> float:
        """Pre-market and first 30 min of trading see amplified reactions."""
        if self.market_state.get("is_pre_market"):
            return 1.15
        return 1.0
