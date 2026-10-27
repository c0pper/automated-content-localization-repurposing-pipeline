"""Domain errors."""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for expected pipeline failures."""


class UnknownJobError(PipelineError):
    """Raised when a job id cannot be found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Unknown job: {job_id}")
        self.job_id = job_id


class GuardrailViolation(PipelineError):
    """Raised when a job would exceed a cost, size or format guardrail."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class MediaProcessingError(PipelineError):
    """Raised when the media backend cannot process an asset."""


class ExternalServiceError(PipelineError):
    """Raised when a third-party API (LLM, TTS, storage, ...) fails."""
