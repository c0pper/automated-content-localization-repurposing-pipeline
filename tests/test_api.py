from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container
from app.main import create_app


def _wait_for_terminal(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"COMPLETED", "FAILED"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish: {payload}")


def _client(tmp_path, **overrides) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        data_dir=tmp_path / "data",
        public_base_url="http://testserver/assets",
        run_worker=True,
        retention_sweep_seconds=0,
        worker_poll_seconds=0.01,
        **overrides,
    )
    return TestClient(create_app(container=build_container(settings)))


def test_submit_and_process_job_end_to_end(tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"video")

    with _client(tmp_path) as client:
        assert client.get("/healthz").json()["status"] == "ok"

        submitted = client.post(
            "/api/jobs",
            json={"input_url": str(source), "target_languages": ["ES", "de"]},
        )
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        assert submitted.json()["status"] == "RECEIVED"

        job = _wait_for_terminal(client, job_id)
        assert job["status"] == "COMPLETED"
        assert job["target_languages"] == ["es", "de"]
        assert len(job["segments"]) == 3
        assert set(job["segments"][0]["localized_assets"]) == {"es", "de"}

        listing = client.get("/api/jobs").json()["items"]
        assert [item["job_id"] for item in listing] == [job_id]


def test_invalid_submission_returns_guardrail_error(tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"video")

    with _client(tmp_path) as client:
        response = client.post(
            "/api/jobs",
            json={"input_url": str(source), "target_languages": ["es", "de", "fr", "pt"]},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "too_many_languages"


def test_unsupported_format_returns_guardrail_error(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("nope")

    with _client(tmp_path) as client:
        response = client.post(
            "/api/jobs",
            json={"input_url": str(source), "target_languages": ["es"]},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_media_format"


def test_unknown_job_returns_404(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/api/jobs/job_missing")

    assert response.status_code == 404


def test_webhook_requires_secret_when_configured(tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"video")

    with _client(tmp_path, webhook_secret="top-secret") as client:
        unauthorized = client.post(
            "/api/webhooks/drive",
            json={"input_url": str(source), "target_languages": ["es"]},
        )
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/api/webhooks/drive",
            json={"input_url": str(source), "target_languages": ["es"]},
            headers={"X-Webhook-Secret": "top-secret"},
        )
        assert authorized.status_code == 202
        assert _wait_for_terminal(client, authorized.json()["job_id"])["status"] == "COMPLETED"


def test_unknown_webhook_source_is_rejected(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/webhooks/vimeo",
            json={"input_url": "https://example.com/clip.mp4"},
        )

    assert response.status_code == 422
