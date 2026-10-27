"""Redis-backed task queue.

A single list is enough for v1: jobs are idempotent to re-run, the orchestrator reloads the
aggregate and resumes from its last checkpoint, and concurrency is capped by workspace leases
rather than by queue depth.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_QUEUE_KEY = "pipeline:jobs"


class RedisTaskQueue:
    def __init__(self, url: str, *, key: str = _QUEUE_KEY) -> None:
        self._redis = Redis.from_url(url, decode_responses=True)
        self._key = key

    async def enqueue(self, job_id: str) -> None:
        await self._redis.lpush(self._key, job_id)

    async def dequeue(self, poll_timeout: float | None = None) -> str | None:
        timeout = 0 if poll_timeout is None else max(0.0, poll_timeout)
        item = await self._redis.brpop(self._key, timeout=timeout)
        if item is None:
            return None
        _, job_id = item
        return job_id

    async def close(self) -> None:
        await self._redis.aclose()

    async def ping(self) -> bool:
        return bool(await self._redis.ping())
