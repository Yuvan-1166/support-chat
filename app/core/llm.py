"""LLM client abstraction using the Groq SDK."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Optional

from groq import Groq

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around the Groq chat-completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model

    # ── public API ───────────────────────────────────────────────────────

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send *messages* to the Groq model and return the response text.

        Parameters
        ----------
        messages:
            Standard OpenAI-style list of ``{"role": ..., "content": ...}``
            dicts.
        temperature:
            Sampling temperature (low → deterministic).
        max_tokens:
            Maximum tokens in the response.
        response_format:
            Optional ``{"type": "json_object"}`` to force JSON output.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        logger.debug("LLM request: model=%s, messages=%d", self._model, len(messages))

        completion = self._client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content or ""

        logger.debug("LLM response length: %d chars", len(content))
        return content

    def chat_completion_json(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Convenience wrapper that forces JSON output and parses it."""
        raw = self.chat_completion(
            messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON: %s", raw[:500])
            return {"error": "LLM returned invalid JSON", "raw": raw}


@lru_cache
def get_llm_client() -> LLMClient:
    """Return a cached singleton LLM client."""
    settings = get_settings()
    return LLMClient(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
