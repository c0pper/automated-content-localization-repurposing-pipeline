"""Apply the database schema.

The Compose ``migrate`` service runs this module before the API and worker start. It is
idempotent: SQLAlchemy creates only missing tables and the SQL migration uses
``IF NOT EXISTS`` guards.
"""

from __future__ import annotations

import asyncio

from app.adapters.sql_repository import SQLDatabase
from app.config import Settings


async def main() -> None:
    settings = Settings()
    settings.ensure_directories()
    if settings.repository_backend not in {"postgres", "sqlite"}:
        raise RuntimeError(
            "Migrations require PIPELINE_REPOSITORY_BACKEND=postgres (or sqlite for local runs)"
        )
    database = SQLDatabase.from_settings(settings)
    try:
        await database.ensure_schema()
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
