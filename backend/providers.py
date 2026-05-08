"""
Provider abstractions for Anthropic (Claude), OpenAI, and Gemini.
Each provider exposes a single async complete() method so the council
orchestrator stays entirely provider-agnostic.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Optional


# Runtime key store — updated via the settings API, never persisted to disk.
_keys: dict[str, str] = {}


def set_key(provider: str, key: str) -> None:
    _keys[provider] = key


def get_key(provider: str) -> Optional[str]:
    return _keys.get(provider)


# ─── Model catalogue ──────────────────────────────────────────────────────────

MODELS: dict[str, dict] = {
    # Anthropic
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "display": "Claude Haiku 4.5",
        "model_id": "claude-haiku-4-5-20251001",
        "is_chairman": False,
    },
    "claude-sonnet-4-6": {
        "provider": "anthropic",
        "display": "Claude Sonnet 4.6",
        "model_id": "claude-sonnet-4-6",
        "is_chairman": False,
    },
    "claude-opus-4-7": {
        "provider": "anthropic",
        "display": "Claude Opus 4.7 (Chairman)",
        "model_id": "claude-opus-4-7",
        "is_chairman": True,
    },
    # OpenAI
    "gpt-4o": {
        "provider": "openai",
        "display": "GPT-4o",
        "model_id": "gpt-4o",
        "is_chairman": False,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "display": "GPT-4o Mini",
        "model_id": "gpt-4o-mini",
        "is_chairman": False,
    },
    # Gemini
    "gemini-2.0-flash": {
        "provider": "gemini",
        "display": "Gemini 2.0 Flash",
        "model_id": "gemini-2.0-flash",
        "is_chairman": False,
    },
    "gemini-1.5-pro": {
        "provider": "gemini",
        "display": "Gemini 1.5 Pro",
        "model_id": "gemini-1.5-pro",
        "is_chairman": False,
    },
}

DEFAULT_CHAIRMAN_KEY = "claude-opus-4-7"


# ─── Provider implementations ─────────────────────────────────────────────────

async def _call_anthropic(model_id: str, system: str, user: str) -> str:
    import anthropic

    key = get_key("anthropic")
    if not key:
        raise ValueError("Anthropic API key not configured")

    client = anthropic.AsyncAnthropic(api_key=key)
    message = await client.messages.create(
        model=model_id,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


async def _call_openai(model_id: str, system: str, user: str) -> str:
    from openai import AsyncOpenAI

    key = get_key("openai")
    if not key:
        raise ValueError("OpenAI API key not configured")

    client = AsyncOpenAI(api_key=key)
    response = await client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=2048,
    )
    return response.choices[0].message.content


async def _call_gemini(model_id: str, system: str, user: str) -> str:
    import google.generativeai as genai

    key = get_key("gemini")
    if not key:
        raise ValueError("Gemini API key not configured")

    genai.configure(api_key=key)
    model = genai.GenerativeModel(
        model_name=model_id,
        system_instruction=system,
    )
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: model.generate_content(user)
    )
    return response.text


async def complete(model_key: str, system: str, user: str) -> str:
    """Route to the right provider and return the model's text response."""
    meta = MODELS[model_key]
    provider = meta["provider"]
    model_id = meta["model_id"]

    if provider == "anthropic":
        return await _call_anthropic(model_id, system, user)
    elif provider == "openai":
        return await _call_openai(model_id, system, user)
    elif provider == "gemini":
        return await _call_gemini(model_id, system, user)
    else:
        raise ValueError(f"Unknown provider: {provider}")
