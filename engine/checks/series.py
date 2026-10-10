"""Kept so pipeline.py's routing still works. FRED now feeds the LLM as one more source (scrape.py),
so every labeled constant goes through news.check."""


def handles(driver: str) -> bool:
    return False


def check(constant: dict, built_on: str) -> dict:
    raise NotImplementedError("FRED is fetched in checks/scrape.py; use checks.news.check")
