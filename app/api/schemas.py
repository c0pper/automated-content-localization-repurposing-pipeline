"""API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import JobStatus
from app.domain.models import SourceInput


class SourcePayload(BaseModel):
    type: Literal["url", "object"]
    url: str | None = None
    key: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> SourcePayload:
        if self.type == "url" and not self.url:
            raise ValueError("A url source requires 'url'")
        if self.type == "object" and not self.key:
            raise ValueError("An object source requires 'key'")
        return self

    def to_domain(self) -> SourceInput:
        return SourceInput(type=self.type, url=self.url, key=self.key)


class JobSubmission(BaseModel):
    source: SourcePayload | None = None
    input_url: str | None = None
    source_language: str | None = None
    target_languages: list[str] = Field(default_factory=lambda: ["es"])
    lip_sync: bool = False
    model_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _source(self) -> JobSubmission:
        if self.source is None:
            if not self.input_url:
                raise ValueError("A source is required")
            if self.input_url.lower().startswith(("http://", "https://", "file://")):
                self.source = SourcePayload(type="url", url=self.input_url)
            else:
                self.source = SourcePayload(type="object", key=self.input_url)
        return self


class IngestWebhook(JobSubmission):
    pass


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str


class JobList(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class SelectionRequest(BaseModel):
    segment_ids: list[int] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    expected_total_usd: str = "0.00"


class DeriveRequest(BaseModel):
    mode: Literal["copy", "localization"]
    target_languages: list[str] | None = None
    lip_sync: bool = False
    model_overrides: dict[str, str] = Field(default_factory=dict)
    refresh_long_form: bool = False


class WorkspaceUpdate(BaseModel):
    target_language_allowlist: list[str]
    default_models: dict[str, str] = Field(default_factory=dict)
    job_budget_usd: str
    monthly_budget_usd: str
    max_concurrent_jobs: int = Field(ge=1)


class VoiceProfileRequest(BaseModel):
    provider: str = "elevenlabs"
    voice_id: str = Field(min_length=1)


class PurgeRequest(BaseModel):
    workspace_id: str
    confirmation_token: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: ErrorDetail
