"""Cost Ledger and budget enforcement.

Every paid call is projected before it starts. The Job Budget and the monthly Workspace
Budget are both checked, and a missing rate fails closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.enums import CostUnitType, JobStage
from app.domain.errors import GuardrailViolation
from app.domain.models import CostLedgerEntry, Job, WorkspaceSettings
from app.domain.rate_card import RateCard
from app.ports import Clock, CostLedgerRepository, WorkspaceRepository


class CostService:
    def __init__(
        self,
        *,
        ledger: CostLedgerRepository,
        workspaces: WorkspaceRepository,
        rate_card: RateCard,
        clock: Clock,
    ) -> None:
        self._ledger = ledger
        self._workspaces = workspaces
        self._rate_card = rate_card
        self._clock = clock

    @property
    def rate_card(self) -> RateCard:
        return self._rate_card

    async def settings_for(self, workspace_id: str) -> WorkspaceSettings:
        settings = await self._workspaces.get_settings(workspace_id)
        if settings is None:
            settings = WorkspaceSettings(workspace_id=workspace_id)
        return settings

    def month_bounds(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        current = now or self._clock.now()
        start = datetime(current.year, current.month, 1, tzinfo=UTC)
        if current.month == 12:
            end = datetime(current.year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
        return start, end

    async def job_spend(self, job_id: str) -> int:
        return sum(entry.estimated_micro_usd for entry in await self._ledger.list_for_job(job_id))

    async def workspace_spend(self, workspace_id: str, *, now: datetime | None = None) -> int:
        start, end = self.month_bounds(now)
        entries = await self._ledger.list_for_workspace(workspace_id)
        return sum(
            entry.estimated_micro_usd
            for entry in entries
            if start <= entry.created_at < end
        )

    async def check_budgets(
        self,
        job: Job,
        projected_micro_usd: int,
        *,
        settings: WorkspaceSettings | None = None,
    ) -> None:
        if projected_micro_usd < 0:
            raise GuardrailViolation("invalid_cost", "Projected cost cannot be negative")

        job_spend = await self.job_spend(job.job_id)
        if job_spend + projected_micro_usd > job.job_budget_micro_usd:
            raise GuardrailViolation(
                "insufficient_job_budget",
                f"Job spend {job_spend} + projected {projected_micro_usd} exceeds the "
                f"Job Budget of {job.job_budget_micro_usd} micro-USD",
                retryable=False,
            )

        workspace_settings = settings or await self.settings_for(job.workspace_id)
        workspace_spend = await self.workspace_spend(job.workspace_id)
        if (
            workspace_spend + projected_micro_usd
            > workspace_settings.monthly_budget_micro_usd
        ):
            raise GuardrailViolation(
                "workspace_budget_exceeded",
                "The monthly Workspace Budget would be exceeded; raise the cap or wait "
                "for the next calendar month",
                retryable=True,
            )

    async def record(
        self,
        job: Job,
        *,
        stage: JobStage,
        provider: str,
        model: str,
        units: float,
        unit_type: CostUnitType,
    ) -> CostLedgerEntry:
        projected = self._rate_card.estimate(
            provider, model, units, unit_type=unit_type
        )
        await self.check_budgets(job, projected)
        rate = self._rate_card.resolve(provider, model)
        entry = CostLedgerEntry(
            entry_id=f"cost_{uuid4().hex[:12]}",
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            stage=stage,
            provider=provider,
            model=model,
            units=units,
            unit_type=unit_type,
            base_rate_micro_usd=rate.micro_usd_per_unit,
            margin=self._rate_card.margin,
            estimated_micro_usd=projected,
            rate_card_version=self._rate_card.version,
            created_at=self._clock.now(),
        )
        await self._ledger.append(entry)
        return entry

    async def charge(
        self,
        job: Job,
        *,
        stage: JobStage,
        provider: str,
        model: str,
        units: float,
        unit_type: CostUnitType,
    ) -> CostLedgerEntry:
        """Alias used by agents: check both budgets, then append the estimate."""
        return await self.record(
            job,
            stage=stage,
            provider=provider,
            model=model,
            units=units,
            unit_type=unit_type,
        )

    async def entries(self, job_id: str) -> list[CostLedgerEntry]:
        return await self._ledger.list_for_job(job_id)

    async def summary(self, job: Job) -> dict[str, int]:
        spent = await self.job_spend(job.job_id)
        settings = await self.settings_for(job.workspace_id)
        workspace_spend = await self.workspace_spend(job.workspace_id)
        return {
            "job_budget_micro_usd": job.job_budget_micro_usd,
            "spent_micro_usd": spent,
            "workspace_budget_micro_usd": settings.monthly_budget_micro_usd,
            "workspace_spend_micro_usd": workspace_spend,
            "workspace_remaining_micro_usd": max(
                0, settings.monthly_budget_micro_usd - workspace_spend
            ),
        }
