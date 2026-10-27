"""Append-only Job Event timeline."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.domain.enums import JobStage
from app.domain.models import Job, JobEvent
from app.ports import Clock, JobEventRepository


class EventService:
    def __init__(self, *, events: JobEventRepository, clock: Clock) -> None:
        self._events = events
        self._clock = clock

    async def emit(
        self,
        job: Job,
        event_type: str,
        *,
        stage: JobStage | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JobEvent:
        event = JobEvent(
            event_id=f"evt_{uuid4().hex[:16]}",
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            type=event_type,
            stage=stage if stage is not None else job.stage,
            payload=payload or {},
            created_at=self._clock.now(),
        )
        await self._events.append(event)
        return event

    async def list(self, job_id: str) -> list[JobEvent]:
        return await self._events.list_for_job(job_id)
