from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.stubs import StubTranscriber
from app.config import Settings
from app.container import build_container
from app.domain.enums import JobStage, JobStatus
from app.domain.errors import GuardrailViolation


async def test_pipeline_produces_clips_copy_and_localized_assets(settings, tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"not-a-real-video")

    container = build_container(settings)
    job = await container.submissions.submit(
        input_url=str(source),
        target_languages=["es", "de"],
    )

    result = await container.orchestrator.run(job.job_id)
    stored = await container.repository.get(job.job_id)

    assert stored is not None
    assert result.status is JobStatus.COMPLETED
    assert stored.status is JobStatus.COMPLETED
    assert stored.stage is None
    assert stored.error is None

    # 3-5 English vertical clips, localized into both requested languages.
    assert len(stored.segments) == 3
    for segment in stored.segments:
        assert segment.start_time.count(":") == 2
        assert set(segment.localized_assets) == {"es", "de"}
        assert segment.video_asset_url is not None
        assert segment.source_text

    # Social copy and newsletter are generated and attached to the job.
    assert stored.content is not None
    assert stored.content.linkedin_post.startswith("# LinkedIn breakdown")
    assert stored.content.newsletter.startswith("# Newsletter draft")

    # Artifacts are uploaded to the object store under the documented layout.
    job_dir = settings.objects_dir / "jobs" / stored.job_id
    assert (job_dir / "clips" / "clip_1_en.mp4").is_file()
    assert (job_dir / "localized" / "clip_1_es.mp4").is_file()
    assert (job_dir / "localized" / "clip_1_de.mp4").is_file()
    assert (job_dir / "copy" / "linkedin.md").is_file()
    assert (job_dir / "copy" / "newsletter.md").is_file()
    assert (job_dir / "copy" / "captions.csv").is_file()

    # Budget accounting is recorded on the job.
    assert stored.usage.input_minutes == pytest.approx(10.0)
    assert stored.usage.characters > 0


async def test_guardrail_failure_is_recorded_on_the_job(settings, tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")

    constrained = settings.model_copy(update={"max_video_minutes": 1.0})
    container = build_container(constrained)

    job = await container.submissions.submit(
        input_url=str(source),
        target_languages=["es"],
    )
    result = await container.orchestrator.run(job.job_id)

    assert result.status is JobStatus.FAILED
    assert result.stage is JobStage.INGEST
    assert result.error is not None
    assert "media_too_long" in result.error
    assert result.segments == []


async def test_submission_rejects_too_many_languages(settings, tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")
    container = build_container(settings)

    with pytest.raises(GuardrailViolation) as excinfo:
        await container.submissions.submit(
            input_url=str(source),
            target_languages=["es", "de", "fr", "pt"],
        )

    assert excinfo.value.code == "too_many_languages"


async def test_localization_budget_is_checked_before_paid_calls(settings, tmp_path):
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"x")

    transcript = await StubTranscriber().transcribe(Path("audio.wav"))
    limit = len(transcript.text) + 100

    constrained = settings.model_copy(update={"max_characters_per_job": limit})
    container = build_container(constrained)
    job = await container.submissions.submit(
        input_url=str(source),
        target_languages=["es", "de"],
    )
    result = await container.orchestrator.run(job.job_id)

    assert result.status is JobStatus.FAILED
    assert result.stage is JobStage.LOCALIZATION
    assert result.error is not None
    assert "character_budget_exceeded" in result.error
    assert result.segments[0].localized_assets == {}


def test_build_container_creates_data_directories(settings):
    build_container(settings)
    assert settings.objects_dir.is_dir()
    assert settings.workspace_dir.is_dir()


def test_settings_rejects_unknown_media_backend():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, media_backend="nope")

    settings = Settings(_env_file=None, media_backend="ffmpeg")
    assert settings.media_backend == "ffmpeg"
