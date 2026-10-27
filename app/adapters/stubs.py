"""Deterministic stand-ins for paid AI/media APIs.

The stub backend lets the whole pipeline run locally (and in tests) without OpenAI,
OpenRouter, Jev, ElevenLabs, Sync Labs or ffmpeg. Real adapters implement the same ports.
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
from app.ports.ai import VoiceSynthesisResult

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

_RATIONALE = (
    "The contrarian hook lands in the first line and the clip stands alone without the "
    "surrounding recording."
)


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
        self.burns: list[dict[str, object]] = []

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

    async def burn_captions(self, video: Path, captions: str, destination: Path) -> Path:
        self.burns.append({"video": video, "captions": captions})
        await _placeholder(video, destination)
        destination.with_suffix(".srt").write_text(captions, encoding="utf-8")
        return destination

    async def replace_audio(self, video: Path, audio: Path, destination: Path) -> Path:
        return await _placeholder(video, destination)


class StubTranscriber:
    def __init__(self, *, duration_seconds: float = 600.0, word_duration: float = 0.4) -> None:
        self._duration_seconds = duration_seconds
        self._word_duration = word_duration

    async def transcribe(self, audio: Path, *, language_hint: str | None = None) -> Transcript:
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

        return Transcript(
            language=language_hint or "en",
            language_confidence=1.0 if language_hint else 0.99,
            duration_seconds=self._duration_seconds,
            words=words,
        )


class StubClipPlanner:
    def __init__(self, *, clip_seconds: float = 45.0) -> None:
        self._clip_seconds = clip_seconds
        self.calls = 0

    async def select_clips(
        self,
        transcript: Transcript,
        *,
        min_clips: int,
        max_clips: int,
        model: str | None = None,
    ) -> list[ClipCandidate]:
        self.calls += 1
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
                    rationale=_RATIONALE,
                    source_text=transcript.text_between(
                        start, min(start + clip_length, transcript.duration_seconds)
                    ),
                )
            )
        return clips


class StubClipScorer:
    """Deterministic 0-4 distributions that comfortably clear the default floor."""

    def __init__(
        self,
        *,
        expected: tuple[float, float, float, float] = (3.6, 3.2, 3.0, 3.4),
    ) -> None:
        self._expected = expected
        self.calls = 0

    async def score(
        self,
        candidate: ClipCandidate,
        *,
        model: str | None = None,
    ) -> dict[str, list[float]]:
        self.calls += 1
        return {
            "hook_strength": _distribution(self._expected[0]),
            "standalone_clarity": _distribution(self._expected[1]),
            "emotional_payoff": _distribution(self._expected[2]),
            "business_fit": _distribution(self._expected[3]),
        }


class StubCopywriter:
    async def write(
        self,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
        *,
        model: str | None = None,
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

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def translate(
        self,
        text: str,
        target_language: str,
        *,
        model: str | None = None,
    ) -> str:
        self.calls.append((target_language, text))
        return f"[{target_language}] {text}"


class SilentVoiceSynthesizer:
    async def synthesize(
        self,
        text: str,
        target_language: str,
        destination: Path,
        *,
        voice_id: str,
        model: str | None = None,
    ) -> VoiceSynthesisResult:
        duration = min(max(len(text) / 15.0, 1.0), 300.0)
        await asyncio.to_thread(_write_silence, destination, duration)
        return VoiceSynthesisResult(
            audio_path=destination,
            characters=len(text),
            alignment=_alignment(text, duration),
        )


class StubLipSyncer:
    def __init__(self) -> None:
        self.calls = 0

    async def sync(
        self,
        video: Path,
        audio: Path,
        destination: Path,
        target_language: str,
    ) -> Path:
        self.calls += 1
        await asyncio.to_thread(shutil.copy2, video, destination)
        return destination


def _distribution(expected: float) -> list[float]:
    """A five-bucket distribution with the requested expected value."""
    lower = min(max(int(expected), 0), 3)
    weight = expected - lower
    distribution = [0.0] * 5
    distribution[lower] = 1.0 - weight
    distribution[lower + 1] = weight
    return distribution


def _alignment(text: str, duration: float) -> list[TranscriptWord]:
    tokens = text.split()
    if not tokens:
        return []
    step = duration / len(tokens)
    return [
        TranscriptWord(
            text=token,
            start=round(index * step, 2),
            end=round((index + 1) * step, 2),
        )
        for index, token in enumerate(tokens)
    ]


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
