"""Create and enqueue jobs from validated submissions."""

from __future__ import annotations

from uuid import uuid4

from app.domain.models import Job
from app.guardrails import Guardrails
from app.ports import JobRepository, TaskQueue


class JobSubmissionService:
    def __init__(
        self,
        *,
        repository: JobRepository,
        queue: TaskQueue,
        guardrails: Guardrails,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._guardrails = guardrails

    async def submit(self, *, input_url: str, target_languages: list[str]) -> Job:
        languages = [language.strip().lower() for language in target_languages]
        self._guardrails.check_submission(input_url, languages)

        job = Job(
            job_id=f"job_{uuid4().hex[:12]}",
            input_url=input_url,
            target_languages=languages,
        )
        await self._repository.add(job)
        await self._queue.enqueue(job.job_id)
        return job
