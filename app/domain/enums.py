"""Domain enums shared by agents, API and persistence."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Coarse job state exposed to clients (see AGENTS.md data schema)."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStage(StrEnum):
    """Finer-grained position inside the pipeline, useful for progress reporting."""

    INGEST = "ingest"
    INTELLIGENCE = "intelligence"
    VIDEO = "video"
    LOCALIZATION = "localization"
    DELIVERY = "delivery"


class WebhookSource(StrEnum):
    DRIVE = "drive"
    YOUTUBE = "youtube"
    ZOOM = "zoom"
    WEB = "web"
