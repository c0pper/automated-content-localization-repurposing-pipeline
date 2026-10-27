"""Local filesystem object store.

Delivered artifacts live under ``<data_dir>/objects`` and are served from
``/assets`` by the API in local development. Raw intermediates live under
``<data_dir>/workspace`` and are pruned by the retention sweeper.

Replace with Silo/S3 in production; the ``ObjectStore`` protocol is the seam.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import shutil
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.domain.errors import ExternalServiceError

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


class LocalObjectStore:
    def __init__(
        self,
        *,
        data_dir: Path,
        public_base_url: str,
        presign_secret: str = "local-presign-secret",
    ) -> None:
        self.objects_root = data_dir / "objects"
        self.workspace_root = data_dir / "workspace"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")
        self._presign_secret = presign_secret

    def _path(self, key: str) -> Path:
        destination = (self.objects_root / key).resolve()
        if not destination.is_relative_to(self.objects_root.resolve()):
            raise ValueError(f"Object key escapes the store root: {key!r}")
        return destination

    async def fetch(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        if url.lower().startswith(("http://", "https://")):
            await self._download(url, destination)
        elif url.lower().startswith("file://"):
            source = Path(url[7:])
            if not await asyncio.to_thread(source.is_file):
                raise ExternalServiceError(f"Input file not found: {source}")
            await asyncio.to_thread(shutil.copy2, source, destination)
        else:
            source = Path(url)
            if await asyncio.to_thread(source.is_file):
                await asyncio.to_thread(shutil.copy2, source, destination)
            else:
                # Treat it as a pre-uploaded object key.
                await self.get(url, destination)

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
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, destination)
        return f"{self._public_base_url}/{key}"

    async def get(self, key: str, destination: Path) -> Path:
        source = self._path(key)
        if not source.is_file():
            raise ExternalServiceError(f"Object not found: {key}", retryable=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, destination)
        return destination

    async def delete(self, key: str) -> None:
        target = self._path(key)
        await asyncio.to_thread(target.unlink, True)

    async def delete_prefix(self, prefix: str) -> int:
        root = self.objects_root.resolve()
        removed = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            key = path.relative_to(root).as_posix()
            if key.startswith(prefix):
                await asyncio.to_thread(path.unlink, True)
                removed += 1
        # Remove now-empty directories so a purge leaves no job shell behind.
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and path != root:
                try:
                    await asyncio.to_thread(path.rmdir)
                except OSError:
                    continue
        return removed

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def size(self, key: str) -> int:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else 0

    async def list_keys(self, prefix: str) -> list[str]:
        root = self.objects_root.resolve()
        return [
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.relative_to(root).as_posix().startswith(prefix)
        ]

    async def copy(self, source_key: str, destination_key: str) -> str:
        source = self._path(source_key)
        destination = self._path(destination_key)
        if not source.is_file():
            raise ExternalServiceError(f"Object not found: {source_key}", retryable=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, destination)
        return f"{self._public_base_url}/{destination_key}"

    async def presign(self, key: str, *, ttl_seconds: int) -> str:
        expires = int(time.time()) + max(1, ttl_seconds)
        signature = hmac.new(
            self._presign_secret.encode(),
            f"{key}:{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{self._public_base_url}/{key}?expires={expires}&signature={signature}"

    def verify_presigned(self, key: str, *, expires: int, signature: str) -> bool:
        if expires < int(time.time()):
            return False
        expected = hmac.new(
            self._presign_secret.encode(),
            f"{key}:{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def local_path(self, key: str) -> Path:
        """Resolve a key to its on-disk path, rejecting traversal."""
        return self._path(key)

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


def key_from_url(url: str) -> str:
    """Extract the object key from a public asset URL."""
    path = urlsplit(url).path
    marker = "/assets/"
    if marker in path:
        return path.split(marker, 1)[1]
    return path.lstrip("/")
