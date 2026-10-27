"""Liveness and readiness checks."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

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


@router.get("/readyz")
async def readyz(container: ContainerDep) -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True

    try:
        await container.repository.list()
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - readiness reports, never raises
        checks["database"] = "error"
        healthy = False

    try:
        await container.store.list_keys("")
        checks["object_store"] = "ok"
    except Exception:  # noqa: BLE001
        checks["object_store"] = "error"
        healthy = False

    ping = getattr(container.queue, "ping", None)
    if ping is None:
        checks["queue"] = "ok"
    else:
        try:
            await ping()
            checks["queue"] = "ok"
        except Exception:  # noqa: BLE001
            checks["queue"] = "error"
            healthy = False

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
