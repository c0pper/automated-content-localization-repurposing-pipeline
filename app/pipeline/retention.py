"""Retention policy: delete raw intermediates after the configured window.

Delivered Review Bundle assets and each Clip's spoken source text and caption-free master
live for the Workspace lifetime. The Source Recording, full Transcript, caption SRTs,
intermediate audio and pre-mux renders are pruned after the Retention Window.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import timedelta
from pathlib import Path

from app.domain.enums import JobStatus
from app.ports import Clock, JobRepository, ObjectStore

logger = logging.getLogger(__name__)

# A Job that is still running may need its Transcript for the next stage. Gate and terminal
# states are safe to prune because localization uses each Clip's retained source text.
_PRUNABLE_STATUSES = {
    JobStatus.AWAITING_SELECTION,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.EXPIRED,
    JobStatus.CANCELLED,
}


class RetentionSweeper:
    def __init__(
        self,
        store: ObjectStore,
        *,
        retention_days: int,
        repository: JobRepository | None = None,
        clock: Clock | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self._store = store
        self._retention = timedelta(days=retention_days)
        self._repository = repository
        self._clock = clock
        self._workspace_root = workspace_root

    async def sweep(self) -> int:
        removed = await self._store.prune(older_than=self._retention)
        if removed:
            logger.info("Retention sweep removed %d workspace(s)", removed)
        removed += await self._clear_job_intermediates()
        return removed

    async def _clear_job_intermediates(self) -> int:
        if self._repository is None or self._clock is None:
            return 0
        cutoff = self._clock.now() - self._retention
        cleared = 0
        for job in await self._repository.list():
            if job.status not in _PRUNABLE_STATUSES:
                continue
            if job.created_at > cutoff:
                continue
            if job.transcript is None and job.source_path is None:
                continue
            if job.source_path:
                await self._remove_workspace(job.source_path)
            job.transcript = None
            job.source_path = None
            await self._repository.save(job)
            cleared += 1
            logger.info("Retention sweep cleared intermediates for %s", job.job_id)
        return cleared

    async def _remove_workspace(self, source_path: str) -> None:
        if self._workspace_root is None:
            return
        job_dir = Path(source_path).parent
        try:
            job_dir.resolve().relative_to(self._workspace_root.resolve())
        except ValueError:
            return
        if job_dir.is_dir():
            await asyncio.to_thread(shutil.rmtree, job_dir, True)

    async def run_forever(self, stop: asyncio.Event, *, interval_seconds: int) -> None:
        while not stop.is_set():
            try:
                await self.sweep()
            except Exception:  # noqa: BLE001 - a sweep failure must not kill the worker
                logger.exception("Retention sweep failed")

            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue
