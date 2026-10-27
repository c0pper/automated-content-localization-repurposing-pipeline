"""Selection Gate: cost matrix, rectangular confirmation and seven-day expiry."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from app.config import Settings
from app.domain.enums import JobStage, JobStatus, NotificationType
from app.domain.errors import ApiError
from app.domain.models import CostCell, Job, Selection
from app.domain.money import format_usd
from app.domain.selection import (
    build_cost_matrix,
    is_empty_selection,
    price_selection,
    validate_selection_shape,
)
from app.ports import Clock, LeaseStore, TaskQueue
from app.services.cost import CostService
from app.services.events import EventService
from app.services.notifications import NotificationService
from app.services.review import ReviewService


class SelectionService:
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
        self._clock = clock
        self._settings = settings
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, job_id: str) -> asyncio.Lock:
        return self._locks.setdefault(job_id, asyncio.Lock())

    def matrix(self, job: Job) -> list[CostCell]:
        return build_cost_matrix(job, rate_card=self._cost.rate_card)

    def projected_total(self, job: Job, matrix: list[CostCell] | None = None) -> int:
        cells = matrix if matrix is not None else self.matrix(job)
        return sum(cell.total_micro_usd for cell in cells)

    async def open_gate(self, job: Job) -> None:
        """Enter AWAITING_SELECTION after Base Clips are ready."""
        job.selection_matrix = self.matrix(job)
        job.projected_total_micro_usd = self.projected_total(job, job.selection_matrix)
        job.expires_at = self._clock.now() + timedelta(days=self._settings.selection_gate_days)
        job.transition_to(JobStatus.AWAITING_SELECTION)
        job.stage = None
        job.mark_stage(JobStage.VIDEO)
        await self._repository.save(job)
        await self._events.emit(
            job,
            "gate_opened",
            payload={
                "expires_at": job.expires_at.isoformat(),
                "projected_total_usd": format_usd(job.projected_total_micro_usd),
            },
        )
        raw_token = await self._review.ensure_token(job)
        await self._repository.save(job)
        await self._notifications.queue(
            job,
            NotificationType.SELECTION_REQUIRED,
            data={
                "review_url": self._review.review_url(job, raw_token),
                "expires_at": job.expires_at.isoformat(),
                "projected_total_usd": format_usd(job.projected_total_micro_usd),
            },
        )
        await self._notifications.dispatch_pending()
        await self._leases.release(job.workspace_id, job.job_id)

    async def gate_payload(self, job: Job) -> dict:
        async with self._lock(job.job_id):
            if await self.expire_if_needed(job):
                raise ApiError(410, "selection_expired", "The Selection Gate has expired")
            if job.status is not JobStatus.AWAITING_SELECTION:
                raise ApiError(
                    409,
                    "invalid_state",
                    "The Job is not awaiting a selection",
                )
            matrix = self.matrix(job)
            job.selection_matrix = matrix
            job.projected_total_micro_usd = self.projected_total(job, matrix)
            return self._gate_payload(job, matrix)

    def _gate_payload(self, job: Job, matrix: list[CostCell]) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "expires_at": job.expires_at.isoformat() if job.expires_at else None,
            "source_language": (
                {
                    "code": job.source_language.code,
                    "origin": job.source_language.origin.value,
                    "detected_code": job.source_language.detected_code,
                }
                if job.source_language
                else None
            ),
            "target_languages": list(job.target_languages),
            "lip_sync": job.lip_sync,
            "segments": [
                {
                    "segment_id": clip.segment_id,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "hook_title": clip.hook_title,
                    "caption": clip.caption,
                    "selection_score": clip.selection_score,
                    "score_breakdown": clip.score_breakdown.model_dump(mode="json"),
                    "rationale": clip.rationale,
                    "base_asset_url": (
                        f"{self._settings.api_base_url.rstrip('/')}/api/jobs/"
                        f"{job.job_id}/assets/base_{clip.segment_id}"
                    ),
                }
                for clip in job.segments
            ],
            "cost_matrix": [
                {
                    "segment_id": cell.segment_id,
                    "language": cell.language,
                    "translation_usd": format_usd(cell.translation_micro_usd),
                    "voice_usd": format_usd(cell.voice_micro_usd),
                    "lip_sync_usd": format_usd(cell.lip_sync_micro_usd),
                    "total_usd": format_usd(cell.total_micro_usd),
                }
                for cell in matrix
            ],
            "projected_total_usd": format_usd(self.projected_total(job, matrix)),
        }

    async def confirm(
        self,
        job: Job,
        *,
        segment_ids: list[int],
        languages: list[str],
        expected_total_micro_usd: int,
    ) -> Job:
        async with self._lock(job.job_id):
            if await self.expire_if_needed(job):
                raise ApiError(410, "selection_expired", "The Selection Gate has expired")
            if job.status is not JobStatus.AWAITING_SELECTION:
                raise ApiError(409, "invalid_state", "The Job is not awaiting a selection")

            validate_selection_shape(job, segment_ids, languages)
            matrix = self.matrix(job)
            total = price_selection(matrix, segment_ids, languages)
            if total != expected_total_micro_usd:
                payload = self._gate_payload(job, matrix)
                raise ApiError(
                    409,
                    "selection_price_changed",
                    "The projected total changed; confirm the new amount explicitly",
                    details={
                        "current_total_usd": format_usd(total),
                        "cost_matrix": payload["cost_matrix"],
                        "projected_total_usd": payload["projected_total_usd"],
                    },
                )

            if job.selection is not None:
                same = (
                    sorted(job.selection.segment_ids) == sorted(segment_ids)
                    and sorted(job.selection.languages) == sorted(languages)
                )
                if same:
                    return job
                raise ApiError(
                    409,
                    "selection_already_confirmed",
                    "A different selection was already confirmed for this Job",
                )

            job.selection = Selection(
                segment_ids=list(segment_ids),
                languages=list(languages),
                expected_total_micro_usd=total,
                confirmed_at=self._clock.now(),
            )
            job.selection_matrix = matrix
            job.projected_total_micro_usd = total
            job.expires_at = None
            empty = is_empty_selection(segment_ids, languages)
            job.transition_to(JobStatus.PROCESSING)
            job.stage = JobStage.DELIVERY if empty else JobStage.LOCALIZATION
            await self._repository.save(job)
            await self._events.emit(
                job,
                "selection_confirmed",
                stage=job.stage,
                payload={
                    "segment_ids": segment_ids,
                    "languages": languages,
                    "expected_total_usd": format_usd(total),
                    "empty": empty,
                },
            )
            await self._queue.enqueue(job.job_id)
            return job

    async def expire_if_needed(self, job: Job) -> bool:
        if job.status is not JobStatus.AWAITING_SELECTION:
            return False
        if job.expires_at is None or self._clock.now() < job.expires_at:
            return False
        job.transition_to(JobStatus.EXPIRED)
        job.stage = None
        await self._repository.save(job)
        await self._events.emit(job, "selection_expired")
        await self._notifications.queue(
            job,
            NotificationType.SELECTION_EXPIRED,
            data={"expired_at": self._clock.now().isoformat()},
        )
        await self._notifications.dispatch_pending()
        await self._leases.release(job.workspace_id, job.job_id)
        return True

    async def expire_due_jobs(self) -> int:
        expired = 0
        for job in await self._repository.list_for_workspace(
            self._settings.workspace_id, status=JobStatus.AWAITING_SELECTION
        ):
            async with self._lock(job.job_id):
                if await self.expire_if_needed(job):
                    expired += 1
        return expired
