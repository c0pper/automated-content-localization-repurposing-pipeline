"""Video Processing & Formatting Agent (``video_editor_agent``).

Cuts the selected moments, re-frames them to 9:16 and burns in kinetic captions.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.agents.base import workspace_for
from app.captions import build_srt
from app.domain.artifacts import EditedClip
from app.domain.models import Clip, ClipCandidate, Job, Transcript
from app.domain.timestamps import format_timestamp
from app.ports import MediaProcessor, ObjectStore


class VideoEditorAgent:
    def __init__(
        self,
        *,
        media: MediaProcessor,
        store: ObjectStore,
        workspace_root: Path,
    ) -> None:
        self._media = media
        self._store = store
        self._workspace_root = workspace_root

    async def run(
        self,
        job: Job,
        *,
        source_path: Path,
        transcript: Transcript,
        clips: Sequence[ClipCandidate],
    ) -> list[EditedClip]:
        workspace = workspace_for(self._workspace_root, job.job_id)
        source_language = job.source_language.code if job.source_language else "en"
        edited: list[EditedClip] = []

        for candidate in clips:
            captions = build_srt(
                transcript.words,
                clip_start=candidate.start_seconds,
                clip_end=candidate.end_seconds,
            )
            destination = workspace / f"clip_{candidate.segment_id}_{source_language}.mp4"
            await self._media.render_vertical_clip(
                source_path,
                destination,
                start_seconds=candidate.start_seconds,
                end_seconds=candidate.end_seconds,
                captions=captions,
            )

            key = (
                f"jobs/{job.job_id}/clips/"
                f"clip_{candidate.segment_id}_{source_language}.mp4"
            )
            url = await self._store.put(destination, key)
            clip = Clip(
                segment_id=candidate.segment_id,
                start_time=format_timestamp(candidate.start_seconds),
                end_time=format_timestamp(candidate.end_seconds),
                hook_title=candidate.hook_title,
                caption=candidate.caption,
                video_asset_url=url,
                source_text=transcript.text_between(
                    candidate.start_seconds, candidate.end_seconds
                ),
            )
            edited.append(EditedClip(clip=clip, candidate=candidate, path=destination))

        return edited
