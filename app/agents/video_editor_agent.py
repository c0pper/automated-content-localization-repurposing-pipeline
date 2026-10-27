"""Video Processing & Formatting Agent (``video_editor_agent``).

Renders a caption-free 9:16 Base Clip Master per Clip, then burns Source Language captions
into the Base Clip review asset. The master is internal and retained for the Workspace
lifetime.
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
            master_path = workspace / f"master_clip_{candidate.segment_id}_{source_language}.mp4"
            await self._media.render_vertical_clip(
                source_path,
                master_path,
                start_seconds=candidate.start_seconds,
                end_seconds=candidate.end_seconds,
                captions=None,
            )
            master_key = (
                f"jobs/{job.job_id}/masters/"
                f"clip_{candidate.segment_id}_{source_language}.mp4"
            )
            await self._store.put(master_path, master_key)

            captions = build_srt(
                transcript.words,
                clip_start=candidate.start_seconds,
                clip_end=candidate.end_seconds,
            )
            base_path = workspace / f"clip_{candidate.segment_id}_{source_language}.mp4"
            await self._media.burn_captions(master_path, captions, base_path)
            base_key = (
                f"jobs/{job.job_id}/clips/"
                f"clip_{candidate.segment_id}_{source_language}.mp4"
            )
            url = await self._store.put(base_path, base_key)

            clip = Clip(
                segment_id=candidate.segment_id,
                start_time=format_timestamp(candidate.start_seconds),
                end_time=format_timestamp(candidate.end_seconds),
                hook_title=candidate.hook_title,
                caption=candidate.caption,
                rationale=candidate.rationale,
                selection_score=candidate.selection_score,
                score_breakdown=candidate.score_breakdown,
                video_asset_url=url,
                video_asset_key=base_key,
                source_text=candidate.source_text
                or transcript.text_between(
                    candidate.start_seconds, candidate.end_seconds
                ),
                base_clip_master_key=master_key,
            )
            edited.append(
                EditedClip(
                    clip=clip,
                    candidate=candidate,
                    path=base_path,
                    master_path=master_path,
                )
            )

        return edited
