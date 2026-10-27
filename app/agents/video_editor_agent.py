"""Video Processing & Formatting Agent (``video_editor_agent``).

Cuts the selected moments, re-frames them to 9:16 and burns in kinetic captions.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.agents.base import workspace_for
from app.captions import build_srt
from app.domain.artifacts import EditedClip
from app.domain.models import ClipCandidate, Job, Segment, Transcript
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
        edited: list[EditedClip] = []

        for clip in clips:
            captions = build_srt(
                transcript.words,
                clip_start=clip.start_seconds,
                clip_end=clip.end_seconds,
            )
            destination = workspace / f"clip_{clip.segment_id}_en.mp4"
            await self._media.render_vertical_clip(
                source_path,
                destination,
                start_seconds=clip.start_seconds,
                end_seconds=clip.end_seconds,
                captions=captions,
            )

            key = f"jobs/{job.job_id}/clips/clip_{clip.segment_id}_en.mp4"
            url = await self._store.put(destination, key)
            segment = Segment(
                segment_id=clip.segment_id,
                start_time=format_timestamp(clip.start_seconds),
                end_time=format_timestamp(clip.end_seconds),
                hook_title=clip.hook_title,
                caption=clip.caption,
                video_asset_url=url,
            )
            edited.append(EditedClip(segment=segment, candidate=clip, path=destination))

        return edited
