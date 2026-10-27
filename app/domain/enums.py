"""Domain enums shared by agents, API and persistence."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Coarse job state exposed to clients (see AGENTS.md data schema)."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    AWAITING_SELECTION = "AWAITING_SELECTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """Terminal states cannot change without a new Job.

        ``FAILED`` is intentionally not terminal: an explicit retry reopens it under the
        same Job ID and budget.
        """
        return self in {JobStatus.COMPLETED, JobStatus.EXPIRED, JobStatus.CANCELLED}


class JobStage(StrEnum):
    """Finer-grained position inside the pipeline, useful for progress reporting."""

    INGEST = "ingest"
    INTELLIGENCE = "intelligence"
    SCORING = "scoring"
    VIDEO = "video"
    LOCALIZATION = "localization"
    DELIVERY = "delivery"


class SourceLanguageOrigin(StrEnum):
    """How the effective Source Language was established."""

    DECLARED = "declared"
    DETECTED = "detected"
    FALLBACK = "fallback"


class DerivedMode(StrEnum):
    """The two supported kinds of Derived Job."""

    COPY = "copy"
    LOCALIZATION = "localization"


class NotificationType(StrEnum):
    """Signed notification events emitted by the pipeline."""

    SELECTION_REQUIRED = "selection_required"
    BUNDLE_READY = "bundle_ready"
    SELECTION_EXPIRED = "selection_expired"


class LocalizedClipStatus(StrEnum):
    """Per Clip-by-Language checkpoint state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CostUnitType(StrEnum):
    """Provider billing units recorded in the Cost Ledger."""

    MINUTES = "minutes"
    CHARACTERS = "characters"
    REQUESTS = "requests"
    SECONDS = "seconds"


class PurgeStatus(StrEnum):
    """Lifecycle of a two-step Workspace Purge."""

    DRY_RUN = "dry_run"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"


class WebhookSource(StrEnum):
    DRIVE = "drive"
    YOUTUBE = "youtube"
    ZOOM = "zoom"
    WEB = "web"
