"""Dataclasses exchanged between pipeline stages.

These are internal artifacts and deliberately kept out of the public ``Job`` schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.models import (
    ClipCandidate,
    ContentBundle,
    MediaProbe,
    Segment,
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


@dataclass(frozen=True, slots=True)
class EditedClip:
    segment: Segment
    candidate: ClipCandidate
    path: Path


@dataclass(frozen=True, slots=True)
class LocalizationResult:
    assets: dict[int, dict[str, str]]
    characters: int


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    links: list[str]
    files: dict[str, str]
