"""Pluggable LLM client for the AI Chat layer.

Local-first by design: if Ollama is running we use it (no API key, no cloud).
If an Anthropic key is set we use Claude. If neither is reachable, callers fall
back to deterministic, evidence-grounded answers — so the product never hard
-depends on a model being available.
"""

from __future__ import annotations

import logging

import httpx

from .config import get_settings

log = logging.getLogger("prl.llm")
settings = get_settings()


def available() -> bool:
    return settings.llm_provider in ("ollama", "anthropic")


def complete(system: str, user: str, *, temperature: float = 0.3,
             max_tokens: int | None = None) -> str | None:
    """Return the model's text answer, or None if no model is reachable."""
    provider = settings.llm_provider
    try:
        if provider == "ollama":
            return _ollama(system, user, temperature, max_tokens)
        if provider == "anthropic" and settings.anthropic_api_key:
            return _anthropic(system, user, temperature, max_tokens)
    except Exception as exc:  # noqa: BLE001 — the model is never allowed to break a reply
        # Any failure (unreachable host, bad URL, malformed response, timeout,
        # IPv6/DNS error) must degrade to the deterministic answer, never 500.
        log.warning("LLM call failed (%s: %s); using deterministic fallback: %s",
                    provider, type(exc).__name__, exc)
    return None


def _ollama(system: str, user: str, temperature: float,
            max_tokens: int | None = None) -> str:
    options: dict = {"temperature": temperature}
    if max_tokens:
        options["num_predict"] = max_tokens
    resp = httpx.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": options,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def _anthropic(system: str, user: str, temperature: float,
               max_tokens: int | None = None) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_model,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
            # Cache the (stable) system prompt to cut latency/cost on repeat calls.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return "".join(block["text"] for block in resp.json()["content"] if block["type"] == "text").strip()
