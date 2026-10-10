"""Part 2, scraping: published figures for a driver between built_on and as_of.

Bright Data SERP API (Google, date-restricted) finds pages, Bright Data Web Unlocker fetches them,
FRED adds an official series when the label maps to one. Everything is cached on disk.
"""

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx

from checks.drivers import fred_series_for

BRIGHTDATA_URL = "https://api.brightdata.com/request"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
CACHE = Path(__file__).parents[1] / ".cache"
MAX_RESULTS = 6
EXCERPT_CHARS = 4000


def gather(label: str, search: list[str], built_on: str, as_of: str) -> list[dict]:
    """Pages for the LLM: [{id, url, publisher, date, title, text}]. Never raises."""
    pages: list[dict] = []
    fred = _fred_page(" ".join([label, *search]), built_on, as_of)
    if fred:
        pages.append(fred)
    seen = set()
    for query in search[:3]:
        for hit in _search(query, built_on, as_of):
            if hit["url"] in seen or len(seen) >= MAX_RESULTS:
                continue
            seen.add(hit["url"])
            snippet = hit.pop("snippet", "")
            text = _excerpt(_fetch_text(hit["url"]), label, query) or snippet
            if text:
                pages.append({**hit, "text": text})
    for i, page in enumerate(pages, 1):
        page["id"] = i
    return pages


# --- Bright Data ---------------------------------------------------------------


def _search(query: str, built_on: str, as_of: str) -> list[dict]:
    """Google results via the SERP API. Google answers date-range searches (tbs=cdr) from
    Bright Data with a captcha, so the window goes into the query text as a year instead."""
    zone = os.environ.get("BRIGHTDATA_SERP_ZONE")
    if not zone:
        return []
    if not re.search(r"\b(19|20)\d{2}\b", query):
        query = f"{query} {as_of[:4]}"
    url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en&gl=us"
    raw = _brightdata(zone, url, data_format="parsed")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return []
    hits = []
    for item in data.get("organic") or []:
        link = item.get("link")
        if not link:
            continue
        extensions = item.get("extensions") or []
        hits.append({
            "url": link,
            "publisher": item.get("source") or urlparse(link).netloc.removeprefix("www."),
            "date": next((d for d in (_iso_date(e.get("text")) for e in extensions) if d), None),
            "title": item.get("title") or "",
            "snippet": item.get("description") or "",
        })
    return hits


def _fetch_text(url: str) -> str:
    zone = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE")
    if not zone:
        return ""
    return html_to_text(_brightdata(zone, url))


class BrightDataError(httpx.HTTPError):
    pass


def _brightdata(zone: str, url: str, data_format: str | None = None) -> str:
    key = os.environ.get("BRIGHTDATA_API_KEY")
    if not key:
        return ""
    body = {"zone": zone, "url": url, "format": "raw"}
    if data_format:
        body["data_format"] = data_format

    def fetch():
        # Bright Data reports most failures as HTTP 200 with an empty body and an x-brd-error header.
        for attempt in range(2):
            r = httpx.post(BRIGHTDATA_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=90)
            r.raise_for_status()
            if r.text and not r.headers.get("x-brd-error"):
                return r.text
            error = r.headers.get("x-brd-error", "empty response")
        raise BrightDataError(error)

    return _cached(("brightdata", zone, url, data_format), fetch)


# --- FRED ----------------------------------------------------------------------


def _fred_page(topic: str, built_on: str, as_of: str) -> dict | None:
    series = fred_series_for(topic)
    key = os.environ.get("FRED_API_KEY")
    if not series or not key:
        return None
    series_id, name, unit = series
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "observation_start": (date.fromisoformat(built_on) - timedelta(days=45)).isoformat(),
        "observation_end": as_of,
    }

    def fetch():
        r = httpx.get(FRED_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.text

    raw = _cached(("fred", series_id, built_on, as_of), fetch)
    if not raw:
        return None
    obs = [(o["date"], float(o["value"])) for o in json.loads(raw).get("observations", []) if o["value"] != "."]
    then = _last_on_or_before(obs, built_on)
    now = _last_on_or_before(obs, as_of)
    if not then or not now:
        return None
    suffix = "%" if unit == "percent" else ""
    change = (now[1] - then[1]) / then[1] * 100
    text = (
        f"FRED series {series_id} ({name}). "
        f"Value on {then[0]}: {then[1]:g}{suffix}. "
        f"Value on {now[0]}: {now[1]:g}{suffix}. "
        f"Change between those dates: {change:+.1f}%."
    )
    return {
        "url": f"https://fred.stlouisfed.org/series/{series_id}",
        "publisher": "FRED, Federal Reserve Bank of St. Louis",
        "date": now[0],
        "title": f"FRED {series_id}",
        "text": text,
    }


def _last_on_or_before(obs: list[tuple[str, float]], day: str) -> tuple[str, float] | None:
    before = [o for o in obs if o[0] <= day]
    return before[-1] if before else None


# --- text ------------------------------------------------------------------------


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    text = "".join(parser.parts)
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _excerpt(text: str, label: str, query: str) -> str:
    """Paragraphs that mention the topic and contain a number, up to EXCERPT_CHARS."""
    if not text:
        return ""
    words = {w for w in re.findall(r"[a-z]{4,}", f"{label} {query}".lower())}
    scored = []
    for i, para in enumerate(text.split("\n")):
        if not re.search(r"\d", para):
            continue
        hits = sum(w in para.lower() for w in words)
        if hits:
            scored.append((-hits, i, para))
    out, size = [], 0
    for _, i, para in sorted(scored)[:20]:
        if size + len(para) > EXCERPT_CHARS:
            break
        out.append((i, para))
        size += len(para)
    return "\n".join(p for _, p in sorted(out))


# --- helpers ---------------------------------------------------------------------


def _cached(key: tuple, fetch) -> str:
    """Disk cache so reruns and the demo don't hit the network. Failures are not cached."""
    path = CACHE / (hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24] + ".txt")
    if path.exists():
        return path.read_text()
    try:
        body = fetch()
    except httpx.HTTPError:
        return ""
    CACHE.mkdir(exist_ok=True)
    path.write_text(body)
    return body


def _iso_date(value) -> str | None:
    if not value:
        return None
    text = str(value)
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if m:
        return m.group(0)
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", text)
    if m:
        try:
            return datetime.strptime(" ".join(m.groups()), "%b %d %Y").date().isoformat()
        except ValueError:
            return None
    return None
