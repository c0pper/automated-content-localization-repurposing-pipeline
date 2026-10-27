"""Pipeline orchestrator.

Owns job state transitions and budget accounting; agents stay stateless and typed.
"""

from __future__ import annotations

import logging

from app.agents.delivery_agent import DeliveryAgent
from app.agents.ingest_agent import IngestAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.agents.localization_agent import LocalizationAgent
from app.agents.video_editor_agent import VideoEditorAgent
from app.domain.enums import JobStage, JobStatus
from app.domain.errors import GuardrailViolation, UnknownJobError
from app.domain.models import Job
from app.guardrails import Guardrails
from app.ports import JobRepository

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        repository: JobRepository,
        guardrails: Guardrails,
        ingest: IngestAgent,
        intelligence: IntelligenceAgent,
        editor: VideoEditorAgent,
        localization: LocalizationAgent,
        delivery: DeliveryAgent,
    ) -> None:
        self._repository = repository
        self._guardrails = guardrails
        self._ingest = ingest
        self._intelligence = intelligence
        self._editor = editor
        self._localization = localization
        self._delivery = delivery

    async def run(self, job_id: str) -> Job:
        job = await self._repository.get(job_id)
        if job is None:
            raise UnknownJobError(job_id)

        if job.status is JobStatus.COMPLETED:
            return job

        job.status = JobStatus.PROCESSING
        job.error = None
        await self._enter_stage(job, JobStage.INGEST)

        try:
            ingested = await self._ingest.run(job)
            minutes = ingested.probe.duration_seconds / 60
            self._guardrails.check_budget(job, additional_minutes=minutes)
            job.usage.input_minutes = round(minutes, 3)
            await self._save(job)

            await self._enter_stage(job, JobStage.INTELLIGENCE)
            intelligence = await self._intelligence.run(ingested.audio_path)
            characters = len(intelligence.transcript.text)
            self._guardrails.check_budget(job, additional_characters=characters)
            job.usage.characters += characters
            job.content = intelligence.content
            await self._save(job)

            await self._enter_stage(job, JobStage.VIDEO)
            edited = await self._editor.run(
                job,
                source_path=ingested.source_path,
                transcript=intelligence.transcript,
                clips=intelligence.clips,
            )
            job.segments = [edited_clip.clip for edited_clip in edited]
            await self._save(job)

            await self._enter_stage(job, JobStage.LOCALIZATION)
            # Pre-flight before paying for translation/TTS: source text is processed once
            # per target language. The actual translated character count is reconciled below.
            estimated_characters = len(intelligence.transcript.text) * len(job.target_languages)
            self._guardrails.check_budget(job, additional_characters=estimated_characters)
            localized = await self._localization.run(
                job,
                edited=edited,
                transcript=intelligence.transcript,
            )
            self._guardrails.check_budget(job, additional_characters=localized.characters)
            job.usage.characters += localized.characters
            for segment in job.segments:
                segment.localized_assets = localized.assets.get(segment.segment_id, {})
            await self._save(job)

            await self._enter_stage(job, JobStage.DELIVERY)
            await self._delivery.run(job, edited=edited, localized=localized)

            job.status = JobStatus.COMPLETED
            job.stage = None
            await self._save(job)
            logger.info("Job %s completed", job.job_id)
            return job

        except GuardrailViolation as exc:
            logger.warning("Job %s blocked by guardrail %s: %s", job.job_id, exc.code, exc)
            job.status = JobStatus.FAILED
            job.error = f"{exc.code}: {exc}"
            await self._save_quietly(job)
            return job

        except Exception as exc:  # noqa: BLE001 - failures must be recorded per job
            logger.exception("Job %s failed", job.job_id)
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            await self._save_quietly(job)
            return job

    async def _enter_stage(self, job: Job, stage: JobStage) -> None:
        job.stage = stage
        await self._save(job)
        logger.info("Job %s -> %s", job.job_id, stage.value)

    async def _save(self, job: Job) -> None:
        await self._repository.save(job)

    async def _save_quietly(self, job: Job) -> None:
        try:
            await self._repository.save(job)
        except Exception:  # noqa: BLE001 - never mask the original failure
            logger.exception("Could not persist failure state for job %s", job.job_id)
