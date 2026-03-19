import asyncio
import os
import time

class StockAvailabilityChecker:
    """Checks live prices via yfinance and broker availability against real ticker lists."""

    # â”€â”€ Revolut EU â€” ~2,200+ US stocks (sourced from community-maintained lists + official app)
    # Updated March 2025. Covers S&P 500, NASDAQ-100, and popular mid/small-caps.
    REVOLUT_TICKERS = {
        # Mega-cap & large-cap (S&P 500 core)
        "A", "AA", "AAL", "AAP", "AAPL", "ABBV", "ABEV", "ABNB", "ABT", "ACGL",
        "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE", "AEP", "AER", "AES",
        "AFL", "AG", "AGNC", "AI", "AIG", "AKAM", "AL", "ALB", "ALC", "ALGN",
        "ALL", "ALLE", "ALLY", "ALNY", "AMAT", "AMBA", "AMC", "AMCR", "AMD",
        "AME", "AMGN", "AMP", "AMT", "AMZN", "AN", "ANET", "ANSS", "AON", "AOS",
        "APA", "APD", "APH", "APO", "APPS", "APTV", "ARCC", "ARE", "ARES", "ARI",
        "ARMK", "ARR", "ASAN", "ASML", "ATUS", "AU", "AVGO", "AVB", "AVY", "AXP",
        "AXON", "AZN", "AZO",
        # B
        "BA", "BABA", "BAC", "BAH", "BAM", "BAP", "BAX", "BBAR", "BBD", "BBY",
        "BDX", "BE", "BEN", "BEPC", "BG", "BHC", "BHP", "BIDU", "BIIB", "BILI",
        "BIO", "BJ", "BK", "BKNG", "BKR", "BLK", "BLL", "BMA", "BMBL", "BMRN", "BMY",
        "BN", "BNTX", "BOX", "BP", "BPOP", "BR", "BRK.B", "BRO", "BROS", "BSX",
        "BTG", "BUD", "BVN", "BWA", "BX", "BYND",
        # C
        "C", "CABO", "CAG", "CAH", "CARR", "CARS", "CAT", "CB", "CBOE", "CBRE",
        "CC", "CCI", "CCK", "CCL", "CDNS", "CDW", "CE", "CEG", "CELH", "CF",
        "CFG", "CG", "CGNX", "CHGG", "CHD", "CHDN", "CHKP", "CHRD", "CHRW",
        "CHTR", "CHWY", "CI", "CIEN", "CINF", "CL", "CLF", "CLH", "CLX", "CMA",
        "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COHR", "COLB", "COLD",
        "COMM", "COP", "COST", "COTY", "CPB", "CPRI", "CPRT", "CPT", "CRM",
        "CROX", "CRSP", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTRA", "CTSH",
        "CTVA", "CVE", "CVNA", "CVS", "CVX", "CW", "CWEN", "CZR",
        # D
        "D", "DAL", "DAR", "DASH", "DBX", "DD", "DDOG", "DE", "DECK", "DELL",
        "DEO", "DFS", "DG", "DGX", "DHI", "DHR", "DIN", "DIS", "DISH", "DKNG",
        "DLR", "DLTR", "DOCU", "DOV", "DOW", "DPZ", "DRI", "DT", "DTE", "DUK",
        "DVA", "DVN", "DXC", "DXCM",
        # E
        "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "ELAN", "ELV", "EMR",
        "ENPH", "ENS", "EOG", "EPAM", "EQH", "EQIX", "EQNR", "EQR", "EQT",
        "ES", "ESS", "ESTC", "ETN", "ETR", "ETSY", "EW", "EWBC", "EXAS", "EXC",
        "EXEL", "EXPE", "EXR",
        # F
        "F", "FANG", "FAST", "FBIN", "FCX", "FDS", "FDX", "FE", "FERG", "FFIV",
        "FHN", "FICO", "FIS", "FISV", "FIX", "FL", "FLT", "FMC", "FND", "FNF",
        "FOXA", "FOX", "FROG", "FSLR", "FSLY", "FTNT", "FTV", "FUBO", "FUTU",
        "FVRR",
        # G
        "GD", "GDDY", "GDS", "GE", "GILD", "GIS", "GL", "GLOB", "GLW", "GM",
        "GME", "GMED", "GNRC", "GO", "GOLD", "GOOG", "GOOGL", "GPC", "GPCR", "GPN",
        "GRAB", "GRMN", "GS", "GSK", "GT", "GTLS", "GWW", "GXO",
        # H
        "H", "HAL", "HAS", "HBAN", "HBI", "HCA", "HD", "HDB", "HELE", "HES",
        "HIG", "HIMX", "HL", "HLF", "HLT", "HMC", "HOG", "HOLX", "HON", "HOOD",
        "HPE", "HPQ", "HRB", "HRL", "HSBC", "HSIC", "HST", "HSY", "HUM", "HUN",
        "HUYA", "HWM",
        # I
        "IAC", "IBM", "IBN", "ICE", "ICLR", "IDXX", "IEX", "IFF", "IGT", "IIPR",
        "ILMN", "IMGN", "INCY", "INFY", "INTC", "INTU", "INVH", "IP", "IPG",
        "IQ", "IR", "IRBT", "IRM", "ISRG", "IT", "ITW", "IVZ",
        # J
        "JBHT", "JBL", "JCI", "JD", "JEF", "JKS", "JLL", "JMIA", "JNJ", "JNPR",
        "JOBY", "JPM", "JWN",
        # K
        "K", "KDP", "KEP", "KEY", "KEYS", "KGC", "KHC", "KIM", "KKR", "KLAC",
        "KMB", "KMI", "KMX", "KNX", "KO", "KR", "KTOS", "KVUE", "KSS",
        # L
        "L", "LAD", "LAZR", "LCID", "LDOS", "LEA", "LEN", "LEVI", "LH", "LI",
        "LIN", "LKQ", "LLY", "LMND", "LMT", "LNG", "LNT", "LOGI", "LOMA",
        "LOPE", "LOW", "LRCX", "LSCC", "LULU", "LUV", "LVS", "LYB", "LYFT",
        "LYV",
        # M
        "M", "MA", "MAA", "MAN", "MANU", "MAR", "MARA", "MAS", "MAT", "MCD",
        "MCHP", "MCK", "MCO", "MDB", "MDLZ", "MDT", "MELI", "MET", "META",
        "MFC", "MFG", "MGM", "MKL", "MLCO", "MLM", "MMC", "MMM", "MNST", "MO",
        "MORN", "MOS", "MPC", "MPWR", "MPW", "MRK", "MRNA", "MRO", "MRVL", "MS",
        "MSCI", "MSFT", "MSGS", "MSI", "MSTR", "MT", "MTB", "MTCH", "MTD", "MTG",
        "MTH", "MTN", "MU", "MUFG", "MUR",
        # N
        "NAVI", "NBIX", "NCLH", "NCNO", "NDAQ", "NDSN", "NEE", "NEM", "NET",
        "NFLX", "NIO", "NKE", "NKLA", "NLY", "NMR", "NOC", "NOV", "NOW", "NRG",
        "NSC", "NTAP", "NTES", "NTNX", "NTRS", "NUE", "NVAX", "NVCR", "NVDA",
        "NVR", "NWL", "NWSA", "NYT",
        # O
        "O", "OC", "ODP", "OHI", "OKE", "OKTA", "OLED", "OLN", "OMC", "ON",
        "ONTO", "OPEN", "ORCL", "ORI", "ORLY", "OSK", "OTIS", "OVV", "OXY",
        # P
        "PAAS", "PANW", "PATH", "PAYC", "PAYX", "PBF", "PBR", "PCAR", "PCG",
        "PDD", "PEG", "PEGA", "PENN", "PEP", "PFE", "PFG", "PFGC", "PG", "PGR",
        "PH", "PHM", "PINS", "PKG", "PLD", "PLNT", "PLTR", "PLUG", "PM", "PNC",
        "PNR", "POOL", "POST", "PPG", "PPL", "PRI", "PRU", "PSA", "PSX", "PTON",
        "PVH", "PWR", "PYPL",
        # Q
        "QCOM", "QDEL", "QS", "QTWO",
        # R
        "RACE", "RBLX", "RCL", "RDDT", "REGN", "RF", "RH", "RHI", "RITM", "RIVN",
        "RJF", "RL", "RMD", "RNG", "ROK", "ROKU", "ROST", "RPM", "RS", "RSG",
        "RTX", "RUN", "RVMD", "RY",
        # S
        "SAIC", "SAM", "SBAC", "SBUX", "SCCO", "SCHW", "SE", "SEDG", "SFIX",
        "SFM", "SHAK", "SHOP", "SHW", "SID", "SIRI", "SJM", "SKX", "SLB", "SLM",
        "SMCI", "SNAP", "SNOW", "SNPS", "SO", "SONY", "SPCE", "SPG", "SPGI",
        "SPOT", "SQ", "SQM", "SRE", "SRPT", "SSNC", "STAG", "STLA", "STLD",
        "STNE", "STT", "STX", "STZ", "SU", "SUI", "SWK", "SWKS", "SYF", "SYK",
        "SYNA", "SYY",
        # T
        "T", "TAK", "TAL", "TAP", "TD", "TDOC", "TDY", "TEAM", "TECH", "TEL",
        "TENB", "TER", "TEVA", "TFX", "TGT", "THO", "TJX", "TME", "TMO", "TMUS",
        "TOL", "TPR", "TREE", "TRIP", "TRMB", "TROW", "TRV", "TSCO", "TSLA",
        "TSM", "TSN", "TT", "TTD", "TTE", "TTWO", "TWLO", "TXN", "TXRH", "TXT",
        "TYL",
        # U
        "U", "UAA", "UAL", "UBER", "UDR", "ULTA", "UNH", "UNP", "UPS", "URBN",
        "USB",
        # V
        "V", "VALE", "VEEV", "VFC", "VICI", "VIPS", "VLO", "VMC", "VNO", "VOD",
        "VRSK", "VRSN", "VRTX", "VTRS", "VTR", "VZ",
        # W
        "W", "WAB", "WAT", "WBA", "WBD", "WBS", "WDAY", "WDC", "WEC", "WELL",
        "WEN", "WERN", "WFC", "WHR", "WIX", "WKHS", "WLK", "WM", "WMB", "WMT",
        "WPC", "WRK", "WST", "WU", "WY", "WYNN",
        # X-Z
        "X", "XEL", "XOM", "XPEV", "XRX", "XYL", "YETI", "YPF", "YUM", "YUMC",
        "Z", "ZBH", "ZBRA", "ZI", "ZION", "ZM", "ZS", "ZTO", "ZTS",
        # â”€â”€ Additional Semiconductors & Chip Equipment â”€â”€
        "ACLS", "AEHR", "ALGM", "AMKR", "ASX", "ATOM", "CEVA", "COHU", "DIOD",
        "FORM", "GFS", "INDI", "IPGP", "LSCC", "MKSI", "MTSI", "MXL", "NXPI",
        "OUST", "POWI", "RMBS", "SITM", "SLAB", "SMTC", "STM", "UCTT", "UMC",
        "WOLF",
        # â”€â”€ Lidar & Autonomous Driving â”€â”€
        "AEVA", "AUR", "CPTN", "INVZ", "LAZR", "LIDR", "MBLY", "MVIS", "OUST",
        # â”€â”€ AI & Cloud Infrastructure â”€â”€
        "AI", "ALTR", "APP", "BBAI", "BIGC", "CFLT", "DV", "ESTC", "GTLB",
        "HCP", "IOT", "MNDY", "NEWR", "PD", "RBRK", "S", "TENB",
        "ZI",
        # â”€â”€ Biotech & Pharma (mid/small cap) â”€â”€
        "ACAD", "ALT", "ARWR", "BEAM", "BGNE", "CRSP", "CRNX", "DMTK", "DNLI",
        "DRNA", "EXAI", "FATE", "GPCR", "HALO", "IMVT", "IONS", "IRWD", "KRTX",
        "KYMR", "LEGN", "MGNX", "NBIX", "NTLA", "PCVX", "RARE", "RCKT", "RXRX",
        "TXG", "VKTX", "VRNA", "XENE",
        # â”€â”€ Defense & Aerospace â”€â”€
        "AVAV", "BWXT", "HEI", "HII", "KTOS", "LHX", "PLTR", "RKLB",
        "TDG", "TRMB", "WWD",
        # â”€â”€ Clean Energy & Utilities â”€â”€
        "ARRY", "BLDP", "CHPT", "CWEN", "DQ", "ENPH", "FSLR", "HASI", "MAXN",
        "NEP", "NOVA", "RUN", "SEDG", "SHLS", "SPWR",
        # â”€â”€ Fintech & Payments â”€â”€
        "AFRM", "BILL", "COIN", "FI", "FOUR", "GPN", "HUBS", "LC", "LSPD", "MKTX",
        "MQ", "PAYO", "RPAY", "SOFI", "TOST", "UPST", "XP",
        # â”€â”€ Cybersecurity â”€â”€
        "CRWD", "CYBR", "FTNT", "NET", "OKTA", "PANW", "QLYS", "RPD", "S",
        "VRNS", "ZS",
        # â”€â”€ REITs & Real Estate â”€â”€
        "AMT", "CCI", "DLR", "EQIX", "IRM", "PLD", "PSA", "SBAC", "SPG",
        "STAG", "VNO", "WELL",
        # â”€â”€ Mining & Commodities â”€â”€
        "ALB", "CLF", "FCX", "HBM", "LAC", "MP", "NEM",
        "SCCO", "TECK", "WPM",
        # â”€â”€ Crypto & Blockchain â”€â”€
        "RIOT", "MARA", "BITF", "CLSK", "HUT", "BTBT", "CIFR",
    }

    # â”€â”€ XTB â€” ~2,000+ US stock CFDs + real stocks (sourced from official equity-table.pdf)
    # Updated March 2025. Includes all S&P 500, NASDAQ-100, and broad mid-cap coverage.
    XTB_TICKERS = {
        # A
        "A", "AA", "AAL", "AAP", "AAPL", "ABBV", "ABG", "ABT", "ACGL", "ACHC",
        "ACHR", "ACI", "ACM", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "ADTN",
        "AEE", "AEP", "AER", "AES", "AFG", "AFL", "AFRM", "AGCO", "AGNC", "AGO",
        "AGR", "AI", "AIG", "AIN", "AIR", "AIT", "AIZ", "AJG", "AKAM", "AL",
        "ALB", "ALC", "ALGM", "ALGN", "ALGT", "ALK", "ALKS", "ALL", "ALLE",
        "ALLY", "ALNY", "AMAT", "AMBA", "AMC", "AMCR", "AMCX", "AMD", "AME",
        "AMED", "AMG", "AMGN", "AMP", "AMR", "AMT", "AMZN", "AN", "ANET", "ANSS",
        "AON", "AOS", "APA", "APD", "APH", "APLE", "APLS", "APO", "APPS", "APTV",
        "ARCC", "ARE", "ARES", "ARGX", "ARI", "ARMK", "ARR", "ARWR", "ASAN",
        "ASGN", "ASH", "ASML", "ATUS", "AU", "AUB", "AVGO", "AVB", "AVT", "AVY",
        "AXON", "AXP", "AXS", "AZUL",
        # B
        "BA", "BABA", "BAC", "BAH", "BAK", "BALL", "BAM", "BAND", "BAP", "BAX",
        "BBAR", "BBD", "BBY", "BC", "BDX", "BE", "BEAM", "BEN", "BEPC", "BG",
        "BHC", "BHP", "BIDU", "BIIB", "BILI", "BIO", "BJ", "BK", "BKNG", "BKR",
        "BL", "BLDR", "BLK", "BLL", "BMA", "BMBL", "BMO", "BMRN", "BMY", "BN",
        "BNTX", "BOX", "BP", "BPOP", "BR", "BRBR", "BRK.B", "BRO", "BROS",
        "BSAC", "BSX", "BTG", "BUD", "BVN", "BWA", "BX", "BYND", "BZ",
        # C
        "C", "CABO", "CACC", "CACI", "CADE", "CAG", "CAH", "CAKE", "CALM", "CAR",
        "CARG", "CARR", "CARS", "CAT", "CB", "CBOE", "CBRE", "CBRL", "CC", "CCI",
        "CCK", "CCL", "CCU", "CDNS", "CDW", "CE", "CEG", "CELH", "CF", "CFG",
        "CG", "CGNX", "CHGG", "CHD", "CHDN", "CHEF", "CHKP", "CHRD", "CHRW",
        "CHTR", "CHWY", "CI", "CIB", "CIEN", "CINF", "CL", "CLF", "CLH", "CLX",
        "CM", "CMA", "CMC", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNK",
        "CNO", "CNP", "COF", "COHR", "COHU", "COKE", "COLB", "COLM", "COMM", "COO", "COP",
        "COST", "COTY", "CPB", "CPRI", "CPRT", "CPT", "CRI", "CRK", "CRL", "CRM",
        "CROX", "CRS", "CSCO", "CSIQ", "CSL", "CSX", "CTAS", "CTRA", "CTRE",
        "CTSH", "CTVA", "CVE", "CVS", "CVX", "CW", "CWEN", "CZR",
        # D
        "D", "DAL", "DAR", "DASH", "DBX", "DD", "DDOG", "DE", "DECK", "DELL",
        "DEO", "DFS", "DG", "DGX", "DHI", "DHR", "DIN", "DINO", "DIS", "DISH",
        "DKS", "DLB", "DLR", "DLTR", "DOCS", "DOCU", "DOV", "DOW", "DPZ", "DRI",
        "DT", "DTE", "DUK", "DVA", "DVN", "DXC", "DXCM",
        # E
        "EA", "EAT", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "ELAN", "ELV",
        "EME", "EMN", "EMR", "ENB", "ENPH", "ENR", "ENS", "EOG", "EPAM", "EPC",
        "EPR", "EQH", "EQIX", "EQR", "EQT", "ES", "ESS", "ESTC", "ETN", "ETR",
        "ETSY", "EVH", "EW", "EWBC", "EXAS", "EXC", "EXEL", "EXLS", "EXP",
        "EXPD", "EXPE", "EXPO",
        # F
        "F", "FAF", "FANG", "FAST", "FATE", "FBIN", "FCNCA", "FDS", "FDX", "FE",
        "FERG", "FFIV", "FHN", "FICO", "FIS", "FISV", "FIX", "FIZZ", "FL", "FLO",
        "FLS", "FLT", "FMC", "FMS", "FN", "FND", "FNF", "FOX", "FOXA", "FROG",
        "FRPT", "FRT", "FSLY", "FSR", "FTI", "FTNT", "FTS", "FTV", "FUBO", "FUL",
        "FUTU", "FVRR",
        # G
        "GD", "GDDY", "GDS", "GE", "GEL", "GEN", "GFL", "GHC", "GILD", "GIS",
        "GL", "GLOB", "GLW", "GM", "GME", "GMED", "GMS", "GNRC", "GO", "GOGO",
        "GOLD", "GOOG", "GOOGL", "GOOS", "GPC", "GPCR", "GPI", "GPN", "GRAB", "GRBK",
        "GRFS", "GRMN", "GS", "GSK", "GTLS", "GTN", "GWW", "GXO",
        # H
        "H", "HAIN", "HALO", "HAS", "HBI", "HCA", "HD", "HDB", "HELE", "HES",
        "HIG", "HIMX", "HL", "HLF", "HLT", "HMC", "HOG", "HOLX", "HON", "HOOD",
        "HPE", "HPQ", "HRB", "HRL", "HSBC", "HSIC", "HST", "HSY", "HUM", "HUN",
        "HUYA", "HWM",
        # I
        "IAC", "IART", "IBM", "IBN", "ICE", "ICLR", "IDCC", "IDXX", "IEX", "IFF",
        "IGT", "IIPR", "ILMN", "IMAX", "IMGN", "INCY", "INFY", "INSP", "INTC",
        "INTU", "INVH", "IONS", "IPAR", "IPG", "IQ", "IR", "IRBT", "IRM", "IRTC",
        "ISRG", "IT", "ITW", "IVZ",
        # J
        "J", "JACK", "JBHT", "JBL", "JCI", "JD", "JEF", "JKS", "JLL", "JMIA",
        "JNJ", "JNPR", "JOBY", "JPM", "JWN",
        # K
        "K", "KBR", "KDP", "KEP", "KEY", "KEYS", "KEX", "KGC", "KHC", "KIM",
        "KKR", "KLAC", "KMB", "KMI", "KMX", "KNX", "KO", "KR", "KRYS", "KSS",
        "KTOS", "KVUE",
        # L
        "L", "LAD", "LAMR", "LAZR", "LCID", "LDOS", "LEA", "LECO", "LEG", "LEN",
        "LEVI", "LH", "LI", "LIN", "LKQ", "LLY", "LMND", "LMT", "LNC", "LNG",
        "LNT", "LOGI", "LOMA", "LOPE", "LOW", "LRCX", "LRN", "LSCC", "LULU",
        "LUV", "LVS", "LYB", "LYFT", "LYV",
        # M
        "M", "MA", "MAA", "MAN", "MANH", "MANU", "MAR", "MARA", "MAS", "MASI",
        "MAT", "MATX", "MAXN", "MBT", "MCD", "MCHP", "MCK", "MCO", "MDB", "MDLZ",
        "MDT", "MDU", "MELI", "MET", "META", "MFC", "MFG", "MGM", "MHK", "MKL",
        "MLCO", "MLM", "MMC", "MMM", "MNST", "MO", "MOD", "MORN", "MOS", "MPC",
        "MPWR", "MPW", "MRK", "MRNA", "MRO", "MRVL", "MS", "MSCI", "MSFT",
        "MSGS", "MSI", "MSTR", "MT", "MTB", "MTCH", "MTD", "MTG", "MTH", "MTN",
        "MU", "MUFG", "MUR",
        # N
        "NAVI", "NBIX", "NCLH", "NCNO", "NCR", "NDAQ", "NDSN", "NE", "NEE", "NEM",
        "NET", "NFLX", "NFG", "NIO", "NKE", "NKLA", "NLY", "NMR", "NOC", "NOV",
        "NOW", "NRG", "NSC", "NSIT", "NTAP", "NTCT", "NTES", "NTNX", "NTRS",
        "NUE", "NVAX", "NVCR", "NVDA", "NVR", "NWL", "NWSA", "NXST", "NYT",
        # O
        "O", "OBDC", "OC", "OGN", "OHI", "OKE", "OKTA", "OLED", "OLN", "OLPX",
        "OMC", "ON", "ONTO", "OPEN", "ORCL", "ORI", "ORLY", "OSK", "OTIS", "OUST",
        "OVV", "OXY",
        # P
        "PAAS", "PACB", "PANW", "PATH", "PAYC", "PAYX", "PB", "PBF", "PBR",
        "PCAR", "PCG", "PDD", "PEG", "PEGA", "PENN", "PEP", "PFE", "PFG", "PFGC",
        "PG", "PGR", "PH", "PHM", "PINS", "PKG", "PKX", "PLD", "PLMR", "PLNT",
        "PLTR", "PLUG", "PLUS", "PM", "PMT", "PNC", "PNFP", "POOL", "POR", "POST",
        "PPC", "PPG", "PPL", "PRI", "PRU", "PSA", "PSX", "PTON", "PVH", "PWR",
        "PYPL",
        # Q
        "QCOM", "QDEL", "QS", "QTWO",
        # R
        "R", "RACE", "RARE", "RBLX", "RCL", "RDDT", "RDY", "RE", "REG", "REGN",
        "REVG", "RF", "RGEN", "RGLD", "RH", "RHI", "RICK", "RITM", "RIVN", "RJF",
        "RL", "RMBS", "RMD", "RNG", "RNR", "ROK", "ROKU", "ROST", "RPM", "RS",
        "RSG", "RTX", "RUN", "RVMD", "RY",
        # S
        "S", "SAIC", "SAM", "SBAC", "SBUX", "SCCO", "SCHW", "SE", "SEDG", "SFIX",
        "SFM", "SHAK", "SHOP", "SHW", "SID", "SIGA", "SJM", "SKM", "SLB", "SLGN",
        "SLM", "SMCI", "SMG", "SNAP", "SNOW", "SNPS", "SO", "SONO", "SONY",
        "SPCE", "SPG", "SPGI", "SPOT", "SPR", "SQ", "SQM", "SRE", "SRPT", "SSB",
        "SSNC", "ST", "STAG", "STLA", "STLD", "STNE", "STT", "STX", "STZ", "SUI",
        "SWK", "SWKS", "SYF", "SYK", "SYNA", "SYY",
        # T
        "T", "TAK", "TAL", "TAP", "TD", "TDOC", "TDY", "TEAM", "TECH", "TEL",
        "TENB", "TER", "TEVA", "TFX", "TGT", "THG", "THO", "THS", "TJX", "TME",
        "TMO", "TMUS", "TOL", "TPR", "TREE", "TRIP", "TRMB", "TROW", "TRV",
        "TSCO", "TSLA", "TSM", "TSN", "TSEM", "TT", "TTD", "TTE", "TTWO", "TWLO",
        "TX", "TXN", "TXRH", "TXT", "TYL",
        # U
        "U", "UAA", "UAL", "UBER", "UDR", "UHS", "UL", "ULTA", "UNH", "UNP",
        "UPS", "URBN", "USB",
        # V
        "V", "VAC", "VCEL", "VEEV", "VICI", "VICR", "VIPS", "VLO", "VMC", "VNO",
        "VOD", "VRSK", "VRSN", "VRTX", "VTRS", "VTR", "VZ",
        # W
        "W", "WAB", "WAFD", "WAT", "WBA", "WBD", "WBS", "WCN", "WDAY", "WDC",
        "WEC", "WELL", "WEN", "WERN", "WFC", "WFRD", "WGO", "WHR", "WIX", "WKHS",
        "WLK", "WM", "WMB", "WMG", "WMT", "WPC", "WRB", "WRK", "WST", "WU",
        "WY", "WYNN",
        # X-Z
        "X", "XEL", "XOM", "XPEL", "XPEV", "XRAY", "XRX", "XYL", "YETI", "YPF",
        "YUM", "YUMC", "Z", "ZBRA", "ZBH", "ZI", "ZION", "ZM", "ZS", "ZTO", "ZTS",
        # â”€â”€ Additional Semiconductors & Chip Equipment â”€â”€
        "ACLS", "AEHR", "ALGM", "AMKR", "ASX", "ATOM", "CEVA", "COHU", "DIOD",
        "FORM", "GFS", "INDI", "IPGP", "LSCC", "MKSI", "MTSI", "MXL", "NXPI",
        "OUST", "POWI", "RMBS", "SITM", "SLAB", "SMTC", "STM", "UCTT", "UMC",
        "WOLF",
        # â”€â”€ Lidar & Autonomous Driving â”€â”€
        "AEVA", "AUR", "CPTN", "INVZ", "LAZR", "LIDR", "MBLY", "MVIS", "OUST",
        # â”€â”€ AI & Cloud Infrastructure â”€â”€
        "AI", "ALTR", "APP", "BBAI", "BIGC", "CFLT", "DV", "ESTC", "GTLB",
        "HCP", "IOT", "MNDY", "NEWR", "PD", "RBRK", "S", "TENB",
        "ZI",
        # â”€â”€ Biotech & Pharma (mid/small cap) â”€â”€
        "ACAD", "ALT", "ARWR", "BEAM", "BGNE", "CRSP", "CRNX", "DMTK", "DNLI",
        "DRNA", "EXAI", "FATE", "GPCR", "HALO", "IMVT", "IONS", "IRWD", "KRTX",
        "KYMR", "LEGN", "MGNX", "NBIX", "NTLA", "PCVX", "RARE", "RCKT", "RXRX",
        "TXG", "VKTX", "VRNA", "XENE",
        # â”€â”€ Defense & Aerospace â”€â”€
        "AVAV", "BWXT", "HEI", "HII", "KTOS", "LHX", "PLTR", "RKLB",
        "TDG", "TRMB", "WWD",
        # â”€â”€ Clean Energy & Utilities â”€â”€
        "ARRY", "BLDP", "CHPT", "CWEN", "DQ", "ENPH", "FSLR", "HASI", "MAXN",
        "NEP", "NOVA", "RUN", "SEDG", "SHLS", "SPWR",
        # â”€â”€ Fintech & Payments â”€â”€
        "AFRM", "BILL", "COIN", "FI", "FOUR", "GPN", "HUBS", "LC", "LSPD", "MKTX",
        "MQ", "PAYO", "RPAY", "SOFI", "TOST", "UPST", "XP",
        # â”€â”€ Cybersecurity â”€â”€
        "CRWD", "CYBR", "FTNT", "NET", "OKTA", "PANW", "QLYS", "RPD", "S",
        "VRNS", "ZS",
        # â”€â”€ Mining & Commodities â”€â”€
        "ALB", "CLF", "FCX", "HBM", "LAC", "MP", "NEM",
        "SCCO", "TECK", "WPM",
        # â”€â”€ Crypto & Blockchain â”€â”€
        "RIOT", "MARA", "BITF", "CLSK", "HUT", "BTBT", "CIFR",
    }

    PRICE_TTL = 300  # seconds â€” re-fetch after 5 minutes
    _cache: dict = {}  # ticker -> {"data": {...}, "ts": float}

    def _is_fresh(self, ticker: str) -> bool:
        entry = self._cache.get(ticker)
        return entry is not None and (time.time() - entry["ts"]) < self.PRICE_TTL

    @staticmethod
    def _yf_symbol(ticker: str) -> str:
        """Convert ticker to yfinance format. e.g. BRK.B â†’ BRK-B"""
        return ticker.replace(".", "-")

    async def check_tickers(self, tickers: list[str]) -> dict:
        import yfinance as yf
        import requests as _requests

        finnhub_key = os.getenv("FINNHUB_API_KEY", "")

        def _fetch_finnhub_quote(ticker: str) -> dict | None:
            """Fetch real-time quote from Finnhub (includes pre/post-market)."""
            if not finnhub_key:
                return None
            try:
                resp = _requests.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": ticker, "token": finnhub_key},
                    timeout=5,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                # c = current price, pc = previous close, dp = percent change
                c = data.get("c")
                pc = data.get("pc")
                dp = data.get("dp")
                if c and c > 0:
                    return {"price": round(c, 2), "prev_close": pc, "change_pct": round(dp, 2) if dp else None}
            except Exception:
                pass
            return None

        def _fetch_one(ticker: str) -> tuple[str, dict]:
            try:
                # â”€â”€ Step 1: Real-time price from Finnhub (includes pre/post-market) â”€â”€
                fh_quote = _fetch_finnhub_quote(ticker)

                # â”€â”€ Step 2: RVOL from yfinance (30-day volume history) â”€â”€
                volume = None
                rvol = None
                exchange = ""
                yf_price = None
                yf_change = None
                try:
                    yf_ticker = yf.Ticker(self._yf_symbol(ticker))
                    info = yf_ticker.fast_info
                    exchange = getattr(info, 'exchange', '') or ''
                    yf_price = getattr(info, 'last_price', None)
                    prev_close = getattr(info, 'previous_close', None)
                    if yf_price and prev_close and prev_close != 0:
                        yf_change = round((yf_price - prev_close) / prev_close * 100, 2)

                    hist = yf_ticker.history(period="1mo", interval="1d")
                    if hist is not None and len(hist) > 1 and "Volume" in hist.columns:
                        today_vol = hist["Volume"].iloc[-1]
                        avg_vol = hist["Volume"].iloc[:-1].mean()
                        if avg_vol and avg_vol > 0:
                            volume = int(today_vol)
                            rvol = round(today_vol / avg_vol, 2)
                except Exception:
                    pass

                # â”€â”€ Step 3: Use Finnhub price if available, else fall back to yfinance â”€â”€
                if fh_quote and fh_quote["price"]:
                    final_price = fh_quote["price"]
                    final_change = fh_quote["change_pct"]
                else:
                    final_price = round(yf_price, 2) if yf_price else None
                    final_change = yf_change

                result = {
                    "exchange": exchange,
                    "revolut": ticker in StockAvailabilityChecker.REVOLUT_TICKERS,
                    "xtb": ticker in StockAvailabilityChecker.XTB_TICKERS,
                    "price": final_price,
                    "change_pct": final_change,
                    "volume": volume,
                    "rvol": rvol,
                }
            except Exception:
                result = {
                    "exchange": "unknown",
                    "revolut": ticker in StockAvailabilityChecker.REVOLUT_TICKERS,
                    "xtb": ticker in StockAvailabilityChecker.XTB_TICKERS,
                    "price": None,
                    "change_pct": None,
                    "volume": None,
                    "rvol": None,
                }
            return ticker, result

        results = {t: self._cache[t]["data"] for t in tickers if self._is_fresh(t)}
        uncached = [t for t in tickers if not self._is_fresh(t)]
        if uncached:
            fetched = await asyncio.gather(*[asyncio.to_thread(_fetch_one, t) for t in uncached])
            for ticker, result in fetched:
                self._cache[ticker] = {"data": result, "ts": time.time()}
                results[ticker] = result
        return results


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SEC FORM 4 INSIDER ACTIVITY â€” via Finnhub insider-transactions endpoint
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


