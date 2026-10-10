"""Hints for where to look up a driver. Labels are free text (see label.py); this is not a closed catalog."""

# FRED series a label can map to. Matched on lowercase keywords in the label; first match wins.
# unit "percent" means FRED publishes 4.33 for 4.33%.
FRED_SERIES = [
    # (keywords that must all appear, series id, display name, unit)
    (("sofr",), "SOFR", "Secured Overnight Financing Rate", "percent"),
    (("fed funds",), "DFF", "Effective federal funds rate", "percent"),
    (("federal funds",), "DFF", "Effective federal funds rate", "percent"),
    (("10", "treasury"), "DGS10", "10-year Treasury yield", "percent"),
    (("2", "treasury"), "DGS2", "2-year Treasury yield", "percent"),
    (("prime rate",), "DPRIME", "Bank prime loan rate", "percent"),
    (("eur/usd",), "DEXUSEU", "US dollars to one euro", "level"),
    (("euro",), "DEXUSEU", "US dollars to one euro", "level"),
    (("wti",), "DCOILWTICO", "WTI crude oil, $/bbl", "level"),
    (("crude",), "DCOILWTICO", "WTI crude oil, $/bbl", "level"),
    (("brent",), "DCOILBRENTEU", "Brent crude oil, $/bbl", "level"),
    (("cpi",), "CPIAUCSL", "CPI, all urban consumers", "level"),
    (("inflation",), "CPIAUCSL", "CPI, all urban consumers", "level"),
    (("used car",), "CUSR0000SETA02", "CPI: used cars and trucks", "level"),
    (("used vehicle",), "CUSR0000SETA02", "CPI: used cars and trucks", "level"),
]


def fred_series_for(label: str) -> tuple[str, str, str] | None:
    """(series id, display name, unit) for a label, or None."""
    text = label.lower()
    for keywords, series_id, name, unit in FRED_SERIES:
        if all(k in text for k in keywords):
            return series_id, name, unit
    return None
