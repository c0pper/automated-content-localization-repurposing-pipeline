"""FastAPI application factory.

Run locally with::

    uvicorn --factory app.main:create_app --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.adapters.local_object_store import LocalObjectStore
from app.api.middleware import ApiAuthMiddleware, IdempotencyMiddleware
from app.api.router import api_router, root_router
from app.config import Settings
from app.container import Container, build_container
from app.domain.errors import ApiError, UnknownJobError
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message, "details": details or {}}},
    )


async def _expiry_loop(container: Container, stop: asyncio.Event, interval: int) -> None:
    while not stop.is_set():
        try:
            await container.selection.expire_due_jobs()
        except Exception:  # noqa: BLE001 - a sweep failure must not kill the API
            logger.exception("Selection Gate expiry sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def _notification_loop(container: Container, stop: asyncio.Event, interval: int) -> None:
    while not stop.is_set():
        try:
            await container.notifications.dispatch_pending()
        except Exception:  # noqa: BLE001 - the outbox is at-most-once, never retried blindly
            logger.exception("Notification outbox sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


def create_app(
    container: Container | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    container = container or build_container(settings or Settings())
    if container.settings.environment == "production":
        configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        tasks: list[asyncio.Task[None]] = []

        if container.settings.run_worker:
            tasks.append(asyncio.create_task(container.worker.run(stop), name="queue-worker"))

        if container.settings.retention_sweep_seconds > 0:
            tasks.append(
                asyncio.create_task(
                    container.retention.run_forever(
                        stop,
                        interval_seconds=container.settings.retention_sweep_seconds,
                    ),
                    name="retention-sweeper",
                )
            )

        if container.settings.expiry_sweep_seconds > 0:
            tasks.append(
                asyncio.create_task(
                    _expiry_loop(
                        container, stop, container.settings.expiry_sweep_seconds
                    ),
                    name="selection-expiry-sweeper",
                )
            )

        if container.settings.notification_sweep_seconds > 0:
            tasks.append(
                asyncio.create_task(
                    _notification_loop(
                        container, stop, container.settings.notification_sweep_seconds
                    ),
                    name="notification-outbox",
                )
            )

        try:
            yield
        finally:
            stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if container.dispose is not None:
                await container.dispose()

    app = FastAPI(
        title="Automated Content Repurposing & Localization Pipeline",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.container = container

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.as_dict()})

    @app.exception_handler(UnknownJobError)
    async def handle_unknown_job(request: Request, exc: UnknownJobError) -> JSONResponse:
        return _error_response(404, "not_found", str(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422,
            "validation_error",
            "The request body or parameters are invalid",
            {"errors": exc.errors()},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Location"],
    )
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(ApiAuthMiddleware)

    assets_dir: Path = container.settings.objects_dir
    assets_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(container.store, LocalObjectStore):

        @app.get("/assets/{key:path}", include_in_schema=False)
        async def local_asset(
            key: str,
            expires: int = Query(...),
            signature: str = Query(...),
        ):
            if not container.store.verify_presigned(
                key, expires=expires, signature=signature
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": {
                            "code": "forbidden",
                            "message": "The asset link is invalid or expired",
                            "details": {},
                        }
                    },
                )
            path = container.store.local_path(key)
            if not path.is_file():
                return JSONResponse(
                    status_code=404,
                    content={
                        "detail": {
                            "code": "not_found",
                            "message": "Unknown asset",
                            "details": {},
                        }
                    },
                )
            return FileResponse(path)

    app.include_router(root_router)
    app.include_router(api_router)
    return app
