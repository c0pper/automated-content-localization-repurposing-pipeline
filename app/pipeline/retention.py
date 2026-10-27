"""Retention policy: delete raw intermediates after the configured window."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.ports import ObjectStore

logger = logging.getLogger(__name__)


class RetentionSweeper:
    def __init__(self, store: ObjectStore, *, retention_days: int) -> None:
        self._store = store
        self._retention = timedelta(days=retention_days)

    async def sweep(self) -> int:
        removed = await self._store.prune(older_than=self._retention)
        if removed:
            logger.info("Retention sweep removed %d workspace(s)", removed)
        return removed

    async def run_forever(self, stop: asyncio.Event, *, interval_seconds: int) -> None:
        while not stop.is_set():
            try:
                await self.sweep()
            except Exception:  # noqa: BLE001 - a sweep failure must not kill the worker
                logger.exception("Retention sweep failed")

            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue
