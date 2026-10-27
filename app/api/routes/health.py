"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(container: ContainerDep) -> dict[str, object]:
    return {
        "status": "ok",
        "environment": container.settings.environment,
        "media_backend": container.settings.media_backend,
        "worker_enabled": container.settings.run_worker,
    }
