"""Delivery & Orchestration Agent (``delivery_agent``).

Bundles copy files, uploads them and notifies the creator with review links.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from pathlib import Path

from app.agents.base import workspace_for
from app.domain.artifacts import DeliveryResult, EditedClip, LocalizationResult
from app.domain.models import Job
from app.ports import Notifier, ObjectStore


class DeliveryAgent:
    def __init__(
        self,
        *,
        store: ObjectStore,
        notifier: Notifier,
        workspace_root: Path,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._workspace_root = workspace_root

    async def run(
        self,
        job: Job,
        *,
        edited: Sequence[EditedClip],
        localized: LocalizationResult,
    ) -> DeliveryResult:
        workspace = workspace_for(self._workspace_root, job.job_id)
        copy_dir = workspace / "copy"
        copy_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}
        content = job.content

        if content is not None:
            linkedin_path = copy_dir / "linkedin.md"
            linkedin_path.write_text(content.linkedin_post, encoding="utf-8")
            files["linkedin"] = await self._store.put(
                linkedin_path, f"jobs/{job.job_id}/copy/linkedin.md"
            )

            newsletter_path = copy_dir / "newsletter.md"
            newsletter_path.write_text(content.newsletter, encoding="utf-8")
            files["newsletter"] = await self._store.put(
                newsletter_path, f"jobs/{job.job_id}/copy/newsletter.md"
            )

        captions_path = copy_dir / "captions.csv"
        captions_path.write_text(self._caption_csv(edited), encoding="utf-8")
        files["captions"] = await self._store.put(
            captions_path, f"jobs/{job.job_id}/copy/captions.csv"
        )

        links = [
            clip.video_asset_url for clip in job.segments if clip.video_asset_url
        ]
        for localized_assets in localized.assets.values():
            links.extend(localized_assets.values())
        links.extend(files.values())

        await self._notifier.notify(job, links)
        return DeliveryResult(links=links, files=files)

    @staticmethod
    def _caption_csv(edited: Sequence[EditedClip]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["segment_id", "start_time", "end_time", "title", "caption"])
        for edited_clip in edited:
            clip = edited_clip.clip
            writer.writerow(
                [
                    clip.segment_id,
                    clip.start_time,
                    clip.end_time,
                    clip.hook_title,
                    clip.caption,
                ]
            )
        return buffer.getvalue()
