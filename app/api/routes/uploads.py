"""Source Upload endpoints: start, sign parts, complete and abort (ADR 0022)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep
from app.api.schemas import UploadCompleteRequest, UploadRequest
from app.api.views import upload_view
from app.domain.errors import ApiError
from app.ports import UploadedPart

router = APIRouter(tags=["uploads"])


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def initiate_upload(payload: UploadRequest, container: ContainerDep) -> dict:
    upload = await container.uploads.initiate(
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )
    return {
        "upload_id": upload.upload_id,
        "key": upload.key,
        "part_size_bytes": container.settings.upload_part_size_bytes,
        "part_count": container.uploads.part_count(upload),
        "status": upload.status.value,
    }


@router.get("/uploads/{upload_id}/parts")
async def sign_upload_parts(
    upload_id: str,
    container: ContainerDep,
    numbers: Annotated[str, Query(max_length=1024)],
) -> dict:
    try:
        part_numbers = [int(value) for value in numbers.split(",")]
    except ValueError as exc:
        raise ApiError(
            422, "upload_parts_invalid", "numbers must be comma-separated integers"
        ) from exc
    urls, expires_at = await container.uploads.sign_parts(upload_id, part_numbers)
    return {
        "parts": [{"part_number": number, "url": url} for number, url in urls],
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: str, payload: UploadCompleteRequest, container: ContainerDep
) -> dict:
    upload = await container.uploads.complete(
        upload_id,
        [UploadedPart(part_number=part.part_number, etag=part.etag) for part in payload.parts],
    )
    return upload_view(upload)


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def abort_upload(upload_id: str, container: ContainerDep) -> Response:
    await container.uploads.abort(upload_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
