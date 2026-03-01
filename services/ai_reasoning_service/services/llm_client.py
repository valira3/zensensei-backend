"""
ZenSensei AI Reasoning Service - LLM Client

Thin async wrapper around Google Gemini (primary) with OpenAI as fallback.
All generation goes through a single `generate()` entry-point that handles
retries, timeout, and model selection transparently.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_PRIMARY = "gemini-2.0-flash"
_DEFAULT_FALLBACK = "gpt-4o-mini"
_MAX_RETRIES = 3
_TIMEOUT_SECS = 30.0


class LLMClient:
    """
    Async LLM client with primary (Gemini) + fallback (OpenAI) support.

    Usage
    -----
    client = LLMClient()
    response_text = await client.generate("Your prompt here")
    """

    def __init__(
        self,
        primary_model: str = _DEFAULT_PRIMARY,
        fallback_model: str = _DEFAULT_FALLBACK,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self._openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")

    # ─── Public ───────────────────────────────────────────────────────────────────

    @property
    def primary_model(self) -> str:
        return self._primary_model

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.4,
        max_output_tokens: int = 4096,
        use_fallback: bool = False,
    ) -> str:
        """
        Generate a completion for *prompt*.

        Tries the primary model first; on failure, falls back to the
        secondary model.  Raises `RuntimeError` if both fail.
        """
        models = [
            (self._primary_model, self._gemini_key, self._call_gemini),
            (self._fallback_model, self._openai_key, self._call_openai),
        ]
        last_error: Optional[Exception] = None

        for model_name, api_key, caller in models:
            if not api_key:
                logger.debug("llm_key_missing", model=model_name)
                continue
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    result = await asyncio.wait_for(
                        caller(prompt, model_name, api_key, temperature, max_output_tokens),
                        timeout=_TIMEOUT_SECS,
                    )
                    logger.info(
                        "llm_generate_ok",
                        model=model_name,
                        attempt=attempt,
                        chars=len(result),
                    )
                    return result
                except asyncio.TimeoutError:
                    logger.warning("llm_timeout", model=model_name, attempt=attempt)
                    last_error = asyncio.TimeoutError(f"{model_name} timed out")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "llm_error", model=model_name, attempt=attempt, error=str(exc)
                    )
                    last_error = exc

        raise RuntimeError(
            f"All LLM calls failed. Last error: {last_error}"
        )

    # ─── Private model callers ───────────────────────────────────────────────

    @staticmethod
    async def _call_gemini(
        prompt: str,
        model: str,
        api_key: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call Google Gemini via the official SDK."""
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel(
            model,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, gemini_model.generate_content, prompt
        )
        return response.text

    @staticmethod
    async def _call_openai(
        prompt: str,
        model: str,
        api_key: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call OpenAI ChatCompletions via the official async SDK."""
        from openai import AsyncOpenAI  # type: ignore

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
