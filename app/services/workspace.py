"""Workspace Settings, Voice Profile and settings audit."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.config import Settings
from app.domain.errors import ApiError, GuardrailViolation
from app.domain.models import (
    VoiceProfile,
    WorkspaceAuditEntry,
    WorkspaceSettings,
)
from app.ports import Clock, WorkspaceRepository
from app.services.cost import CostService


class WorkspaceService:
    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        cost: CostService,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._workspaces = workspaces
        self._cost = cost
        self._clock = clock
        self._settings = settings

    async def ensure_settings(self) -> WorkspaceSettings:
        existing = await self._workspaces.get_settings(self._settings.workspace_id)
        if existing is not None:
            return existing
        from app.domain.money import parse_usd

        created = WorkspaceSettings(
            workspace_id=self._settings.workspace_id,
            target_language_allowlist=self._settings.allowlist,
            default_models=self._settings.default_models,
            job_budget_micro_usd=parse_usd(self._settings.job_budget_usd),
            monthly_budget_micro_usd=parse_usd(self._settings.monthly_budget_usd),
            max_concurrent_jobs=self._settings.max_concurrent_jobs,
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        await self._workspaces.save_settings(created)
        return created

    async def get_settings(self) -> WorkspaceSettings:
        return await self.ensure_settings()

    async def update_settings(self, payload: dict[str, Any]) -> WorkspaceSettings:
        current = await self.ensure_settings()
        allowlist = payload.get("target_language_allowlist", current.target_language_allowlist)
        if not isinstance(allowlist, list) or not allowlist:
            raise GuardrailViolation(
                "invalid_allowlist", "target_language_allowlist must be a non-empty list"
            )
        allowlist = [str(language) for language in allowlist]
        if len(set(allowlist)) != len(allowlist):
            raise GuardrailViolation("invalid_allowlist", "Target languages must be unique")
        unsupported = [
            language
            for language in allowlist
            if language not in self._settings.source_languages
        ]
        if unsupported:
            raise GuardrailViolation(
                "unsupported_language",
                "The configured providers do not support every allowlist language",
                details={"languages": unsupported},
            )

        default_models = payload.get("default_models", current.default_models)
        if not isinstance(default_models, dict):
            raise GuardrailViolation("invalid_model", "default_models must be an object")
        for task, model in default_models.items():
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

        job_budget = payload.get("job_budget_micro_usd", current.job_budget_micro_usd)
        monthly_budget = payload.get(
            "monthly_budget_micro_usd", current.monthly_budget_micro_usd
        )
        if int(job_budget) <= 0 or int(monthly_budget) <= 0:
            raise GuardrailViolation(
                "invalid_budget", "Budgets must be positive"
            )
        max_concurrent = int(
            payload.get("max_concurrent_jobs", current.max_concurrent_jobs)
        )
        if max_concurrent < 1 or max_concurrent > self._settings.worker_capacity:
            raise GuardrailViolation(
                "invalid_concurrency",
                f"max_concurrent_jobs must be between 1 and "
                f"{self._settings.worker_capacity}",
            )

        updated = current.model_copy(
            update={
                "target_language_allowlist": allowlist,
                "default_models": dict(default_models),
                "job_budget_micro_usd": int(job_budget),
                "monthly_budget_micro_usd": int(monthly_budget),
                "max_concurrent_jobs": max_concurrent,
                "updated_at": self._clock.now(),
            }
        )
        await self._workspaces.save_settings(updated)
        await self._audit("settings_updated", updated.model_dump(mode="json"))
        return updated

    async def get_voice_profile(self) -> VoiceProfile | None:
        return await self._workspaces.get_voice_profile(self._settings.workspace_id)

    async def set_voice_profile(self, payload: dict[str, Any]) -> VoiceProfile:
        voice_id = str(payload.get("voice_id", "")).strip()
        provider = str(payload.get("provider", "elevenlabs")).strip() or "elevenlabs"
        if provider != "elevenlabs":
            raise GuardrailViolation(
                "unsupported_voice_provider",
                "v1 supports the ElevenLabs Voice Profile provider only",
            )
        if not voice_id:
            raise GuardrailViolation("invalid_voice_profile", "voice_id is required")
        existing = await self.get_voice_profile()
        now = self._clock.now()
        profile = VoiceProfile(
            workspace_id=self._settings.workspace_id,
            provider=provider,
            voice_id=voice_id,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._workspaces.save_voice_profile(profile)
        await self._audit("voice_profile_set", {"provider": provider, "voice_id": voice_id})
        return profile

    async def delete_voice_profile(self) -> None:
        await self._workspaces.delete_voice_profile(self._settings.workspace_id)
        await self._audit("voice_profile_deleted", {})

    async def snapshot(self) -> dict[str, Any]:
        settings = await self.ensure_settings()
        spent = await self._cost.workspace_spend(settings.workspace_id)
        voice = await self.get_voice_profile()
        return {
            "workspace_id": settings.workspace_id,
            "target_language_allowlist": settings.target_language_allowlist,
            "default_models": settings.default_models,
            "job_budget_micro_usd": settings.job_budget_micro_usd,
            "monthly_budget_micro_usd": settings.monthly_budget_micro_usd,
            "max_concurrent_jobs": settings.max_concurrent_jobs,
            # Deployment config, not a stored Workspace setting: read-only here.
            "max_video_minutes": self._settings.max_video_minutes,
            "current_month_spend_micro_usd": spent,
            "remaining_micro_usd": max(
                0, settings.monthly_budget_micro_usd - spent
            ),
            "voice_profile": (
                {
                    "provider": voice.provider,
                    "voice_id": voice.voice_id,
                    "updated_at": voice.updated_at,
                }
                if voice
                else None
            ),
        }

    async def remaining_budget(self) -> int:
        settings = await self.ensure_settings()
        spent = await self._cost.workspace_spend(settings.workspace_id)
        return max(0, settings.monthly_budget_micro_usd - spent)

    async def audit_log(self) -> list[WorkspaceAuditEntry]:
        return await self._workspaces.list_audit(self._settings.workspace_id)

    async def _audit(self, action: str, payload: dict[str, Any]) -> None:
        await self._workspaces.append_audit(
            WorkspaceAuditEntry(
                audit_id=f"audit_{uuid4().hex[:12]}",
                workspace_id=self._settings.workspace_id,
                action=action,
                payload=payload,
                created_at=self._clock.now(),
            )
        )


def require_voice_profile(profile: VoiceProfile | None) -> VoiceProfile:
    if profile is None:
        raise ApiError(
            409,
            "voice_profile_missing",
            "The Workspace has no Voice Profile; register one before localization",
            retryable=True,
        )
    return profile
