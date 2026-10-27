"""OpenRouter translation adapter.

Implements :class:`app.ports.ai.Translator` using OpenRouter chat completions.
Translates text while preserving domain nuance.
"""

from __future__ import annotations

from typing import Sequence

from app.ports.ai import Translator


class OpenRouterTranslator(Translator):
    def __init__(self, *, model: str | None = None) -> None:
        self._model = model

    async def translate(
        self,
        text: str,
        target_language: str,
        *,
        model: str | None = None,
    ) -> str:
        effective_model = model or self._model
        from openai import AsyncOpenAI  # type: ignore[no-redef]

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
        system_prompt = (
            "You are a professional translator. Translate the given text into "
            f"{target_language}, preserving domain nuance and technical terms. "
            "Return ONLY the translated text, nothing else."
        )
        user_prompt = f"Target language: {target_language}\nText: {text}\n"
        response = await client.chat.completions.create(
            model=effective_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or text