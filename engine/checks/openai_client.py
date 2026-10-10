"""One OpenAI call that must answer with JSON matching a schema (structured outputs)."""

import json
import os

import httpx

URL = "https://api.openai.com/v1/chat/completions"


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
        r = httpx.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=90)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMUnavailable(str(e)) from e
