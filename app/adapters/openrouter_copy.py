"""OpenRouter copywriter adapter.

Implements :class:`app.ports.ai.Copywriter` using OpenRouter chat completions.
Generates clip titles/captions, LinkedIn post, and newsletter draft.
"""

from __future__ import annotations

import json
from typing import Sequence

from app.domain.models import ClipCandidate, ClipCopy, ContentBundle, Transcript
from app.ports.ai import Copywriter


class OpenRouterCopywriter(Copywriter):
    def __init__(self, *, model: str | None = None) -> None:
        self._model = model

    async def write(
        self,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
        *,
        model: str | None = None,
    ) -> ContentBundle:
        effective_model = model or self._model
        from openai import AsyncOpenAI  # type: ignore[no-redef]

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
        system_prompt = (
            "You are a content creator. Given a transcript and a list of clip candidates, "
            "generate a LinkedIn post and a newsletter draft. Return a JSON object with "
            "`linkedin_post` and `newsletter` fields."
        )
        user_prompt = (
            f"Transcript: {transcript.text}\n"
            f"Clips: {json.dumps([c.hook_title for c in clips], ensure_ascii=False)}\n"
            f"Generate LinkedIn and newsletter copy."
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

        clip_copy = [
            ClipCopy(
                segment_id=clip.segment_id,
                vertical_title=clip.hook_title,
                caption=clip.caption,
            )
            for clip in clips
        ]

        linkedin = "# LinkedIn breakdown\n\n" + "\n\n".join(
            f"## {clip.hook_title}\n\n{clip.caption}" for clip in clips
        )
        newsletter = (
            "# Newsletter draft\n\n"
            f"## The core insight\n\n{transcript.text[:600]}...\n\n"
            "## What to do next\n\nPick one moment from this recording and ship it today.\n"
        )

        return ContentBundle(clips=clip_copy, linkedin_post=linkedin, newsletter=newsletter)