"""AI provider ports (Whisper, OpenRouter, Jev, ElevenLabs, Sync Labs, ...)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.domain.models import ClipCandidate, ContentBundle, Transcript, TranscriptWord


class Transcriber(Protocol):
    async def transcribe(self, audio: Path, *, language_hint: str | None = None) -> Transcript:
        """Return a timestamped, word-level transcript."""
        ...


class ClipPlanner(Protocol):
    async def select_clips(
        self,
        transcript: Transcript,
        *,
        min_clips: int,
        max_clips: int,
        model: str | None = None,
    ) -> list[ClipCandidate]:
        """Pick the highest-value short-form moments in the transcript."""
        ...


class Copywriter(Protocol):
    async def write(
        self,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
        *,
        model: str | None = None,
    ) -> ContentBundle:
        """Generate clip titles/captions, a LinkedIn post and a newsletter draft."""
        ...


class ClipScorer(Protocol):
    async def score(
        self,
        candidate: ClipCandidate,
        *,
        model: str | None = None,
    ) -> dict[str, list[float]]:
        """Return four 0-4 probability distributions for one Clip Candidate."""
        ...


class Translator(Protocol):
    async def translate(
        self,
        text: str,
        target_language: str,
        *,
        model: str | None = None,
    ) -> str:
        """Translate text while preserving domain nuance."""
        ...


@dataclass(frozen=True, slots=True)
class VoiceSynthesisResult:
    audio_path: Path
    characters: int
    alignment: list[TranscriptWord] | None = field(default=None)


class VoiceSynthesizer(Protocol):
    async def synthesize(
        self,
        text: str,
        target_language: str,
        destination: Path,
        *,
        voice_id: str,
        model: str | None = None,
    ) -> VoiceSynthesisResult:
        """Render localized speech and return the provider's alignment, if any."""
        ...


class LipSyncer(Protocol):
    async def sync(
        self,
        video: Path,
        audio: Path,
        destination: Path,
        target_language: str,
    ) -> Path:
        """Align lip movement with a localized audio track."""
        ...
