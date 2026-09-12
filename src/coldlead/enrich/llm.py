"""Provider-agnostic JSON completion: Gemini, Anthropic, OpenRouter, OpenAI or local Ollama.

Only used when a key is configured. Every failure degrades gracefully to ``None`` so the
heuristic path always remains available.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from coldlead.settings import Settings

log = logging.getLogger(__name__)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def complete_json(
    prompt: str, settings: Settings, system: str = "", client: httpx.Client | None = None
) -> dict | None:
    if not settings.llm_enabled:
        return None
    owns = client is None
    client = client or httpx.Client(timeout=45.0)
    provider, model, key = settings.llm_provider, settings.llm_model, settings.llm_api_key
    try:
        if provider == "gemini":
            body: dict = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
            }
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
            resp = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key or ""},
                json=body,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        elif provider == "anthropic":
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key or "", "anthropic-version": "2023-06-01"},
                json={
                    "model": model,
                    "max_tokens": 2000,
                    "system": system or "Reply with a single valid JSON object and nothing else.",
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            text = "".join(
                b.get("text", "") for b in resp.json()["content"] if b.get("type") == "text"
            )
        else:  # OpenAI-compatible: openai, openrouter, ollama, LM Studio…
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            messages = ([{"role": "system", "content": system}] if system else []) + [
                {"role": "user", "content": prompt}
            ]
            resp = client.post(
                f"{(settings.llm_base_url or '').rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(text)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("LLM call failed (%s): %s", provider, exc)
        return None
    finally:
        if owns:
            client.close()
