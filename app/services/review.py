"""Review tokens, the Review Bundle manifest and stable asset resolution."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.domain.enums import LocalizedClipStatus
from app.domain.errors import ApiError
from app.domain.models import Job, ReviewToken
from app.ports import Clock, ReviewTokenRepository

_TOKEN_BYTES = 32


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ReviewService:
    def __init__(
        self,
        *,
        tokens: ReviewTokenRepository,
        clock: Clock,
        secret: str,
        api_base_url: str,
    ) -> None:
        self._tokens = tokens
        self._clock = clock
        self._secret = secret
        self._api_base_url = api_base_url.rstrip("/")

    # -- token lifecycle ---------------------------------------------------------
    def _raw_token(self, token_id: str) -> str:
        signature = hmac.new(
            self._secret.encode(), token_id.encode(), hashlib.sha256
        ).hexdigest()
        return f"{token_id}.{signature}"

    def _new_token(self, job: Job) -> tuple[ReviewToken, str]:
        token_id = secrets.token_urlsafe(_TOKEN_BYTES)
        raw = self._raw_token(token_id)
        token = ReviewToken(
            token_id=token_id,
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            token_hash=_hash(raw),
            created_at=self._clock.now(),
        )
        return token, raw

    async def ensure_token(self, job: Job) -> str:
        """Return the stable raw token, creating one only when an asset exists."""
        if job.review_token_id:
            token = await self._tokens.get_by_hash(
                _hash(self._raw_token(job.review_token_id))
            )
            if token is not None and token.revoked_at is None:
                return self._raw_token(job.review_token_id)
        if not self.has_reviewable_assets(job):
            raise ApiError(409, "no_reviewable_assets", "The Job has no reviewable asset yet")
        token, raw = self._new_token(job)
        await self._tokens.add(token)
        job.review_token_id = token.token_id
        job.review_token_hash = token.token_hash
        return raw

    async def rotate(self, job: Job) -> str:
        existing = await self._tokens.get_for_job(job.job_id)
        if existing is not None:
            existing.revoked_at = self._clock.now()
            existing.rotated_at = self._clock.now()
            await self._tokens.save(existing)
        if not self.has_reviewable_assets(job):
            raise ApiError(409, "no_reviewable_assets", "The Job has no reviewable asset yet")
        token, raw = self._new_token(job)
        await self._tokens.add(token)
        job.review_token_id = token.token_id
        job.review_token_hash = token.token_hash
        return raw

    async def revoke(self, job: Job) -> None:
        token = await self._tokens.get_for_job(job.job_id)
        if token is not None:
            token.revoked_at = self._clock.now()
            await self._tokens.save(token)
        job.review_token_id = None
        job.review_token_hash = None

    async def resolve(self, raw: str) -> ReviewToken | None:
        token_id, _, signature = raw.partition(".")
        if not token_id or not signature:
            return None
        expected = hmac.new(
            self._secret.encode(), token_id.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        token = await self._tokens.get_by_hash(_hash(raw))
        if token is None or token.revoked_at is not None:
            return None
        return token

    def review_url(self, job: Job, raw_token: str | None = None) -> str | None:
        if raw_token is None and job.review_token_id:
            raw_token = self._raw_token(job.review_token_id)
        if not raw_token:
            return None
        return f"{self._api_base_url}/api/review/{raw_token}"

    # -- manifest ----------------------------------------------------------------
    def has_reviewable_assets(self, job: Job) -> bool:
        if any(clip.video_asset_key for clip in job.segments):
            return True
        return bool(job.content_assets)

    def _asset_base(self, job: Job, token: str | None) -> str:
        if token is None:
            return f"{self._api_base_url}/api/jobs/{job.job_id}/assets"
        return f"{self._api_base_url}/api/review/{token}/assets"

    def manifest(
        self,
        job: Job,
        *,
        token: str | None = None,
        raw_token: str | None = None,
    ) -> dict:
        base = self._asset_base(job, raw_token or token)
        segments: list[dict] = []
        for clip in job.segments:
            localized_assets = {
                language: f"{base}/clip_{clip.segment_id}_{language}"
                for language, _ in clip.localized_assets.items()
            }
            localized_copy = {
                language: copy.model_dump(mode="json")
                for language, copy in clip.localized_copy.items()
            }
            segments.append(
                {
                    "segment_id": clip.segment_id,
                    "hook_title": clip.hook_title,
                    "caption": clip.caption,
                    "video_asset_url": (
                        f"{base}/base_{clip.segment_id}" if clip.video_asset_key else None
                    ),
                    "localized_assets": localized_assets,
                    "localized_copy": localized_copy,
                }
            )

        source_language = None
        if job.source_language is not None:
            source_language = {
                "code": job.source_language.code,
                "origin": job.source_language.origin.value,
                "detected_code": job.source_language.detected_code,
            }

        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "created_at": job.created_at.isoformat().replace("+00:00", "Z"),
            "source_language": source_language,
            "target_languages": list(job.target_languages),
            "lip_sync": job.lip_sync,
            "segments": segments,
            "content": {
                "linkedin_post": job.content.linkedin_post if job.content else "",
                "newsletter": job.content.newsletter if job.content else "",
            },
            "copy_origin": job.copy_origin.model_dump(mode="json"),
        }

    # -- assets ------------------------------------------------------------------
    def asset_key(self, job: Job, asset_id: str) -> str | None:
        if asset_id.startswith("base_"):
            try:
                segment_id = int(asset_id.removeprefix("base_"))
            except ValueError:
                return None
            for clip in job.segments:
                if clip.segment_id == segment_id:
                    return clip.video_asset_key
            return None

        if asset_id.startswith("clip_"):
            _, _, remainder = asset_id.partition("_")
            segment_text, _, language = remainder.partition("_")
            if not language:
                return None
            try:
                segment_id = int(segment_text)
            except ValueError:
                return None
            for localized in job.localized_clips:
                if (
                    localized.segment_id == segment_id
                    and localized.language == language
                    and localized.status is LocalizedClipStatus.COMPLETED
                ):
                    return localized.video_asset_key
            return None

        return {
            "copy_linkedin": job.content_assets.get("linkedin"),
            "copy_newsletter": job.content_assets.get("newsletter"),
        }.get(asset_id)

    def manifest_is_frozen(self, job: Job) -> bool:
        return job.bundle_frozen
