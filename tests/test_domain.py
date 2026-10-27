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


def test_money_is_exact_integer_micro_usd():
    from app.domain.money import format_usd, parse_usd, with_margin

    assert parse_usd("0.000001") == 1
    assert parse_usd("50.00") == 50_000_000
    assert parse_usd("0.1") == 100_000
    assert format_usd(50_000_000) == "50.00"
    assert format_usd(1) == "0.000001"
    assert format_usd(120_000) == "0.12"
    assert with_margin(10_000, 3, 0.20) == 36_000
    assert with_margin(10_000, 0, 0.20) == 0

    with pytest.raises(ValueError):
        parse_usd("-1")
    with pytest.raises(ValueError):
        parse_usd("not-money")
    with pytest.raises(ValueError):
        format_usd(-1)


def test_rate_card_applies_margin_and_fails_closed():
    from app.domain.money import with_margin
    from app.domain.rate_card import RateCard

    card = RateCard.default(version="v-test", margin=0.20)
    assert card.estimate("openrouter", "translation", 100) == with_margin(120, 100, 0.20)
    assert card.estimate("openrouter", "some-curated-model", 10) == with_margin(100, 10, 0.20)

    with pytest.raises(Exception) as excinfo:
        card.estimate("unknown", "model", 1)
    assert getattr(excinfo.value, "code", None) == "rate_missing"

    with pytest.raises(Exception) as excinfo:
        card.estimate("synclabs", "lipsync-2", 1, unit_type=CostUnitType.CHARACTERS)
    assert getattr(excinfo.value, "code", None) == "rate_unit_mismatch"


def test_jev_score_math_and_quality_floor():
    from app.domain.models import ClipCandidate
    from app.domain.scoring import (
        apply_quality_floor,
        breakdown_from_distributions,
        expected_value,
        score_candidate,
        selection_score,
    )

    assert expected_value([0, 0, 0, 0, 1]) == 4.0
    assert expected_value([1, 0, 0, 0, 0]) == 0.0

    distributions = {
        "hook_strength": [0, 0, 0, 0.4, 0.6],
        "standalone_clarity": [0, 0, 0, 0.8, 0.2],
        "emotional_payoff": [0, 0, 0, 1, 0],
        "business_fit": [0, 0, 0, 0.6, 0.4],
    }
    breakdown = breakdown_from_distributions(distributions)
    assert breakdown.hook_strength == 3.6
    assert breakdown.standalone_clarity == 3.2
    assert breakdown.emotional_payoff == 3.0
    assert breakdown.business_fit == 3.4
    assert selection_score(breakdown) == 82.5

    candidate = ClipCandidate(
        segment_id=1,
        start_seconds=0,
        end_seconds=10,
        hook_title="Hook",
        caption="Caption",
    )
    scored = score_candidate(candidate, distributions)
    assert scored.selection_score == 82.5

    weak = scored.model_copy(update={"segment_id": 2, "selection_score": 40.0})
    passing = apply_quality_floor([scored, weak], floor=70, max_clips=5)
    assert [item.segment_id for item in passing] == [1]


def test_selection_rectangle_validation_and_pricing():
    from app.domain.models import Clip, CostCell
    from app.domain.rate_card import RateCard
    from app.domain.selection import (
        build_cost_matrix,
        is_empty_selection,
        price_selection,
        validate_selection_shape,
    )

    clip = Clip(
        segment_id=1,
        start_time="00:00:00",
        end_time="00:01:00",
        hook_title="Hook",
        caption="Caption",
        source_text="x" * 100,
        base_clip_master_key="masters/1.mp4",
    )
    job = Job(
        job_id="job_selection",
        target_languages=["es", "de"],
        lip_sync=False,
        segments=[clip],
    )

    validate_selection_shape(job, [1], ["es"])
    validate_selection_shape(job, [], [])
    assert is_empty_selection([], [])

    with pytest.raises(Exception) as excinfo:
        validate_selection_shape(job, [2], ["es"])
    assert getattr(excinfo.value, "code", None) == "invalid_selection"

    with pytest.raises(Exception) as excinfo:
        validate_selection_shape(job, [1], ["fr"])
    assert getattr(excinfo.value, "code", None) == "invalid_selection"

    with pytest.raises(Exception) as excinfo:
        validate_selection_shape(job, [1], [])
    assert getattr(excinfo.value, "code", None) == "invalid_selection"

    matrix = build_cost_matrix(job, rate_card=RateCard.default())
    assert len(matrix) == 2
    assert price_selection(matrix, [1], ["es"]) == matrix[0].total_micro_usd
    assert price_selection(matrix, [1], ["es", "de"]) == sum(
        cell.total_micro_usd for cell in matrix
    )
    assert price_selection(matrix, [], []) == 0
    assert all(cell.translation_micro_usd > 0 for cell in matrix)

    lip_sync_job = job.model_copy(update={"lip_sync": True})
    lip_matrix = build_cost_matrix(lip_sync_job, rate_card=RateCard.default())
    assert all(cell.lip_sync_micro_usd > 0 for cell in lip_matrix)

    cells = [
        CostCell(
            segment_id=1,
            language="es",
            translation_micro_usd=10,
            voice_micro_usd=20,
            total_micro_usd=30,
        )
    ]
    assert price_selection(cells, [1], ["es"]) == 30

