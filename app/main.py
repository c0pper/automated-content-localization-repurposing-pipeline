"""FastAPI application factory.

Run locally with::

    uvicorn --factory app.main:create_app --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router, root_router
from app.config import Settings
from app.container import Container, build_container
from app.domain.errors import GuardrailViolation

logger = logging.getLogger(__name__)


def create_app(
    container: Container | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    container = container or build_container(settings or Settings())

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

        try:
            yield
        finally:
            stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="Automated Content Repurposing & Localization Pipeline",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = container

    @app.exception_handler(GuardrailViolation)
    async def handle_guardrail_violation(
        request: Request, exc: GuardrailViolation
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.as_dict()})

    assets_dir: Path = container.settings.objects_dir
    assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.include_router(root_router)
    app.include_router(api_router)
    return app
