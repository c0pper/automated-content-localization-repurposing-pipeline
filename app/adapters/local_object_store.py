"""Local filesystem object store.

Delivered artifacts live under ``<data_dir>/objects`` and are served from
``/assets`` by the API in local development. Raw intermediates live under
``<data_dir>/workspace`` and are pruned by the retention sweeper.

Replace with S3/R2 in production; the ``ObjectStore`` protocol is the seam.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import timedelta
from pathlib import Path

import httpx

from app.domain.errors import ExternalServiceError

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


class LocalObjectStore:
    def __init__(self, *, data_dir: Path, public_base_url: str) -> None:
        self.objects_root = data_dir / "objects"
        self.workspace_root = data_dir / "workspace"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")

    async def fetch(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        if url.lower().startswith(("http://", "https://")):
            await self._download(url, destination)
        else:
            source = Path(url[7:]) if url.lower().startswith("file://") else Path(url)
            if not source.is_file():
                raise ExternalServiceError(f"Input file not found: {source}")
            await asyncio.to_thread(shutil.copy2, source, destination)

        return destination

    async def _download(self, url: str, destination: Path) -> None:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with destination.open("wb") as handle:
                        async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                            handle.write(chunk)
        except httpx.HTTPError as exc:
            await asyncio.to_thread(destination.unlink, True)
            raise ExternalServiceError(f"Could not download {url}: {exc}") from exc

    async def put(self, source: Path, key: str) -> str:
        destination = (self.objects_root / key).resolve()
        if not destination.is_relative_to(self.objects_root.resolve()):
            raise ValueError(f"Object key escapes the store root: {key!r}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, destination)
        return f"{self._public_base_url}/{key}"

    async def delete(self, key: str) -> None:
        target = (self.objects_root / key).resolve()
        if target.is_relative_to(self.objects_root.resolve()):
            await asyncio.to_thread(target.unlink, True)

    async def prune(self, older_than: timedelta) -> int:
        """Remove job workspaces whose last write predates the retention window."""
        cutoff = time.time() - older_than.total_seconds()
        removed = 0

        for entry in self.workspace_root.iterdir():
            if not entry.is_dir():
                continue
            try:
                last_modified = entry.stat().st_mtime
            except FileNotFoundError:
                continue
            if last_modified < cutoff:
                await asyncio.to_thread(shutil.rmtree, entry, True)
                removed += 1
                logger.info("Retention sweep removed workspace %s", entry.name)

        return removed
