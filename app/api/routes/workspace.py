"""Workspace Settings, Voice Profile and Purge endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep
from app.api.schemas import PresignedUploadRequest, PurgeRequest, VoiceProfileRequest, WorkspaceUpdate
from app.api.views import workspace_view
from app.domain.errors import ApiError
from app.domain.money import parse_usd

router = APIRouter(tags=["workspace"])


@router.get("/workspace")
async def get_workspace(container: ContainerDep) -> dict:
    return workspace_view(await container.workspaces.snapshot())


@router.post("/workspace/uploads/presign")
async def presign_upload(
    payload: PresignedUploadRequest,
    container: ContainerDep,
) -> dict:
    """Issue a short-lived presigned URL for uploading an object under uploads/."""
    key = payload.key
    if not key.startswith("uploads/"):
        raise ApiError(422, "invalid_key", "Upload key must start with 'uploads/'")
    # Guard against traversal and double slashes.
    if ".." in key.split("/"):
        raise ApiError(422, "invalid_key", "Upload key must not contain '..'")
    if "//" in key:
        raise ApiError(422, "invalid_key", "Upload key must not contain '//'")

    expected_key = f"uploads/{key[len('uploads/'):]}"
    url = await container.store.presign(
        expected_key,
        ttl_seconds=container.settings.presign_ttl_seconds,
    )
    return {"upload_url": url, "key": expected_key}


@router.put("/workspace")
async def put_workspace(payload: WorkspaceUpdate, container: ContainerDep) -> dict:
    try:
        job_budget = parse_usd(payload.job_budget_usd)
        monthly_budget = parse_usd(payload.monthly_budget_usd)
    except ValueError as exc:
        raise ApiError(422, "invalid_amount", str(exc)) from exc
    await container.workspaces.update_settings(
        {
            "target_language_allowlist": payload.target_language_allowlist,
            "default_models": payload.default_models,
            "job_budget_micro_usd": job_budget,
            "monthly_budget_micro_usd": monthly_budget,
            "max_concurrent_jobs": payload.max_concurrent_jobs,
        }
    )
    return workspace_view(await container.workspaces.snapshot())


@router.get("/workspace/voice-profile")
async def get_voice_profile(container: ContainerDep) -> dict:
    profile = await container.workspaces.get_voice_profile()
    if profile is None:
        return {"voice_profile": None}
    return {
        "voice_profile": {
            "provider": profile.provider,
            "voice_id": profile.voice_id,
            "updated_at": profile.updated_at.isoformat().replace("+00:00", "Z"),
        }
    }


@router.put("/workspace/voice-profile")
async def put_voice_profile(payload: VoiceProfileRequest, container: ContainerDep) -> dict:
    profile = await container.workspaces.set_voice_profile(
        {"provider": payload.provider, "voice_id": payload.voice_id}
    )
    return {
        "voice_profile": {
            "provider": profile.provider,
            "voice_id": profile.voice_id,
            "updated_at": profile.updated_at.isoformat().replace("+00:00", "Z"),
        }
    }


@router.delete("/workspace/voice-profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_profile(container: ContainerDep) -> Response:
    await container.workspaces.delete_voice_profile()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/workspace/purge/dry-run")
async def purge_dry_run(container: ContainerDep) -> dict:
    return await container.purge.dry_run()


@router.post("/workspace/purge", status_code=status.HTTP_202_ACCEPTED)
async def purge_confirm(payload: PurgeRequest, container: ContainerDep) -> dict:
    purge = await container.purge.confirm(
        workspace_id=payload.workspace_id,
        confirmation_token=payload.confirmation_token,
    )
    return {"purge_id": purge.purge_id, "status": purge.status.value}


@router.get("/workspace/purge/{purge_id}")
async def purge_status(purge_id: str, container: ContainerDep) -> dict:
    purge = await container.purge.status(purge_id)
    return {
        "purge_id": purge.purge_id,
        "status": purge.status.value,
        "counts": purge.dry_run_counts,
        "created_at": purge.created_at.isoformat().replace("+00:00", "Z"),
        "completed_at": (
            purge.completed_at.isoformat().replace("+00:00", "Z")
            if purge.completed_at
            else None
        ),
        "error": purge.error,
    }
