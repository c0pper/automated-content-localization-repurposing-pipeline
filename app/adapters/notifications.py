"""Notification adapters (log locally, POST a webhook in production)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from app.domain.models import Job

logger = logging.getLogger(__name__)


class LogNotifier:
    async def notify(self, job: Job, links: Sequence[str]) -> None:
        logger.info(
            "Job %s completed with %d assets: %s",
            job.job_id,
            len(links),
            ", ".join(links),
        )


class WebhookNotifier:
    """POST the completed review bundle to Slack/Telegram/Zapier-style endpoints."""

    def __init__(self, url: str, *, timeout: float = 15.0) -> None:
        self._url = url
        self._timeout = timeout

    async def notify(self, job: Job, links: Sequence[str]) -> None:
        payload = {
            "job_id": job.job_id,
            "status": job.status.value,
            "languages": job.target_languages,
            "segments": [segment.model_dump(mode="json") for segment in job.segments],
            "links": list(links),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, json=payload)
            response.raise_for_status()
        logger.info("Delivered job %s notification to %s", job.job_id, self._url)
