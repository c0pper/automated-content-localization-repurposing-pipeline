"""Build the SRT caption track burned into each vertical clip."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import TranscriptWord

_MAX_WORDS = 6
_MAX_SECONDS = 3.5


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(
    words: Sequence[TranscriptWord],
    *,
    clip_start: float,
    clip_end: float,
) -> str:
    """Group words into short kinetic-caption cues relative to the clip start."""
    selected = [word for word in words if word.end > clip_start and word.start < clip_end]

    cues: list[list[TranscriptWord]] = []
    current: list[TranscriptWord] = []
    for word in selected:
        if current:
            cue_duration = word.end - current[0].start
            if len(current) >= _MAX_WORDS or cue_duration > _MAX_SECONDS:
                cues.append(current)
                current = []
        current.append(word)
    if current:
        cues.append(current)

    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        start = max(cue[0].start, clip_start) - clip_start
        end = min(cue[-1].end, clip_end) - clip_start
        end = max(end, start + 0.2)
        text = " ".join(word.text for word in cue).strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}"
        )

    return "\n\n".join(blocks) + ("\n" if blocks else "")
