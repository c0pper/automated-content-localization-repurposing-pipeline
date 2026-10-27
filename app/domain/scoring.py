"""Jev scoring math and the Quality Floor.

Four signals (hook strength, standalone clarity, emotional payoff, business/CTA fit) are
distributions over the 0-4 scale. Each expected value is computed, the four values are
equally weighted and averaged, then multiplied by 25 to produce a 0-100 Selection Score.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.domain.models import ClipCandidate, ScoreBreakdown

SIGNALS: tuple[str, ...] = (
    "hook_strength",
    "standalone_clarity",
    "emotional_payoff",
    "business_fit",
)


def expected_value(distribution: Sequence[float]) -> float:
    """Return the expected value of a distribution over buckets 0..4."""
    if len(distribution) != 5:
        raise ValueError("A Jev distribution must contain five probabilities (0-4)")
    total = sum(distribution)
    if total <= 0:
        raise ValueError("A Jev distribution must have positive probability mass")
    weighted = sum(index * probability for index, probability in enumerate(distribution))
    return round(weighted / total, 2)


def breakdown_from_distributions(
    distributions: dict[str, Sequence[float]],
) -> ScoreBreakdown:
    missing = [signal for signal in SIGNALS if signal not in distributions]
    if missing:
        raise ValueError(f"Missing Jev signals: {', '.join(missing)}")
    values = {signal: expected_value(distributions[signal]) for signal in SIGNALS}
    return ScoreBreakdown(**values)


def selection_score(breakdown: ScoreBreakdown) -> float:
    values = [getattr(breakdown, signal) for signal in SIGNALS]
    return round(sum(values) / len(values) * 25, 2)


def score_candidate(
    candidate: ClipCandidate,
    distributions: dict[str, Sequence[float]],
) -> ClipCandidate:
    breakdown = breakdown_from_distributions(distributions)
    return candidate.model_copy(
        update={
            "score_breakdown": breakdown,
            "selection_score": selection_score(breakdown),
        }
    )


def apply_quality_floor(
    candidates: Iterable[ClipCandidate],
    *,
    floor: float,
    max_clips: int,
) -> list[ClipCandidate]:
    """Retain candidates at or above the floor, top-scoring first, capped at ``max_clips``."""
    passing = [candidate for candidate in candidates if candidate.selection_score >= floor]
    passing.sort(key=lambda candidate: candidate.selection_score, reverse=True)
    return passing[:max_clips]
