"""Source Uploads: sign and complete direct multipart uploads to object storage (ADR 0022).

The API never streams the bytes. It checks the declared file, generates the key, signs
parts on demand and verifies the assembled object. Submitting the key then attaches the
upload to an ordinary Job.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath
from uuid import uuid4

from app.config import Settings
from app.domain.enums import SourceUploadStatus
from app.domain.errors import ApiError, ExternalServiceError, GuardrailViolation
from app.domain.models import SourceUpload
from app.ports import Clock, ObjectStore, SourceUploadRepository, UploadedPart

# Content types browsers report for each accepted container.
_CONTENT_TYPES = {
    ".mp4": {"video/mp4"},
    ".m4v": {"video/x-m4v", "video/mp4"},
    ".mov": {"video/quicktime"},
}


class SourceUploadService:
    def __init__(
        self,
        *,
        uploads: SourceUploadRepository,
        store: ObjectStore,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._uploads = uploads
        self._store = store
        self._clock = clock
        self._settings = settings

    def part_count(self, upload: SourceUpload) -> int:
        return math.ceil(upload.declared_size_bytes / self._settings.upload_part_size_bytes)

    async def initiate(
        self, *, filename: str, content_type: str, size_bytes: int
    ) -> SourceUpload:
        # The filename is display metadata: only its extension is used, never its path.
        display_name = PureWindowsPath(PurePosixPath(filename).name).name
        suffix = PurePosixPath(display_name).suffix.lower()
        if suffix not in self._settings.input_suffixes or content_type.lower() not in (
            _CONTENT_TYPES.get(suffix, set())
        ):
            raise GuardrailViolation(
                "unsupported_media_format",
                f"Unsupported media format {suffix or display_name!r} ({content_type})",
                details={"allowed": list(self._settings.input_suffixes)},
            )
        if size_bytes > self._settings.max_source_bytes:
            raise GuardrailViolation(
                "source_too_large",
                f"The file exceeds the {self._settings.max_source_bytes}-byte limit",
                details={"max_source_bytes": self._settings.max_source_bytes},
            )

        upload_id = f"upl_{uuid4().hex[:12]}"
        key = f"uploads/{upload_id}/source{suffix}"
        provider_upload_id = await self._store.initiate_multipart(
            key, content_type=content_type.lower()
        )
        upload = SourceUpload(
            upload_id=upload_id,
            workspace_id=self._settings.workspace_id,
            key=key,
            provider_upload_id=provider_upload_id,
            filename=display_name,
            content_type=content_type.lower(),
            declared_size_bytes=size_bytes,
            status=SourceUploadStatus.UPLOADING,
            created_at=self._clock.now(),
        )
        await self._uploads.add(upload)
        return upload

    async def sign_parts(
        self, upload_id: str, numbers: list[int]
    ) -> tuple[list[tuple[int, str]], datetime]:
        """Presign ``PUT`` URLs for the requested parts of an in-progress upload."""
        upload = await self._in_progress(upload_id)
        count = self.part_count(upload)
        if not numbers or len(set(numbers)) != len(numbers) or any(
            not 1 <= number <= count for number in numbers
        ):
            raise GuardrailViolation(
                "upload_parts_invalid",
                f"Part numbers must be unique and between 1 and {count}",
            )
        ttl = self._settings.presign_ttl_seconds
        expires_at = self._clock.now() + timedelta(seconds=ttl)
        urls = [
            (
                number,
                await self._store.presign_part(
                    upload.key, upload.provider_upload_id, number, ttl_seconds=ttl
                ),
            )
            for number in numbers
        ]
        return urls, expires_at

    async def complete(self, upload_id: str, parts: list[UploadedPart]) -> SourceUpload:
        """Assemble the parts and check the object's real size against the declared one."""
        upload = await self._in_progress(upload_id)
        try:
            await self._store.complete_multipart(upload.key, upload.provider_upload_id, parts)
        except ExternalServiceError as exc:
            if exc.retryable:
                raise
            raise GuardrailViolation(
                "upload_parts_invalid", "The uploaded parts could not be assembled"
            ) from exc

        head = await self._store.head(upload.key)
        actual = head.size if head is not None else 0
        upload.actual_size_bytes = actual
        upload.completed_at = self._clock.now()
        if actual != upload.declared_size_bytes or actual > self._settings.max_source_bytes:
            await self._store.delete(upload.key)
            upload.status = SourceUploadStatus.ABORTED
            await self._uploads.save(upload)
            raise GuardrailViolation(
                "upload_size_mismatch",
                "The uploaded object does not match the declared size; it was deleted",
                details={"declared_size_bytes": upload.declared_size_bytes, "size_bytes": actual},
            )
        upload.status = SourceUploadStatus.COMPLETED
        await self._uploads.save(upload)
        return upload

    async def abort(self, upload_id: str) -> None:
        """Discard an in-progress upload; aborting an aborted upload is a no-op."""
        upload = await self._get(upload_id)
        if upload.status is SourceUploadStatus.ABORTED:
            return
        self._ensure_in_progress(upload)
        await self._store.abort_multipart(upload.key, upload.provider_upload_id)
        upload.status = SourceUploadStatus.ABORTED
        await self._uploads.save(upload)

    async def ensure_attachable(self, key: str) -> None:
        """Reject a key whose Source Upload is unfinished or already belongs to a Job."""
        upload = await self._uploads.get_by_key(key)
        if upload is None:
            return  # An object placed under uploads/ by other means.
        if upload.status is not SourceUploadStatus.COMPLETED:
            raise GuardrailViolation(
                "invalid_object_key",
                f"The Source Upload is {upload.status.value.lower()}, not completed",
                details={"upload_id": upload.upload_id, "status": upload.status.value},
            )
        if upload.job_id is not None:
            raise GuardrailViolation(
                "invalid_object_key",
                "The Source Upload is already attached to another Job",
                details={"upload_id": upload.upload_id, "job_id": upload.job_id},
            )

    async def attach(self, key: str, job_id: str) -> None:
        """Attach the Source Upload behind ``key``, if any, to ``job_id``.

        Runs before the Job is stored: a failure afterwards leaves an upload claimed by a
        missing Job, never a live Job whose upload looks unattached to the retention sweep.
        """
        if await self._uploads.get_by_key(key) is None:
            return
        if not await self._uploads.claim(key, job_id):
            # A concurrent submission claimed it between validation and now.
            await self.ensure_attachable(key)
            raise GuardrailViolation(
                "invalid_object_key", "The Source Upload is already attached to another Job"
            )

    async def _get(self, upload_id: str) -> SourceUpload:
        upload = await self._uploads.get(upload_id)
        if upload is None or upload.workspace_id != self._settings.workspace_id:
            raise ApiError(404, "not_found", f"Unknown upload: {upload_id}")
        return upload

    async def _in_progress(self, upload_id: str) -> SourceUpload:
        upload = await self._get(upload_id)
        self._ensure_in_progress(upload)
        return upload

    @staticmethod
    def _ensure_in_progress(upload: SourceUpload) -> None:
        if upload.status is not SourceUploadStatus.UPLOADING:
            raise ApiError(
                409,
                "upload_not_in_progress",
                f"The upload is {upload.status.value.lower()}",
                details={"status": upload.status.value},
            )
