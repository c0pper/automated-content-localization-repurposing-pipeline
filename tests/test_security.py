from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.errors import GuardrailViolation
from app.security.urls import validate_file_source, validate_http_url, validate_object_key


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/raw.mp4",
        "http://10.0.0.1/raw.mp4",
        "http://169.254.169.254/latest/meta-data/raw.mp4",
        "http://localhost/raw.mp4",
        "ftp://example.com/raw.mp4",
        "file:///etc/passwd",
    ],
)
async def test_ssrf_rejects_private_and_non_http_sources(url):
    with pytest.raises(GuardrailViolation) as excinfo:
        await validate_http_url(url, allowed_suffixes=(".mp4",))
    assert excinfo.value.code == "unsafe_source"


async def test_ssrf_allows_public_http_sources():
    await validate_http_url(
        "https://8.8.8.8/raw.mp4", allowed_suffixes=(".mp4",)
    )


async def test_ssrf_rejects_unsupported_suffix():
    with pytest.raises(GuardrailViolation) as excinfo:
        await validate_http_url(
            "https://8.8.8.8/notes.txt", allowed_suffixes=(".mp4",)
        )
    assert excinfo.value.code == "unsupported_media_format"


def test_object_keys_must_live_under_uploads():
    validate_object_key("uploads/raw.mp4")

    for key in (
        "raw.mp4",
        "/uploads/raw.mp4",
        "uploads/../secret.mp4",
        "uploads\\raw.mp4",
        "uploads/raw\x00.mp4",
    ):
        with pytest.raises(GuardrailViolation) as excinfo:
            validate_object_key(key)
        assert excinfo.value.code == "invalid_object_key"


def test_local_file_validation(tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    validate_file_source(source, allowed_suffixes=(".mp4",))

    with pytest.raises(GuardrailViolation) as excinfo:
        validate_file_source(Path(tmp_path / "missing.mp4"), allowed_suffixes=(".mp4",))
    assert excinfo.value.code == "invalid_input"

    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    with pytest.raises(GuardrailViolation) as excinfo:
        validate_file_source(notes, allowed_suffixes=(".mp4",))
    assert excinfo.value.code == "unsupported_media_format"
