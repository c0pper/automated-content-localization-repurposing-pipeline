"""Background queue worker."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.orchestrator import PipelineOrchestrator
from app.ports import TaskQueue

logger = logging.getLogger(__name__)


class QueueWorker:
    def __init__(
        self,
        *,
        queue: TaskQueue,
        orchestrator: PipelineOrchestrator,
        poll_timeout: float = 0.25,
    ) -> None:
        self._queue = queue
        self._orchestrator = orchestrator
        self._poll_timeout = poll_timeout

    async def run_once(self) -> bool:
        """Process a single job; return ``False`` when the queue was idle."""
        job_id = await self._queue.dequeue(poll_timeout=self._poll_timeout)
        if job_id is None:
            return False

        try:
            await self._orchestrator.run(job_id)
        except Exception:  # noqa: BLE001 - keep the worker alive
            logger.exception("Unhandled error while processing job %s", job_id)
        return True

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("Queue worker started")
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001 - keep the worker alive
                logger.exception("Queue worker loop error")
                await asyncio.sleep(self._poll_timeout)
        logger.info("Queue worker stopped")
