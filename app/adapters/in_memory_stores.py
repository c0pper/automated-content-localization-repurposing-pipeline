"""In-memory implementations of every persistence and coordination port.

These are the fast test doubles and the local-development default. The same contract suite
runs against the SQLite adapter so the doubles do not drift.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.errors import UnknownJobError
from app.domain.models import (
    CostLedgerEntry,
    IdempotencyRecord,
    Job,
    JobEvent,
    NotificationOutboxEntry,
    Purge,
    ReviewToken,
    VoiceProfile,
    WorkspaceAuditEntry,
    WorkspaceSettings,
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


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

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        status=None,
    ) -> list[Job]:
        jobs = [job for job in await self.list() if job.workspace_id == workspace_id]
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        return jobs

    async def delete_all(self, workspace_id: str) -> None:
        for job_id in [
            job_id
            for job_id, job in self._jobs.items()
            if job.workspace_id == workspace_id
        ]:
            del self._jobs[job_id]


class InMemoryCostLedger:
    def __init__(self) -> None:
        self._entries: list[CostLedgerEntry] = []

    async def append(self, entry: CostLedgerEntry) -> None:
        self._entries.append(entry.model_copy(deep=True))

    async def list_for_job(self, job_id: str) -> list[CostLedgerEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._entries
            if entry.job_id == job_id
        ]

    async def list_for_workspace(self, workspace_id: str) -> list[CostLedgerEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._entries
            if entry.workspace_id == workspace_id
        ]

    async def delete_all(self, workspace_id: str) -> None:
        self._entries = [
            entry for entry in self._entries if entry.workspace_id != workspace_id
        ]


class InMemoryJobEvents:
    def __init__(self) -> None:
        self._events: list[JobEvent] = []

    async def append(self, event: JobEvent) -> None:
        self._events.append(event.model_copy(deep=True))

    async def list_for_job(self, job_id: str) -> list[JobEvent]:
        events = [event for event in self._events if event.job_id == job_id]
        return [event.model_copy(deep=True) for event in events]

    async def delete_all(self, workspace_id: str) -> None:
        self._events = [event for event in self._events if event.workspace_id != workspace_id]


class InMemoryOutbox:
    def __init__(self) -> None:
        self._entries: dict[str, NotificationOutboxEntry] = {}

    async def add(self, entry: NotificationOutboxEntry) -> None:
        self._entries[entry.event_id] = entry.model_copy(deep=True)

    async def list_for_job(self, job_id: str) -> list[NotificationOutboxEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._entries.values()
            if entry.job_id == job_id
        ]

    async def list_pending(self) -> list[NotificationOutboxEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._entries.values()
            if entry.status == "pending"
        ]

    async def save(self, entry: NotificationOutboxEntry) -> None:
        self._entries[entry.event_id] = entry.model_copy(deep=True)

    async def delete_all(self, workspace_id: str) -> None:
        self._entries = {
            event_id: entry
            for event_id, entry in self._entries.items()
            if entry.workspace_id != workspace_id
        }


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, workspace_id: str, key: str) -> IdempotencyRecord | None:
        record = self._records.get((workspace_id, key))
        return record.model_copy(deep=True) if record is not None else None

    async def put(self, record: IdempotencyRecord) -> None:
        self._records[(record.workspace_id, record.key)] = record.model_copy(deep=True)

    async def delete(self, workspace_id: str, key: str) -> None:
        self._records.pop((workspace_id, key), None)

    async def delete_all(self, workspace_id: str) -> None:
        self._records = {
            key: record
            for key, record in self._records.items()
            if record.workspace_id != workspace_id
        }


class InMemoryReviewTokens:
    def __init__(self) -> None:
        self._tokens: dict[str, ReviewToken] = {}

    async def add(self, token: ReviewToken) -> None:
        self._tokens[token.token_id] = token.model_copy(deep=True)

    async def get_by_hash(self, token_hash: str) -> ReviewToken | None:
        for token in self._tokens.values():
            if token.token_hash == token_hash:
                return token.model_copy(deep=True)
        return None

    async def get_for_job(self, job_id: str) -> ReviewToken | None:
        active = [
            token
            for token in self._tokens.values()
            if token.job_id == job_id and token.revoked_at is None
        ]
        if not active:
            return None
        return max(active, key=lambda token: token.created_at).model_copy(deep=True)

    async def save(self, token: ReviewToken) -> None:
        self._tokens[token.token_id] = token.model_copy(deep=True)

    async def delete_for_job(self, job_id: str) -> None:
        self._tokens = {
            token_id: token
            for token_id, token in self._tokens.items()
            if token.job_id != job_id
        }

    async def delete_all(self, workspace_id: str) -> None:
        self._tokens = {
            token_id: token
            for token_id, token in self._tokens.items()
            if token.workspace_id != workspace_id
        }


class InMemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._settings: dict[str, WorkspaceSettings] = {}
        self._voices: dict[str, VoiceProfile] = {}
        self._audit: list[WorkspaceAuditEntry] = []

    async def get_settings(self, workspace_id: str) -> WorkspaceSettings | None:
        settings = self._settings.get(workspace_id)
        return settings.model_copy(deep=True) if settings is not None else None

    async def save_settings(self, settings: WorkspaceSettings) -> None:
        self._settings[settings.workspace_id] = settings.model_copy(deep=True)

    async def get_voice_profile(self, workspace_id: str) -> VoiceProfile | None:
        profile = self._voices.get(workspace_id)
        return profile.model_copy(deep=True) if profile is not None else None

    async def save_voice_profile(self, profile: VoiceProfile) -> None:
        self._voices[profile.workspace_id] = profile.model_copy(deep=True)

    async def delete_voice_profile(self, workspace_id: str) -> None:
        self._voices.pop(workspace_id, None)

    async def append_audit(self, entry: WorkspaceAuditEntry) -> None:
        self._audit.append(entry.model_copy(deep=True))

    async def list_audit(self, workspace_id: str) -> list[WorkspaceAuditEntry]:
        return [
            entry.model_copy(deep=True)
            for entry in self._audit
            if entry.workspace_id == workspace_id
        ]

    async def delete_workspace_data(self, workspace_id: str) -> None:
        # Settings, Voice Profile and audit survive a Workspace Purge.
        return None


class InMemoryPurgeRepository:
    def __init__(self) -> None:
        self._purges: dict[str, Purge] = {}

    async def add(self, purge: Purge) -> None:
        self._purges[purge.purge_id] = purge.model_copy(deep=True)

    async def get(self, purge_id: str) -> Purge | None:
        purge = self._purges.get(purge_id)
        return purge.model_copy(deep=True) if purge is not None else None

    async def list_for_workspace(self, workspace_id: str) -> list[Purge]:
        return [
            purge.model_copy(deep=True)
            for purge in self._purges.values()
            if purge.workspace_id == workspace_id
        ]

    async def save(self, purge: Purge) -> None:
        self._purges[purge.purge_id] = purge.model_copy(deep=True)

    async def delete_all(self, workspace_id: str) -> None:
        self._purges = {
            purge_id: purge
            for purge_id, purge in self._purges.items()
            if purge.workspace_id != workspace_id
        }


class InMemoryLeaseStore:
    def __init__(self, clock=None) -> None:
        self._clock = clock or SystemClock()
        self._leases: dict[tuple[str, str], datetime] = {}

    def _purge_expired(self) -> None:
        now = self._clock.now()
        for key, expires_at in list(self._leases.items()):
            if expires_at <= now:
                del self._leases[key]

    async def acquire(
        self,
        workspace_id: str,
        job_id: str,
        *,
        limit: int,
        ttl: timedelta,
    ) -> bool:
        self._purge_expired()
        key = (workspace_id, job_id)
        if key in self._leases:
            self._leases[key] = self._clock.now() + ttl
            return True
        active = [item for item in self._leases if item[0] == workspace_id]
        if len(active) >= limit:
            return False
        self._leases[key] = self._clock.now() + ttl
        return True

    async def release(self, workspace_id: str, job_id: str) -> None:
        self._leases.pop((workspace_id, job_id), None)

    async def count(self, workspace_id: str) -> int:
        self._purge_expired()
        return len([item for item in self._leases if item[0] == workspace_id])

    async def delete_all(self, workspace_id: str) -> None:
        self._leases = {
            key: value for key, value in self._leases.items() if key[0] != workspace_id
        }
