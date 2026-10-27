"""In-process asyncio task queue.

Replace with Celery/Redis or QStash in production to get durable, rate-limited workers.
"""

from __future__ import annotations

import asyncio


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    async def dequeue(self, poll_timeout: float | None = None) -> str | None:
        if poll_timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=poll_timeout)
        except TimeoutError:
            return None

    def size(self) -> int:
        return self._queue.qsize()

    async def ping(self) -> bool:
        return True
