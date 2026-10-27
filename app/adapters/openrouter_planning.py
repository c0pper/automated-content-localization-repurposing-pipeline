"""OpenRouter planning adapter.

Implements :class:`app.ports.ai.ClipPlanner` using OpenRouter chat completions.
Model ID is configuration-driven; overrides restricted to a curated allowlist.
"""

from __future__ import annotations

from typing import Mapping

from app.domain.models import ClipCandidate, Transcript
from app.ports.ai import ClipPlanner


class OpenRouterClipPlanner(ClipPlanner):
    def __init__(
        self,
        *,
        model: str,
        allowlist: Mapping[str, str] | None = None,
    ) -> None:
        self._default_model = model
        self._allowlist = dict(allowlist or {})

    async def select_clips(
        self,
        transcript: Transcript,
        *,
        min_clips: int,
        max_clips: int,
        model: str | None = None,
    ) -> list[ClipCandidate]:
        effective_model = model or self._default_model
        if effective_model not in self._allowlist and model is not None:
            raise ValueError(f"Planning model override not allowed: {effective_model}")

        from openai import AsyncOpenAI  # type: ignore[no-redef]

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
        system_prompt = (
            "You are a content planning assistant. Given a word-level transcript, "
            f"select {min_clips} to {max_clips} high-value short-form clip candidates. "
            "Return JSON with a `clips` array: each clip has `start_seconds`, "
            "`end_seconds`, `hook_title`, `caption`, `rationale`, and `source_text`. "
            "All times are seconds."
        )
        user_prompt = (
            f"Transcript text: {transcript.text}\n"
            f"Transcript words (start/end/text): {[(w.start, w.end, w.text) for w in transcript.words]}\n"
        )
        response = await client.chat.completions.create(
            model=effective_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        clips: list[ClipCandidate] = []
        for item in data.get("clips", []):
            clips.append(
                ClipCandidate(
                    segment_id=len(clips) + 1,
                    start_seconds=float(item["start_seconds"]),
                    end_seconds=float(item["end_seconds"]),
                    hook_title=item["hook_title"],
                    caption=item["caption"],
                    rationale=item.get("rationale", ""),
                    source_text=item.get("source_text", ""),
                )
            )
        return clips


import json  # noqa: E402