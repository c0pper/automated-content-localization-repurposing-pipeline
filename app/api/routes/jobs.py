"""Job endpoints: submission, status, gate, lifecycle, review links and assets."""

from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import ContainerDep
from app.api.schemas import DeriveRequest, JobAccepted, JobList, JobSubmission, SelectionRequest
from app.api.views import event_view, job_summary, job_view, ledger_view
from app.domain.enums import JobStatus
from app.domain.errors import ApiError
from app.domain.money import format_usd, parse_usd

router = APIRouter(tags=["jobs"])


async def _job(container, job_id: str):
    job = await container.repository.get(job_id)
    if job is None:
        raise ApiError(404, "not_found", f"Unknown job: {job_id}")
    return job


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: JobSubmission,
    container: ContainerDep,
    response: Response,
) -> JobAccepted:
    job = await container.submissions.submit(
        source=payload.source.to_domain(),
        target_languages=payload.target_languages,
        source_language=payload.source_language,
        lip_sync=payload.lip_sync,
        model_overrides=payload.model_overrides,
    )
    response.headers["Location"] = f"/api/jobs/{job.job_id}"
    return JobAccepted(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at.isoformat().replace("+00:00", "Z"),
    )


@router.get("/jobs", response_model=JobList)
async def list_jobs(
    container: ContainerDep,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> JobList:
    jobs = await container.repository.list_for_workspace(
        container.settings.workspace_id, status=status_filter
    )
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    start = 0
    if cursor:
        decoded = _decode_cursor(cursor)
        for index, job in enumerate(jobs):
            if job.job_id == decoded:
                start = index + 1
                break
    window = jobs[start : start + limit]
    next_cursor = None
    if start + limit < len(jobs) and window:
        next_cursor = _encode_cursor(window[-1].job_id)
    return JobList(
        items=[job_summary(job, review=container.review) for job in window],
        next_cursor=next_cursor,
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    return await job_view(job, cost=container.cost, review=container.review)


@router.get("/jobs/{job_id}/bundle")
async def get_bundle(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    return container.review.manifest(job)


@router.get("/jobs/{job_id}/events")
async def get_events(
    job_id: str,
    container: ContainerDep,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict:
    await _job(container, job_id)
    events = await container.events.list(job_id)
    start = 0
    if cursor:
        decoded = _decode_cursor(cursor)
        for index, event in enumerate(events):
            if event.event_id == decoded:
                start = index + 1
                break
    window = events[start : start + limit]
    next_cursor = (
        _encode_cursor(window[-1].event_id)
        if start + limit < len(events) and window
        else None
    )
    return {"items": [event_view(event) for event in window], "next_cursor": next_cursor}


@router.get("/jobs/{job_id}/cost")
async def get_cost(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    summary = await container.cost.summary(job)
    entries = await container.cost.entries(job_id)
    return {
        "job_budget_usd": format_usd(summary["job_budget_micro_usd"]),
        "spent_usd": format_usd(summary["spent_micro_usd"]),
        "entries": [ledger_view(entry) for entry in entries],
    }


@router.get("/jobs/{job_id}/selection")
async def get_selection(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    return await container.selection.gate_payload(job)


@router.post("/jobs/{job_id}/selection", status_code=status.HTTP_202_ACCEPTED)
async def confirm_selection(
    job_id: str,
    payload: SelectionRequest,
    container: ContainerDep,
) -> dict:
    job = await _job(container, job_id)
    try:
        expected = parse_usd(payload.expected_total_usd)
    except ValueError as exc:
        raise ApiError(422, "invalid_amount", str(exc)) from exc
    job = await container.selection.confirm(
        job,
        segment_ids=payload.segment_ids,
        languages=payload.languages,
        expected_total_micro_usd=expected,
    )
    return await job_view(job, cost=container.cost, review=container.review)


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_job(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    job = await container.lifecycle.cancel(job)
    return await job_view(job, cost=container.cost, review=container.review)


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    job = await container.lifecycle.retry(job)
    return await job_view(job, cost=container.cost, review=container.review)


@router.post("/jobs/{job_id}/derive", status_code=status.HTTP_202_ACCEPTED)
async def derive_job(
    job_id: str,
    payload: DeriveRequest,
    container: ContainerDep,
) -> dict:
    parent = await _job(container, job_id)
    child = await container.derived.derive(
        parent,
        mode=payload.mode,
        target_languages=payload.target_languages,
        lip_sync=payload.lip_sync,
        model_overrides=payload.model_overrides,
        refresh_long_form=payload.refresh_long_form,
    )
    return await job_view(child, cost=container.cost, review=container.review)


@router.post("/jobs/{job_id}/review-link")
async def rotate_review_link(job_id: str, container: ContainerDep) -> dict:
    job = await _job(container, job_id)
    raw = await container.review.rotate(job)
    await container.repository.save(job)
    return {
        "review_url": container.review.review_url(job, raw),
        "rotated_at": job.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.delete("/jobs/{job_id}/review-link", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_review_link(job_id: str, container: ContainerDep) -> Response:
    job = await _job(container, job_id)
    await container.review.revoke(job)
    await container.repository.save(job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/assets/{asset_id}")
async def get_job_asset(job_id: str, asset_id: str, container: ContainerDep):
    job = await _job(container, job_id)
    key = container.review.asset_key(job, asset_id)
    if key is None:
        raise ApiError(404, "not_found", f"Unknown asset: {asset_id}")
    url = await container.store.presign(
        key, ttl_seconds=container.settings.presign_ttl_seconds
    )
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> str:
    padding = "=" * (-len(cursor) % 4)
    try:
        return base64.urlsafe_b64decode(cursor + padding).decode()
    except Exception as exc:  # noqa: BLE001 - invalid cursors are a client error
        raise ApiError(422, "invalid_cursor", "The cursor is not valid") from exc
