"""Runtime configuration, loaded from environment variables prefixed with PIPELINE_."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    run_worker: bool = True
    worker_poll_seconds: float = 0.25

    media_backend: Literal["stub", "ffmpeg"] = "stub"
    lip_sync_enabled: bool = False

    # Comma-separated so it can be set from a plain environment variable.
    allowed_input_suffixes: str = ".mp4,.mov,.m4v"
    max_video_minutes: float = 90.0
    max_characters_per_job: int = 60_000
    max_target_languages: int = 3
    min_clips_per_job: int = 3
    max_clips_per_job: int = 5

    retention_days: int = 7
    retention_sweep_seconds: int = 86_400

    webhook_secret: str | None = None
    notification_webhook_url: str | None = None

    @property
    def input_suffixes(self) -> tuple[str, ...]:
        return tuple(
            suffix.strip().lower()
            for suffix in self.allowed_input_suffixes.split(",")
            if suffix.strip()
        )

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    @property
    def workspace_dir(self) -> Path:
        return self.data_dir / "workspace"

    def ensure_directories(self) -> None:
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
