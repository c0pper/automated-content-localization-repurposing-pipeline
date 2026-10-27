"""Shared helpers for the API and pipeline tests."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container
from app.domain.money import format_usd, parse_usd
from app.main import create_app

API_KEY = "dev-workspace-key"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "environment": "test",
        "data_dir": tmp_path / "data",
        "public_base_url": "http://testserver/assets",
        "api_base_url": "http://testserver",
        "run_worker": False,
        "retention_sweep_seconds": 0,
        "expiry_sweep_seconds": 0,
        "notification_sweep_seconds": 0,
        "worker_poll_seconds": 0.01,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def auth_headers(key: str = API_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def idem_headers(key: str, auth: dict[str, str] | None = None) -> dict[str, str]:
    return {**(auth or auth_headers()), "Idempotency-Key": key}


def make_client(settings: Settings) -> TestClient:
    return TestClient(create_app(container=build_container(settings)))


def source_file(tmp_path: Path, name: str = "raw.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"not-a-real-video")
    return path


def set_voice_profile(client: TestClient, voice_id: str = "voice_test") -> None:
    response = client.put(
        "/api/workspace/voice-profile",
        json={"provider": "elevenlabs", "voice_id": voice_id},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text


def submit_job(
    client: TestClient,
    source: Path,
    *,
    target_languages: list[str] | None = None,
    key: str = "submit-1",
    source_language: str | None = None,
    lip_sync: bool = False,
    model_overrides: dict[str, str] | None = None,
) -> dict:
    body: dict = {
        "source": {"type": "url", "url": str(source)},
        "target_languages": target_languages or ["es", "de"],
        "lip_sync": lip_sync,
        "model_overrides": model_overrides or {},
    }
    if source_language:
        body["source_language"] = source_language
    response = client.post("/api/jobs", json=body, headers=idem_headers(key))
    assert response.status_code == 202, response.text
    return response.json()


def wait_for_status(
    client: TestClient,
    job_id: str,
    statuses: set[str],
    *,
    timeout: float = 20.0,
) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}", headers=auth_headers())
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in statuses:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach {statuses}: {payload}")


def reach_gate(client: TestClient, source: Path, **kwargs) -> dict:
    accepted = submit_job(client, source, **kwargs)
    return wait_for_status(client, accepted["job_id"], {"AWAITING_SELECTION", "FAILED"})


def selection_cell(gate: dict, segment_id: int, language: str) -> dict:
    return next(
        cell
        for cell in gate["cost_matrix"]
        if cell["segment_id"] == segment_id and cell["language"] == language
    )


def confirm(
    client: TestClient,
    job_id: str,
    *,
    segment_ids: list[int],
    languages: list[str],
    expected_total_usd: str,
    key: str = "selection-1",
):
    return client.post(
        f"/api/jobs/{job_id}/selection",
        json={
            "segment_ids": segment_ids,
            "languages": languages,
            "expected_total_usd": expected_total_usd,
        },
        headers=idem_headers(key),
    )


def complete_job(
    client: TestClient,
    source: Path,
    *,
    segment_ids: list[int] | None = None,
    languages: list[str] | None = None,
    **kwargs,
) -> dict:
    """Submit, wait for the gate, confirm, and wait for a terminal status."""
    gate_job = reach_gate(client, source, **kwargs)
    assert gate_job["status"] == "AWAITING_SELECTION", gate_job
    gate = client.get(
        f"/api/jobs/{gate_job['job_id']}/selection", headers=auth_headers()
    ).json()
    if segment_ids is not None:
        chosen_segments = segment_ids
    else:
        chosen_segments = [gate["segments"][0]["segment_id"]]
    chosen_languages = languages if languages is not None else [gate["target_languages"][0]]
    total = sum(
        parse_usd(selection_cell(gate, segment_id, language)["total_usd"])
        for segment_id in chosen_segments
        for language in chosen_languages
    )

    response = confirm(
        client,
        gate_job["job_id"],
        segment_ids=chosen_segments,
        languages=chosen_languages,
        expected_total_usd=format_usd(total),
    )
    assert response.status_code == 202, response.text
    return wait_for_status(client, gate_job["job_id"], {"COMPLETED", "FAILED"})


class MutableClock:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 10, 27, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)

    def set(self, value: datetime) -> None:
        self._now = value
