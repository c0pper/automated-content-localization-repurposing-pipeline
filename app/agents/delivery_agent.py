"""Delivery & Orchestration Agent (``delivery_agent``).

Assembles the Review Bundle manifest, writes Markdown copy files and freezes the bundle.
Notifications are queued by the orchestrator after the bundle is frozen.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base import workspace_for
from app.domain.artifacts import DeliveryResult
from app.domain.models import Job
from app.ports import ObjectStore


class DeliveryAgent:
    def __init__(
        self,
        *,
        store: ObjectStore,
        workspace_root: Path,
    ) -> None:
        self._store = store
        self._workspace_root = workspace_root

    async def run(self, job: Job) -> DeliveryResult:
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

            clips_path = copy_dir / "clips.md"
            clips_path.write_text(self._clips_markdown(job), encoding="utf-8")
            files["clips"] = await self._store.put(
                clips_path, f"jobs/{job.job_id}/copy/clips.md"
            )

        job.content_assets = files
        job.bundle_frozen = True
        links = [clip.video_asset_url for clip in job.segments if clip.video_asset_url]
        links.extend(
            localized.video_asset_key
            for localized in job.localized_clips
            if localized.video_asset_key
        )
        links.extend(files.values())
        return DeliveryResult(links=[link for link in links if link], files=files)

    @staticmethod
    def _clips_markdown(job: Job) -> str:
        lines = ["# Clip copy", ""]
        for clip in job.segments:
            lines.append(f"## {clip.hook_title}")
            lines.append("")
            lines.append(clip.caption)
            lines.append("")
            for language, copy in sorted(clip.localized_copy.items()):
                lines.append(f"### {language}")
                lines.append("")
                lines.append(f"**{copy.hook_title}**")
                lines.append("")
                lines.append(copy.caption)
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
