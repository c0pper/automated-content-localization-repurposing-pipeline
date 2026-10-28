"""Create and enqueue Jobs from validated submissions."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.domain.enums import JobStatus, SourceLanguageOrigin
from app.domain.errors import GuardrailViolation
from app.domain.models import Job, SourceInput, SourceLanguage
from app.ports import Clock, ObjectStore, TaskQueue
from app.security.urls import (
    validate_file_source,
    validate_http_url,
    validate_object_key,
)
from app.services.cost import CostService
from app.services.events import EventService
from app.services.workspace import WorkspaceService


class JobSubmissionService:
    def __init__(
        self,
        *,
        repository,
        queue: TaskQueue,
        store: ObjectStore,
        workspaces: WorkspaceService,
        cost: CostService,
        events: EventService,
        clock: Clock,
        settings: Settings,
        purge=None,
        uploads=None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._store = store
        self._workspaces = workspaces
        self._cost = cost
        self._events = events
        self._clock = clock
        self._settings = settings
        self._purge = purge
        self._uploads = uploads

    async def submit(
        self,
        *,
        source: SourceInput,
        target_languages: list[str],
        source_language: str | None = None,
        lip_sync: bool = False,
        model_overrides: dict[str, str] | None = None,
    ) -> Job:
        if self._purge is not None and self._purge.locked:
            raise GuardrailViolation(
                "workspace_locked",
                "The Workspace is locked while a purge is running",
                status_code=409,
            )
        workspace = await self._workspaces.get_settings()
        languages = [language.strip() for language in target_languages if language.strip()]
        self._validate_languages(languages, workspace.target_language_allowlist)
        await self._validate_source(source)
        declared = self._validate_declared_language(source_language)
        if declared is not None:
            self._reject_conflict(declared, languages)

        if lip_sync and not self._settings.lip_sync_enabled:
            raise GuardrailViolation(
                "lip_sync_unavailable",
                "Lip-sync is not enabled in this deployment",
                retryable=True,
            )

        overrides = self._validate_models(model_overrides or {}, workspace.default_models)
        remaining = await self._workspaces.remaining_budget()
        if remaining <= 0:
            raise GuardrailViolation(
                "workspace_budget_exhausted",
                "The monthly Workspace Budget is exhausted; no Job can be accepted",
                retryable=True,
            )

        job = Job(
            job_id=f"job_{uuid4().hex[:12]}",
            workspace_id=self._settings.workspace_id,
            creator_id=self._settings.creator_id,
            status=JobStatus.RECEIVED,
            source=source,
            input_url=source.location,
            declared_source_language=declared,
            source_language=(
                SourceLanguage(code=declared, origin=SourceLanguageOrigin.DECLARED)
                if declared
                else None
            ),
            target_languages=languages,
            lip_sync=lip_sync,
            model_overrides=overrides,
            job_budget_micro_usd=workspace.job_budget_micro_usd,
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        if source.type == "object" and self._uploads is not None:
            await self._uploads.attach(source.key or "", job.job_id)
        await self._repository.add(job)
        await self._events.emit(
            job,
            "job_received",
            payload={
                "source_type": source.type,
                "target_languages": languages,
                "declared_source_language": declared,
            },
        )
        await self._queue.enqueue(job.job_id)
        return job

    def _validate_languages(self, languages: list[str], allowlist: list[str]) -> None:
        if not languages:
            raise GuardrailViolation(
                "no_target_languages", "At least one target language is required"
            )
        if len(languages) > self._settings.max_target_languages:
            raise GuardrailViolation(
                "too_many_languages",
                f"At most {self._settings.max_target_languages} target languages per job",
            )
        if len(set(languages)) != len(languages):
            raise GuardrailViolation("duplicate_languages", "Target languages must be unique")
        outside = [language for language in languages if language not in allowlist]
        if outside:
            raise GuardrailViolation(
                "language_not_allowed",
                "Every Target Language must be on the Workspace allowlist",
                details={"languages": outside, "allowlist": allowlist},
            )

    async def _validate_source(self, source: SourceInput) -> None:
        if source.type == "object":
            validate_object_key(source.key or "")
            if self._uploads is not None:
                await self._uploads.ensure_attachable(source.key or "")
            if not await self._store.exists(source.key or ""):
                raise GuardrailViolation(
                    "invalid_object_key", f"Object not found: {source.key}"
                )
            return

        url = source.url or ""
        if url.lower().startswith(("http://", "https://")):
            await validate_http_url(url, allowed_suffixes=self._settings.input_suffixes)
            return

        if self._settings.environment == "production":
            raise GuardrailViolation(
                "unsafe_source", "Only HTTP(S) source URLs are accepted in production"
            )

        raw = url[7:] if url.lower().startswith("file://") else url
        validate_file_source(Path(raw), allowed_suffixes=self._settings.input_suffixes)

    def _validate_declared_language(self, language: str | None) -> str | None:
        if language is None:
            return None
        value = language.strip()
        if not value:
            return None
        if value not in self._settings.source_languages:
            raise GuardrailViolation(
                "unsupported_source_language",
                f"Unsupported Source Language: {value}",
                details={"supported": list(self._settings.source_languages)},
            )
        return value

    def _reject_conflict(self, source_language: str, targets: list[str]) -> None:
        primary = source_language.split("-", 1)[0].lower()
        conflicting = [
            language for language in targets if language.split("-", 1)[0].lower() == primary
        ]
        if conflicting:
            raise GuardrailViolation(
                "source_target_conflict",
                "A Target Language cannot be the Source Language",
                details={"source_language": source_language, "languages": conflicting},
            )

    def _validate_models(
        self,
        overrides: dict[str, str],
        defaults: dict[str, str],
    ) -> dict[str, str]:
        resolved = {**self._settings.default_models, **defaults}
        for task, model in overrides.items():
            allowed = self._settings.model_allowlists.get(task)
            if allowed is None:
                raise GuardrailViolation(
                    "invalid_model", f"Unknown model task: {task!r}"
                )
            if model not in allowed:
                raise GuardrailViolation(
                    "invalid_model",
                    f"Model {model!r} is not curated for {task}",
                    details={"allowed": list(allowed)},
                )
            resolved[task] = model
        return resolved
