from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.enums import (
    CostUnitType,
    DerivedMode,
    JobStage,
    JobStatus,
    LocalizedClipStatus,
    NotificationType,
    PurgeStatus,
    SourceLanguageOrigin,
)
from app.domain.errors import InvalidJobTransitionError
from app.domain.lifecycle import allowed_transitions, can_transition, ensure_transition
from app.domain.models import (
    Clip,
    CostLedgerEntry,
    IdempotencyRecord,
    Job,
    JobEvent,
    LocalizedClip,
    NotificationOutboxEntry,
    Purge,
    ReviewToken,
    Selection,
    SourceLanguage,
    VoiceProfile,
    WorkspaceSettings,
)


def _job(**overrides) -> Job:
    return Job(
        job_id="job_test",
        input_url="https://example.com/raw.mp4",
        **overrides,
    )


def _clip(**overrides) -> Clip:
    values = {
        "segment_id": 1,
        "start_time": "00:00:00",
        "end_time": "00:00:10",
        "hook_title": "Why ads fail",
        "caption": "Stop wasting budget.",
        "source_text": "The spoken source text for this clip.",
        "base_clip_master_key": "jobs/job_test/masters/clip_1.mp4",
    }
    values.update(overrides)
    return Clip(**values)


def test_documented_lifecycle_path_is_allowed():
    job = _job()

    job.transition_to(JobStatus.PROCESSING)
    job.transition_to(JobStatus.AWAITING_SELECTION)
    job.transition_to(JobStatus.PROCESSING)
    job.transition_to(JobStatus.COMPLETED)

    assert job.status is JobStatus.COMPLETED
    assert job.status.is_terminal


def test_cancellation_is_terminal():
    job = _job()
    job.transition_to(JobStatus.CANCELLED)

    assert job.status.is_terminal
    with pytest.raises(InvalidJobTransitionError):
        job.transition_to(JobStatus.PROCESSING)


def test_failed_job_can_be_retried():
    job = _job()
    job.transition_to(JobStatus.PROCESSING)
    job.transition_to(JobStatus.FAILED)

    assert not job.status.is_terminal
    job.transition_to(JobStatus.PROCESSING)

    assert job.status is JobStatus.PROCESSING


def test_illegal_transition_is_rejected():
    with pytest.raises(InvalidJobTransitionError):
        _job().transition_to(JobStatus.COMPLETED)


def test_same_status_is_a_no_op():
    job = _job()

    job.transition_to(JobStatus.RECEIVED)

    assert job.status is JobStatus.RECEIVED


def test_transition_table_matches_the_spec():
    assert can_transition(JobStatus.RECEIVED, JobStatus.PROCESSING)
    assert can_transition(JobStatus.AWAITING_SELECTION, JobStatus.EXPIRED)
    assert can_transition(JobStatus.FAILED, JobStatus.PROCESSING)
    assert not can_transition(JobStatus.COMPLETED, JobStatus.PROCESSING)
    assert not can_transition(JobStatus.EXPIRED, JobStatus.PROCESSING)
    assert not can_transition(JobStatus.AWAITING_SELECTION, JobStatus.COMPLETED)
    assert JobStatus.PROCESSING in set(allowed_transitions(JobStatus.RECEIVED))


@pytest.mark.parametrize("current", list(JobStatus))
def test_every_transition_pair_is_guarded(current):
    for target in JobStatus:
        expected = current == target or target in set(allowed_transitions(current))
        assert can_transition(current, target) is expected

        if expected:
            ensure_transition(current, target)
        else:
            with pytest.raises(InvalidJobTransitionError):
                ensure_transition(current, target)


def test_internal_clip_fields_are_not_public():
    clip = _clip()
    payload = clip.model_dump(mode="json")

    assert payload["segment_id"] == 1
    assert "source_text" not in payload
    assert "base_clip_master_key" not in payload


def test_job_keeps_the_segments_wire_alias():
    job = _job(segments=[_clip()])
    payload = job.model_dump(mode="json")

    assert "segments" in payload
    assert "clips" not in payload
    assert payload["segments"][0]["segment_id"] == 1
    assert "source_text" not in payload["segments"][0]
    assert job.clips == job.segments


def test_source_language_requires_an_origin():
    language = SourceLanguage(code="en", origin=SourceLanguageOrigin.DECLARED)

    assert language.origin is SourceLanguageOrigin.DECLARED
    with pytest.raises(ValidationError):
        SourceLanguage(code="en")


def test_v1_records_are_constructible():
    now = datetime.now(UTC)
    selection = Selection(
        segment_ids=[1, 2],
        languages=["es", "de"],
        expected_total_micro_usd=1_250_000,
        confirmed_at=now,
    )
    localized = LocalizedClip(
        clip_id="clip_job_test_1",
        language="es",
        localized_hook_title="Por que fallan",
        localized_caption="Deja de gastar.",
        video_asset_key="jobs/job_test/localized/clip_1_es.mp4",
        status=LocalizedClipStatus.COMPLETED,
    )
    entry = CostLedgerEntry(
        entry_id="cost_1",
        job_id="job_test",
        stage=JobStage.SCORING,
        provider="jev",
        model="jev-pinned",
        units=4,
        unit_type=CostUnitType.REQUESTS,
        base_rate_micro_usd=10_000,
        estimated_micro_usd=12_000,
        rate_card_version="2026-10-01",
        created_at=now,
    )
    event = JobEvent(event_id="evt_1", job_id="job_test", type="selection_required")
    outbox = NotificationOutboxEntry(
        event_id="evt_1",
        job_id="job_test",
        type=NotificationType.SELECTION_REQUIRED,
    )
    idempotency = IdempotencyRecord(
        workspace_id="ws_test",
        key="key_1",
        method="POST",
        path="/api/jobs",
        request_hash="abc",
        response_status=202,
        expires_at=now + timedelta(days=7),
    )
    token = ReviewToken(token_id="tok_1", job_id="job_test", token_hash="hash")
    profile = VoiceProfile(workspace_id="ws_test", voice_id="voice_1")
    settings = WorkspaceSettings(workspace_id="ws_test")
    purge = Purge(purge_id="purge_1", workspace_id="ws_test")

    assert selection.languages == ["es", "de"]
    assert localized.status is LocalizedClipStatus.COMPLETED
    assert entry.unit_type is CostUnitType.REQUESTS
    assert event.type == "selection_required"
    assert outbox.type is NotificationType.SELECTION_REQUIRED
    assert idempotency.response_status == 202
    assert token.job_id == "job_test"
    assert profile.provider == "elevenlabs"
    assert settings.target_language_allowlist == ["en", "es", "de", "pt-BR", "fr", "it"]
    assert settings.job_budget_micro_usd == 50_000_000
    assert settings.monthly_budget_micro_usd == 500_000_000
    assert settings.max_concurrent_jobs == 2
    assert purge.status is PurgeStatus.DRY_RUN


def test_derived_mode_vocabulary():
    assert DerivedMode.COPY.value == "copy"
    assert DerivedMode.LOCALIZATION.value == "localization"
