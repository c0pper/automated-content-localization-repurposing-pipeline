"""Ingestion & Preprocessing Agent (``ingest_agent``).

Pulls the raw asset, validates it against guardrails and extracts a transcription-ready
audio track. Remote URLs go through the SSRF-safe fetcher; object sources are read from
the Silo/local store under the ``uploads/`` prefix.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from app.agents.base import workspace_for
from app.domain.artifacts import IngestResult
from app.domain.errors import GuardrailViolation
from app.domain.models import Job
from app.guardrails import Guardrails
from app.ports import MediaProcessor, ObjectStore
from app.security.fetch import SafeRemoteFetcher
from app.security.urls import validate_object_key


class IngestAgent:
    def __init__(
        self,
        *,
        media: MediaProcessor,
        store: ObjectStore,
        guardrails: Guardrails,
        workspace_root: Path,
        fetcher: SafeRemoteFetcher | None = None,
        allow_local_files: bool = True,
    ) -> None:
        self._media = media
        self._store = store
        self._guardrails = guardrails
        self._workspace_root = workspace_root
        self._fetcher = fetcher
        self._allow_local_files = allow_local_files

    async def run(self, job: Job) -> IngestResult:
        source = job.source
        if source is None:
            raise GuardrailViolation("invalid_input", "The Job has no source")

        workspace = workspace_for(self._workspace_root, job.job_id)
        if source.type == "object":
            key = source.key or ""
            validate_object_key(key)
            suffix = Path(key).suffix.lower() or ".mp4"
            source_path = workspace / f"source{suffix}"
            await self._store.get(key, source_path)
        else:
            url = source.url or ""
            suffix = Path(urlsplit(url).path).suffix.lower() or ".mp4"
            source_path = workspace / f"source{suffix}"
            if url.lower().startswith(("http://", "https://")):
                if self._fetcher is None:
                    raise GuardrailViolation(
                        "unsafe_source", "Remote fetching is not configured"
                    )
                await self._fetcher.fetch(url, source_path)
            elif self._allow_local_files:
                await self._store.fetch(url, source_path)
            else:
                raise GuardrailViolation(
                    "unsafe_source", "Only HTTP(S) source URLs are accepted in production"
                )

        probe = await self._media.probe(source_path)
        self._guardrails.check_media(probe)
        audio = await self._media.extract_audio(source_path, workspace / "audio.wav")
        return IngestResult(probe=probe, source_path=source_path, audio_path=audio)
