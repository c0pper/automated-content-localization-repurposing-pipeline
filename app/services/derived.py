"""Derived Jobs: copy and localization modes over retained Base Clips."""

from __future__ import annotations

from uuid import uuid4

from app.config import Settings
from app.domain.enums import CostUnitType, DerivedMode, JobStage, JobStatus
from app.domain.errors import ApiError, GuardrailViolation
from app.domain.models import (
    Clip,
    ClipCandidate,
    CopyOrigin,
    Job,
    Transcript,
)
from app.ports import Clock, ObjectStore, TaskQueue
from app.services.cost import CostService
from app.services.events import EventService
from app.services.selection import SelectionService
from app.services.workspace import WorkspaceService


class DerivedJobService:
    def __init__(
        self,
        *,
        repository,
        queue: TaskQueue,
        store: ObjectStore,
        copywriter,
        cost: CostService,
        events: EventService,
        workspaces: WorkspaceService,
        selection: SelectionService,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._store = store
        self._copywriter = copywriter
        self._cost = cost
        self._events = events
        self._workspaces = workspaces
        self._selection = selection
        self._clock = clock
        self._settings = settings

    async def derive(
        self,
        parent: Job,
        *,
        mode: str,
        target_languages: list[str] | None = None,
        lip_sync: bool = False,
        model_overrides: dict[str, str] | None = None,
        refresh_long_form: bool = False,
    ) -> Job:
        if refresh_long_form:
            raise GuardrailViolation(
                "long_form_refresh_requires_fresh_job",
                "Long-form copy cannot be regenerated from Clip excerpts; submit a fresh "
                "Job from the Source Recording",
            )
        try:
            derived_mode = DerivedMode(mode)
        except ValueError as exc:
            raise GuardrailViolation(
                "invalid_derived_mode", "mode must be 'copy' or 'localization'"
            ) from exc

        if parent.status not in {
            JobStatus.COMPLETED,
            JobStatus.EXPIRED,
            JobStatus.CANCELLED,
        }:
            raise ApiError(
                409,
                "parent_not_eligible",
                "The parent Job must be COMPLETED, EXPIRED or CANCELLED",
            )
        if not parent.segments:
            raise ApiError(
                409, "parent_not_eligible", "The parent Job has no retained Base Clips"
            )
        if parent.source_language is None:
            raise ApiError(
                409, "parent_not_eligible", "The parent Job has no Source Language"
            )

        workspace = await self._workspaces.get_settings()
        languages: list[str] = []
        if derived_mode is DerivedMode.LOCALIZATION:
            languages = [
                language.strip() for language in (target_languages or []) if language.strip()
            ]
            if not languages:
                raise GuardrailViolation(
                    "no_target_languages",
                    "A localization Derived Job requires target_languages",
                )
            if len(set(languages)) != len(languages):
                raise GuardrailViolation(
                    "duplicate_languages", "Target languages must be unique"
                )
            if len(languages) > self._settings.max_target_languages:
                raise GuardrailViolation(
                    "too_many_languages",
                    f"At most {self._settings.max_target_languages} target languages per job",
                )
            outside = [
                language
                for language in languages
                if language not in workspace.target_language_allowlist
            ]
            if outside:
                raise GuardrailViolation(
                    "language_not_allowed",
                    "Every Target Language must be on the Workspace allowlist",
                    details={"languages": outside},
                )
            primary = parent.source_language.code.split("-", 1)[0].lower()
            conflicting = [
                language
                for language in languages
                if language.split("-", 1)[0].lower() == primary
            ]
            if conflicting:
                raise GuardrailViolation(
                    "source_target_conflict",
                    "A Target Language cannot be the Source Language",
                    details={"languages": conflicting},
                )
            if lip_sync and not self._settings.lip_sync_enabled:
                raise GuardrailViolation(
                    "lip_sync_unavailable", "Lip-sync is not enabled in this deployment"
                )
        else:
            lip_sync = False

        overrides = self._validate_models(
            model_overrides or {}, workspace.default_models
        )

        child = Job(
            job_id=f"job_{uuid4().hex[:12]}",
            workspace_id=parent.workspace_id,
            creator_id=parent.creator_id,
            status=JobStatus.PROCESSING,
            stage=JobStage.DELIVERY if derived_mode is DerivedMode.COPY else JobStage.VIDEO,
            source=parent.source,
            input_url=parent.input_url,
            source_language=parent.source_language.model_copy(),
            declared_source_language=parent.declared_source_language,
            target_languages=languages,
            lip_sync=lip_sync,
            model_overrides=overrides,
            job_budget_micro_usd=workspace.job_budget_micro_usd,
            parent_job_id=parent.job_id,
            derived_mode=derived_mode,
            content=(
                parent.content.model_copy(deep=True) if parent.content is not None else None
            ),
            copy_origin=CopyOrigin(
                clips="parent" if derived_mode is DerivedMode.LOCALIZATION else "generated",
                linkedin="parent",
                newsletter="parent",
            ),
            completed_stages=[
                JobStage.INGEST,
                JobStage.INTELLIGENCE,
                JobStage.SCORING,
                JobStage.VIDEO,
            ],
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )

        await self._copy_base_clips(parent, child)
        if derived_mode is DerivedMode.COPY:
            await self._refresh_clip_copy(parent, child)
        await self._repository.add(child)
        await self._events.emit(
            child,
            "derived_job_created",
            payload={"parent_job_id": parent.job_id, "mode": derived_mode.value},
        )
        await self._events.emit(
            parent,
            "derived_job_created",
            payload={"child_job_id": child.job_id, "mode": derived_mode.value},
        )
        await self._repository.save(parent)

        if derived_mode is DerivedMode.LOCALIZATION:
            await self._selection.open_gate(child)
        else:
            await self._queue.enqueue(child.job_id)
        return child

    async def _copy_base_clips(self, parent: Job, child: Job) -> None:
        language = parent.source_language.code if parent.source_language else "en"
        copied: list[Clip] = []
        for clip in parent.segments:
            new_clip = clip.model_copy(deep=True)
            if clip.base_clip_master_key:
                new_master_key = (
                    f"jobs/{child.job_id}/masters/clip_{clip.segment_id}_{language}.mp4"
                )
                await self._store.copy(clip.base_clip_master_key, new_master_key)
                new_clip.base_clip_master_key = new_master_key
            if clip.video_asset_key:
                new_key = f"jobs/{child.job_id}/clips/clip_{clip.segment_id}_{language}.mp4"
                new_clip.video_asset_url = await self._store.copy(
                    clip.video_asset_key, new_key
                )
                new_clip.video_asset_key = new_key
            new_clip.localized_assets = {}
            new_clip.localized_copy = {}
            copied.append(new_clip)
        child.segments = copied

    async def _refresh_clip_copy(self, parent: Job, child: Job) -> None:
        candidates = [
            ClipCandidate(
                segment_id=clip.segment_id,
                start_seconds=0,
                end_seconds=1,
                hook_title=clip.hook_title,
                caption=clip.caption,
                rationale=clip.rationale,
                source_text=clip.source_text,
            )
            for clip in parent.segments
        ]
        source_text = "\n".join(clip.source_text for clip in parent.segments)
        transcript = Transcript(
            language=parent.source_language.code if parent.source_language else "en",
            duration_seconds=float(len(parent.segments)),
            words=[],
        )
        await self._cost.charge(
            child,
            stage=JobStage.INTELLIGENCE,
            provider="openrouter",
            model=child.model_overrides.get(
                "copy", self._settings.default_copy_model
            ).split("/", 1)[-1],
            units=float(len(source_text)),
            unit_type=CostUnitType.CHARACTERS,
        )
        bundle = await self._copywriter.write(
            transcript,
            candidates,
            model=child.model_overrides.get("copy", self._settings.default_copy_model),
        )
        by_id = {copy.segment_id: copy for copy in bundle.clips}
        for clip in child.segments:
            refreshed = by_id.get(clip.segment_id)
            if refreshed is not None:
                clip.hook_title = refreshed.vertical_title
                clip.caption = refreshed.caption

    def _validate_models(
        self,
        overrides: dict[str, str],
        defaults: dict[str, str] | None = None,
    ) -> dict[str, str]:
        resolved = {**self._settings.default_models, **(defaults or {})}
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
