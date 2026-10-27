"""SQL persistence adapters (SQLite for local durability, Postgres for production).

The adapter stores the complete Job aggregate as JSON so the aggregate can evolve without a
column-per-field migration, while duplicating the query-critical fields into indexed columns.
Append-only tables (Cost Ledger, Job Events, outbox, idempotency, review tokens) use explicit
columns and never expose an update/delete path except the Workspace Purge.

The same SQLAlchemy Core schema runs on SQLite (``sqlite+aiosqlite``) and Postgres
(``postgresql+asyncpg``).
"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.domain.enums import JobStatus
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

metadata = MetaData()

jobs = Table(
    "jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("creator_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("stage", String(32), nullable=True),
    Column("source_kind", String(16), nullable=True),
    Column("source_location", Text, nullable=True),
    Column("source_language_code", String(16), nullable=True),
    Column("source_language_origin", String(16), nullable=True),
    Column("declared_source_language", String(16), nullable=True),
    Column("target_languages", JSON, nullable=False),
    Column("lip_sync", Boolean, nullable=False, default=False),
    Column("model_overrides", JSON, nullable=False),
    Column("job_budget_micro_usd", BigInteger, nullable=False),
    Column("parent_job_id", String(64), nullable=True),
    Column("derived_mode", String(16), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(64), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("retryable", Boolean, nullable=False, default=False),
    Column("cancel_requested", Boolean, nullable=False, default=False),
    Column("bundle_frozen", Boolean, nullable=False, default=False),
    Column("review_token_id", String(128), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_jobs_workspace_status_created", "workspace_id", "status", "created_at"),
)

clips = Table(
    "clips",
    metadata,
    Column("clip_id", String(160), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("ordinal", Integer, nullable=False),
    Column("start_seconds", Float, nullable=False),
    Column("end_seconds", Float, nullable=False),
    Column("spoken_source_text", Text, nullable=False),
    Column("hook_title", Text, nullable=False),
    Column("caption", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("selection_score", Float, nullable=False),
    Column("score_breakdown", JSON, nullable=False),
    Column("base_clip_asset_key", Text, nullable=True),
    Column("base_clip_master_key", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

clip_localizations = Table(
    "clip_localizations",
    metadata,
    Column("clip_id", String(160), primary_key=True),
    Column("language", String(16), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("localized_hook_title", Text, nullable=False),
    Column("localized_caption", Text, nullable=False),
    Column("audio_key", Text, nullable=True),
    Column("video_key", Text, nullable=True),
    Column("lip_sync", Boolean, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

cost_ledger = Table(
    "cost_ledger",
    metadata,
    Column("entry_id", String(64), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("stage", String(32), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("model", String(160), nullable=False),
    Column("units", Float, nullable=False),
    Column("unit_type", String(32), nullable=False),
    Column("base_rate_micro_usd", BigInteger, nullable=False),
    Column("margin", Float, nullable=False),
    Column("estimated_micro_usd", BigInteger, nullable=False),
    Column("actual_micro_usd", BigInteger, nullable=True),
    Column("rate_card_version", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_cost_job_created", "job_id", "created_at"),
)

job_events = Table(
    "job_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("type", String(64), nullable=False),
    Column("stage", String(32), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_events_job_created", "job_id", "created_at"),
)

notification_outbox = Table(
    "notification_outbox",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("type", String(32), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Index("ix_outbox_status_created", "status", "created_at"),
)

idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("workspace_id", String(64), primary_key=True),
    Column("key", String(256), primary_key=True),
    Column("method", String(8), nullable=False),
    Column("path", Text, nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_status", Integer, nullable=False),
    Column("response_body", JSON, nullable=False),
    Column("response_headers", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
)

review_tokens = Table(
    "review_tokens",
    metadata,
    Column("token_id", String(128), primary_key=True),
    Column("job_id", String(64), nullable=False, index=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("token_hash", String(128), nullable=False, unique=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)

workspace_settings = Table(
    "workspace_settings",
    metadata,
    Column("workspace_id", String(64), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

voice_profiles = Table(
    "voice_profiles",
    metadata,
    Column("workspace_id", String(64), primary_key=True),
    Column("provider", String(32), nullable=False),
    Column("voice_id", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

workspace_audit = Table(
    "workspace_audit",
    metadata,
    Column("audit_id", String(64), primary_key=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("actor", String(64), nullable=False),
    Column("action", String(64), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

purges = Table(
    "purges",
    metadata,
    Column("purge_id", String(64), primary_key=True),
    Column("workspace_id", String(64), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

leases = Table(
    "concurrency_leases",
    metadata,
    Column("workspace_id", String(64), primary_key=True),
    Column("job_id", String(64), primary_key=True),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _dump_job(job: Job) -> dict[str, Any]:
    """Serialize the complete aggregate, including fields excluded from public JSON."""
    data = job.model_dump(mode="json")
    data["transcript"] = (
        job.transcript.model_dump(mode="json") if job.transcript is not None else None
    )
    data["source_path"] = job.source_path
    data["candidates"] = [
        candidate.model_dump(mode="json") for candidate in job.candidates
    ]
    data["review_token_hash"] = job.review_token_hash
    for segment, clip in zip(data["segments"], job.segments, strict=False):
        segment["source_text"] = clip.source_text
        segment["base_clip_master_key"] = clip.base_clip_master_key
        segment["video_asset_key"] = clip.video_asset_key
    return data


def _load_job(payload: dict[str, Any]) -> Job:
    return Job.model_validate(payload)


class SQLDatabase:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._schema_ready = False
        self._schema_lock: asyncio.Lock | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> SQLDatabase:
        if settings.repository_backend == "sqlite":
            default_path = settings.data_dir / "pipeline.db"
            path = settings.database_url or f"sqlite+aiosqlite:///{default_path}"
            if path.startswith("sqlite:///") and not path.startswith("sqlite+aiosqlite"):
                path = path.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        else:
            if not settings.database_url:
                raise RuntimeError("PIPELINE_DATABASE_URL is required for the postgres backend")
            path = settings.database_url
            if path.startswith("postgresql://"):
                path = path.replace("postgresql://", "postgresql+asyncpg://", 1)
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if path.startswith("sqlite"):
            # SQLite connections are cheap; closing them per use avoids lingering aiosqlite
            # worker threads when an event loop (for example a test loop) shuts down.
            kwargs["poolclass"] = NullPool
        return cls(create_async_engine(path, **kwargs))

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        self._schema_ready = True

    async def ensure_schema(self) -> None:
        """Create the schema once, lazily, so the container can be built in any context."""
        if self._schema_ready:
            return
        if self._schema_lock is None:
            self._schema_lock = asyncio.Lock()
        async with self._schema_lock:
            if not self._schema_ready:
                await self.create_schema()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        await self.ensure_schema()
        async with self.session_factory() as session:
            yield session


class SQLJobRepository:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def add(self, job: Job) -> None:
        async with self._db.session() as session:
            await session.execute(delete(jobs).where(jobs.c.job_id == job.job_id))
            await session.execute(
                jobs.insert().values(
                    job_id=job.job_id,
                    workspace_id=job.workspace_id,
                    creator_id=job.creator_id,
                    status=job.status.value,
                    stage=job.stage.value if job.stage else None,
                    source_kind=job.source.type if job.source else None,
                    source_location=job.source.location if job.source else job.input_url,
                    source_language_code=(
                        job.source_language.code if job.source_language else None
                    ),
                    source_language_origin=(
                        job.source_language.origin.value if job.source_language else None
                    ),
                    declared_source_language=job.declared_source_language,
                    target_languages=job.target_languages,
                    lip_sync=job.lip_sync,
                    model_overrides=job.model_overrides,
                    job_budget_micro_usd=job.job_budget_micro_usd,
                    parent_job_id=job.parent_job_id,
                    derived_mode=job.derived_mode.value if job.derived_mode else None,
                    expires_at=_utc(job.expires_at),
                    error_code=job.error_code,
                    error_message=job.error_message,
                    retryable=job.retryable,
                    cancel_requested=job.cancel_requested,
                    bundle_frozen=job.bundle_frozen,
                    review_token_id=job.review_token_id,
                    payload=_dump_job(job),
                    created_at=_utc(job.created_at),
                    updated_at=_utc(job.updated_at),
                )
            )
            await self._sync_clips(session, job)
            await session.commit()

    async def get(self, job_id: str) -> Job | None:
        async with self._db.session() as session:
            row = (
                await session.execute(select(jobs.c.payload).where(jobs.c.job_id == job_id))
            ).first()
        return _load_job(row.payload) if row else None

    async def save(self, job: Job) -> None:
        job.touch()
        async with self._db.session() as session:
            result = await session.execute(
                update(jobs)
                .where(jobs.c.job_id == job.job_id)
                .values(
                    status=job.status.value,
                    stage=job.stage.value if job.stage else None,
                    source_language_code=(
                        job.source_language.code if job.source_language else None
                    ),
                    source_language_origin=(
                        job.source_language.origin.value if job.source_language else None
                    ),
                    declared_source_language=job.declared_source_language,
                    target_languages=job.target_languages,
                    model_overrides=job.model_overrides,
                    job_budget_micro_usd=job.job_budget_micro_usd,
                    parent_job_id=job.parent_job_id,
                    derived_mode=job.derived_mode.value if job.derived_mode else None,
                    expires_at=_utc(job.expires_at),
                    error_code=job.error_code,
                    error_message=job.error_message,
                    retryable=job.retryable,
                    cancel_requested=job.cancel_requested,
                    bundle_frozen=job.bundle_frozen,
                    review_token_id=job.review_token_id,
                    payload=_dump_job(job),
                    updated_at=_utc(job.updated_at),
                )
            )
            if result.rowcount == 0:
                from app.domain.errors import UnknownJobError

                raise UnknownJobError(job.job_id)
            await self._sync_clips(session, job)
            await session.commit()

    async def list(self) -> builtins.list[Job]:
        async with self._db.session() as session:
            rows = (
                await session.execute(select(jobs.c.payload).order_by(jobs.c.created_at.desc()))
            ).all()
        return [_load_job(row.payload) for row in rows]

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        status: JobStatus | None = None,
    ) -> builtins.list[Job]:
        query = select(jobs.c.payload).where(jobs.c.workspace_id == workspace_id)
        if status is not None:
            query = query.where(jobs.c.status == status.value)
        query = query.order_by(jobs.c.created_at.desc())
        async with self._db.session() as session:
            rows = (await session.execute(query)).all()
        return [_load_job(row.payload) for row in rows]

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(delete(clips).where(clips.c.job_id.in_(
                select(jobs.c.job_id).where(jobs.c.workspace_id == workspace_id)
            )))
            await session.execute(delete(clip_localizations).where(
                clip_localizations.c.job_id.in_(
                    select(jobs.c.job_id).where(jobs.c.workspace_id == workspace_id)
                )
            ))
            await session.execute(delete(jobs).where(jobs.c.workspace_id == workspace_id))
            await session.commit()

    async def dispose(self) -> None:
        await self._db.engine.dispose()

    async def _sync_clips(self, session: AsyncSession, job: Job) -> None:
        await session.execute(delete(clips).where(clips.c.job_id == job.job_id))
        await session.execute(
            delete(clip_localizations).where(clip_localizations.c.job_id == job.job_id)
        )
        for clip in job.segments:
            await session.execute(
                clips.insert().values(
                    clip_id=f"{job.job_id}_{clip.segment_id}",
                    job_id=job.job_id,
                    ordinal=clip.segment_id,
                    start_seconds=_seconds(clip.start_time),
                    end_seconds=_seconds(clip.end_time),
                    spoken_source_text=clip.source_text,
                    hook_title=clip.hook_title,
                    caption=clip.caption,
                    rationale=clip.rationale,
                    selection_score=clip.selection_score,
                    score_breakdown=clip.score_breakdown.model_dump(mode="json"),
                    base_clip_asset_key=clip.video_asset_key,
                    base_clip_master_key=clip.base_clip_master_key,
                    created_at=_utc(job.created_at),
                )
            )
        for localized in job.localized_clips:
            await session.execute(
                clip_localizations.insert().values(
                    clip_id=f"{job.job_id}_{localized.segment_id}",
                    language=localized.language,
                    job_id=job.job_id,
                    localized_hook_title=localized.localized_hook_title,
                    localized_caption=localized.localized_caption,
                    audio_key=localized.audio_asset_key,
                    video_key=localized.video_asset_key,
                    lip_sync=localized.lip_sync,
                    status=localized.status.value,
                    created_at=_utc(localized.created_at),
                )
            )


def _seconds(timestamp: str) -> float:
    from app.domain.timestamps import parse_timestamp

    try:
        return parse_timestamp(timestamp)
    except ValueError:
        return 0.0


class SQLCostLedger:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def append(self, entry: CostLedgerEntry) -> None:
        async with self._db.session() as session:
            await session.execute(
                cost_ledger.insert().values(
                    entry_id=entry.entry_id,
                    job_id=entry.job_id,
                    workspace_id=entry.workspace_id,
                    stage=entry.stage.value,
                    provider=entry.provider,
                    model=entry.model,
                    units=entry.units,
                    unit_type=entry.unit_type.value,
                    base_rate_micro_usd=entry.base_rate_micro_usd,
                    margin=entry.margin,
                    estimated_micro_usd=entry.estimated_micro_usd,
                    actual_micro_usd=entry.actual_micro_usd,
                    rate_card_version=entry.rate_card_version,
                    created_at=_utc(entry.created_at),
                )
            )
            await session.commit()

    async def list_for_job(self, job_id: str) -> builtins.list[CostLedgerEntry]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(cost_ledger)
                    .where(cost_ledger.c.job_id == job_id)
                    .order_by(cost_ledger.c.created_at)
                )
            ).mappings().all()
        return [_ledger_entry(row) for row in rows]

    async def list_for_workspace(self, workspace_id: str) -> builtins.list[CostLedgerEntry]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(cost_ledger)
                    .where(cost_ledger.c.workspace_id == workspace_id)
                    .order_by(cost_ledger.c.created_at)
                )
            ).mappings().all()
        return [_ledger_entry(row) for row in rows]

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(cost_ledger).where(cost_ledger.c.workspace_id == workspace_id)
            )
            await session.commit()


def _ledger_entry(row) -> CostLedgerEntry:
    return CostLedgerEntry.model_validate(
        {
            **dict(row),
            "created_at": _utc(row["created_at"]),
        }
    )


class SQLJobEvents:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def append(self, event: JobEvent) -> None:
        async with self._db.session() as session:
            await session.execute(
                job_events.insert().values(
                    event_id=event.event_id,
                    job_id=event.job_id,
                    workspace_id=event.workspace_id,
                    type=event.type,
                    stage=event.stage.value if event.stage else None,
                    payload=event.payload,
                    created_at=_utc(event.created_at),
                )
            )
            await session.commit()

    async def list_for_job(self, job_id: str) -> builtins.list[JobEvent]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(job_events)
                    .where(job_events.c.job_id == job_id)
                    .order_by(job_events.c.created_at, job_events.c.event_id)
                )
            ).mappings().all()
        return [
            JobEvent.model_validate({**dict(row), "created_at": _utc(row["created_at"])})
            for row in rows
        ]

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(job_events).where(job_events.c.workspace_id == workspace_id)
            )
            await session.commit()


class SQLOutbox:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def add(self, entry: NotificationOutboxEntry) -> None:
        async with self._db.session() as session:
            await session.execute(
                notification_outbox.insert().values(
                    event_id=entry.event_id,
                    job_id=entry.job_id,
                    workspace_id=entry.workspace_id,
                    type=entry.type.value,
                    payload=entry.payload,
                    status=entry.status,
                    attempts=entry.attempts,
                    last_error=entry.last_error,
                    created_at=_utc(entry.created_at),
                    sent_at=_utc(entry.sent_at),
                )
            )
            await session.commit()

    async def list_for_job(self, job_id: str) -> builtins.list[NotificationOutboxEntry]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(notification_outbox)
                    .where(notification_outbox.c.job_id == job_id)
                    .order_by(notification_outbox.c.created_at)
                )
            ).mappings().all()
        return [_outbox_entry(row) for row in rows]

    async def list_pending(self) -> builtins.list[NotificationOutboxEntry]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(notification_outbox)
                    .where(notification_outbox.c.status == "pending")
                    .order_by(notification_outbox.c.created_at)
                )
            ).mappings().all()
        return [_outbox_entry(row) for row in rows]

    async def save(self, entry: NotificationOutboxEntry) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(notification_outbox)
                .where(notification_outbox.c.event_id == entry.event_id)
                .values(
                    status=entry.status,
                    attempts=entry.attempts,
                    last_error=entry.last_error,
                    sent_at=_utc(entry.sent_at),
                )
            )
            await session.commit()

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(notification_outbox).where(
                    notification_outbox.c.workspace_id == workspace_id
                )
            )
            await session.commit()


def _outbox_entry(row) -> NotificationOutboxEntry:
    return NotificationOutboxEntry.model_validate(
        {
            **dict(row),
            "created_at": _utc(row["created_at"]),
            "sent_at": _utc(row["sent_at"]),
        }
    )


class SQLIdempotencyStore:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def get(self, workspace_id: str, key: str) -> IdempotencyRecord | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(idempotency_keys).where(
                        and_(
                            idempotency_keys.c.workspace_id == workspace_id,
                            idempotency_keys.c.key == key,
                        )
                    )
                )
            ).mappings().first()
        return _idempotency_record(row) if row else None

    async def put(self, record: IdempotencyRecord) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(idempotency_keys).where(
                    and_(
                        idempotency_keys.c.workspace_id == record.workspace_id,
                        idempotency_keys.c.key == record.key,
                    )
                )
            )
            await session.execute(
                idempotency_keys.insert().values(
                    workspace_id=record.workspace_id,
                    key=record.key,
                    method=record.method,
                    path=record.path,
                    request_hash=record.request_hash,
                    response_status=record.response_status,
                    response_body=record.response_body,
                    response_headers=record.response_headers,
                    created_at=_utc(record.created_at),
                    expires_at=_utc(record.expires_at),
                )
            )
            await session.commit()

    async def delete(self, workspace_id: str, key: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(idempotency_keys).where(
                    and_(
                        idempotency_keys.c.workspace_id == workspace_id,
                        idempotency_keys.c.key == key,
                    )
                )
            )
            await session.commit()

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(idempotency_keys).where(
                    idempotency_keys.c.workspace_id == workspace_id
                )
            )
            await session.commit()


def _idempotency_record(row) -> IdempotencyRecord:
    return IdempotencyRecord.model_validate(
        {
            **dict(row),
            "created_at": _utc(row["created_at"]),
            "expires_at": _utc(row["expires_at"]),
        }
    )


class SQLReviewTokens:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def add(self, token: ReviewToken) -> None:
        async with self._db.session() as session:
            await session.execute(
                review_tokens.insert().values(
                    token_id=token.token_id,
                    job_id=token.job_id,
                    workspace_id=token.workspace_id,
                    token_hash=token.token_hash,
                    created_at=_utc(token.created_at),
                    rotated_at=_utc(token.rotated_at),
                    revoked_at=_utc(token.revoked_at),
                )
            )
            await session.commit()

    async def get_by_hash(self, token_hash: str) -> ReviewToken | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(review_tokens).where(review_tokens.c.token_hash == token_hash)
                )
            ).mappings().first()
        return _review_token(row) if row else None

    async def get_for_job(self, job_id: str) -> ReviewToken | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(review_tokens)
                    .where(
                        and_(
                            review_tokens.c.job_id == job_id,
                            review_tokens.c.revoked_at.is_(None),
                        )
                    )
                    .order_by(review_tokens.c.created_at.desc())
                    .limit(1)
                )
            ).mappings().first()
        return _review_token(row) if row else None

    async def save(self, token: ReviewToken) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(review_tokens)
                .where(review_tokens.c.token_id == token.token_id)
                .values(rotated_at=_utc(token.rotated_at), revoked_at=_utc(token.revoked_at))
            )
            await session.commit()

    async def delete_for_job(self, job_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(review_tokens).where(review_tokens.c.job_id == job_id)
            )
            await session.commit()

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(review_tokens).where(review_tokens.c.workspace_id == workspace_id)
            )
            await session.commit()


def _review_token(row) -> ReviewToken:
    return ReviewToken.model_validate(
        {
            **dict(row),
            "created_at": _utc(row["created_at"]),
            "rotated_at": _utc(row["rotated_at"]),
            "revoked_at": _utc(row["revoked_at"]),
        }
    )


class SQLWorkspaceRepository:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def get_settings(self, workspace_id: str) -> WorkspaceSettings | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(workspace_settings.c.payload).where(
                        workspace_settings.c.workspace_id == workspace_id
                    )
                )
            ).first()
        return WorkspaceSettings.model_validate(row.payload) if row else None

    async def save_settings(self, settings: WorkspaceSettings) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(workspace_settings).where(
                    workspace_settings.c.workspace_id == settings.workspace_id
                )
            )
            await session.execute(
                workspace_settings.insert().values(
                    workspace_id=settings.workspace_id,
                    payload=settings.model_dump(mode="json"),
                    updated_at=_utc(settings.updated_at),
                )
            )
            await session.commit()

    async def get_voice_profile(self, workspace_id: str) -> VoiceProfile | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(voice_profiles).where(
                        voice_profiles.c.workspace_id == workspace_id
                    )
                )
            ).mappings().first()
        if not row:
            return None
        return VoiceProfile.model_validate(
            {
                **dict(row),
                "created_at": _utc(row["created_at"]),
                "updated_at": _utc(row["updated_at"]),
            }
        )

    async def save_voice_profile(self, profile: VoiceProfile) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(voice_profiles).where(
                    voice_profiles.c.workspace_id == profile.workspace_id
                )
            )
            await session.execute(
                voice_profiles.insert().values(
                    workspace_id=profile.workspace_id,
                    provider=profile.provider,
                    voice_id=profile.voice_id,
                    created_at=_utc(profile.created_at),
                    updated_at=_utc(profile.updated_at),
                )
            )
            await session.commit()

    async def delete_voice_profile(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(voice_profiles).where(
                    voice_profiles.c.workspace_id == workspace_id
                )
            )
            await session.commit()

    async def append_audit(self, entry: WorkspaceAuditEntry) -> None:
        async with self._db.session() as session:
            await session.execute(
                workspace_audit.insert().values(
                    audit_id=entry.audit_id,
                    workspace_id=entry.workspace_id,
                    actor=entry.actor,
                    action=entry.action,
                    payload=entry.payload,
                    created_at=_utc(entry.created_at),
                )
            )
            await session.commit()

    async def list_audit(self, workspace_id: str) -> builtins.list[WorkspaceAuditEntry]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(workspace_audit)
                    .where(workspace_audit.c.workspace_id == workspace_id)
                    .order_by(workspace_audit.c.created_at)
                )
            ).mappings().all()
        return [
            WorkspaceAuditEntry.model_validate(
                {**dict(row), "created_at": _utc(row["created_at"])}
            )
            for row in rows
        ]

    async def delete_workspace_data(self, workspace_id: str) -> None:
        return None


class SQLPurgeRepository:
    def __init__(self, db: SQLDatabase) -> None:
        self._db = db

    async def add(self, purge: Purge) -> None:
        async with self._db.session() as session:
            await session.execute(
                purges.insert().values(
                    purge_id=purge.purge_id,
                    workspace_id=purge.workspace_id,
                    payload=purge.model_dump(mode="json"),
                    created_at=_utc(purge.created_at),
                )
            )
            await session.commit()

    async def get(self, purge_id: str) -> Purge | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(purges.c.payload).where(purges.c.purge_id == purge_id)
                )
            ).first()
        return Purge.model_validate(row.payload) if row else None

    async def list_for_workspace(self, workspace_id: str) -> builtins.list[Purge]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(purges.c.payload)
                    .where(purges.c.workspace_id == workspace_id)
                    .order_by(purges.c.created_at.desc())
                )
            ).all()
        return [Purge.model_validate(row.payload) for row in rows]

    async def save(self, purge: Purge) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(purges)
                .where(purges.c.purge_id == purge.purge_id)
                .values(payload=purge.model_dump(mode="json"))
            )
            await session.commit()

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(purges).where(purges.c.workspace_id == workspace_id)
            )
            await session.commit()


class SQLLeaseStore:
    def __init__(self, db: SQLDatabase, clock) -> None:
        self._db = db
        self._clock = clock

    async def _purge_expired(self, session: AsyncSession) -> None:
        await session.execute(delete(leases).where(leases.c.expires_at <= _utc(self._clock.now())))

    async def acquire(
        self,
        workspace_id: str,
        job_id: str,
        *,
        limit: int,
        ttl: timedelta,
    ) -> bool:
        now = self._clock.now()
        async with self._db.session() as session:
            await self._purge_expired(session)
            existing = (
                await session.execute(
                    select(leases).where(
                        and_(
                            leases.c.workspace_id == workspace_id,
                            leases.c.job_id == job_id,
                        )
                    )
                )
            ).first()
            if existing is not None:
                await session.execute(
                    update(leases)
                    .where(
                        and_(
                            leases.c.workspace_id == workspace_id,
                            leases.c.job_id == job_id,
                        )
                    )
                    .values(expires_at=_utc(now + ttl))
                )
                await session.commit()
                return True
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(leases)
                    .where(leases.c.workspace_id == workspace_id)
                )
            ).scalar_one()
            if count >= limit:
                await session.commit()
                return False
            await session.execute(
                leases.insert().values(
                    workspace_id=workspace_id,
                    job_id=job_id,
                    expires_at=_utc(now + ttl),
                )
            )
            await session.commit()
            return True

    async def release(self, workspace_id: str, job_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(leases).where(
                    and_(
                        leases.c.workspace_id == workspace_id,
                        leases.c.job_id == job_id,
                    )
                )
            )
            await session.commit()

    async def count(self, workspace_id: str) -> int:
        async with self._db.session() as session:
            await self._purge_expired(session)
            await session.commit()
            return (
                await session.execute(
                    select(func.count())
                    .select_from(leases)
                    .where(leases.c.workspace_id == workspace_id)
                )
            ).scalar_one()

    async def delete_all(self, workspace_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(leases).where(leases.c.workspace_id == workspace_id)
            )
            await session.commit()


def build_sql_repositories(settings: Settings, clock):
    """Build every SQL-backed repository.

    The schema is created lazily on first use, so the container can be built from a sync
    factory or inside an already-running event loop. Production deployments also run the
    versioned migration in ``migrations/``.
    """
    db = SQLDatabase.from_settings(settings)
    return (
        SQLJobRepository(db),
        SQLCostLedger(db),
        SQLJobEvents(db),
        SQLOutbox(db),
        SQLIdempotencyStore(db),
        SQLReviewTokens(db),
        SQLWorkspaceRepository(db),
        SQLPurgeRepository(db),
        SQLLeaseStore(db, clock),
    )
