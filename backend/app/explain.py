import json
import re

import httpx

from .config import Settings

EXPAND_SECONDS = 8
MAX_SUGGESTIONS = 6
SUGGESTION = re.compile(r"[A-Za-z_][\w.]{0,59}")

EXPAND_PROMPT = """You help search a Python code repository.
Reply with only a JSON array of up to 6 likely Python identifiers or code words
(function, class, module or variable names) that would appear in code answering the question.
Example: ["open_session", "SecureCookieSessionInterface", "cookie"]"""


class AIUnavailable(Exception):
    """The AI provider is not configured, failed, or replied with something unusable."""


def chat(settings: Settings, system: str, user: str, seconds: float, max_tokens: int) -> str:
    """One OpenAI-compatible chat completion; every failure becomes AIUnavailable."""
    if not settings.ai_configured:
        raise AIUnavailable("AI is not configured")
    try:
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_key}"},
            json={
                "model": settings.ai_model,
                "temperature": 0,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("AI reply content is not text")
        return content
    except (httpx.HTTPError, ValueError, LookupError, TypeError) as exc:
        raise AIUnavailable("The AI service did not respond in time or failed") from exc


def parse_json(text: str):
    """The first JSON object/array in a reply, tolerating code fences or prose around it."""
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    end = max(text.rfind("}"), text.rfind("]"))
    if not starts or end < min(starts):
        raise AIUnavailable("The AI reply was not valid JSON")
    try:
        return json.loads(text[min(starts) : end + 1])
    except ValueError as exc:
        raise AIUnavailable("The AI reply was not valid JSON") from exc


def suggest_terms(settings: Settings, question: str) -> list[str]:
    """Up to six validated identifier-like search terms suggested for the question."""
    reply = parse_json(chat(settings, EXPAND_PROMPT, question, EXPAND_SECONDS, 120))
    if not isinstance(reply, list):
        raise AIUnavailable("The AI reply was not a list of terms")
    found = [t for t in reply if isinstance(t, str) and SUGGESTION.fullmatch(t)]
    return list(dict.fromkeys(found))[:MAX_SUGGESTIONS]
