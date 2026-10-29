"""Runtime configuration, loaded from environment variables prefixed with PIPELINE_."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


class Settings(BaseSettings):
    """Process-wide configuration.

    Everything is overridable via ``PIPELINE_*`` environment variables (or a local ``.env``).
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"
    data_dir: Path = Path(".data")
    public_base_url: str = "http://localhost:8000/assets"
    api_base_url: str = "http://localhost:8000"

    # Tenancy is reserved in v1.
    workspace_id: str = "ws_default"
    creator_id: str = "cr_default"
    workspace_api_key: str = "dev-workspace-key"

    # Persistence, queue and object storage composition.
    repository_backend: Literal["memory", "sqlite", "postgres"] = "memory"
    database_url: str | None = None
    queue_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    object_store_backend: Literal["local", "silo"] = "local"

    silo_endpoint: str | None = None
    silo_public_endpoint: str | None = None
    silo_bucket: str = "pipeline"
    silo_region: str = "us-east-1"
    silo_access_key: str | None = None
    silo_secret_key: str | None = None
    presign_ttl_seconds: int = 900

    run_worker: bool = True
    worker_poll_seconds: float = 0.25
    worker_capacity: int = 4

    media_backend: Literal["stub", "ffmpeg"] = "stub"
    lip_sync_enabled: bool = False

    # Provider credentials. Stub adapters are used when unset in local/test.
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    elevenlabs_api_key: str | None = None
    synclabs_api_key: str | None = None
    provider_timeout_seconds: float = 120.0
    provider_max_attempts: int = 3

    # Comma-separated so they can be set from plain environment variables.
    allowed_input_suffixes: str = ".mp4,.mov,.m4v"
    target_language_allowlist: str = "en,es,de,pt-BR,fr,it"
    supported_source_languages: str = "en,es,de,pt-BR,fr,it,ja,ko,zh"
    max_target_languages: int = 3
    planning_models: str = (
        "openrouter/anthropic/claude-3.5-sonnet,"
        "openrouter/openai/gpt-4o,"
        "openrouter/google/gemini-1.5-pro"
    )
    copy_models: str = (
        "openrouter/anthropic/claude-3.5-sonnet,"
        "openrouter/openai/gpt-4o,"
        "openrouter/google/gemini-1.5-pro"
    )
    translation_models: str = (
        "openrouter/anthropic/claude-3.5-sonnet,"
        "openrouter/openai/gpt-4o-mini,"
        "openrouter/google/gemini-1.5-flash"
    )
    default_planning_model: str = "openrouter/anthropic/claude-3.5-sonnet"
    default_copy_model: str = "openrouter/anthropic/claude-3.5-sonnet"
    default_translation_model: str = "openrouter/openai/gpt-4o-mini"
    jev_model: str = "jev-decisions-pinned"

    job_budget_usd: str = "50.00"
    monthly_budget_usd: str = "500.00"
    max_concurrent_jobs: int = 2
    quality_floor: float = 70.0
    min_clips_per_job: int = 3
    max_clips_per_job: int = 5
    max_video_minutes: float = 90.0
    max_characters_per_job: int = 60_000
    max_source_bytes: int = 2_000_000_000
    upload_part_size_bytes: int = 32 * 1024 * 1024

    retention_days: int = 7
    retention_sweep_seconds: int = 86_400
    expiry_sweep_seconds: int = 60
    notification_sweep_seconds: int = 30
    selection_gate_days: int = 7
    idempotency_retention_days: int = 7
    backup_retention_days: int = 30
    purge_confirmation_ttl_seconds: int = 600

    rate_card_version: str = "2026-10-01"
    rate_card_path: Path | None = None
    cost_margin: float = 0.20

    webhook_secret: str | None = None
    notification_webhook_url: str | None = None
    notification_signing_secret: str = "dev-notification-secret"
    cors_allowed_origins: str = "http://localhost:3000"
    jwt_secret: str = "dev-jwt-secret-change-in-production"
    jwt_access_token_ttl_seconds: int = 900  # 15 minutes
    jwt_refresh_token_ttl_seconds: int = 604800  # 7 days

    @property
    def input_suffixes(self) -> tuple[str, ...]:
        return tuple(suffix.lower() for suffix in _csv(self.allowed_input_suffixes))

    @property
    def allowlist(self) -> list[str]:
        return list(_csv(self.target_language_allowlist))

    @property
    def source_languages(self) -> tuple[str, ...]:
        return _csv(self.supported_source_languages)

    @property
    def planning_model_allowlist(self) -> tuple[str, ...]:
        return _csv(self.planning_models)

    @property
    def copy_model_allowlist(self) -> tuple[str, ...]:
        return _csv(self.copy_models)

    @property
    def translation_model_allowlist(self) -> tuple[str, ...]:
        return _csv(self.translation_models)

    @property
    def cors_origins(self) -> list[str]:
        return list(_csv(self.cors_allowed_origins))

    @property
    def default_models(self) -> dict[str, str]:
        return {
            "planning": self.default_planning_model,
            "copy": self.default_copy_model,
            "translation": self.default_translation_model,
        }

    @property
    def model_allowlists(self) -> dict[str, tuple[str, ...]]:
        return {
            "planning": self.planning_model_allowlist,
            "copy": self.copy_model_allowlist,
            "translation": self.translation_model_allowlist,
        }

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    @property
    def workspace_dir(self) -> Path:
        return self.data_dir / "workspace"

    def ensure_directories(self) -> None:
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def validate_for_runtime(self) -> None:
        """Fail closed on unsafe production configuration.

        Local and test runs keep the convenient defaults. A production process must be
        wired to durable infrastructure and must not ship the development secrets.
        """
        if self.environment != "production":
            return

        problems: list[str] = []

        if len(self.workspace_api_key) < 32 or self.workspace_api_key == "dev-workspace-key":
            problems.append("PIPELINE_WORKSPACE_API_KEY must be a unique secret of 32+ characters")
        if (
            len(self.notification_signing_secret) < 32
            or self.notification_signing_secret == "dev-notification-secret"
        ):
            problems.append(
                "PIPELINE_NOTIFICATION_SIGNING_SECRET must be a unique secret of 32+ characters"
            )
        if not self.webhook_secret or len(self.webhook_secret) < 16:
            problems.append("PIPELINE_WEBHOOK_SECRET must be set to a secret of 16+ characters")

        for name, value in (
            ("PIPELINE_API_BASE_URL", self.api_base_url),
            ("PIPELINE_PUBLIC_BASE_URL", self.public_base_url),
        ):
            if not value.lower().startswith("https://"):
                problems.append(f"{name} must use https in production")

        if self.repository_backend != "postgres":
            problems.append("PIPELINE_REPOSITORY_BACKEND must be postgres")
        if not self.database_url:
            problems.append("PIPELINE_DATABASE_URL is required")
        if self.queue_backend != "redis":
            problems.append("PIPELINE_QUEUE_BACKEND must be redis")
        if not self.redis_url:
            problems.append("PIPELINE_REDIS_URL is required")

        if self.object_store_backend != "silo":
            problems.append("PIPELINE_OBJECT_STORE_BACKEND must be silo")
        for name, value in (
            ("PIPELINE_SILO_ENDPOINT", self.silo_endpoint),
            ("PIPELINE_SILO_PUBLIC_ENDPOINT", self.silo_public_endpoint),
            ("PIPELINE_SILO_ACCESS_KEY", self.silo_access_key),
            ("PIPELINE_SILO_SECRET_KEY", self.silo_secret_key),
        ):
            if not value:
                problems.append(f"{name} is required")
        if not self.silo_bucket:
            problems.append("PIPELINE_SILO_BUCKET is required")

        if self.media_backend != "ffmpeg":
            problems.append("PIPELINE_MEDIA_BACKEND must be ffmpeg")
        if not self.input_suffixes:
            problems.append("PIPELINE_ALLOWED_INPUT_SUFFIXES must not be empty")
        if not self.allowlist:
            problems.append("PIPELINE_TARGET_LANGUAGE_ALLOWLIST must not be empty")
        if self.job_budget_usd == "0" or self.monthly_budget_usd == "0":
            problems.append("Job and monthly budgets must be positive")

        if problems:
            raise RuntimeError(
                "Invalid production configuration:\n- " + "\n- ".join(problems)
            )
