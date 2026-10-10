"""Public time series (FRED): value at built_on vs latest → drift_pct."""

from checks.drivers import DRIVERS


def handles(driver: str) -> bool:
    return DRIVERS[driver][1] == "series"


def check(constant: dict, built_on: str) -> dict:
    raise NotImplementedError
