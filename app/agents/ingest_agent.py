"""Ingestion & Preprocessing Agent (``ingest_agent``).

Pulls the raw asset, validates it against guardrails and extracts a transcription-ready
audio track.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from app.agents.base import workspace_for
from app.domain.artifacts import IngestResult
from app.domain.models import Job
from app.guardrails import Guardrails
from app.ports import MediaProcessor, ObjectStore


class IngestAgent:
    def __init__(
        self,
        *,
        media: MediaProcessor,
        store: ObjectStore,
        guardrails: Guardrails,
        workspace_root: Path,
    ) -> None:
        self._media = media
        self._store = store
        self._guardrails = guardrails
        self._workspace_root = workspace_root

    async def run(self, job: Job) -> IngestResult:
        guardrails = self._guardrails
        guardrails.check_submission(job.input_url, job.target_languages)

        workspace = workspace_for(self._workspace_root, job.job_id)
        suffix = Path(urlsplit(job.input_url).path).suffix.lower() or ".mp4"
        source = await self._store.fetch(job.input_url, workspace / f"source{suffix}")

        probe = await self._media.probe(source)
        guardrails.check_media(probe)

        audio = await self._media.extract_audio(source, workspace / "audio.wav")
        return IngestResult(probe=probe, source_path=source, audio_path=audio)
