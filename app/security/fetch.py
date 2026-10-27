"""Bounded, SSRF-safe remote fetch with per-hop validation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.domain.errors import ExternalServiceError, GuardrailViolation
from app.security.urls import validate_http_url

_MAX_REDIRECTS = 5
_CHUNK_SIZE = 1024 * 1024


class SafeRemoteFetcher:
    def __init__(
        self,
        *,
        allowed_suffixes: tuple[str, ...],
        max_bytes: int,
        timeout: float = 120.0,
    ) -> None:
        self._allowed_suffixes = allowed_suffixes
        self._max_bytes = max_bytes
        self._timeout = timeout

    async def fetch(self, url: str, destination: Path) -> Path:
        current = url
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=self._timeout
            ) as client:
                for _ in range(_MAX_REDIRECTS + 1):
                    await validate_http_url(
                        current, allowed_suffixes=self._allowed_suffixes
                    )
                    async with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise GuardrailViolation(
                                    "unsafe_source", "Redirect without a Location header"
                                )
                            current = urljoin(current, location)
                            continue
                        response.raise_for_status()
                        total = 0
                        with destination.open("wb") as handle:
                            async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                                total += len(chunk)
                                if total > self._max_bytes:
                                    raise GuardrailViolation(
                                        "source_too_large",
                                        f"Source exceeds the {self._max_bytes}-byte cap",
                                    )
                                handle.write(chunk)
                        return destination
                raise GuardrailViolation(
                    "unsafe_source", "The source URL redirected too many times"
                )
        except GuardrailViolation:
            await asyncio.to_thread(destination.unlink, True)
            raise
        except httpx.HTTPError as exc:
            await asyncio.to_thread(destination.unlink, True)
            raise ExternalServiceError(f"Could not download {url}: {exc}") from exc
