"""Standalone queue worker entrypoint used by the Compose worker service."""

from __future__ import annotations

import asyncio
import signal

from app.config import Settings
from app.container import build_container
from app.logging_config import configure_logging


async def run() -> None:
    settings = Settings()
    container = build_container(settings)
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            # Windows does not support asyncio signal handlers.
            pass

    try:
        await container.worker.run(stop)
    finally:
        if container.dispose is not None:
            await container.dispose()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
