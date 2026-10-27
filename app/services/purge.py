"""Two-step Workspace Purge and review-link rotation support."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import shutil
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.domain.enums import JobStatus, PurgeStatus
from app.domain.errors import ApiError
from app.domain.models import Purge
from app.ports import (
    Clock,
    CostLedgerRepository,
    IdempotencyStore,
    JobEventRepository,
    JobRepository,
    LeaseStore,
    ObjectStore,
    OutboxRepository,
    PurgeRepository,
    ReviewTokenRepository,
)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PurgeService:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        ledger: CostLedgerRepository,
        events: JobEventRepository,
        outbox: OutboxRepository,
        idempotency: IdempotencyStore,
        review_tokens: ReviewTokenRepository,
        purges: PurgeRepository,
        leases: LeaseStore,
        store: ObjectStore,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._jobs = jobs
        self._ledger = ledger
        self._events = events
        self._outbox = outbox
        self._idempotency = idempotency
        self._review_tokens = review_tokens
        self._purges = purges
        self._leases = leases
        self._store = store
        self._clock = clock
        self._settings = settings
        self._locked = False

    @property
    def locked(self) -> bool:
        return self._locked

    async def dry_run(self) -> dict:
        jobs = await self._jobs.list_for_workspace(self._settings.workspace_id)
        base_clips = sum(1 for job in jobs for clip in job.segments if clip.video_asset_key)
        localized = sum(
            1
            for job in jobs
            for clip in job.localized_clips
            if clip.video_asset_key
        )
        copy_files = sum(len(job.content_assets) for job in jobs)
        review_tokens = 0
        cost_entries = 0
        events = 0
        total_bytes = 0
        for job in jobs:
            token = await self._review_tokens.get_for_job(job.job_id)
            if token is not None:
                review_tokens += 1
            cost_entries += len(await self._ledger.list_for_job(job.job_id))
            events += len(await self._events.list_for_job(job.job_id))
            for key in await self._store.list_keys(f"jobs/{job.job_id}/"):
                total_bytes += await self._store.size(key)

        raw_token = secrets.token_urlsafe(32)
        purge = Purge(
            purge_id=f"purge_{uuid4().hex[:12]}",
            workspace_id=self._settings.workspace_id,
            status=PurgeStatus.DRY_RUN,
            dry_run_counts={
                "jobs": len(jobs),
                "base_clips": base_clips,
                "localized_clips": localized,
                "copy_files": copy_files,
                "review_tokens": review_tokens,
                "cost_entries": cost_entries,
                "events": events,
                "bytes": total_bytes,
            },
            confirmation_token_hash=_hash(raw_token),
            expires_at=self._clock.now()
            + timedelta(seconds=self._settings.purge_confirmation_ttl_seconds),
            created_at=self._clock.now(),
        )
        await self._purges.add(purge)
        return {
            **purge.dry_run_counts,
            "purge_id": purge.purge_id,
            "confirmation_token": raw_token,
            "expires_at": purge.expires_at.isoformat() if purge.expires_at else None,
        }

    async def confirm(self, *, workspace_id: str, confirmation_token: str) -> Purge:
        if workspace_id != self._settings.workspace_id:
            raise ApiError(
                409, "workspace_id_mismatch", "The Workspace ID does not match"
            )
        purge = None
        for candidate in await self._purges.list_for_workspace(self._settings.workspace_id):
            if candidate.confirmation_token_hash == _hash(confirmation_token):
                purge = candidate
                break
        if purge is None:
            raise ApiError(
                410, "purge_confirmation_expired", "The purge confirmation token is stale"
            )
        if purge.expires_at is None or self._clock.now() >= purge.expires_at:
            raise ApiError(
                410, "purge_confirmation_expired", "The purge confirmation token is stale"
            )
        if purge.status is not PurgeStatus.DRY_RUN:
            raise ApiError(409, "invalid_state", "This purge was already confirmed")

        jobs = await self._jobs.list_for_workspace(self._settings.workspace_id)
        active = [
            job
            for job in jobs
            if not job.status.is_terminal and job.status is not JobStatus.FAILED
        ]
        if active:
            raise ApiError(
                409,
                "active_jobs",
                "Cancel every active Job before purging the Workspace",
                details={"job_ids": [job.job_id for job in active]},
            )

        self._locked = True
        purge.status = PurgeStatus.CONFIRMED
        await self._purges.save(purge)
        try:
            for job in jobs:
                await self._store.delete_prefix(f"jobs/{job.job_id}/")
                await self._remove_workspace(job.job_id)
            await self._store.delete_prefix("uploads/")
            await self._jobs.delete_all(self._settings.workspace_id)
            await self._ledger.delete_all(self._settings.workspace_id)
            await self._events.delete_all(self._settings.workspace_id)
            await self._outbox.delete_all(self._settings.workspace_id)
            await self._idempotency.delete_all(self._settings.workspace_id)
            await self._review_tokens.delete_all(self._settings.workspace_id)
            await self._leases.delete_all(self._settings.workspace_id)
        except Exception as exc:  # noqa: BLE001 - record and surface the failure
            purge.status = PurgeStatus.FAILED
            purge.error = str(exc)
            await self._purges.save(purge)
            self._locked = False
            raise ApiError(500, "purge_failed", str(exc)) from exc
        finally:
            self._locked = False

        purge.status = PurgeStatus.COMPLETED
        purge.completed_at = self._clock.now()
        await self._purges.save(purge)
        return purge

    async def status(self, purge_id: str) -> Purge:
        purge = await self._purges.get(purge_id)
        if purge is None:
            raise ApiError(404, "not_found", f"Unknown purge: {purge_id}")
        return purge

    async def _remove_workspace(self, job_id: str) -> None:
        job_dir: Path = self._settings.workspace_dir / job_id
        if await asyncio.to_thread(job_dir.is_dir):
            await asyncio.to_thread(shutil.rmtree, job_dir, True)
