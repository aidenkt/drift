"""Hints for where to look up a driver. Labels are free text (see label.py); this is not a closed catalog."""

import re

# FRED series a label can map to. Matched on lowercase keywords in the label, as whole words ("2" is not
# found in "2026", nor "euro" in "eurozone"); first match wins, so a specific name goes before a generic one.
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
    (("brent",), "DCOILBRENTEU", "Brent crude oil, $/bbl", "level"),  # before "crude": Brent crude is not WTI
    (("wti",), "DCOILWTICO", "WTI crude oil, $/bbl", "level"),
    (("crude",), "DCOILWTICO", "WTI crude oil, $/bbl", "level"),
    # exchange rates as FRED quotes them; a model holding the inverse fails the anchor test and is left alone
    (("jpy",), "DEXJPUS", "Japanese yen to one US dollar", "level"),
    (("yen",), "DEXJPUS", "Japanese yen to one US dollar", "level"),
    (("cad",), "DEXCAUS", "Canadian dollars to one US dollar", "level"),
    (("canadian dollar",), "DEXCAUS", "Canadian dollars to one US dollar", "level"),
    (("mxn",), "DEXMXUS", "Mexican pesos to one US dollar", "level"),
    (("peso",), "DEXMXUS", "Mexican pesos to one US dollar", "level"),
    (("brl",), "DEXBZUS", "Brazilian reais to one US dollar", "level"),
    (("brazilian real",), "DEXBZUS", "Brazilian reais to one US dollar", "level"),
    (("gbp",), "DEXUSUK", "US dollars to one British pound", "level"),
    (("cny",), "DEXCHUS", "Chinese yuan to one US dollar", "level"),
    (("yuan",), "DEXCHUS", "Chinese yuan to one US dollar", "level"),
    (("jet fuel",), "DJFUELUSGULF", "Kerosene-type jet fuel, US Gulf Coast, $/gal", "level"),
    (("diesel",), "GASDESW", "US on-highway diesel, $/gal", "level"),
    (("henry hub",), "DHHNGSP", "Henry Hub natural gas spot, $/MMBtu", "level"),
    (("natural gas",), "DHHNGSP", "Henry Hub natural gas spot, $/MMBtu", "level"),
    (("arabica",), "PCOFFOTMUSDM", "Coffee, other mild arabicas, cents/lb", "level"),
    (("30", "mortgage"), "MORTGAGE30US", "30-year fixed mortgage rate", "percent"),
    (("cpi",), "CPIAUCSL", "CPI, all urban consumers", "level"),
    (("inflation",), "CPIAUCSL", "CPI, all urban consumers", "level"),
    (("used car",), "CUSR0000SETA02", "CPI: used cars and trucks", "level"),
    (("used vehicle",), "CUSR0000SETA02", "CPI: used cars and trucks", "level"),
]

# A label with one of these is priced off a benchmark, not the benchmark: "Term loan margin over SOFR".
PRICED_OFF = re.compile(r"margin|spread|premium|\bover\b|\bplus\b|\+", re.I)
FRED_ANCHOR = 0.02  # the model was built from the series if its value is within 2% of the series on built_on


def fred_series_for(label: str) -> tuple[str, str, str] | None:
    """(series id, display name, unit) for a label, or None."""
    text = label.lower()
    for keywords, series_id, name, unit in FRED_SERIES:
        if all(_has_word(text, k) for k in keywords):
            return series_id, name, unit
    return None


def _has_word(text: str, keyword: str) -> bool:
    """keyword as a word of its own: "10" in "10-year" and "10y" but not "2010"; "used car" in "used cars"."""
    end = r"(?!\d)" if keyword[-1].isdigit() else r"s?(?![a-z0-9])"
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}{end}", text))


def series_scale(label: str, value: float, obs: dict) -> float | None:
    """Factor from a FRED observation's units to the model's (1, or 0.01 for a percent series the model holds
    as a decimal) when the series IS this constant's quantity, else None. Keywords are only a hint, so two
    things must hold: the label names the series itself, not something priced off it, and the model's value
    is what the series printed on built_on, to FRED_ANCHOR. obs is the "fred" dict of scrape's data page."""
    series = fred_series_for(label)
    if not value or not series or series[0] != obs["series"] or PRICED_OFF.search(label):
        return None
    # a model dated the 1st usually took the previous close, so any of the last few prints may be its source
    for scale in (1, 0.01) if obs["unit"] == "percent" else (1,):
        if any(abs(then * scale - value) <= FRED_ANCHOR * abs(value) for then in obs.get("then_recent") or [obs["then"]]):
            return scale
    return None
