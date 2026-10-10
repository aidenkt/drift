import json

from checks import scrape

SERP = json.dumps({"organic": [
    {"link": "https://www.example.com/used-ev-prices", "title": "Used EV prices fall", "source": "Example News", "date": "2023-07-12"},
]})
ARTICLE = """<html><head><script>var x = 99;</script><style>p{}</style></head><body>
<nav>Home 2023</nav>
<p>Used EV prices fell 29.5% in June compared with a year earlier, according to iSeeCars.</p>
<p>Gas car prices were roughly flat.</p>
<p>Weather today.</p>
</body></html>"""
FRED = json.dumps({"observations": [
    {"date": "2022-12-14", "value": "4.30"}, {"date": "2022-12-15", "value": "."},
    {"date": "2023-12-01", "value": "5.32"}, {"date": "2023-12-04", "value": "5.31"},
]})


def test_html_to_text_drops_scripts_and_nav():
    text = scrape.html_to_text(ARTICLE)
    assert "var x" not in text and "Home 2023" not in text
    assert "Used EV prices fell 29.5% in June" in text


def test_gather_builds_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "serp")
    monkeypatch.setenv("BRIGHTDATA_UNLOCKER_ZONE", "unlocker")
    monkeypatch.setenv("FRED_API_KEY", "k")
    fetched = []

    def fake_cached(key, fetch):
        fetched.append(key)
        if key[0] == "fred":
            return FRED
        return SERP if "google.com" in key[2] else ARTICLE

    monkeypatch.setattr(scrape, "_cached", fake_cached)
    pages = scrape.gather("Used EV residual value", ["used EV prices 2023", "SOFR 2023"], "2022-12-15", "2023-12-04")

    fred = pages[0]
    assert fred["url"] == "https://fred.stlouisfed.org/series/SOFR"
    assert "Value on 2022-12-14: 4.3%" in fred["text"]  # holiday "." skipped, last value on or before built_on
    assert "Value on 2023-12-04: 5.31%" in fred["text"]

    article = pages[1]
    assert article["publisher"] == "Example News" and article["date"] == "2023-07-12"
    assert "fell 29.5%" in article["text"]
    assert "Weather" not in article["text"]  # no topic words, no numbers
    assert [p["id"] for p in pages] == [1, 2]
    assert sum(1 for k in fetched if k[0] == "brightdata" and k[2].endswith("used-ev-prices")) == 1  # fetched once


def test_no_keys_returns_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    for k in ("BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert scrape.gather("SOFR", ["SOFR"], "2022-12-15", "2023-12-04") == []


def test_cache_skips_second_fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return "body"

    assert scrape._cached(("a",), fetch) == "body"
    assert scrape._cached(("a",), fetch) == "body"
    assert len(calls) == 1
