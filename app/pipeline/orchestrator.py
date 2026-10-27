"""Pipeline orchestrator.

Owns job state transitions, concurrency slots, checkpoints, budgets and the Selection
Gate pause. Agents stay stateless and typed; the orchestrator commits every checkpoint.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from app.agents.delivery_agent import DeliveryAgent
from app.agents.ingest_agent import IngestAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.agents.localization_agent import LocalizationAgent
from app.agents.video_editor_agent import VideoEditorAgent
from app.config import Settings
from app.domain.enums import JobStage, JobStatus, NotificationType
from app.domain.errors import (
    CancellationRequested,
    GuardrailViolation,
    UnknownJobError,
)
from app.domain.models import Job
from app.domain.selection import is_empty_selection
from app.ports import Clock, LeaseStore, TaskQueue
from app.services.cost import CostService
from app.services.events import EventService
from app.services.lifecycle import JobLifecycleService
from app.services.notifications import NotificationService
from app.services.review import ReviewService
from app.services.selection import SelectionService
from app.services.workspace import WorkspaceService

logger = logging.getLogger(__name__)

_LEASE_TTL = timedelta(minutes=30)


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        repository,
        queue: TaskQueue,
        leases: LeaseStore,
        cost: CostService,
        events: EventService,
        notifications: NotificationService,
        review: ReviewService,
        selection: SelectionService,
        lifecycle: JobLifecycleService,
        workspaces: WorkspaceService,
        ingest: IngestAgent,
        intelligence: IntelligenceAgent,
        editor: VideoEditorAgent,
        localization: LocalizationAgent,
        delivery: DeliveryAgent,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._leases = leases
        self._cost = cost
        self._events = events
        self._notifications = notifications
        self._review = review
        self._selection = selection
        self._lifecycle = lifecycle
        self._workspaces = workspaces
        self._ingest = ingest
        self._intelligence = intelligence
        self._editor = editor
        self._localization = localization
        self._delivery = delivery
        self._clock = clock
        self._settings = settings

    async def run(self, job_id: str) -> Job:
        job = await self._repository.get(job_id)
        if job is None:
            raise UnknownJobError(job_id)

        if job.status.is_terminal or job.status is JobStatus.AWAITING_SELECTION:
            return job
        if job.status is JobStatus.FAILED:
            return job

        if job.status is JobStatus.RECEIVED:
            acquired = await self._leases.acquire(
                job.workspace_id,
                job.job_id,
                limit=await self._concurrency_limit(job),
                ttl=_LEASE_TTL,
            )
            if not acquired:
                await self._queue.enqueue(job.job_id)
                return job
            job.transition_to(JobStatus.PROCESSING)
            await self._repository.save(job)
        else:
            acquired = await self._leases.acquire(
                job.workspace_id,
                job.job_id,
                limit=await self._concurrency_limit(job),
                ttl=_LEASE_TTL,
            )
            if not acquired:
                await self._queue.enqueue(job.job_id)
                return job

        try:
            return await self._run_job(job)
        except CancellationRequested:
            await self._lifecycle.finalize_cancel(job)
            return await self._repository.get(job.job_id) or job
        except GuardrailViolation as exc:
            await self._fail(job, exc.code, str(exc), retryable=exc.retryable)
            return await self._repository.get(job.job_id) or job
        except Exception as exc:  # noqa: BLE001 - every failure is recorded per job
            logger.exception("Job %s failed", job.job_id)
            await self._fail(
                job,
                "internal_error",
                f"{type(exc).__name__}: {exc}",
                retryable=True,
            )
            return await self._repository.get(job.job_id) or job

    async def _run_job(self, job: Job) -> Job:
        self._check_cancel(job)
        if JobStage.VIDEO not in job.completed_stages:
            await self._run_source_stages(job)
            if job.status is not JobStatus.PROCESSING:
                return job
            await self._selection.open_gate(job)
            return await self._repository.get(job.job_id) or job

        # Base Clips already exist: either localization (or empty selection) then delivery.
        if (
            job.selection is not None
            and not is_empty_selection(job.selection.segment_ids, job.selection.languages)
            and JobStage.LOCALIZATION not in job.completed_stages
        ):
            await self._run_localization(job)
        await self._run_delivery(job)
        return await self._repository.get(job.job_id) or job

    async def _run_source_stages(self, job: Job) -> None:
        if JobStage.INGEST not in job.completed_stages:
            await self._enter_stage(job, JobStage.INGEST)
            ingested = await self._ingest.run(job)
            minutes = ingested.probe.duration_seconds / 60
            job.usage.input_minutes = round(minutes, 3)
            job.source_path = str(ingested.source_path)
            job.mark_stage(JobStage.INGEST)
            await self._complete_stage(job, JobStage.INGEST)

        if JobStage.INTELLIGENCE not in job.completed_stages:
            await self._enter_stage(job, JobStage.INTELLIGENCE)
            if job.source_path is None:
                raise GuardrailViolation(
                    "missing_checkpoint", "The ingest checkpoint is missing"
                )
            intelligence = await self._intelligence.run(
                job,
                audio_path=Path(job.source_path).with_name("audio.wav"),
                duration_seconds=job.usage.input_minutes * 60,
            )
            job.transcript = intelligence.transcript
            job.source_language = intelligence.source_language
            job.content = intelligence.content
            job.candidates = intelligence.clips
            job.mark_stage(JobStage.INTELLIGENCE)
            job.mark_stage(JobStage.SCORING)
            await self._complete_stage(job, JobStage.INTELLIGENCE)
            await self._events.emit(
                job,
                "scored",
                payload={
                    "clips": [
                        {
                            "segment_id": candidate.segment_id,
                            "selection_score": candidate.selection_score,
                        }
                        for candidate in intelligence.clips
                    ]
                },
            )

        if JobStage.VIDEO not in job.completed_stages:
            await self._enter_stage(job, JobStage.VIDEO)
            if job.source_path is None or job.transcript is None:
                raise GuardrailViolation(
                    "missing_checkpoint", "The intelligence checkpoint is missing"
                )
            edited = await self._editor.run(
                job,
                source_path=Path(job.source_path),
                transcript=job.transcript,
                clips=job.candidates,
            )
            job.segments = [item.clip for item in edited]
            job.mark_stage(JobStage.VIDEO)
            await self._complete_stage(job, JobStage.VIDEO)

    async def _run_localization(self, job: Job) -> None:
        await self._enter_stage(job, JobStage.LOCALIZATION)
        profile = await self._workspaces.get_voice_profile()
        if profile is None:
            raise GuardrailViolation(
                "voice_profile_missing",
                "The Workspace has no Voice Profile; localization cannot start",
                retryable=True,
            )

        async def checkpoint(updated: Job) -> None:
            await self._repository.save(updated)

        await self._localization.run(
            job,
            clips=job.segments,
            voice_profile=profile,
            on_checkpoint=checkpoint,
        )
        job.mark_stage(JobStage.LOCALIZATION)
        await self._complete_stage(job, JobStage.LOCALIZATION)

    async def _run_delivery(self, job: Job) -> None:
        await self._enter_stage(job, JobStage.DELIVERY)
        await self._delivery.run(job)
        job.mark_stage(JobStage.DELIVERY)
        raw_token = await self._review.ensure_token(job)
        job.transition_to(JobStatus.COMPLETED)
        job.stage = None
        job.expires_at = None
        job.bundle_frozen = True
        await self._repository.save(job)
        await self._events.emit(job, "bundle_ready", payload={"frozen": True})
        await self._notifications.queue(
            job,
            NotificationType.BUNDLE_READY,
            data={
                "review_url": self._review.review_url(job, raw_token),
                "base_clips": len(job.segments),
                "localized_clips": len(job.localized_clips),
            },
        )
        await self._notifications.dispatch_pending()
        await self._leases.release(job.workspace_id, job.job_id)
        logger.info("Job %s completed", job.job_id)

    async def _fail(self, job: Job, code: str, message: str, *, retryable: bool) -> None:
        if job.status is JobStatus.CANCELLED:
            return
        try:
            job.transition_to(JobStatus.FAILED)
        except Exception:  # noqa: BLE001 - preserve the original failure
            job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        job.error = f"{code}: {message}"
        job.retryable = retryable
        await self._save_quietly(job)
        await self._events.emit(job, "failed", payload={"code": code, "retryable": retryable})
        await self._leases.release(job.workspace_id, job.job_id)
        logger.warning("Job %s failed with %s: %s", job.job_id, code, message)

    async def _enter_stage(self, job: Job, stage: JobStage) -> None:
        self._check_cancel(job)
        job.stage = stage
        await self._repository.save(job)
        await self._events.emit(job, "stage_started", stage=stage)
        logger.info("Job %s -> %s", job.job_id, stage.value)

    async def _complete_stage(self, job: Job, stage: JobStage) -> None:
        job.mark_stage(stage)
        await self._repository.save(job)
        await self._events.emit(job, "stage_completed", stage=stage)

    async def _concurrency_limit(self, job: Job) -> int:
        settings = await self._workspaces.get_settings()
        return max(1, min(settings.max_concurrent_jobs, self._settings.worker_capacity))

    @staticmethod
    def _check_cancel(job: Job) -> None:
        if job.cancel_requested:
            raise CancellationRequested(job.job_id)

    async def _save_quietly(self, job: Job) -> None:
        try:
            await self._repository.save(job)
        except Exception:  # noqa: BLE001 - never mask the original failure
            logger.exception("Could not persist failure state for job %s", job.job_id)
