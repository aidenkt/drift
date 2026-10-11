"""Check one labeled constant: scrape figures and events → OpenAI compares them with the graph summary → verify.
Entry point for pipeline.py."""

import logging
import os
import threading
from datetime import date

from checks import assess, scrape, verify
from checks.openai_client import LLMUnavailable

log = logging.getLogger(__name__)

# (driver, built_on, as_of) -> pages, so cells sharing a driver are scraped once
_pages: dict[tuple, list[dict]] = {}
_locks: dict[tuple, threading.Lock] = {}  # one per key: check runs in several threads, a driver is still scraped once
_guard = threading.Lock()  # for _locks


def check(constant: dict, built_on: str, as_of: str | None = None) -> dict:
    """Schema-valid `check` dict. Never raises: any failure gives status "unknown". Safe to call from
    several threads at once."""
    as_of = as_of or os.environ.get("DRIFT_AS_OF") or date.today().isoformat()
    try:
        key = (constant.get("driver"), built_on, as_of)
        with _guard:
            lock = _locks.setdefault(key, threading.Lock())
        with lock:  # held while scraping, so a second cell with this driver waits instead of scraping again
            if key not in _pages:
                _pages[key] = scrape.gather(constant["label"], constant.get("search") or [constant["label"]], built_on,
                                            as_of, constant.get("events") or [], constant.get("value"))
            pages = _pages[key]
        finding = assess.assess(constant, pages, built_on, as_of)
        return verify.build_check(constant, finding, pages, as_of, built_on)
    except LLMUnavailable as e:
        log.warning("check %s: LLM unavailable: %s", constant.get("cell"), e)
    except Exception:
        log.exception("check %s failed", constant.get("cell"))
    return verify.unknown_check(as_of)
