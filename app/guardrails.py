"""Cost, size and format guardrails.

Guardrails are pure checks: they raise :class:`GuardrailViolation` and never mutate a job.
The orchestrator decides how to record usage and failures.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from app.config import Settings
from app.domain.errors import GuardrailViolation
from app.domain.models import Job, MediaProbe, Transcript

_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")


class Guardrails:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_submission(self, input_url: str, target_languages: Sequence[str]) -> None:
        if not input_url.strip():
            raise GuardrailViolation("invalid_input", "input_url is required")

        scheme = urlsplit(input_url).scheme.lower() if "://" in input_url else ""
        if scheme and scheme not in {"http", "https", "file"}:
            raise GuardrailViolation(
                "invalid_input", f"Unsupported input scheme: {scheme!r}"
            )

        suffix = Path(urlsplit(input_url).path).suffix.lower()
        if suffix and suffix not in self._settings.input_suffixes:
            allowed = ", ".join(self._settings.input_suffixes)
            raise GuardrailViolation(
                "unsupported_media_format",
                f"Unsupported media format {suffix!r}; expected one of: {allowed}",
            )

        if not target_languages:
            raise GuardrailViolation(
                "no_target_languages", "At least one target language is required"
            )

        if len(target_languages) > self._settings.max_target_languages:
            raise GuardrailViolation(
                "too_many_languages",
                f"At most {self._settings.max_target_languages} target languages per job",
            )

        if len(set(target_languages)) != len(target_languages):
            raise GuardrailViolation("duplicate_languages", "Target languages must be unique")

        invalid = [lang for lang in target_languages if not _LANGUAGE_PATTERN.fullmatch(lang)]
        if invalid:
            raise GuardrailViolation(
                "invalid_language",
                f"Invalid language codes: {', '.join(invalid)} (expected e.g. 'es', 'de', 'pt-BR')",
            )

    def check_media(self, probe: MediaProbe) -> None:
        if not probe.has_audio:
            raise GuardrailViolation("missing_audio", "Input media has no audio track")

        if probe.duration_seconds <= 0:
            raise GuardrailViolation("empty_media", "Input media has no duration")

        limit_seconds = self._settings.max_video_minutes * 60
        if probe.duration_seconds > limit_seconds:
            raise GuardrailViolation(
                "media_too_long",
                f"Input is {probe.duration_seconds / 60:.1f} minutes; "
                f"limit is {self._settings.max_video_minutes:.1f} minutes",
            )

    def check_transcript(self, transcript: Transcript) -> None:
        if not transcript.words:
            raise GuardrailViolation("empty_transcript", "Transcription produced no words")

    def check_clip_count(self, count: int) -> None:
        if count < self._settings.min_clips_per_job:
            raise GuardrailViolation(
                "too_few_clips",
                f"Planner returned {count} clips; expected at least "
                f"{self._settings.min_clips_per_job}",
            )

        if count > self._settings.max_clips_per_job:
            raise GuardrailViolation(
                "too_many_clips",
                f"Planner returned {count} clips; limit is {self._settings.max_clips_per_job}",
            )

    def check_budget(
        self,
        job: Job,
        *,
        additional_characters: int = 0,
        additional_minutes: float = 0.0,
    ) -> None:
        """Fail before the next paid call when the job would exceed its budget."""
        total_characters = job.usage.characters + additional_characters
        if total_characters > self._settings.max_characters_per_job:
            raise GuardrailViolation(
                "character_budget_exceeded",
                f"Job would process {total_characters} characters; limit is "
                f"{self._settings.max_characters_per_job}",
            )

        total_minutes = job.usage.input_minutes + additional_minutes
        if total_minutes > self._settings.max_video_minutes:
            raise GuardrailViolation(
                "minute_budget_exceeded",
                f"Job would process {total_minutes:.1f} minutes; limit is "
                f"{self._settings.max_video_minutes:.1f}",
            )
