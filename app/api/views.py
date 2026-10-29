"""Public JSON views over internal domain objects."""

from __future__ import annotations

from datetime import datetime

from app.domain.enums import JobStatus
from app.domain.models import CostLedgerEntry, Job, JobEvent, SourceUpload
from app.domain.money import format_usd
from app.services.cost import CostService
from app.services.review import ReviewService


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _source_language(job: Job) -> dict | None:
    if job.source_language is None:
        return None
    return {
        "code": job.source_language.code,
        "origin": job.source_language.origin.value,
        "detected_code": job.source_language.detected_code,
    }


def clip_view(clip) -> dict:
    return {
        "segment_id": clip.segment_id,
        "start_time": clip.start_time,
        "end_time": clip.end_time,
        "hook_title": clip.hook_title,
        "caption": clip.caption,
        "selection_score": clip.selection_score,
        "score_breakdown": clip.score_breakdown.model_dump(mode="json"),
        "rationale": clip.rationale,
        "video_asset_url": clip.video_asset_url,
        "localized_assets": dict(clip.localized_assets),
        "localized_copy": {
            language: copy.model_dump(mode="json")
            for language, copy in clip.localized_copy.items()
        },
    }


async def job_view(
    job: Job,
    *,
    cost: CostService,
    review: ReviewService,
) -> dict:
    summary = await cost.summary(job)
    projected = None
    if job.status is JobStatus.AWAITING_SELECTION:
        projected = format_usd(job.projected_total_micro_usd)
    elif job.selection is not None:
        projected = format_usd(job.selection.expected_total_micro_usd)

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "stage": job.stage.value if job.stage else None,
        "source": job.source.public_dict() if job.source else None,
        "source_language": _source_language(job),
        "target_languages": list(job.target_languages),
        "lip_sync": job.lip_sync,
        "parent_job_id": job.parent_job_id,
        "derived_mode": job.derived_mode.value if job.derived_mode else None,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "expires_at": _iso(job.expires_at),
        "review_url": review.review_url(job),
        "segments": [clip_view(clip) for clip in job.segments],
        "content": {
            "linkedin_post": job.content.linkedin_post if job.content else "",
            "newsletter": job.content.newsletter if job.content else "",
        },
        "copy_origin": job.copy_origin.model_dump(mode="json"),
        "selection": (
            {
                "segment_ids": list(job.selection.segment_ids),
                "languages": list(job.selection.languages),
                "expected_total_usd": format_usd(job.selection.expected_total_micro_usd),
                "confirmed_at": _iso(job.selection.confirmed_at),
            }
            if job.selection
            else None
        ),
        "cost": {
            "job_budget_usd": format_usd(summary["job_budget_micro_usd"]),
            "spent_usd": format_usd(summary["spent_micro_usd"]),
            "workspace_remaining_usd": format_usd(
                summary["workspace_remaining_micro_usd"]
            ),
            "projected_localization_usd": projected,
        },
        "error": (
            {
                "code": job.error_code or "internal_error",
                "message": job.error_message or job.error or "",
                "retryable": job.retryable,
            }
            if job.status is JobStatus.FAILED
            else None
        ),
    }


def job_summary(job: Job, *, review: ReviewService) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "stage": job.stage.value if job.stage else None,
        "created_at": _iso(job.created_at),
        "expires_at": _iso(job.expires_at),
        "review_url": review.review_url(job),
    }


def event_view(event: JobEvent) -> dict:
    return {
        "event_id": event.event_id,
        "type": event.type,
        "stage": event.stage.value if event.stage else None,
        "payload": event.payload,
        "created_at": _iso(event.created_at),
    }


def ledger_view(entry: CostLedgerEntry) -> dict:
    return {
        "entry_id": entry.entry_id,
        "stage": entry.stage.value,
        "provider": entry.provider,
        "model": entry.model,
        "units": entry.units,
        "unit_type": entry.unit_type.value,
        "rate_usd": format_usd(entry.base_rate_micro_usd),
        "estimated_usd": format_usd(entry.estimated_micro_usd),
        "actual_usd": (
            format_usd(entry.actual_micro_usd)
            if entry.actual_micro_usd is not None
            else None
        ),
        "rate_card_version": entry.rate_card_version,
        "created_at": _iso(entry.created_at),
    }


def workspace_view(snapshot: dict) -> dict:
    voice = snapshot["voice_profile"]
    return {
        "workspace_id": snapshot["workspace_id"],
        "target_language_allowlist": snapshot["target_language_allowlist"],
        "default_models": snapshot["default_models"],
        "job_budget_usd": format_usd(snapshot["job_budget_micro_usd"]),
        "monthly_budget_usd": format_usd(snapshot["monthly_budget_micro_usd"]),
        "max_concurrent_jobs": snapshot["max_concurrent_jobs"],
        "max_video_minutes": snapshot["max_video_minutes"],
        "current_month_spend_usd": format_usd(
            snapshot["current_month_spend_micro_usd"]
        ),
        "remaining_usd": format_usd(snapshot["remaining_micro_usd"]),
        "voice_profile": (
            {
                "provider": voice["provider"],
                "voice_id": voice["voice_id"],
                "updated_at": _iso(voice["updated_at"]),
            }
            if voice
            else None
        ),
    }


def upload_view(upload: SourceUpload) -> dict:
    return {
        "upload_id": upload.upload_id,
        "key": upload.key,
        "size_bytes": upload.actual_size_bytes,
        "status": upload.status.value,
    }
