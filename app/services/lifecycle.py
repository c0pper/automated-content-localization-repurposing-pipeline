"""Cancellation and explicit retry."""

from __future__ import annotations

from app.domain.enums import JobStage, JobStatus
from app.domain.errors import ApiError
from app.domain.models import Job
from app.ports import Clock, LeaseStore, ObjectStore, TaskQueue
from app.services.cost import CostService
from app.services.events import EventService
from app.services.workspace import WorkspaceService

_NON_RETRYABLE = {
    "insufficient_job_budget",
    "invalid_input",
    "unsupported_media_format",
    "source_target_conflict",
    "quality_floor_not_met",
    "invalid_selection",
    "rate_missing",
    "rate_unit_mismatch",
}


class JobLifecycleService:
    def __init__(
        self,
        *,
        repository,
        queue: TaskQueue,
        leases: LeaseStore,
        store: ObjectStore,
        cost: CostService,
        events: EventService,
        workspaces: WorkspaceService,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._leases = leases
        self._store = store
        self._cost = cost
        self._events = events
        self._workspaces = workspaces
        self._clock = clock

    async def cancel(self, job: Job) -> Job:
        if job.status not in {
            JobStatus.RECEIVED,
            JobStatus.PROCESSING,
            JobStatus.AWAITING_SELECTION,
        }:
            raise ApiError(409, "invalid_state", "Only an active Job can be cancelled")

        job.cancel_requested = True
        if job.status is JobStatus.PROCESSING and job.stage is not None:
            # The orchestrator observes the flag between stages and before paid calls.
            await self._repository.save(job)
            await self._events.emit(job, "cancel_requested", stage=job.stage)
            return job

        await self._finalize_cancel(job)
        return job

    async def finalize_cancel(self, job: Job) -> None:
        await self._finalize_cancel(job)

    async def _finalize_cancel(self, job: Job) -> None:
        if job.status is JobStatus.PROCESSING:
            job.transition_to(JobStatus.CANCELLED)
        else:
            job.transition_to(JobStatus.CANCELLED)
        job.stage = None
        job.expires_at = None
        await self._prune_incomplete_localized(job)
        await self._repository.save(job)
        await self._events.emit(job, "cancelled")
        await self._leases.release(job.workspace_id, job.job_id)

    async def _prune_incomplete_localized(self, job: Job) -> None:
        kept = []
        for localized in job.localized_clips:
            if localized.video_asset_key and localized.status.value == "completed":
                kept.append(localized)
                continue
            if localized.video_asset_key:
                await self._store.delete(localized.video_asset_key)
            if localized.audio_asset_key:
                await self._store.delete(localized.audio_asset_key)
        job.localized_clips = kept
        for clip in job.segments:
            clip.localized_assets = {
                language: url
                for language, url in clip.localized_assets.items()
                if any(
                    item.segment_id == clip.segment_id
                    and item.language == language
                    and item.status.value == "completed"
                    for item in job.localized_clips
                )
            }

    async def retry(self, job: Job) -> Job:
        if job.status is not JobStatus.FAILED:
            raise ApiError(409, "not_retryable", "Only a FAILED Job can be retried")
        if not job.retryable or job.error_code in _NON_RETRYABLE:
            raise ApiError(
                409,
                "not_retryable",
                "This failure is not retryable",
                details={"code": job.error_code},
            )
        if job.error_code == "workspace_budget_exceeded":
            if await self._workspaces.remaining_budget() <= 0:
                raise ApiError(
                    409,
                    "not_retryable",
                    "The Workspace Budget is still exhausted",
                    details={"code": job.error_code},
                )
        if job.error_code == "voice_profile_missing":
            if await self._workspaces.get_voice_profile() is None:
                raise ApiError(
                    409,
                    "not_retryable",
                    "The Voice Profile is still missing",
                    details={"code": job.error_code},
                )

        job.transition_to(JobStatus.PROCESSING)
        job.stage = self._resume_stage(job)
        job.error = None
        job.error_code = None
        job.error_message = None
        job.retryable = False
        job.cancel_requested = False
        await self._repository.save(job)
        await self._events.emit(job, "retry_requested", stage=job.stage)
        await self._queue.enqueue(job.job_id)
        return job

    @staticmethod
    def _resume_stage(job: Job) -> JobStage | None:
        if JobStage.VIDEO in job.completed_stages:
            return JobStage.LOCALIZATION
        if JobStage.SCORING in job.completed_stages:
            return JobStage.VIDEO
        if JobStage.INTELLIGENCE in job.completed_stages:
            return JobStage.SCORING
        if JobStage.INGEST in job.completed_stages:
            return JobStage.INTELLIGENCE
        return JobStage.INGEST
