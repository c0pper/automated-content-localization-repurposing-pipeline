"""Domain models.

``Job`` and ``Segment`` intentionally mirror the agent communication schema in AGENTS.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import JobStage, JobStatus


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


class Segment(BaseModel):
    """Public segment schema (see AGENTS.md)."""

    segment_id: int
    start_time: str
    end_time: str
    hook_title: str
    caption: str
    video_asset_url: str | None = None
    localized_assets: dict[str, str] = Field(default_factory=dict)


class Usage(BaseModel):
    """Tracked spend inputs, used by the cost guardrails."""

    input_minutes: float = Field(default=0.0, ge=0)
    characters: int = Field(default=0, ge=0)


class Job(BaseModel):
    """The unit of work shared between every agent."""

    model_config = ConfigDict(validate_assignment=True)

    job_id: str
    status: JobStatus = JobStatus.RECEIVED
    stage: JobStage | None = None
    input_url: str
    target_languages: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    content: ContentBundle | None = None
    usage: Usage = Field(default_factory=Usage)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
