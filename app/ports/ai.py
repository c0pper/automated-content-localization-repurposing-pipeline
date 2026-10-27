"""AI provider ports (Whisper, Claude/GPT, DeepL, ElevenLabs, Sync Labs, ...)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.domain.models import ClipCandidate, ContentBundle, Transcript


class Transcriber(Protocol):
    async def transcribe(self, audio: Path) -> Transcript:
        """Return a timestamped, word-level transcript."""
        ...


class ClipPlanner(Protocol):
    async def select_clips(
        self,
        transcript: Transcript,
        *,
        min_clips: int,
        max_clips: int,
    ) -> list[ClipCandidate]:
        """Pick the highest-value short-form moments in the transcript."""
        ...


class Copywriter(Protocol):
    async def write(
        self,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
    ) -> ContentBundle:
        """Generate clip titles/captions, a LinkedIn post and a newsletter draft."""
        ...


class Translator(Protocol):
    async def translate(self, text: str, target_language: str) -> str:
        """Translate text while preserving domain nuance."""
        ...


class VoiceSynthesizer(Protocol):
    async def synthesize(self, text: str, target_language: str, destination: Path) -> Path:
        """Render localized speech with the creator's cloned voice."""
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
