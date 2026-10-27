"""Domain errors and the deterministic API error vocabulary."""

from __future__ import annotations

from typing import Any


class PipelineError(Exception):
    """Base class for expected pipeline failures."""


class UnknownJobError(PipelineError):
    """Raised when a job id cannot be found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Unknown job: {job_id}")
        self.job_id = job_id


class ApiError(PipelineError):
    """An error that maps directly to an HTTP status and error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class GuardrailViolation(ApiError):
    """Raised when a job would exceed a cost, size or format guardrail."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            status_code,
            code,
            message,
            details=details,
            retryable=retryable,
        )


class InvalidJobTransitionError(PipelineError):
    """Raised when a Job status change violates the lifecycle contract."""

    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"Invalid Job transition: {current} -> {target}")
        self.current = current
        self.target = target


class MediaProcessingError(PipelineError):
    """Raised when the media backend cannot process an asset."""


class ExternalServiceError(PipelineError):
    """Raised when a third-party API (LLM, TTS, storage, ...) fails."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class CancellationRequested(PipelineError):
    """Raised internally when a Job's durable cancel flag is observed."""


class QualityFloorNotMet(GuardrailViolation):
    def __init__(self, passing: int, floor: float) -> None:
        super().__init__(
            "quality_floor_not_met",
            f"{passing} Clip Candidates cleared the Quality Floor of {floor}; "
            "at least three are required",
            retryable=False,
        )
