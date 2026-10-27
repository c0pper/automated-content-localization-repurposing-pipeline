"""OpenAI Whisper transcription adapter.

Implements :class:`app.ports.ai.Transcriber` using the OpenAI Whisper API.
Audio is sent to Whisper and a word-level timestamped transcript is returned.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.ports.ai import Transcriber
from app.domain.models import Transcript, TranscriptWord


class OpenAIWhisperTranscriber(Transcriber):
    """Transcribe audio using OpenAI's Whisper model.

    Requires ``OPENAI_API_KEY`` in environment.
    """

    def __init__(self, *, model: str = "whisper-1", language_hint: str | None = None) -> None:
        self._model = model
        self._language_hint = language_hint

    async def transcribe(self, audio: Path, *, language_hint: str | None = None) -> Transcript:
        from openai import AsyncOpenAI  # type: ignore[no-redef]

        client = AsyncOpenAI()
        effective_language = language_hint or self._language_hint

        with audio.open("rb") as f:
            transcript = await client.audio.transcriptions.create(
                model=self._model,
                file=f,
                language=effective_language if effective_language else None,
                response_format="verbose_json",
            )

        words: list[TranscriptWord] = []
        for w in transcript.get("words", []):
            words.append(
                TranscriptWord(
                    text=w["word"],
                    start=round(float(w["start"]), 2),
                    end=round(float(w["end"]), 2),
                )
            )

        return Transcript(
            language=transcript.get("language", effective_language or "en") or "en",
            language_confidence=float(transcript.get("language_probability", 1.0)),
            duration_seconds=float(transcript.get("duration", 0.0)),
            words=words,
        )