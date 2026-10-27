"""Transcription & Intelligence Agent (``intelligence_agent``).

Transcribes audio, resolves the Source Language, plans 3-5 Clip Candidates, scores them
with Jev and the Quality Floor, and generates the multi-channel copy.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.domain.artifacts import IntelligenceResult
from app.domain.enums import CostUnitType, JobStage, SourceLanguageOrigin
from app.domain.errors import GuardrailViolation, QualityFloorNotMet
from app.domain.models import Job, SourceLanguage, Transcript
from app.domain.scoring import apply_quality_floor, score_candidate
from app.guardrails import Guardrails
from app.ports import ClipPlanner, ClipScorer, Copywriter, Transcriber
from app.services.cost import CostService


class IntelligenceAgent:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        planner: ClipPlanner,
        scorer: ClipScorer,
        copywriter: Copywriter,
        cost: CostService,
        guardrails: Guardrails,
        settings: Settings,
    ) -> None:
        self._transcriber = transcriber
        self._planner = planner
        self._scorer = scorer
        self._copywriter = copywriter
        self._cost = cost
        self._guardrails = guardrails
        self._settings = settings

    async def run(
        self,
        job: Job,
        *,
        audio_path: Path,
        duration_seconds: float,
    ) -> IntelligenceResult:
        model = job.model_overrides.get("planning", self._settings.default_planning_model)
        await self._cost.charge(
            job,
            stage=JobStage.INTELLIGENCE,
            provider="openai",
            model="whisper-1",
            units=max(duration_seconds, 0.0) / 60.0,
            unit_type=CostUnitType.MINUTES,
        )
        transcript = await self._transcriber.transcribe(
            audio_path, language_hint=job.declared_source_language
        )
        self._guardrails.check_transcript(transcript)
        self._guardrails.check_budget(
            job, additional_characters=len(transcript.text)
        )
        job.usage.characters += len(transcript.text)
        source_language = self.resolve_source_language(job, transcript)
        self._reject_conflict(source_language, job.target_languages)

        await self._cost.charge(
            job,
            stage=JobStage.INTELLIGENCE,
            provider="openrouter",
            model=model,
            units=float(len(transcript.text)),
            unit_type=CostUnitType.CHARACTERS,
        )
        candidates = await self._planner.select_clips(
            transcript,
            min_clips=self._settings.min_clips_per_job,
            max_clips=self._settings.max_clips_per_job,
            model=model,
        )
        self._guardrails.check_clip_count(len(candidates))

        scored = []
        for candidate in candidates:
            await self._cost.charge(
                job,
                stage=JobStage.SCORING,
                provider="jev",
                model=self._settings.jev_model,
                units=1,
                unit_type=CostUnitType.REQUESTS,
            )
            distributions = await self._scorer.score(candidate)
            scored.append(score_candidate(candidate, distributions))

        passing = apply_quality_floor(
            scored,
            floor=self._settings.quality_floor,
            max_clips=self._settings.max_clips_per_job,
        )
        if len(passing) < self._settings.min_clips_per_job:
            raise QualityFloorNotMet(len(passing), self._settings.quality_floor)

        copy_model = job.model_overrides.get("copy", self._settings.default_copy_model)
        copy_characters = len(transcript.text) + sum(
            len(candidate.hook_title) + len(candidate.caption) for candidate in passing
        )
        self._guardrails.check_budget(job, additional_characters=copy_characters)
        await self._cost.charge(
            job,
            stage=JobStage.INTELLIGENCE,
            provider="openrouter",
            model=copy_model,
            units=float(copy_characters),
            unit_type=CostUnitType.CHARACTERS,
        )
        content = await self._copywriter.write(
            transcript, passing, model=copy_model
        )
        job.usage.characters += copy_characters
        return IntelligenceResult(
            transcript=transcript,
            clips=passing,
            content=content,
            source_language=source_language,
        )

    def resolve_source_language(self, job: Job, transcript: Transcript) -> SourceLanguage:
        detected = transcript.language or None
        if job.declared_source_language:
            return SourceLanguage(
                code=job.declared_source_language,
                origin=SourceLanguageOrigin.DECLARED,
                detected_code=(
                    detected
                    if detected and detected != job.declared_source_language
                    else None
                ),
            )
        if detected and transcript.language_confidence >= 0.5:
            return SourceLanguage(
                code=detected,
                origin=SourceLanguageOrigin.DETECTED,
                detected_code=detected,
            )
        return SourceLanguage(
            code="en",
            origin=SourceLanguageOrigin.FALLBACK,
            detected_code=detected,
        )

    @staticmethod
    def _reject_conflict(source: SourceLanguage, targets: list[str]) -> None:
        primary = source.code.split("-", 1)[0].lower()
        conflicting = [
            language
            for language in targets
            if language.split("-", 1)[0].lower() == primary
        ]
        if conflicting:
            raise GuardrailViolation(
                "source_target_conflict",
                "The detected Source Language matches a Target Language",
                details={
                    "source_language": source.code,
                    "languages": conflicting,
                },
                retryable=False,
            )
