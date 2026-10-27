"""Transcription & Intelligence Agent (``intelligence_agent``).

Transcribes audio, selects 3-5 high-value moments and generates the multi-channel copy.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.artifacts import IntelligenceResult
from app.guardrails import Guardrails
from app.ports import ClipPlanner, Copywriter, Transcriber


class IntelligenceAgent:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        planner: ClipPlanner,
        copywriter: Copywriter,
        guardrails: Guardrails,
        min_clips: int,
        max_clips: int,
    ) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._copywriter = copywriter
        self._guardrails = guardrails
        self._min_clips = min_clips
        self._max_clips = max_clips

    async def run(self, audio_path: Path) -> IntelligenceResult:
        transcript = await self._transcriber.transcribe(audio_path)
        self._guardrails.check_transcript(transcript)

        clips = await self._planner.select_clips(
            transcript,
            min_clips=self._min_clips,
            max_clips=self._max_clips,
        )
        self._guardrails.check_clip_count(len(clips))

        content = await self._copywriter.write(transcript, clips)
        return IntelligenceResult(transcript=transcript, clips=clips, content=content)
