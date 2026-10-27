"""Webhook triggers for Google Drive, YouTube, Zoom and dashboard uploads."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import ContainerDep
from app.api.schemas import IngestWebhook, JobAccepted
from app.domain.enums import WebhookSource

router = APIRouter(tags=["webhooks"])


@router.post(
    "/webhooks/{source}",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_webhook(
    source: WebhookSource,
    payload: IngestWebhook,
    request: Request,
    container: ContainerDep,
) -> JobAccepted:
    _verify_secret(request, container.settings.webhook_secret)

    job = await container.submissions.submit(
        input_url=payload.input_url,
        target_languages=payload.target_languages,
    )
    return JobAccepted(job_id=job.job_id, status=job.status)


def _verify_secret(request: Request, expected: str | None) -> None:
    if not expected:
        return

    provided = request.headers.get("x-webhook-secret", "")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )
