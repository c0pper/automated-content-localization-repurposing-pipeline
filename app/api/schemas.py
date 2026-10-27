"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import JobStatus
from app.domain.models import Job


class JobSubmission(BaseModel):
    input_url: str = Field(min_length=1)
    target_languages: list[str] = Field(default_factory=lambda: ["es"])

    @field_validator("target_languages")
    @classmethod
    def _normalize_languages(cls, languages: list[str]) -> list[str]:
        return [language.strip().lower() for language in languages]


class IngestWebhook(BaseModel):
    """Normalized payload for Drive/YouTube/Zoom/dashboard triggers."""

    input_url: str = Field(min_length=1)
    target_languages: list[str] = Field(default_factory=lambda: ["es"])

    @field_validator("target_languages")
    @classmethod
    def _normalize_languages(cls, languages: list[str]) -> list[str]:
        return [language.strip().lower() for language in languages]


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus


class JobList(BaseModel):
    items: list[Job]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail
