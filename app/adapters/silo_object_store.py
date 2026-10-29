"""Silo (S3-compatible) object store.

All boto3 calls are blocking, so each one is wrapped in ``asyncio.to_thread``. The adapter
keeps the same key layout as :class:`LocalObjectStore`: delivered artifacts under
``jobs/<job_id>/...`` and prunable raw intermediates under ``workspace/...``.
"""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
import time
from datetime import timedelta
from pathlib import Path

import boto3
import httpx
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.domain.errors import ExternalServiceError
from app.ports.infra import ObjectHead, UploadedPart

_CHUNK_SIZE = 1024 * 1024
_WORKSPACE_PREFIX = "workspace/"
# Completion errors caused by the request itself; retrying the same parts cannot succeed.
_REJECTED_COMPLETION_CODES = {"InvalidPart", "InvalidPartOrder", "EntityTooSmall", "NoSuchUpload"}


class SiloObjectStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.silo_endpoint or not settings.silo_bucket:
            raise RuntimeError("PIPELINE_SILO_ENDPOINT and PIPELINE_SILO_BUCKET are required")
        self._bucket = settings.silo_bucket
        self._public_endpoint = (
            settings.silo_public_endpoint or settings.silo_endpoint
        ).rstrip("/")
        self._presign_ttl = settings.presign_ttl_seconds
        client_config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": settings.provider_max_attempts},
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.silo_endpoint,
            region_name=settings.silo_region,
            aws_access_key_id=settings.silo_access_key,
            aws_secret_access_key=settings.silo_secret_key,
            config=client_config,
        )
        # Presigned URLs must be signed for the public hostname: the signature covers
        # the Host header, so signing against the internal endpoint breaks through Caddy.
        self._public_client = (
            self._client
            if self._public_endpoint == settings.silo_endpoint.rstrip("/")
            else boto3.client(
                "s3",
                endpoint_url=self._public_endpoint,
                region_name=settings.silo_region,
                aws_access_key_id=settings.silo_access_key,
                aws_secret_access_key=settings.silo_secret_key,
                config=client_config,
            )
        )

    async def fetch(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if url.lower().startswith(("http://", "https://")):
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
            return destination

        if url.lower().startswith("file://"):
            source = Path(url[7:])
            if not await asyncio.to_thread(source.is_file):
                raise ExternalServiceError(f"Input file not found: {source}")
            await asyncio.to_thread(shutil.copy2, source, destination)
            return destination

        source = Path(url)
        if await asyncio.to_thread(source.is_file):
            await asyncio.to_thread(shutil.copy2, source, destination)
            return destination

        return await self.get(url, destination)

    async def put(self, source: Path, key: str) -> str:
        # Without a type Silo serves binary/octet-stream, which Firefox will not play.
        content_type, _ = mimetypes.guess_type(key)
        extra_args = {"ContentType": content_type} if content_type else None

        def _upload() -> None:
            self._client.upload_file(str(source), self._bucket, key, ExtraArgs=extra_args)

        try:
            await asyncio.to_thread(_upload)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not upload {key}: {exc}") from exc
        return f"{self._public_endpoint}/{self._bucket}/{key}"

    async def get(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        def _download() -> None:
            self._client.download_file(self._bucket, key, str(destination))

        try:
            await asyncio.to_thread(_download)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Object not found: {key}", retryable=False) from exc
        return destination

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=key
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not delete {key}: {exc}") from exc

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list_keys(prefix)
        if not keys:
            return 0
        try:
            for start in range(0, len(keys), 1000):
                batch = keys[start : start + 1000]
                await asyncio.to_thread(
                    self._client.delete_objects,
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch]},
                )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not delete prefix {prefix}: {exc}") from exc
        return len(keys)

    async def exists(self, key: str) -> bool:
        def _head() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                    return False
                raise
            return True

        try:
            return await asyncio.to_thread(_head)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not stat {key}: {exc}") from exc

    async def size(self, key: str) -> int:
        def _head() -> int:
            try:
                response = self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError:
                return 0
            return int(response.get("ContentLength", 0))

        try:
            return await asyncio.to_thread(_head)
        except BotoCoreError as exc:
            raise ExternalServiceError(f"Could not stat {key}: {exc}") from exc

    async def list_keys(self, prefix: str) -> list[str]:
        def _list() -> list[str]:
            keys: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                keys.extend(item["Key"] for item in page.get("Contents", []))
            return keys

        try:
            return await asyncio.to_thread(_list)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not list {prefix}: {exc}") from exc

    async def copy(self, source_key: str, destination_key: str) -> str:
        try:
            await asyncio.to_thread(
                self._client.copy_object,
                Bucket=self._bucket,
                Key=destination_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(
                f"Could not copy {source_key} to {destination_key}: {exc}"
            ) from exc
        return f"{self._public_endpoint}/{self._bucket}/{destination_key}"

    async def presign(self, key: str, *, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds or self._presign_ttl
        try:
            return await asyncio.to_thread(
                self._public_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=max(1, ttl),
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not presign {key}: {exc}") from exc

    async def head(self, key: str) -> ObjectHead | None:
        def _head() -> ObjectHead | None:
            try:
                response = self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                    return None
                raise
            return ObjectHead(
                size=int(response.get("ContentLength", 0)),
                content_type=response.get("ContentType"),
            )

        try:
            return await asyncio.to_thread(_head)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not stat {key}: {exc}") from exc

    async def initiate_multipart(self, key: str, *, content_type: str) -> str:
        try:
            response = await asyncio.to_thread(
                self._client.create_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not start an upload to {key}: {exc}") from exc
        return response["UploadId"]

    async def presign_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        ttl = ttl_seconds or self._presign_ttl
        try:
            return await asyncio.to_thread(
                self._public_client.generate_presigned_url,
                "upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=max(1, ttl),
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(
                f"Could not presign part {part_number} of {key}: {exc}"
            ) from exc

    async def complete_multipart(
        self, key: str, upload_id: str, parts: list[UploadedPart]
    ) -> None:
        try:
            await asyncio.to_thread(
                self._client.complete_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": part.part_number, "ETag": part.etag} for part in parts
                    ]
                },
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            raise ExternalServiceError(
                f"Could not complete the upload to {key}: {exc}",
                retryable=code not in _REJECTED_COMPLETION_CODES,
            ) from exc
        except BotoCoreError as exc:
            raise ExternalServiceError(f"Could not complete the upload to {key}: {exc}") from exc

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.abort_multipart_upload,
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchUpload":
                return  # Already completed or aborted: aborting is idempotent.
            raise ExternalServiceError(f"Could not abort the upload to {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise ExternalServiceError(f"Could not abort the upload to {key}: {exc}") from exc

    async def prune(self, older_than: timedelta) -> int:
        cutoff = time.time() - older_than.total_seconds()

        def _prune() -> int:
            removed = 0
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=_WORKSPACE_PREFIX):
                stale = [
                    {"Key": item["Key"]}
                    for item in page.get("Contents", [])
                    if item.get("LastModified")
                    and item["LastModified"].timestamp() < cutoff
                ]
                if not stale:
                    continue
                self._client.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": stale}
                )
                removed += len(stale)
            return removed

        try:
            return await asyncio.to_thread(_prune)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Could not prune workspace objects: {exc}") from exc
