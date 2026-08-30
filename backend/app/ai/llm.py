"""LLM providers.

Two implementations behind one protocol: Ollama (local, no key) and Groq
(hosted, needs a key). Both are optional -- the pipeline runs without either,
falling back to rule-based extraction and lexical classification.

What an LLM is allowed to do here is deliberately narrow:

- Extract claims and interpret supplied evidence.
- NOTHING ELSE. It never decides a verdict; scoring does that deterministically
  from labeled evidence. It never uses unstated world knowledge as evidence --
  a model asserting something from training data is not a citable source.

All output is Pydantic-validated. Unparseable output fails the stage rather
than being coerced into something plausible-looking.

On the paid-API rule: the project must run with zero keys, and it does. Groq is
strictly opt-in and off by default, so the no-key path stays the tested default.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AIOutputValidationError, ProviderUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(Protocol):
    """A text-generation provider."""

    name: str

    def is_available(self) -> bool: ...

    async def complete_json(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 2000
    ) -> dict[str, Any]:
        """Return parsed JSON. Raises AIOutputValidationError if unparseable."""
        ...


def _extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose or fences even when told not to, so the object is
    located rather than assumed. A response with no valid object fails loudly --
    never partially parsed into something that looks like a result.
    """
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if len(lines) > 2 else lines).strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise AIOutputValidationError(
        "The model did not return valid JSON.",
        {"response_preview": text[:200]},
    )


class OllamaProvider:
    """Local Ollama. No API key, no data leaves the machine."""

    name = "ollama"

    def is_available(self) -> bool:
        settings = get_settings()
        if not settings.ollama_enabled:
            return False
        try:
            with httpx.Client(timeout=2.0) as client:
                return client.get(f"{settings.ollama_base_url}/api/tags").status_code == 200
        except Exception:
            return False

    async def complete_json(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 2000
    ) -> dict[str, Any]:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.ollama_text_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "format": "json",
                        # Deterministic decoding: the same submission should not
                        # produce different claims on a re-run.
                        "options": {"temperature": 0.1, "num_predict": max_tokens},
                    },
                )
                response.raise_for_status()
                return _extract_json(response.json()["message"]["content"])
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                "The local language model is not reachable.",
                {"error_type": type(exc).__name__},
            ) from exc


class GroqProvider:
    """Groq-hosted inference.

    Opt-in: disabled unless a key is configured. Submitted text is sent to a
    third party, which is why this is never the default.
    """

    name = "groq"

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.groq_enabled and settings.groq_api_key)

    async def complete_json(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 2000
    ) -> dict[str, Any]:
        settings = get_settings()
        if not self.is_available():
            raise ProviderUnavailableError("Groq is not configured.")

        try:
            async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.groq_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.groq_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                if response.status_code == 429:
                    raise ProviderUnavailableError("Groq rate limit reached.", {"status": 429})
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return _extract_json(content)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                "Groq is not reachable.", {"error_type": type(exc).__name__}
            ) from exc


def get_llm_provider() -> LLMProvider | None:
    """Select the configured provider, or None when neither is available.

    Ollama is preferred when both are up: it is local, so no submitted content
    leaves the machine.
    """
    for provider in (OllamaProvider(), GroqProvider()):
        if provider.is_available():
            logger.info("llm.provider_selected", provider=provider.name)
            return provider
    return None
