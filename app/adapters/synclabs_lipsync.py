"""Sync Labs lip-sync adapter.

Implements :class:`app.ports.ai.LipSyncer` using Sync Labs.
Requires ``SYNCLABS_API_KEY`` in environment.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.ports.ai import LipSyncer


class SyncLabsLipSyncer(LipSyncer):
    def __init__(self, *, model: str | None = None) -> None:
        self._model = model

    async def sync(
        self,
        video: Path,
        audio: Path,
        destination: Path,
        target_language: str,
    ) -> Path:
        import httpx
        headers = {
            "x-api-key": __import__("os").environ.get("SYNCLABS_API_KEY", ""),
            "Content-Type": "multipart/form-data",
        }
        url = "https://api.synclabs.so/v2/generate"
        with open(video, "rb") as video_file, open(audio, "rb") as audio_file:
            files = {
                "video": video_file,
                "audio": audio_file,
            }
            data = {
                "model": self._model or "v2",
                "language": target_language,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
                destination.write_bytes(response.content)
        return destination