"""In-memory job repository.

Swap for Postgres/SQLite in production; the ``JobRepository`` protocol is the seam.
"""

from __future__ import annotations

from app.domain.errors import UnknownJobError
from app.domain.models import Job


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    async def add(self, job: Job) -> None:
        self._jobs[job.job_id] = job.model_copy(deep=True)

    async def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        return job.model_copy(deep=True) if job is not None else None

    async def save(self, job: Job) -> None:
        if job.job_id not in self._jobs:
            raise UnknownJobError(job.job_id)
        job.touch()
        self._jobs[job.job_id] = job.model_copy(deep=True)

    async def list(self) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
        return [job.model_copy(deep=True) for job in jobs]
