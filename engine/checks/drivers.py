"""Fixed catalog of real-world drivers a constant can map to. Labels never leave this list."""

DRIVERS = {
    # key: (display label, kind, source id)
    "sofr": ("SOFR", "series", "FRED:SOFR"),
    "ust10y": ("10Y Treasury yield", "series", "FRED:DGS10"),
    "fed_funds": ("Fed funds rate", "series", "FRED:FEDFUNDS"),
    "eurusd": ("EUR/USD rate", "series", "FRED:DEXUSEU"),
    "wti": ("WTI crude $/bbl", "series", "FRED:DCOILWTICO"),
    "cpi": ("CPI inflation", "series", "FRED:CPIAUCSL"),
    "freight_feu": ("Container freight $/FEU", "news", "brightdata:freight"),
    "tariff": ("Import tariff rate", "news", "brightdata:tariff"),
}
