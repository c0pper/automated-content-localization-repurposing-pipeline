"""Read-only review endpoints authenticated by the review token only."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import RedirectResponse

from app.api.deps import ContainerDep
from app.domain.errors import ApiError

router = APIRouter(tags=["review"])


async def _resolve(container, token: str):
    resolved = await container.review.resolve(token)
    if resolved is None:
        raise ApiError(404, "not_found", "Unknown or revoked review token")
    job = await container.repository.get(resolved.job_id)
    if job is None:
        raise ApiError(404, "not_found", "Unknown or revoked review token")
    return resolved, job


@router.get("/review/{token}")
async def review_manifest(token: str, container: ContainerDep) -> dict:
    _, job = await _resolve(container, token)
    return container.review.manifest(job, raw_token=token)


@router.get("/review/{token}/assets/{asset_id}")
async def review_asset(token: str, asset_id: str, container: ContainerDep):
    _, job = await _resolve(container, token)
    key = container.review.asset_key(job, asset_id)
    if key is None:
        raise ApiError(404, "not_found", f"Unknown asset: {asset_id}")
    url = await container.store.presign(
        key, ttl_seconds=container.settings.presign_ttl_seconds
    )
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)
