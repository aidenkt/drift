"""TypeSafe Jev on OpenRouter (typesafe/jev). Classifies only: returns p_stale, never writes prose."""


def p_stale(constant: dict, articles: list[dict]) -> float:
    raise NotImplementedError
