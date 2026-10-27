from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.in_memory_stores import InMemoryOutbox, SystemClock
from app.adapters.notifications import RecordingNotifier, sign_payload, verify_signature
from app.adapters.stubs import StubTranscriber
from app.config import Settings
from app.container import build_container
from app.domain.enums import JobStage, JobStatus, LocalizedClipStatus, NotificationType
from app.domain.errors import GuardrailViolation
from app.domain.models import (
    Job,
    LocalizedClip,
    SourceInput,
    Transcript,
)
from app.ports.ai import VoiceSynthesisResult
from app.services.notifications import NotificationService
from tests.helpers import make_settings, source_file


async def _submit(container, source: Path, **kwargs) -> Job:
    return await container.submissions.submit(
        source=SourceInput(type="url", url=str(source)),
        target_languages=kwargs.pop("target_languages", ["es", "de"]),
        **kwargs,
    )


async def _to_gate(container, source: Path, **kwargs) -> Job:
    job = await _submit(container, source, **kwargs)
    result = await container.orchestrator.run(job.job_id)
    assert result.status is JobStatus.AWAITING_SELECTION, result
    return result


async def _confirm_first_cell(container, job: Job, *, segment_id: int = 1, language: str = "es"):
    matrix = container.selection.matrix(job)
    total = sum(
        cell.total_micro_usd
        for cell in matrix
        if cell.segment_id == segment_id and cell.language == language
    )
    return await container.selection.confirm(
        job,
        segment_ids=[segment_id],
        languages=[language],
        expected_total_micro_usd=total,
    )


async def test_pipeline_stops_at_selection_gate_then_completes(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source)
    stored = await container.repository.get(job.job_id)
    assert stored is not None
    assert stored.status is JobStatus.AWAITING_SELECTION
    assert stored.stage is None
    assert stored.transcript is not None
    assert len(stored.segments) == 3
    assert all(clip.source_text for clip in stored.segments)
    assert all(clip.base_clip_master_key for clip in stored.segments)
    assert stored.projected_total_micro_usd > 0

    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    confirmed = await _confirm_first_cell(container, stored)
    assert confirmed.status is JobStatus.PROCESSING
    assert confirmed.stage is JobStage.LOCALIZATION

    result = await container.orchestrator.run(stored.job_id)
    assert result.status is JobStatus.COMPLETED, result
    assert result.stage is None
    assert result.error is None

    assert set(result.segments[0].localized_assets) == {"es"}
    assert result.segments[1].localized_assets == {}
    assert result.segments[0].localized_copy["es"].hook_title.startswith("[es]")
    assert result.content is not None
    assert result.content.linkedin_post.startswith("# LinkedIn breakdown")
    assert result.content.newsletter.startswith("# Newsletter draft")

    job_dir = settings.objects_dir / "jobs" / result.job_id
    assert (job_dir / "clips" / "clip_1_en.mp4").is_file()
    assert (job_dir / "masters" / "clip_1_en.mp4").is_file()
    assert (job_dir / "localized" / "clip_1_es.mp4").is_file()
    assert (job_dir / "copy" / "linkedin.md").is_file()
    assert (job_dir / "copy" / "newsletter.md").is_file()
    assert not (job_dir / "localized" / "clip_2_es.mp4").exists()

    events = await container.events.list(result.job_id)
    types = [event.type for event in events]
    assert "gate_opened" in types
    assert "selection_confirmed" in types
    assert "bundle_ready" in types


async def test_media_guardrail_failure_is_recorded_on_the_job(tmp_path):
    settings = make_settings(tmp_path, max_video_minutes=1.0)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _submit(container, source, target_languages=["es"])
    result = await container.orchestrator.run(job.job_id)

    assert result.status is JobStatus.FAILED
    assert result.stage is JobStage.INGEST
    assert result.error_code == "media_too_long"
    assert result.retryable is False
    assert result.segments == []


async def test_submission_rejects_too_many_languages(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    with pytest.raises(GuardrailViolation) as excinfo:
        await _submit(container, source, target_languages=["es", "de", "fr", "it"])

    assert excinfo.value.code == "too_many_languages"


async def test_character_budget_fails_before_planning(tmp_path):
    settings = make_settings(tmp_path, max_characters_per_job=10)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _submit(container, source, target_languages=["es"])
    result = await container.orchestrator.run(job.job_id)

    assert result.status is JobStatus.FAILED
    assert result.stage is JobStage.INTELLIGENCE
    assert result.error_code == "character_budget_exceeded"


async def test_quality_floor_failure_is_not_retryable(tmp_path):
    settings = make_settings(tmp_path, quality_floor=101.0)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _submit(container, source, target_languages=["es"])
    result = await container.orchestrator.run(job.job_id)

    assert result.status is JobStatus.FAILED
    assert result.stage is JobStage.INTELLIGENCE
    assert result.error_code == "quality_floor_not_met"
    assert result.retryable is False
    assert result.segments == []


async def test_missing_voice_profile_fails_then_retry_succeeds(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source)
    confirmed = await _confirm_first_cell(container, job)
    failed = await container.orchestrator.run(confirmed.job_id)

    assert failed.status is JobStatus.FAILED
    assert failed.stage is JobStage.LOCALIZATION
    assert failed.error_code == "voice_profile_missing"
    assert failed.retryable is True
    assert failed.segments[0].localized_assets == {}

    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    retried = await container.lifecycle.retry(failed)
    assert retried.status is JobStatus.PROCESSING
    result = await container.orchestrator.run(retried.job_id)

    assert result.status is JobStatus.COMPLETED, result
    assert set(result.segments[0].localized_assets) == {"es"}


async def test_lip_sync_is_priced_and_recorded(tmp_path):
    settings = make_settings(tmp_path, lip_sync_enabled=True)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source, lip_sync=True)
    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    matrix = container.selection.matrix(job)
    assert all(cell.lip_sync_micro_usd > 0 for cell in matrix)

    confirmed = await _confirm_first_cell(container, job)
    result = await container.orchestrator.run(confirmed.job_id)
    assert result.status is JobStatus.COMPLETED, result
    localized = result.localized_clips[0]
    assert localized.lip_sync is True

    entries = await container.cost.entries(result.job_id)
    assert any(entry.provider == "synclabs" for entry in entries)


async def test_unavailable_lip_sync_fails_without_fallback(tmp_path):
    settings = make_settings(tmp_path, lip_sync_enabled=True)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source, lip_sync=True)
    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    container.orchestrator._localization._lip_syncer = None
    confirmed = await _confirm_first_cell(container, job)
    result = await container.orchestrator.run(confirmed.job_id)

    assert result.status is JobStatus.FAILED
    assert result.error_code == "lip_sync_unavailable"
    assert result.retryable is True
    assert result.segments[0].localized_assets == {}
    assert result.localized_clips == []


async def test_missing_caption_alignment_fails_without_asset(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    class NoAlignmentVoice:
        async def synthesize(
            self, text, target_language, destination, *, voice_id, model=None
        ):
            return VoiceSynthesisResult(
                audio_path=destination, characters=len(text), alignment=None
            )

    job = await _to_gate(container, source)
    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    container.orchestrator._localization._voice = NoAlignmentVoice()
    confirmed = await _confirm_first_cell(container, job)
    result = await container.orchestrator.run(confirmed.job_id)

    assert result.status is JobStatus.FAILED
    assert result.error_code == "caption_alignment_unavailable"
    assert result.segments[0].localized_assets == {}
    assert result.localized_clips == []


async def test_declared_source_language_wins(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(
        container, source, target_languages=["de"], source_language="es"
    )
    assert job.source_language.code == "es"
    assert job.source_language.origin.value == "declared"


def test_source_language_falls_back_only_when_detection_is_inconclusive(tmp_path):
    settings = make_settings(tmp_path)
    container = build_container(settings)
    agent = container.orchestrator._intelligence
    job = Job(job_id="job_test", target_languages=["es"])

    detected = agent.resolve_source_language(
        job,
        Transcript(language="ja", language_confidence=0.99, duration_seconds=1),
    )
    assert detected.code == "ja"
    assert detected.origin.value == "detected"

    fallback = agent.resolve_source_language(
        job,
        Transcript(language="ja", language_confidence=0.1, duration_seconds=1),
    )
    assert fallback.code == "en"
    assert fallback.origin.value == "fallback"


async def test_retention_clears_transcript_but_keeps_clip_source_text(tmp_path):
    settings = make_settings(tmp_path, retention_days=0)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source)
    assert job.transcript is not None
    assert job.source_path is not None
    retained_text = job.segments[0].source_text
    retained_master = job.segments[0].base_clip_master_key

    job.created_at = job.created_at - timedelta(days=8)
    await container.repository.save(job)

    removed = await container.retention.sweep()
    assert removed >= 1

    stored = await container.repository.get(job.job_id)
    assert stored.transcript is None
    assert stored.source_path is None
    assert stored.segments[0].source_text == retained_text
    assert stored.segments[0].base_clip_master_key == retained_master
    assert stored.segments[0].video_asset_key is not None


async def test_cancel_prunes_incomplete_localized_artifacts(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source)
    done_key = f"jobs/{job.job_id}/localized/clip_1_es.mp4"
    pending_key = f"jobs/{job.job_id}/localized/clip_2_es.mp4"
    audio_key = f"jobs/{job.job_id}/localized/clip_2_es.wav"
    for key in (done_key, pending_key, audio_key):
        path = container.store.local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"asset")

    job.status = JobStatus.PROCESSING
    job.stage = JobStage.LOCALIZATION
    job.localized_clips = [
        LocalizedClip(
            clip_id=f"clip_{job.job_id}_1",
            segment_id=1,
            language="es",
            video_asset_key=done_key,
            status=LocalizedClipStatus.COMPLETED,
        ),
        LocalizedClip(
            clip_id=f"clip_{job.job_id}_2",
            segment_id=2,
            language="es",
            video_asset_key=pending_key,
            audio_asset_key=audio_key,
            status=LocalizedClipStatus.PENDING,
        ),
    ]
    job.segments[0].localized_assets = {"es": "url-1"}
    job.segments[1].localized_assets = {"es": "url-2"}
    await container.repository.save(job)

    await container.lifecycle.finalize_cancel(job)

    stored = await container.repository.get(job.job_id)
    assert stored.status is JobStatus.CANCELLED
    assert [item.segment_id for item in stored.localized_clips] == [1]
    assert stored.segments[0].localized_assets == {"es": "url-1"}
    assert stored.segments[1].localized_assets == {}
    assert (settings.objects_dir / done_key).is_file()
    assert not (settings.objects_dir / pending_key).exists()
    assert not (settings.objects_dir / audio_key).exists()


async def test_derived_job_uses_retained_source_text_after_transcript_pruned(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)
    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )

    parent = await _to_gate(container, source)
    await _confirm_first_cell(container, parent)
    parent = await container.orchestrator.run(parent.job_id)
    assert parent.status is JobStatus.COMPLETED

    # Simulate the Retention Sweeper: the full Transcript and Source Recording are gone.
    parent.transcript = None
    parent.source_path = None
    await container.repository.save(parent)

    class ExplodingTranscriber:
        async def transcribe(self, audio, *, language_hint=None):
            raise AssertionError("a Derived Job must not re-transcribe")

    container.orchestrator._intelligence._transcriber = ExplodingTranscriber()

    copy_child = await container.derived.derive(parent, mode="copy")
    copy_done = await container.orchestrator.run(copy_child.job_id)
    assert copy_done.status is JobStatus.COMPLETED, copy_done
    assert copy_done.copy_origin.clips == "generated"
    assert copy_done.copy_origin.linkedin == "parent"
    assert copy_done.content.linkedin_post == parent.content.linkedin_post

    localization_child = await container.derived.derive(
        parent, mode="localization", target_languages=["fr"]
    )
    assert localization_child.status is JobStatus.AWAITING_SELECTION
    assert localization_child.source_language.code == parent.source_language.code
    confirmed = await _confirm_first_cell(
        container, localization_child, language="fr"
    )
    localized = await container.orchestrator.run(confirmed.job_id)
    assert localized.status is JobStatus.COMPLETED, localized
    assert set(localized.segments[0].localized_assets) == {"fr"}


async def test_derived_copy_refreshes_clip_copy_only(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)
    container = build_container(settings)

    parent = await _to_gate(container, source)
    await container.selection.confirm(
        parent, segment_ids=[], languages=[], expected_total_micro_usd=0
    )
    parent = await container.orchestrator.run(parent.job_id)
    assert parent.status is JobStatus.COMPLETED
    child = await container.derived.derive(parent, mode="copy")
    done = await container.orchestrator.run(child.job_id)

    assert done.status is JobStatus.COMPLETED
    assert done.content.linkedin_post == parent.content.linkedin_post
    assert done.content.newsletter == parent.content.newsletter
    assert done.copy_origin.linkedin == "parent"
    assert done.copy_origin.clips == "generated"
    assert done.segments[0].hook_title == parent.segments[0].hook_title


async def test_notification_outbox_is_signed_and_at_most_once(tmp_path):
    clock = SystemClock()
    outbox = InMemoryOutbox()
    notifier = RecordingNotifier(secret="secret")
    service = NotificationService(outbox=outbox, notifier=notifier, clock=clock)
    job = Job(job_id="job_notify", status=JobStatus.AWAITING_SELECTION)

    await service.queue(job, NotificationType.SELECTION_REQUIRED, data={"review_url": "x"})
    assert await service.dispatch_pending() == 1
    assert await service.dispatch_pending() == 0
    assert len(notifier.requests) == 1

    request = notifier.requests[0]
    assert verify_signature(
        "secret",
        request["headers"]["X-Timestamp"],
        request["raw"],
        request["headers"]["X-Signature"],
    )
    assert request["body"]["type"] == "selection_required"
    assert request["body"]["job_id"] == "job_notify"

    failing = RecordingNotifier(secret="secret", fail=True)
    failure_service = NotificationService(outbox=outbox, notifier=failing, clock=clock)
    await failure_service.queue(job, NotificationType.SELECTION_EXPIRED, data={})
    assert await failure_service.dispatch_pending() == 0
    assert await failure_service.dispatch_pending() == 0
    assert failing.requests == []

    pending = await outbox.list_pending()
    assert pending == []


def test_hmac_signature_round_trip():
    signature = sign_payload("secret", "123", b'{"a":1}')
    assert verify_signature("secret", "123", b'{"a":1}', signature)
    assert not verify_signature("secret", "123", b'{"a":2}', signature)
    assert not verify_signature("other", "123", b'{"a":1}', signature)


def test_build_container_creates_data_directories(tmp_path):
    settings = make_settings(tmp_path)
    build_container(settings)
    assert settings.objects_dir.is_dir()
    assert settings.workspace_dir.is_dir()


def test_settings_rejects_unknown_media_backend():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, media_backend="nope")

    settings = Settings(_env_file=None, media_backend="ffmpeg")
    assert settings.media_backend == "ffmpeg"


async def test_sqlite_repository_round_trips_the_aggregate(tmp_path):
    settings = make_settings(tmp_path, repository_backend="sqlite")
    source = source_file(tmp_path)
    container = build_container(settings)

    job = await _to_gate(container, source)
    assert job.transcript is not None

    # Rebuild the container against the same database: durable state must survive.
    reopened = build_container(settings)
    stored = await reopened.repository.get(job.job_id)
    assert stored is not None
    assert stored.status is JobStatus.AWAITING_SELECTION
    assert stored.transcript is not None
    assert len(stored.segments) == 3
    assert stored.segments[0].source_text
    assert stored.segments[0].base_clip_master_key

    await reopened.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_test"}
    )
    confirmed = await _confirm_first_cell(reopened, stored)
    result = await reopened.orchestrator.run(confirmed.job_id)
    assert result.status is JobStatus.COMPLETED, result
    assert set(result.segments[0].localized_assets) == {"es"}

    events = await reopened.events.list(result.job_id)
    assert any(event.type == "bundle_ready" for event in events)
    entries = await reopened.cost.entries(result.job_id)
    assert entries
    tokens = await reopened.review_tokens.get_for_job(result.job_id)
    assert tokens is not None


async def test_sqlite_workspace_and_idempotency_round_trip(tmp_path):
    settings = make_settings(tmp_path, repository_backend="sqlite")
    container = build_container(settings)

    await container.workspaces.set_voice_profile(
        {"provider": "elevenlabs", "voice_id": "voice_sql"}
    )
    reopened = build_container(settings)
    profile = await reopened.workspaces.get_voice_profile()
    assert profile is not None
    assert profile.voice_id == "voice_sql"

    from datetime import UTC, datetime

    from app.domain.models import IdempotencyRecord

    now = datetime.now(UTC)
    await container.idempotency.put(
        IdempotencyRecord(
            workspace_id="ws_default",
            key="sql-key",
            method="POST",
            path="/api/jobs",
            request_hash="abc",
            response_status=202,
            response_body={"job_id": "job_sql"},
            expires_at=now + timedelta(days=7),
            created_at=now,
        )
    )
    record = await reopened.idempotency.get("ws_default", "sql-key")
    assert record is not None
    assert record.response_body == {"job_id": "job_sql"}


async def test_sqlite_lease_store_enforces_concurrency(tmp_path):
    settings = make_settings(tmp_path, repository_backend="sqlite")
    container = build_container(settings)

    assert await container.leases.acquire(
        "ws_default", "job_1", limit=1, ttl=timedelta(minutes=5)
    )
    assert not await container.leases.acquire(
        "ws_default", "job_2", limit=1, ttl=timedelta(minutes=5)
    )
    await container.leases.release("ws_default", "job_1")
    assert await container.leases.acquire(
        "ws_default", "job_2", limit=1, ttl=timedelta(minutes=5)
    )
    assert await container.leases.count("ws_default") == 1


def test_transcript_text_between_returns_the_clip_excerpt():
    transcript = Transcript(
        duration_seconds=10,
        words=[
            {"text": "before", "start": 0.0, "end": 1.0},
            {"text": "inside", "start": 2.0, "end": 3.0},
            {"text": "after", "start": 8.0, "end": 9.0},
        ],
    )
    assert transcript.text_between(1.5, 4.0) == "inside"


async def test_stub_transcriber_is_word_timed():
    transcript = await StubTranscriber().transcribe(Path("audio.wav"))
    assert transcript.words
    assert transcript.words[0].end >= transcript.words[0].start
