"""FFmpeg media backend.

Not exercised by the default stub backend. Requires ``ffmpeg`` and ``ffprobe`` on PATH.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.domain.errors import MediaProcessingError
from app.domain.models import MediaProbe


class FFmpegMediaProcessor:
    def __init__(self, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe

    async def probe(self, source: Path) -> MediaProbe:
        output = await self._run(
            [
                self._ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(source),
            ]
        )
        data = json.loads(output)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration = float(data.get("format", {}).get("duration", 0.0))
        return MediaProbe(
            duration_seconds=duration,
            width=int(video["width"]) if video and video.get("width") else None,
            height=int(video["height"]) if video and video.get("height") else None,
            has_audio=audio is not None,
            container=data.get("format", {}).get("format_name"),
        )

    async def extract_audio(self, source: Path, destination: Path) -> Path:
        await self._run(
            [
                self._ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )
        return destination

    async def render_vertical_clip(
        self,
        source: Path,
        destination: Path,
        *,
        start_seconds: float,
        end_seconds: float,
        captions: str | None = None,
    ) -> Path:
        filters = [
            "crop='min(iw,ih*9/16)':ih:'(iw-min(iw,ih*9/16))/2':0",
            "scale=1080:1920:flags=lanczos",
        ]

        if captions:
            subtitle_path = destination.with_suffix(".srt")
            subtitle_path.write_text(captions, encoding="utf-8")
            escaped = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
            filters.append(
                f"subtitles='{escaped}':force_style='FontSize=18,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'"
            )

        await self._run(
            [
                self._ffmpeg,
                "-y",
                "-ss",
                f"{start_seconds:.3f}",
                "-to",
                f"{end_seconds:.3f}",
                "-i",
                str(source),
                "-vf",
                ",".join(filters),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )
        return destination

    async def replace_audio(self, video: Path, audio: Path, destination: Path) -> Path:
        await self._run(
            [
                self._ffmpeg,
                "-y",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-shortest",
                str(destination),
            ]
        )
        return destination

    async def _run(self, args: list[str]) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise MediaProcessingError(f"Executable not found: {args[0]}") from exc

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise MediaProcessingError(f"{args[0]} failed ({process.returncode}): {detail}")
        return stdout.decode("utf-8", errors="replace")
