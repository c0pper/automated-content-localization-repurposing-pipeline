"""Deterministic stand-ins for paid AI/media APIs.

The stub backend lets the whole pipeline run locally (and in tests) without OpenAI,
DeepL, ElevenLabs, Sync Labs or ffmpeg. Real adapters implement the same ports.
"""

from __future__ import annotations

import asyncio
import shutil
import wave
from collections.abc import Sequence
from pathlib import Path

from app.domain.models import (
    ClipCandidate,
    ClipCopy,
    ContentBundle,
    MediaProbe,
    Transcript,
    TranscriptWord,
)

_SCRIPT = (
    "Most B2B SaaS ads fail because they target everyone and speak to no one. "
    "The fix is a narrow promise, a sharp hook, and proof within the first three seconds. "
    "Here is the framework we use: pick one painful moment, show the cost of staying there, "
    "then demonstrate the smallest believable step forward. Repeat the winning angle across "
    "every channel, measure hold rate, and cut anything that does not earn attention. "
    "That is how a single long-form recording becomes a week of demand."
)

_HOOKS = [
    (
        "Why 90% of B2B SaaS Ads Fail",
        "Stop wasting budget on broad audiences. Here is the narrow promise that converts.",
    ),
    (
        "The 3-Second Hook Framework",
        "Proof inside the first three seconds beats clever copy every time.",
    ),
    (
        "Turn One Recording Into a Week of Content",
        "One long-form asset, five sharp clips, every channel covered.",
    ),
    (
        "Cut Anything That Does Not Earn Attention",
        "Hold rate is the only metric that matters when you repurpose content.",
    ),
    (
        "The Smallest Believable Step Forward",
        "Show the cost of staying put, then remove every excuse to start.",
    ),
]


class StubMediaProcessor:
    """Writes placeholder artifacts so downstream stages have real files to move around."""

    def __init__(
        self,
        *,
        duration_seconds: float = 600.0,
        width: int = 1920,
        height: int = 1080,
        has_audio: bool = True,
    ) -> None:
        self._duration_seconds = duration_seconds
        self._width = width
        self._height = height
        self._has_audio = has_audio

    async def probe(self, source: Path) -> MediaProbe:
        return MediaProbe(
            duration_seconds=self._duration_seconds,
            width=self._width,
            height=self._height,
            has_audio=self._has_audio,
            container=source.suffix.lstrip(".") or None,
        )

    async def extract_audio(self, source: Path, destination: Path) -> Path:
        return await _placeholder(source, destination)

    async def render_vertical_clip(
        self,
        source: Path,
        destination: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        captions: str | None = None,
    ) -> Path:
        await _placeholder(source, destination)
        if captions:
            destination.with_suffix(".srt").write_text(captions, encoding="utf-8")
        return destination

    async def replace_audio(self, video: Path, audio: Path, destination: Path) -> Path:
        return await _placeholder(video, destination)


class StubTranscriber:
    def __init__(self, *, duration_seconds: float = 600.0, word_duration: float = 0.4) -> None:
        self._duration_seconds = duration_seconds
        self._word_duration = word_duration

    async def transcribe(self, audio: Path) -> Transcript:
        tokens = _SCRIPT.split()
        words: list[TranscriptWord] = []
        timestamp = 0.0
        index = 0

        while timestamp < self._duration_seconds:
            end = min(timestamp + self._word_duration * 0.9, self._duration_seconds)
            words.append(
                TranscriptWord(
                    text=tokens[index % len(tokens)],
                    start=round(timestamp, 2),
                    end=round(end, 2),
                )
            )
            timestamp += self._word_duration
            index += 1

        return Transcript(language="en", duration_seconds=self._duration_seconds, words=words)


class StubClipPlanner:
    def __init__(self, *, clip_seconds: float = 45.0) -> None:
        self._clip_seconds = clip_seconds

    async def select_clips(
        self,
        transcript: Transcript,
        *,
        min_clips: int,
        max_clips: int,
    ) -> list[ClipCandidate]:
        count = max(min_clips, min(max_clips, 3))
        if count <= 0 or transcript.duration_seconds <= 0:
            return []

        clip_length = min(self._clip_seconds, transcript.duration_seconds)
        span = max(transcript.duration_seconds - clip_length, 0.0)
        step = span / count if count > 1 else 0.0

        clips: list[ClipCandidate] = []
        for index in range(count):
            start = index * step
            hook, caption = _HOOKS[index % len(_HOOKS)]
            clips.append(
                ClipCandidate(
                    segment_id=index + 1,
                    start_seconds=round(start, 2),
                    end_seconds=round(min(start + clip_length, transcript.duration_seconds), 2),
                    hook_title=hook,
                    caption=caption,
                    rationale="stub: evenly spaced high-emotion windows",
                )
            )
        return clips


class StubCopywriter:
    async def write(
        self,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
    ) -> ContentBundle:
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


class EchoTranslator:
    """Prefixes the text so localized assets are visibly distinct in local runs."""

    async def translate(self, text: str, target_language: str) -> str:
        return f"[{target_language}] {text}"


class SilentVoiceSynthesizer:
    async def synthesize(self, text: str, target_language: str, destination: Path) -> Path:
        duration = min(max(len(text) / 15.0, 1.0), 300.0)
        await asyncio.to_thread(_write_silence, destination, duration)
        return destination


class StubLipSyncer:
    async def sync(
        self,
        video: Path,
        audio: Path,
        destination: Path,
        target_language: str,
    ) -> Path:
        await asyncio.to_thread(shutil.copy2, video, destination)
        return destination


async def _placeholder(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = f"stub media derived from {source.name}\n".encode()
    await asyncio.to_thread(destination.write_bytes, payload)
    return destination


def _write_silence(destination: Path, duration_seconds: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16_000
    frames = int(sample_rate * duration_seconds)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
