from __future__ import annotations

import pytest

from app.config import Settings


def production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "workspace_api_key": "w" * 40,
        "notification_signing_secret": "n" * 40,
        "webhook_secret": "h" * 24,
        "api_base_url": "https://pipeline.example.com",
        "public_base_url": "https://s3.pipeline.example.com/pipeline",
        "repository_backend": "postgres",
        "database_url": "postgresql+asyncpg://pipeline:secret@postgres:5432/pipeline",
        "queue_backend": "redis",
        "redis_url": "redis://redis:6379/0",
        "object_store_backend": "silo",
        "silo_endpoint": "http://silo:9000",
        "silo_public_endpoint": "https://s3.pipeline.example.com",
        "silo_bucket": "pipeline",
        "silo_access_key": "access",
        "silo_secret_key": "secret",
        "media_backend": "ffmpeg",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_configuration_accepts_the_compose_shape():
    production_settings().validate_for_runtime()


def test_production_configuration_fails_closed_on_defaults():
    settings = production_settings(
        workspace_api_key="dev-workspace-key",
        notification_signing_secret="dev-notification-secret",
        webhook_secret=None,
        api_base_url="http://localhost:8000",
        repository_backend="memory",
        queue_backend="memory",
        object_store_backend="local",
        media_backend="stub",
    )

    with pytest.raises(RuntimeError) as error:
        settings.validate_for_runtime()

    message = str(error.value)
    assert "PIPELINE_WORKSPACE_API_KEY" in message
    assert "PIPELINE_NOTIFICATION_SIGNING_SECRET" in message
    assert "PIPELINE_WEBHOOK_SECRET" in message
    assert "PIPELINE_REPOSITORY_BACKEND" in message
    assert "PIPELINE_QUEUE_BACKEND" in message
    assert "PIPELINE_OBJECT_STORE_BACKEND" in message
    assert "PIPELINE_MEDIA_BACKEND" in message


def test_local_configuration_keeps_development_defaults(settings):
    settings.validate_for_runtime()
