"""Inbound webhook triggers (shared secret, idempotent on the provider event ID)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, status

from app.api.deps import ContainerDep
from app.api.schemas import IngestWebhook, JobAccepted
from app.domain.enums import WebhookSource
from app.domain.errors import ApiError

router = APIRouter(tags=["webhooks"])


@router.post(
    "/webhooks/{source}",
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
        source=payload.source.to_domain(),
        target_languages=payload.target_languages,
        source_language=payload.source_language,
        lip_sync=payload.lip_sync,
        model_overrides=payload.model_overrides,
    )
    return JobAccepted(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at.isoformat().replace("+00:00", "Z"),
    )


def _verify_secret(request: Request, expected: str | None) -> None:
    if not expected:
        return

    provided = request.headers.get("x-webhook-secret", "")
    if not secrets.compare_digest(provided, expected):
        raise ApiError(401, "unauthorized", "Invalid webhook secret")
