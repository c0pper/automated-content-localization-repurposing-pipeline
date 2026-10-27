"""Selection Gate validation and cost-matrix helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.domain.enums import CostUnitType
from app.domain.errors import GuardrailViolation
from app.domain.models import Clip, CostCell, Job
from app.domain.money import with_margin
from app.domain.rate_card import RateCard


def _primary_subtag(code: str) -> str:
    return code.split("-", 1)[0].lower()


def language_matches(a: str, b: str) -> bool:
    return _primary_subtag(a) == _primary_subtag(b)


def validate_selection_shape(
    job: Job,
    segment_ids: Sequence[int],
    languages: Sequence[str],
) -> None:
    """Validate that the request is a rectangle over the Job's Clips and languages."""
    known_segments = {clip.segment_id for clip in job.segments}
    unknown = [segment_id for segment_id in segment_ids if segment_id not in known_segments]
    if unknown:
        raise GuardrailViolation(
            "invalid_selection",
            f"Unknown segment_ids: {unknown}",
            details={"segment_ids": unknown},
        )

    allowed_languages = set(job.target_languages)
    widened = [language for language in languages if language not in allowed_languages]
    if widened:
        raise GuardrailViolation(
            "invalid_selection",
            "The Selection Gate can narrow but never widen Target Languages",
            details={"languages": widened},
        )

    if len(set(segment_ids)) != len(segment_ids):
        raise GuardrailViolation("invalid_selection", "segment_ids must be unique")
    if len(set(languages)) != len(languages):
        raise GuardrailViolation("invalid_selection", "languages must be unique")

    empty_clips = len(segment_ids) == 0
    empty_languages = len(languages) == 0
    if empty_clips != empty_languages:
        raise GuardrailViolation(
            "invalid_selection",
            "A non-empty selection requires both Clips and languages; "
            "an empty selection requires both to be empty",
        )


def is_empty_selection(segment_ids: Sequence[int], languages: Sequence[str]) -> bool:
    return not segment_ids and not languages


def build_cost_matrix(
    job: Job,
    *,
    rate_card: RateCard,
    clips: Iterable[Clip] | None = None,
) -> list[CostCell]:
    """Price every Clip by every declared Target Language."""
    clip_list = list(clips if clips is not None else job.segments)
    cells: list[CostCell] = []
    for clip in clip_list:
        characters = len(clip.source_text or "")
        duration = _duration_seconds(clip)
        for language in job.target_languages:
            translation = rate_card.estimate(
                "openrouter", "translation", characters, unit_type=CostUnitType.CHARACTERS
            )
            voice = rate_card.estimate(
                "elevenlabs",
                "eleven_multilingual_v2",
                characters,
                unit_type=CostUnitType.CHARACTERS,
            )
            lip_sync = (
                rate_card.estimate(
                    "synclabs",
                    "lipsync-2",
                    duration,
                    unit_type=CostUnitType.SECONDS,
                )
                if job.lip_sync
                else 0
            )
            cells.append(
                CostCell(
                    segment_id=clip.segment_id,
                    language=language,
                    translation_micro_usd=translation,
                    voice_micro_usd=voice,
                    lip_sync_micro_usd=lip_sync,
                    total_micro_usd=translation + voice + lip_sync,
                )
            )
    return cells


def price_selection(
    matrix: Sequence[CostCell],
    segment_ids: Sequence[int],
    languages: Sequence[str],
) -> int:
    """Return the projected total for a rectangle using the active matrix."""
    clips = set(segment_ids)
    langs = set(languages)
    return sum(
        cell.total_micro_usd
        for cell in matrix
        if cell.segment_id in clips and cell.language in langs
    )


def projected_translation_and_voice(
    *,
    source_text: str,
    duration_seconds: float,
    language: str,
    rate_card: RateCard,
    lip_sync: bool,
) -> int:
    """Projected cost of one Clip-by-Language cell (used by tests and planners)."""
    characters = len(source_text)
    total = rate_card.estimate(
        "openrouter", "translation", characters, unit_type=CostUnitType.CHARACTERS
    ) + rate_card.estimate(
        "elevenlabs",
        "eleven_multilingual_v2",
        characters,
        unit_type=CostUnitType.CHARACTERS,
    )
    if lip_sync:
        total += rate_card.estimate(
            "synclabs", "lipsync-2", duration_seconds, unit_type=CostUnitType.SECONDS
        )
    return total


def _duration_seconds(clip: Clip) -> float:
    from app.domain.timestamps import parse_timestamp

    try:
        return max(0.0, parse_timestamp(clip.end_time) - parse_timestamp(clip.start_time))
    except ValueError:
        return 0.0


def estimate_translation_cost(characters: int, rate_card: RateCard) -> int:
    return rate_card.estimate(
        "openrouter", "translation", characters, unit_type=CostUnitType.CHARACTERS
    )


def estimate_voice_cost(characters: int, rate_card: RateCard) -> int:
    return rate_card.estimate(
        "elevenlabs",
        "eleven_multilingual_v2",
        characters,
        unit_type=CostUnitType.CHARACTERS,
    )


def estimate_lip_sync_cost(seconds: float, rate_card: RateCard) -> int:
    return with_margin(rate_card.rate_for("synclabs", "lipsync-2"), seconds, rate_card.margin)
