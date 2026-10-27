"""Domain models.

``Clip`` is the canonical internal name; ``Job.segments`` and ``Clip.segment_id`` remain
the public wire aliases documented in AGENTS.md.

Money is integer micro-USD. Scores are 0-100 floats; Jev signal values are 0-4 floats.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    CostUnitType,
    DerivedMode,
    JobStage,
    JobStatus,
    LocalizedClipStatus,
    NotificationType,
    PurgeStatus,
    SourceLanguageOrigin,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class MediaProbe(BaseModel):
    """Result of inspecting the raw input asset."""

    duration_seconds: float = Field(ge=0)
    width: int | None = None
    height: int | None = None
    has_audio: bool
    container: str | None = None


class TranscriptWord(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def _end_after_start(self) -> TranscriptWord:
        self.end = max(self.end, self.start)
        return self


class Transcript(BaseModel):
    """Word-level transcript produced by the intelligence stage."""

    language: str = "en"
    duration_seconds: float = Field(ge=0)
    words: list[TranscriptWord] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    def text_between(self, start_seconds: float, end_seconds: float) -> str:
        """Return text for words overlapping the given window."""
        words = [
            word.text
            for word in self.words
            if word.end > start_seconds and word.start < end_seconds
        ]
        return " ".join(words)


class ClipCandidate(BaseModel):
    """A high-value moment chosen by the intelligence agent."""

    segment_id: Annotated[int, Field(ge=1)]
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    hook_title: str
    caption: str
    rationale: str = ""
    source_text: str = ""

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


class ClipCopy(BaseModel):
    segment_id: int
    vertical_title: str
    caption: str


class ContentBundle(BaseModel):
    """Multi-channel copy generated alongside the clips."""

    clips: list[ClipCopy] = Field(default_factory=list)
    linkedin_post: str = ""
    newsletter: str = ""


class SourceLanguage(BaseModel):
    """Effective Source Language plus provenance for audit."""

    code: str = Field(min_length=2)
    origin: SourceLanguageOrigin
    detected_code: str | None = None


class Selection(BaseModel):
    """The confirmed rectangular Clip-by-Language selection."""

    segment_ids: list[int] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    expected_total_micro_usd: int = Field(default=0, ge=0)
    confirmed_at: datetime = Field(default_factory=utc_now)


class LocalizedClip(BaseModel):
    """Per Clip-by-Language result and checkpoint."""

    clip_id: str
    language: str
    localized_hook_title: str = ""
    localized_caption: str = ""
    audio_asset_key: str | None = None
    video_asset_key: str | None = None
    lip_sync: bool = False
    status: LocalizedClipStatus = LocalizedClipStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)


class Clip(BaseModel):
    """A rendered Base Clip.

    ``segment_id`` and ``Job.segments`` are the public wire aliases; new code uses Clip.
    ``source_text`` and the Base Clip Master key are internal and never serialized into the
    public Job or Review Bundle.
    """

    segment_id: int
    start_time: str
    end_time: str
    hook_title: str
    caption: str
    video_asset_url: str | None = None
    localized_assets: dict[str, str] = Field(default_factory=dict)
    source_text: str = Field(default="", exclude=True)
    base_clip_master_key: str | None = Field(default=None, exclude=True)


# Backward-compatible import for code and tests written before the Clip prefactor.
Segment = Clip


class Usage(BaseModel):
    """Tracked spend inputs, used by the cost guardrails."""

    input_minutes: float = Field(default=0.0, ge=0)
    characters: int = Field(default=0, ge=0)


class CostLedgerEntry(BaseModel):
    """Append-only record of one paid provider call."""

    entry_id: str
    job_id: str
    stage: JobStage
    provider: str
    model: str
    units: float = Field(ge=0)
    unit_type: CostUnitType
    base_rate_micro_usd: int = Field(ge=0)
    margin: float = Field(default=0.20, ge=0)
    estimated_micro_usd: int = Field(ge=0)
    actual_micro_usd: int | None = Field(default=None, ge=0)
    rate_card_version: str
    created_at: datetime = Field(default_factory=utc_now)


class JobEvent(BaseModel):
    """Append-only lifecycle/audit entry for a Job."""

    event_id: str
    job_id: str
    type: str
    stage: JobStage | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class NotificationOutboxEntry(BaseModel):
    """One signed webhook attempt."""

    event_id: str
    job_id: str
    type: NotificationType
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    sent_at: datetime | None = None


class IdempotencyRecord(BaseModel):
    """Stored response for a Workspace-scoped idempotency key."""

    workspace_id: str
    key: str
    method: str
    path: str
    request_hash: str
    response_status: int
    response_body: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime


class ReviewToken(BaseModel):
    """Opaque, hashed, revocable read-only access to one Job."""

    token_id: str
    job_id: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


class VoiceProfile(BaseModel):
    """The Creator's provider-side voice ID; raw samples are never stored."""

    workspace_id: str
    provider: str = "elevenlabs"
    voice_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkspaceSettings(BaseModel):
    """Workspace-level defaults and ceilings."""

    workspace_id: str
    target_language_allowlist: list[str] = Field(
        default_factory=lambda: ["en", "es", "de", "pt-BR", "fr", "it"]
    )
    default_models: dict[str, str] = Field(default_factory=dict)
    job_budget_micro_usd: int = Field(default=50_000_000, ge=0)
    monthly_budget_micro_usd: int = Field(default=500_000_000, ge=0)
    max_concurrent_jobs: int = Field(default=2, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Purge(BaseModel):
    """Two-step Workspace deletion operation."""

    purge_id: str
    workspace_id: str
    status: PurgeStatus = PurgeStatus.DRY_RUN
    dry_run_counts: dict[str, int] = Field(default_factory=dict)
    confirmation_token_hash: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class Job(BaseModel):
    """The unit of work shared between every agent."""

    model_config = ConfigDict(validate_assignment=True)

    job_id: str
    status: JobStatus = JobStatus.RECEIVED
    stage: JobStage | None = None
    input_url: str
    source_language: SourceLanguage | None = None
    target_languages: list[str] = Field(default_factory=list)
    lip_sync: bool = False
    model_overrides: dict[str, str] = Field(default_factory=dict)
    job_budget_micro_usd: int = Field(default=50_000_000, ge=0)
    parent_job_id: str | None = None
    derived_mode: DerivedMode | None = None
    expires_at: datetime | None = None
    segments: list[Clip] = Field(default_factory=list)
    content: ContentBundle | None = None
    selection: Selection | None = None
    usage: Usage = Field(default_factory=Usage)
    error: str | None = None
    error_code: str | None = None
    retryable: bool = False
    review_token_hash: str | None = Field(default=None, exclude=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def clips(self) -> list[Clip]:
        """Canonical internal view of the wire ``segments`` list."""
        return self.segments

    def transition_to(self, target: JobStatus) -> None:
        """Apply a guarded lifecycle transition."""
        if self.status == target:
            return

        from app.domain.lifecycle import ensure_transition

        ensure_transition(self.status, target)
        self.status = target

    def touch(self) -> None:
        self.updated_at = utc_now()
