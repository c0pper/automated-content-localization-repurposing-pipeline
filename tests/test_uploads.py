"""Source Uploads (ADR 0022) through the public API, against the local object store."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.container import build_container
from app.main import create_app
from tests.helpers import (
    MutableClock,
    auth_headers,
    idem_headers,
    make_client,
    make_settings,
    wait_for_status,
)

_MIB = 1024 * 1024
# The S3 minimum for every part but the last; keeps multi-part tests small.
_PART = 5 * _MIB


def _initiate(client, *, key: str = "upload-1", **overrides):
    body = {"filename": "keynote.mp4", "content_type": "video/mp4", "size_bytes": 70 * _MIB}
    body.update(overrides)
    return client.post("/api/uploads", json=body, headers=idem_headers(key))


def test_initiate_generates_the_key_and_part_plan(tmp_path):
    with make_client(make_settings(tmp_path)) as client:
        response = _initiate(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["upload_id"].startswith("upl_")
    assert body["key"] == f"uploads/{body['upload_id']}/source.mp4"
    assert body["part_size_bytes"] == 32 * _MIB
    assert body["part_count"] == 3
    assert body["status"] == "UPLOADING"


def _upload_parts(client, upload: dict, data: bytes) -> list[dict]:
    """PUT each part to its presigned URL, as the browser does, and collect the ETags."""
    size = upload["part_size_bytes"]
    numbers = list(range(1, upload["part_count"] + 1))
    signed = client.get(
        f"/api/uploads/{upload['upload_id']}/parts",
        params={"numbers": ",".join(map(str, numbers))},
        headers=auth_headers(),
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["expires_at"]
    parts = []
    for part in signed.json()["parts"]:
        number = part["part_number"]
        chunk = data[(number - 1) * size : number * size]
        put = client.put(part["url"], content=chunk)
        assert put.status_code == 200, put.text
        parts.append({"part_number": number, "etag": put.headers["ETag"]})
    return parts


def _complete(client, upload_id: str, parts: list[dict], *, key: str = "complete-1"):
    return client.post(
        f"/api/uploads/{upload_id}/complete",
        json={"parts": parts},
        headers=idem_headers(key),
    )


def _real_mp4(tmp_path) -> bytes:
    """Encode a short lossless clip with audio: large enough to need several parts."""
    path = tmp_path / "real.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return path.read_bytes()


@pytest.mark.parametrize(
    "media_backend",
    [
        "stub",
        pytest.param(
            "ffmpeg",
            marks=pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg"),
        ),
    ],
)
def test_uploaded_file_is_submitted_as_a_job_that_passes_ingest(tmp_path, media_backend):
    settings = make_settings(
        tmp_path, run_worker=True, upload_part_size_bytes=_PART, media_backend=media_backend
    )
    container = build_container(settings)
    if media_backend == "ffmpeg":
        data = _real_mp4(tmp_path)
    else:
        data = b"a" * _PART + b"b" * _PART + b"c" * 1024

    with TestClient(create_app(container=container)) as client:
        upload = _initiate(client, size_bytes=len(data)).json()
        assert upload["part_count"] >= 2

        completed = _complete(client, upload["upload_id"], _upload_parts(client, upload, data))
        assert completed.status_code == 200, completed.text
        assert completed.json() == {
            "upload_id": upload["upload_id"],
            "key": upload["key"],
            "size_bytes": len(data),
            "status": "COMPLETED",
        }

        submitted = client.post(
            "/api/jobs",
            json={"source": {"type": "object", "key": upload["key"]}, "target_languages": ["es"]},
            headers=idem_headers("submit-upload"),
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]

        wait_for_status(client, job_id, {"AWAITING_SELECTION", "FAILED"})
        events = client.get(f"/api/jobs/{job_id}/events", headers=auth_headers()).json()
        assert any(
            event["type"] == "stage_completed" and event["stage"] == "ingest"
            for event in events["items"]
        ), events

    stored = asyncio.run(container.source_uploads.get(upload["upload_id"]))
    assert stored.job_id == job_id


def _staged_uploads(settings) -> list:
    root = settings.data_dir / "multipart"
    return list(root.iterdir()) if root.is_dir() else []


def test_initiate_rejects_unsupported_files_before_signing_anything(tmp_path):
    settings = make_settings(tmp_path, max_source_bytes=100 * _MIB)
    with make_client(settings) as client:
        wrong_extension = _initiate(client, key="u-1", filename="notes.pdf")
        wrong_type = _initiate(client, key="u-2", content_type="application/pdf")
        too_large = _initiate(client, key="u-3", size_bytes=100 * _MIB + 1)

    assert wrong_extension.status_code == 422
    assert wrong_extension.json()["detail"]["code"] == "unsupported_media_format"
    assert wrong_type.status_code == 422
    assert wrong_type.json()["detail"]["code"] == "unsupported_media_format"
    assert too_large.status_code == 422
    assert too_large.json()["detail"]["code"] == "source_too_large"
    assert _staged_uploads(settings) == []


def test_a_path_in_the_filename_never_reaches_the_key(tmp_path):
    with make_client(make_settings(tmp_path)) as client:
        posix = _initiate(client, key="u-1", filename="../../jobs/job_1/clip.MP4").json()
        windows = _initiate(
            client, key="u-2", filename="..\\..\\evil.mov", content_type="video/quicktime"
        ).json()

    assert posix["key"] == f"uploads/{posix['upload_id']}/source.mp4"
    assert windows["key"] == f"uploads/{windows['upload_id']}/source.mov"


def test_size_mismatch_deletes_the_assembled_object(tmp_path):
    container = build_container(make_settings(tmp_path))
    with TestClient(create_app(container=container)) as client:
        upload = _initiate(client, size_bytes=2048).json()
        parts = _upload_parts(client, upload, b"x" * 1024)

        response = _complete(client, upload["upload_id"], parts)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "upload_size_mismatch"
    assert asyncio.run(container.store.head(upload["key"])) is None


def test_finished_uploads_cannot_be_signed_completed_or_aborted(tmp_path):
    with make_client(make_settings(tmp_path)) as client:
        done = _initiate(client, key="u-1", size_bytes=1024).json()
        parts = _upload_parts(client, done, b"x" * 1024)
        assert _complete(client, done["upload_id"], parts).status_code == 200

        aborted = _initiate(client, key="u-2", size_bytes=1024).json()
        first_abort = client.delete(
            f"/api/uploads/{aborted['upload_id']}", headers=idem_headers("abort-1")
        )
        second_abort = client.delete(
            f"/api/uploads/{aborted['upload_id']}", headers=idem_headers("abort-2")
        )
        assert first_abort.status_code == 204
        assert second_abort.status_code == 204

        for upload in (done, aborted):
            signed = client.get(
                f"/api/uploads/{upload['upload_id']}/parts",
                params={"numbers": "1"},
                headers=auth_headers(),
            )
            completed = _complete(
                client, upload["upload_id"], parts, key=f"c-{upload['upload_id']}"
            )
            for response in (signed, completed):
                assert response.status_code == 409, response.text
                assert response.json()["detail"]["code"] == "upload_not_in_progress"

        abort_done = client.delete(
            f"/api/uploads/{done['upload_id']}", headers=idem_headers("abort-3")
        )
        assert abort_done.status_code == 409
        assert abort_done.json()["detail"]["code"] == "upload_not_in_progress"


def test_upload_endpoints_require_the_api_key_and_honour_idempotency(tmp_path):
    with make_client(make_settings(tmp_path)) as client:
        body = {"filename": "keynote.mp4", "content_type": "video/mp4", "size_bytes": 1024}
        for method, path in (
            ("POST", "/api/uploads"),
            ("GET", "/api/uploads/upl_x/parts?numbers=1"),
            ("POST", "/api/uploads/upl_x/complete"),
            ("DELETE", "/api/uploads/upl_x"),
        ):
            response = client.request(method, path, json=body, headers={"Idempotency-Key": "k"})
            assert response.status_code == 401, (method, path)

        missing_key = client.post("/api/uploads", json=body, headers=auth_headers())
        assert missing_key.status_code == 422
        assert missing_key.json()["detail"]["code"] == "idempotency_key_required"

        first = client.post("/api/uploads", json=body, headers=idem_headers("same"))
        replay = client.post("/api/uploads", json=body, headers=idem_headers("same"))
        assert replay.status_code == 201
        assert replay.json() == first.json()


def _submit_object(client, key: str, *, idempotency_key: str):
    return client.post(
        "/api/jobs",
        json={"source": {"type": "object", "key": key}, "target_languages": ["es"]},
        headers=idem_headers(idempotency_key),
    )


def test_only_a_completed_unattached_upload_can_be_submitted(tmp_path):
    with make_client(make_settings(tmp_path)) as client:
        in_progress = _initiate(client, key="u-1", size_bytes=1024).json()
        done = _initiate(client, key="u-2", size_bytes=1024).json()
        _complete(client, done["upload_id"], _upload_parts(client, done, b"x" * 1024))

        not_finished = _submit_object(client, in_progress["key"], idempotency_key="s-1")
        first = _submit_object(client, done["key"], idempotency_key="s-2")
        second = _submit_object(client, done["key"], idempotency_key="s-3")

    assert not_finished.status_code == 422
    assert not_finished.json()["detail"]["code"] == "invalid_object_key"
    assert first.status_code == 202, first.text
    assert second.status_code == 422
    assert second.json()["detail"]["code"] == "invalid_object_key"


def test_sqlite_source_uploads_survive_a_restart(tmp_path):
    settings = make_settings(tmp_path, repository_backend="sqlite")
    with make_client(settings) as client:
        upload = _initiate(client, size_bytes=1024).json()
        _complete(client, upload["upload_id"], _upload_parts(client, upload, b"x" * 1024))
        job_id = _submit_object(client, upload["key"], idempotency_key="s-1").json()["job_id"]

    reopened = build_container(settings)
    by_id = asyncio.run(reopened.source_uploads.get(upload["upload_id"]))
    by_key = asyncio.run(reopened.source_uploads.get_by_key(upload["key"]))

    assert by_id == by_key
    assert by_id.status.value == "COMPLETED"
    assert by_id.filename == "keynote.mp4"
    assert by_id.declared_size_bytes == by_id.actual_size_bytes == 1024
    assert by_id.provider_upload_id
    assert by_id.completed_at is not None
    assert by_id.job_id == job_id


def _completed_upload(client, *, key: str) -> dict:
    upload = _initiate(client, key=f"init-{key}", size_bytes=1024).json()
    completed = _complete(
        client, upload["upload_id"], _upload_parts(client, upload, b"x" * 1024), key=key
    )
    assert completed.status_code == 200, completed.text
    return upload


_BACKENDS = pytest.mark.parametrize("repository_backend", ["memory", "sqlite"])


@_BACKENDS
def test_unattached_upload_is_swept_after_the_retention_window(tmp_path, repository_backend):
    clock = MutableClock(datetime.now(UTC))
    settings = make_settings(tmp_path, repository_backend=repository_backend)
    container = build_container(settings, clock=clock)
    with TestClient(create_app(container=container)) as client:
        old = _completed_upload(client, key="old")
        clock.advance(days=5)
        young = _completed_upload(client, key="young")

    clock.advance(days=2, minutes=1)
    asyncio.run(container.retention.sweep())

    assert asyncio.run(container.source_uploads.get(old["upload_id"])) is None
    assert asyncio.run(container.store.head(old["key"])) is None
    assert asyncio.run(container.source_uploads.get(young["upload_id"])) is not None
    assert asyncio.run(container.store.head(young["key"])) is not None


@_BACKENDS
def test_attached_upload_expires_with_its_jobs_source_recording(tmp_path, repository_backend):
    clock = MutableClock(datetime.now(UTC))
    settings = make_settings(tmp_path, repository_backend=repository_backend)
    container = build_container(settings, clock=clock)
    with TestClient(create_app(container=container)) as client:
        upload = _completed_upload(client, key="attached")
        job_id = _submit_object(client, upload["key"], idempotency_key="s-1").json()["job_id"]

        clock.advance(days=8)
        asyncio.run(container.retention.sweep())
        assert asyncio.run(container.source_uploads.get(upload["upload_id"])) is not None
        assert asyncio.run(container.store.head(upload["key"])) is not None

        cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=idem_headers("cancel"))
        assert cancelled.status_code == 202, cancelled.text

    asyncio.run(container.retention.sweep())

    assert asyncio.run(container.store.head(upload["key"])) is None
    assert asyncio.run(container.source_uploads.get(upload["upload_id"])) is None


@_BACKENDS
def test_aborted_and_abandoned_uploads_are_swept_idempotently(tmp_path, repository_backend):
    settings = make_settings(tmp_path, repository_backend=repository_backend)
    clock = MutableClock(datetime.now(UTC))
    container = build_container(settings, clock=clock)
    with TestClient(create_app(container=container)) as client:
        aborted = _initiate(client, key="u-1", size_bytes=1024).json()
        client.delete(f"/api/uploads/{aborted['upload_id']}", headers=idem_headers("abort"))
        abandoned = _initiate(client, key="u-2", size_bytes=1024).json()
        _upload_parts(client, abandoned, b"x" * 1024)
        done = _completed_upload(client, key="done")

    clock.advance(days=7, minutes=1)
    first = asyncio.run(container.retention.sweep())
    second = asyncio.run(container.retention.sweep())

    for upload in (aborted, abandoned, done):
        assert asyncio.run(container.source_uploads.get(upload["upload_id"])) is None
    assert _staged_uploads(settings) == []
    assert first == 3
    assert second == 0


@_BACKENDS
def test_workspace_purge_counts_and_removes_source_uploads(tmp_path, repository_backend):
    settings = make_settings(tmp_path, repository_backend=repository_backend)
    container = build_container(settings)
    with TestClient(create_app(container=container)) as client:
        attached = _completed_upload(client, key="attached")
        job_id = _submit_object(client, attached["key"], idempotency_key="s-1").json()["job_id"]
        client.post(f"/api/jobs/{job_id}/cancel", headers=idem_headers("cancel"))
        unattached = _completed_upload(client, key="unattached")
        in_progress = _initiate(client, key="u-3", size_bytes=1024).json()

        preview = client.post(
            "/api/workspace/purge/dry-run", headers=idem_headers("purge-dry")
        ).json()
        assert preview["source_uploads"] == 3
        assert preview["bytes"] >= 2048

        confirmed = client.post(
            "/api/workspace/purge",
            json={
                "workspace_id": "ws_default",
                "confirmation_token": preview["confirmation_token"],
            },
            headers=idem_headers("purge-confirm"),
        )
        assert confirmed.status_code == 202, confirmed.text

    for upload in (attached, unattached, in_progress):
        assert asyncio.run(container.source_uploads.get(upload["upload_id"])) is None
        assert asyncio.run(container.store.head(upload["key"])) is None
    assert _staged_uploads(settings) == []


def test_upload_claimed_by_a_job_not_yet_stored_is_kept(tmp_path):
    # attach() claims the upload before the Job is saved; a sweep in between must wait.
    clock = MutableClock(datetime.now(UTC))
    container = build_container(make_settings(tmp_path), clock=clock)
    with TestClient(create_app(container=container)) as client:
        upload = _completed_upload(client, key="claimed")
    assert asyncio.run(container.source_uploads.claim(upload["key"], "job_in_flight"))

    clock.advance(days=8)
    asyncio.run(container.retention.sweep())

    assert asyncio.run(container.store.head(upload["key"])) is not None
    assert asyncio.run(container.source_uploads.get(upload["upload_id"])) is not None
