"""Localization & Dubbing Agent (``localization_agent``).

Translates each clip, synthesizes the creator's cloned voice in the target language and
optionally runs lip-sync before muxing the localized audio onto the vertical video.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.agents.base import workspace_for
from app.domain.artifacts import EditedClip, LocalizationResult
from app.domain.models import Job, Transcript
from app.ports import LipSyncer, MediaProcessor, ObjectStore, Translator, VoiceSynthesizer


class LocalizationAgent:
    def __init__(
        self,
        *,
        translator: Translator,
        voice: VoiceSynthesizer,
        media: MediaProcessor,
        store: ObjectStore,
        workspace_root: Path,
        lip_syncer: LipSyncer | None = None,
    ) -> None:
        self._translator = translator
        self._voice = voice
        self._media = media
        self._store = store
        self._workspace_root = workspace_root
        self._lip_syncer = lip_syncer

    async def run(
        self,
        job: Job,
        *,
        edited: Sequence[EditedClip],
        transcript: Transcript,
    ) -> LocalizationResult:
        workspace = workspace_for(self._workspace_root, job.job_id)
        assets: dict[int, dict[str, str]] = {}
        characters = 0

        for clip in edited:
            source_text = transcript.text_between(
                clip.candidate.start_seconds, clip.candidate.end_seconds
            )
            if not source_text:
                source_text = clip.candidate.caption

            for language in job.target_languages:
                translated = await self._translator.translate(source_text, language)
                characters += len(translated)

                voice_path = workspace / f"clip_{clip.segment.segment_id}_{language}.wav"
                await self._voice.synthesize(translated, language, voice_path)
                dubbed_path = workspace / f"clip_{clip.segment.segment_id}_{language}.mp4"

                if self._lip_syncer is not None:
                    output = await self._lip_syncer.sync(
                        clip.path, voice_path, dubbed_path, language
                    )
                else:
                    output = await self._media.replace_audio(
                        clip.path, voice_path, dubbed_path
                    )

                key = (
                    f"jobs/{job.job_id}/localized/"
                    f"clip_{clip.segment.segment_id}_{language}.mp4"
                )
                url = await self._store.put(output, key)
                assets.setdefault(clip.segment.segment_id, {})[language] = url

        return LocalizationResult(assets=assets, characters=characters)
