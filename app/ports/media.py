"""Media processing port (FFmpeg, Shotstack, cloud render workers, ...)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain.models import MediaProbe


class MediaProcessor(Protocol):
    async def probe(self, source: Path) -> MediaProbe:
        """Inspect duration, dimensions and audio presence."""
        ...

    async def extract_audio(self, source: Path, destination: Path) -> Path:
        """Extract a mono 16 kHz audio track suitable for transcription."""
        ...

    async def render_vertical_clip(
        self,
        source: Path,
        destination: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        captions: str | None = None,
    ) -> Path:
        """Cut, re-frame to 9:16 and optionally burn in an SRT caption track."""
        ...

    async def burn_captions(
        self,
        video: Path,
        captions: str,
        destination: Path,
    ) -> Path:
        """Burn an SRT caption track into an existing rendered video."""
        ...

    async def replace_audio(self, video: Path, audio: Path, destination: Path) -> Path:
        """Mux a localized audio track onto a rendered clip."""
        ...
