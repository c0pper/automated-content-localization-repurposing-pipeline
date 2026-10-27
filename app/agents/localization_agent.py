"""Localization & Dubbing Agent (``localization_agent``).

Localizes only the confirmed selection. For each Clip-by-Language cell it translates the
retained spoken source text, synthesizes the Creator's voice, optionally lip-syncs the
caption-free Base Clip Master, then burns translated captions in after lip-sync.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from app.agents.base import workspace_for
from app.captions import build_srt
from app.config import Settings
from app.domain.artifacts import LocalizationResult
from app.domain.enums import CostUnitType, JobStage, LocalizedClipStatus
from app.domain.errors import CancellationRequested, GuardrailViolation
from app.domain.models import Clip, Job, LocalizedClip, LocalizedClipCopy, VoiceProfile
from app.domain.timestamps import parse_timestamp
from app.guardrails import Guardrails
from app.ports import LipSyncer, MediaProcessor, ObjectStore, Translator, VoiceSynthesizer
from app.services.cost import CostService


class LocalizationAgent:
    def __init__(
        self,
        *,
        translator: Translator,
        voice: VoiceSynthesizer,
        media: MediaProcessor,
        store: ObjectStore,
        cost: CostService,
        guardrails: Guardrails,
        settings: Settings,
        workspace_root: Path,
        lip_syncer: LipSyncer | None = None,
    ) -> None:
        self._translator = translator
        self._voice = voice
        self._media = media
        self._store = store
        self._cost = cost
        self._guardrails = guardrails
        self._settings = settings
        self._workspace_root = workspace_root
        self._lip_syncer = lip_syncer

    async def run(
        self,
        job: Job,
        *,
        clips: Sequence[Clip],
        voice_profile: VoiceProfile,
        on_checkpoint: Callable[[Job], Awaitable[None]] | None = None,
    ) -> LocalizationResult:
        selection = job.selection
        if selection is None:
            raise GuardrailViolation(
                "invalid_state", "Localization requires a confirmed Selection"
            )

        assets: dict[int, dict[str, str]] = {}
        characters = 0
        completed: list[LocalizedClip] = []
        selected_ids = set(selection.segment_ids)
        selected_languages = list(selection.languages)

        for clip in clips:
            if clip.segment_id not in selected_ids:
                continue
            for language in selected_languages:
                existing = job.localized(clip.segment_id, language)
                if existing is not None and existing.status is LocalizedClipStatus.COMPLETED:
                    if existing.video_asset_key:
                        assets.setdefault(clip.segment_id, {})[language] = (
                            clip.localized_assets.get(language, "")
                        )
                    completed.append(existing)
                    continue

                localized = await self.run_cell(
                    job, clip=clip, language=language, voice_profile=voice_profile
                )
                characters += len(clip.source_text or "")
                completed.append(localized)
                assets.setdefault(clip.segment_id, {})[language] = (
                    clip.localized_assets.get(language, "")
                )
                if on_checkpoint is not None:
                    await on_checkpoint(job)

        return LocalizationResult(
            assets=assets,
            characters=characters,
            localized_clips=completed,
        )

    async def run_cell(
        self,
        job: Job,
        *,
        clip: Clip,
        language: str,
        voice_profile: VoiceProfile,
    ) -> LocalizedClip:
        self._check_cancel(job)
        source_text = clip.source_text
        if not source_text:
            raise GuardrailViolation(
                "missing_source_text",
                "The Clip has no retained spoken source text",
                retryable=False,
            )
        if not clip.base_clip_master_key:
            raise GuardrailViolation(
                "missing_base_clip_master",
                "The Clip has no caption-free Base Clip Master",
                retryable=False,
            )

        workspace = workspace_for(self._workspace_root, job.job_id)
        master_path = workspace / f"master_clip_{clip.segment_id}_{language}.mp4"
        if not master_path.is_file():
            await self._store.get(clip.base_clip_master_key, master_path)

        cell_characters = (
            len(source_text) + len(clip.hook_title) + len(clip.caption)
        )
        self._guardrails.check_budget(job, additional_characters=cell_characters)

        translation_model = job.model_overrides.get(
            "translation", self._settings.default_translation_model
        )
        await self._cost.charge(
            job,
            stage=JobStage.LOCALIZATION,
            provider="openrouter",
            model=translation_model,
            units=float(cell_characters),
            unit_type=CostUnitType.CHARACTERS,
        )
        translated = await self._translator.translate(
            source_text, language, model=translation_model
        )
        localized_hook = await self._translator.translate(
            clip.hook_title, language, model=translation_model
        )
        localized_caption = await self._translator.translate(
            clip.caption, language, model=translation_model
        )

        self._check_cancel(job)
        await self._cost.charge(
            job,
            stage=JobStage.LOCALIZATION,
            provider="elevenlabs",
            model="eleven_multilingual_v2",
            units=float(len(translated)),
            unit_type=CostUnitType.CHARACTERS,
        )
        audio_path = workspace / f"clip_{clip.segment_id}_{language}.wav"
        synthesis = await self._voice.synthesize(
            translated,
            language,
            audio_path,
            voice_id=voice_profile.voice_id,
        )
        if synthesis.alignment is None:
            raise GuardrailViolation(
                "caption_alignment_unavailable",
                "The speech provider returned no caption alignment",
                retryable=True,
            )

        duration = _duration_seconds(clip)
        if job.lip_sync:
            if self._lip_syncer is None:
                raise GuardrailViolation(
                    "lip_sync_unavailable",
                    "Lip-sync was requested but no lip-sync provider is configured",
                    retryable=True,
                )
            self._check_cancel(job)
            await self._cost.charge(
                job,
                stage=JobStage.LOCALIZATION,
                provider="synclabs",
                model="lipsync-2",
                units=duration,
                unit_type=CostUnitType.SECONDS,
            )
            lipsynced_path = workspace / f"clip_{clip.segment_id}_{language}_lipsync.mp4"
            output = await self._lip_syncer.sync(
                master_path, audio_path, lipsynced_path, language
            )
        else:
            muxed_path = workspace / f"clip_{clip.segment_id}_{language}_muxed.mp4"
            output = await self._media.replace_audio(
                master_path, audio_path, muxed_path
            )

        captions = build_srt(
            synthesis.alignment, clip_start=0.0, clip_end=max(duration, 1.0)
        )
        final_path = workspace / f"clip_{clip.segment_id}_{language}.mp4"
        final = await self._media.burn_captions(output, captions, final_path)

        video_key = f"jobs/{job.job_id}/localized/clip_{clip.segment_id}_{language}.mp4"
        audio_key = f"jobs/{job.job_id}/localized/clip_{clip.segment_id}_{language}.wav"
        video_url = await self._store.put(final, video_key)
        await self._store.put(audio_path, audio_key)

        localized = LocalizedClip(
            clip_id=f"clip_{job.job_id}_{clip.segment_id}",
            segment_id=clip.segment_id,
            language=language,
            localized_hook_title=localized_hook,
            localized_caption=localized_caption,
            audio_asset_key=audio_key,
            video_asset_key=video_key,
            lip_sync=job.lip_sync,
            status=LocalizedClipStatus.COMPLETED,
        )
        _upsert(job.localized_clips, localized)
        clip.localized_assets[language] = video_url
        clip.localized_copy[language] = LocalizedClipCopy(
            hook_title=localized_hook, caption=localized_caption
        )
        job.usage.characters += cell_characters
        return localized

    @staticmethod
    def _check_cancel(job: Job) -> None:
        if job.cancel_requested:
            raise CancellationRequested(job.job_id)


def _upsert(items: list[LocalizedClip], item: LocalizedClip) -> None:
    for index, existing in enumerate(items):
        if existing.segment_id == item.segment_id and existing.language == item.language:
            items[index] = item
            return
    items.append(item)


def _duration_seconds(clip: Clip) -> float:
    try:
        return max(0.0, parse_timestamp(clip.end_time) - parse_timestamp(clip.start_time))
    except ValueError:
        return 0.0
