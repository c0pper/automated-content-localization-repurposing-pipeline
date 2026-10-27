"""Dataclasses exchanged between pipeline stages.

These are internal artifacts and deliberately kept out of the public ``Job`` schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.models import (
    Clip,
    ClipCandidate,
    ContentBundle,
    LocalizedClip,
    MediaProbe,
    SourceLanguage,
    Transcript,
)


@dataclass(frozen=True, slots=True)
class IngestResult:
    probe: MediaProbe
    source_path: Path
    audio_path: Path


@dataclass(frozen=True, slots=True)
class IntelligenceResult:
    transcript: Transcript
    clips: list[ClipCandidate]
    content: ContentBundle
    source_language: SourceLanguage


@dataclass(frozen=True, slots=True)
class EditedClip:
    clip: Clip
    candidate: ClipCandidate
    path: Path
    master_path: Path


@dataclass(frozen=True, slots=True)
class LocalizationResult:
    assets: dict[int, dict[str, str]]
    characters: int
    localized_clips: list[LocalizedClip]


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    links: list[str]
    files: dict[str, str]
