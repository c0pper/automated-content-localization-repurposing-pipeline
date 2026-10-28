"""Local filesystem object store.

Delivered artifacts live under ``<data_dir>/objects`` and are served from
``/assets`` by the API in local development. Raw intermediates live under
``<data_dir>/workspace`` and are pruned by the retention sweeper. In-progress multipart
uploads stage their parts under ``<data_dir>/multipart/<upload_id>`` until completed.

Presigned URLs carry an HMAC over the HTTP method, key, upload ID, part number and expiry,
so a URL authorizes exactly one method on one key (and one part), as SigV4 does on Silo.

Replace with Silo/S3 in production; the ``ObjectStore`` protocol is the seam.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.domain.errors import ExternalServiceError
from app.ports.infra import ObjectHead, UploadedPart

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
# S3 limits, mirrored so the same client works against both backends.
_MIN_PART_BYTES = 5 * 1024 * 1024
_MAX_PART_NUMBER = 10_000
_UPLOAD_ID = re.compile(r"[0-9a-f]{32}")


class PartTooLargeError(Exception):
    """A part upload exceeded the caller's byte limit."""


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
        self.multipart_root = data_dir / "multipart"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.multipart_root.mkdir(parents=True, exist_ok=True)
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
        signature = self._sign("GET", key, expires=expires)
        return f"{self._public_base_url}/{key}?expires={expires}&signature={signature}"

    async def presign_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        *,
        ttl_seconds: int,
    ) -> str:
        expires = int(time.time()) + max(1, ttl_seconds)
        signature = self._sign(
            "PUT", key, expires=expires, upload_id=upload_id, part_number=part_number
        )
        return (
            f"{self._public_base_url}/{key}?upload_id={upload_id}"
            f"&part_number={part_number}&expires={expires}&signature={signature}"
        )

    def verify_presigned(
        self,
        method: str,
        key: str,
        *,
        expires: int,
        signature: str,
        upload_id: str = "",
        part_number: int = 0,
    ) -> bool:
        if expires < int(time.time()):
            return False
        expected = self._sign(
            method, key, expires=expires, upload_id=upload_id, part_number=part_number
        )
        return hmac.compare_digest(expected, signature)

    def _sign(
        self,
        method: str,
        key: str,
        *,
        expires: int,
        upload_id: str = "",
        part_number: int = 0,
    ) -> str:
        # JSON keeps the fields unambiguous whatever characters the key contains.
        message = json.dumps([method.upper(), key, upload_id, part_number, expires])
        return hmac.new(
            self._presign_secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

    async def head(self, key: str) -> ObjectHead | None:
        path = self._path(key)
        if not path.is_file():
            return None
        content_type, _ = mimetypes.guess_type(path.name)
        return ObjectHead(size=path.stat().st_size, content_type=content_type)

    async def initiate_multipart(self, key: str, *, content_type: str) -> str:
        self._path(key)  # Reject traversal before staging anything.
        upload_id = secrets.token_hex(16)
        staging = self.multipart_root / upload_id
        staging.mkdir(parents=True)
        meta = json.dumps({"key": key, "content_type": content_type})
        await asyncio.to_thread((staging / "upload.json").write_text, meta)
        return upload_id

    async def write_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        chunks: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> str:
        """Stage one part from a signed ``PUT`` and return its quoted MD5 ``ETag``."""
        if not 1 <= part_number <= _MAX_PART_NUMBER:
            raise ExternalServiceError(f"Invalid part number: {part_number}", retryable=False)
        staging = self._staging(key, upload_id)
        name = f"part-{part_number:05d}"
        partial = staging / f"{name}.partial"
        digest = hashlib.md5(usedforsecurity=False)
        written = 0
        try:
            with partial.open("wb") as handle:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise PartTooLargeError(f"Part exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    handle.write(chunk)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        etag = f'"{digest.hexdigest()}"'
        os.replace(partial, staging / name)
        (staging / f"{name}.etag").write_text(etag)
        return etag

    async def complete_multipart(
        self, key: str, upload_id: str, parts: list[UploadedPart]
    ) -> None:
        staging = self._staging(key, upload_id)
        numbers = [part.part_number for part in parts]
        if not parts or numbers != sorted(set(numbers)):
            raise ExternalServiceError(
                "Parts must be listed once each in ascending order", retryable=False
            )

        sources: list[Path] = []
        for index, part in enumerate(parts):
            name = f"part-{part.part_number:05d}"
            source = staging / name
            etag_file = staging / f"{name}.etag"
            if not source.is_file() or etag_file.read_text() != _quoted(part.etag):
                raise ExternalServiceError(
                    f"Part {part.part_number} was not uploaded or its ETag does not match",
                    retryable=False,
                )
            if index < len(parts) - 1 and source.stat().st_size < _MIN_PART_BYTES:
                raise ExternalServiceError(
                    f"Part {part.part_number} is smaller than {_MIN_PART_BYTES} bytes",
                    retryable=False,
                )
            sources.append(source)

        destination = self._path(key)

        def _assemble() -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            assembling = staging / "assembled"
            with assembling.open("wb") as output:
                for source in sources:
                    with source.open("rb") as handle:
                        shutil.copyfileobj(handle, output, _CHUNK_SIZE)
            os.replace(assembling, destination)
            shutil.rmtree(staging, ignore_errors=True)

        await asyncio.to_thread(_assemble)

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            staging = self._staging(key, upload_id)
        except ExternalServiceError:
            return  # Already completed or aborted: aborting is idempotent.
        await asyncio.to_thread(shutil.rmtree, staging, True)

    def _staging(self, key: str, upload_id: str) -> Path:
        """Resolve an in-progress upload's staging directory; it must belong to ``key``."""
        staging = self.multipart_root / upload_id
        meta_file = staging / "upload.json"
        if (
            not _UPLOAD_ID.fullmatch(upload_id)
            or not meta_file.is_file()
            or json.loads(meta_file.read_text())["key"] != key
        ):
            raise ExternalServiceError(f"Unknown multipart upload: {upload_id}", retryable=False)
        return staging

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


def _quoted(etag: str) -> str:
    return etag if etag.startswith('"') else f'"{etag}"'


def key_from_url(url: str) -> str:
    """Extract the object key from a public asset URL."""
    path = urlsplit(url).path
    marker = "/assets/"
    if marker in path:
        return path.split(marker, 1)[1]
    return path.lstrip("/")
