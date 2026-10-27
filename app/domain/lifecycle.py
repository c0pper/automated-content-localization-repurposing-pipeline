"""Job lifecycle transitions.

The transition table is the single source of truth for legal status changes. A same-state
transition is a no-op so idempotent retry/requeue paths can call it safely.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import JobStatus
from app.domain.errors import InvalidJobTransitionError

_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.RECEIVED: frozenset({JobStatus.PROCESSING, JobStatus.CANCELLED}),
    JobStatus.PROCESSING: frozenset(
        {
            JobStatus.AWAITING_SELECTION,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.AWAITING_SELECTION: frozenset(
        {
            JobStatus.PROCESSING,
            JobStatus.EXPIRED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.FAILED: frozenset({JobStatus.PROCESSING}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.EXPIRED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def allowed_transitions(status: JobStatus) -> Iterable[JobStatus]:
    """Return the statuses reachable from ``status``."""
    return _ALLOWED[status]


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    """Return whether ``current -> target`` is legal (or a no-op)."""
    return current == target or target in _ALLOWED[current]


def ensure_transition(current: JobStatus, target: JobStatus) -> None:
    """Raise if ``current -> target`` is not a legal lifecycle transition."""
    if not can_transition(current, target):
        raise InvalidJobTransitionError(current, target)
