"""Infrastructure ports: persistence, object storage, queueing and notifications."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from app.domain.models import Job


class JobRepository(Protocol):
    async def add(self, job: Job) -> None: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def save(self, job: Job) -> None: ...

    async def list(self) -> list[Job]: ...


class ObjectStore(Protocol):
    async def fetch(self, url: str, destination: Path) -> Path:
        """Download a remote asset (or copy a local one) into the job workspace."""
        ...

    async def put(self, source: Path, key: str) -> str:
        """Upload an artifact and return a URL clients can use."""
        ...

    async def delete(self, key: str) -> None: ...

    async def prune(self, older_than: timedelta) -> int:
        """Delete raw/intermediate job workspaces older than the retention window."""
        ...


class TaskQueue(Protocol):
    async def enqueue(self, job_id: str) -> None: ...

    async def dequeue(self, poll_timeout: float | None = None) -> str | None:
        """Block up to ``poll_timeout`` seconds; return ``None`` when idle."""
        ...


class Notifier(Protocol):
    async def notify(self, job: Job, links: Sequence[str]) -> None:
        """Tell the creator that their review bundle is ready."""
        ...
