"""Signed, at-most-once notification outbox."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from app.domain.enums import NotificationType
from app.domain.models import Job, NotificationOutboxEntry
from app.ports import Clock, Notifier, OutboxRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Queue one outbox entry per event and make exactly one delivery attempt."""

    def __init__(
        self,
        *,
        outbox: OutboxRepository,
        notifier: Notifier,
        clock: Clock,
    ) -> None:
        self._outbox = outbox
        self._notifier = notifier
        self._clock = clock

    async def queue(
        self,
        job: Job,
        notification_type: NotificationType,
        *,
        data: dict[str, Any] | None = None,
    ) -> NotificationOutboxEntry:
        payload = {
            "job_id": job.job_id,
            "status": job.status.value,
        }
        if data:
            payload.update(data)
        if "review_url" not in payload:
            payload["review_url"] = None
        entry = NotificationOutboxEntry(
            event_id=f"notify_{uuid4().hex[:16]}",
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            type=notification_type,
            payload=payload,
            created_at=self._clock.now(),
        )
        await self._outbox.add(entry)
        return entry

    async def dispatch_pending(self) -> int:
        delivered = 0
        for entry in await self._outbox.list_pending():
            # Mark the attempt before sending: a crash loses the notification rather than
            # duplicating it. This is the at-most-once contract.
            entry.status = "attempting"
            entry.attempts += 1
            await self._outbox.save(entry)
            try:
                await self._notifier.deliver(
                    event_id=entry.event_id,
                    event_type=entry.type.value,
                    payload=entry.payload,
                    occurred_at=entry.created_at,
                )
            except Exception as exc:  # noqa: BLE001 - ambiguous failures are recorded
                entry.status = "failed"
                entry.last_error = str(exc)
                await self._outbox.save(entry)
                logger.warning("Notification %s failed: %s", entry.event_id, exc)
            else:
                entry.status = "sent"
                entry.sent_at = self._clock.now()
                await self._outbox.save(entry)
                delivered += 1
        return delivered
