"""Check one labeled constant: scrape (part 2) → OpenAI (part 3) → verify. Entry point for pipeline.py."""

import logging
import os
from datetime import date

from checks import assess, scrape, verify
from checks.openai_client import LLMUnavailable

log = logging.getLogger(__name__)

# (driver, built_on, as_of) -> pages, so cells sharing a driver are scraped once
_pages: dict[tuple, list[dict]] = {}


def check(constant: dict, built_on: str, as_of: str | None = None) -> dict:
    """Schema-valid `check` dict. Never raises: any failure gives status "unknown"."""
    as_of = as_of or os.environ.get("DRIFT_AS_OF") or date.today().isoformat()
    try:
        key = (constant.get("driver"), built_on, as_of)
        if key not in _pages:
            _pages[key] = scrape.gather(constant["label"], constant.get("search") or [constant["label"]], built_on, as_of)
        pages = _pages[key]
        finding = assess.assess(constant, pages, built_on, as_of)
        return verify.build_check(constant, finding, pages, as_of)
    except LLMUnavailable as e:
        log.warning("check %s: LLM unavailable: %s", constant.get("cell"), e)
    except Exception:
        log.exception("check %s failed", constant.get("cell"))
    return verify.unknown_check(as_of)
