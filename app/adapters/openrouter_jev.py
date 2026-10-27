"""OpenRouter Jev scoring adapter.

Implements :class:`app.ports.ai.ClipScorer` using OpenRouter Decisions API.
Returns four 0-4 probability distributions for one Clip Candidate per Jev spec.
"""

from __future__ import annotations

from typing import Mapping

from app.domain.models import ClipCandidate
from app.ports.ai import ClipScorer


class OpenRouterClipScorer(ClipScorer):
    def __init__(
        self,
        *,
        model: str,
        allowlist: Mapping[str, str] | None = None,
    ) -> None:
        self._default_model = model
        self._allowlist = dict(allowlist or {})

    async def score(
        self,
        candidate: ClipCandidate,
        *,
        model: str | None = None,
    ) -> dict[str, list[float]]:
        effective_model = model or self._default_model
        if effective_model not in self._allowlist and model is not None:
            raise ValueError(f"Jev model override not allowed: {effective_model}")

        from openai import AsyncOpenAI  # type: ignore[no-redef]

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
        system_prompt = (
            "You are a decision engine. Given a Clip Candidate (start/end seconds, "
            "hook_title, caption, rationale, source_text), produce four 0-4 probability "
            "distributions: hook_strength, standalone_clarity, emotional_payoff, "
            "business_fit. Each is a list of 5 floats summing to 1.0 with the "
            "specified expected value."
        )
        user_prompt = (
            f"Clip start: {candidate.start_seconds}, end: {candidate.end_seconds}\n"
            f"Hook: {candidate.hook_title}\n"
            f"Caption: {candidate.caption}\n"
            f"Rationale: {candidate.rationale}\n"
            f"Source: {candidate.source_text[:200]}\n"
            f"Jev expected values: hook_strength={candidate.score_breakdown.hook_strength}, "
            f"standalone_clarity={candidate.score_breakdown.standalone_clarity}, "
            f"emotional_payoff={candidate.score_breakdown.emotional_payoff}, "
            f"business_fit={candidate.score_breakdown.business_fit}"
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

        # Validate shapes and sum to 1.0 (Naïve enforcement)
        results: dict[str, list[float]] = {}
        for key in ("hook_strength", "standalone_clarity", "emotional_payoff", "business_fit"):
            dist = data.get(key, [])
            if len(dist) != 5:
                dist = [0.2, 0.2, 0.2, 0.2, 0.2]
            # Naïve normalization
            total = sum(dist)
            if total <= 0:
                dist = [0.2, 0.2, 0.2, 0.2, 0.2]
                total = 1.0
            results[key] = [float(v) / total for v in dist]
        return results

import json  # noqa: E402