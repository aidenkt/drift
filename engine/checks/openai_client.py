"""One OpenAI call that must answer with JSON matching a schema (structured outputs)."""

import json
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

URL = "https://api.openai.com/v1/chat/completions"
RETRY = {429, 500, 502, 503}


class LLMUnavailable(RuntimeError):
    """No key or model configured, or the call failed. Callers fall back instead of crashing."""


def chat_json(system: str, user: str, schema: dict, name: str) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not key or not model:
        raise LLMUnavailable("OPENAI_API_KEY and OPENAI_MODEL must be set")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    try:
        for attempt in range(5):
            r = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=90)
            # rate limited or overloaded: wait as told, else back off 1, 2, 4, 8s
            wait = float(r.headers.get("retry-after") or 2**attempt)
            if r.status_code not in RETRY or attempt == 4 or wait > 30:
                break  # a daily limit says "try again in 28m"; waiting won't help
            log.info("OpenAI %s, retrying in %.0fs", r.status_code, wait)
            time.sleep(min(wait, 30))
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        detail = getattr(getattr(e, "response", None), "text", "")[:200]
        log.warning("OpenAI call failed: %s %s", e, detail)
        raise LLMUnavailable(str(e)) from e
