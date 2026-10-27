"""Notification adapters: signed HMAC webhooks, log-only delivery, and a test recorder."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def sign_payload(secret: str, timestamp: str, raw_body: bytes) -> str:
    """HMAC-SHA256 over ``timestamp + "." + raw_body``."""
    message = timestamp.encode() + b"." + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature: str,
) -> bool:
    expected = sign_payload(secret, timestamp, raw_body)
    return hmac.compare_digest(expected, signature)


class LogNotifier:
    """Local notifier; records the signed payload shape without network access."""

    def __init__(self) -> None:
        self.deliveries: list[dict[str, Any]] = []

    async def deliver(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
        occurred_at: datetime,
    ) -> None:
        self.deliveries.append(
            {
                "event_id": event_id,
                "type": event_type,
                "payload": payload,
                "occurred_at": occurred_at.isoformat(),
            }
        )
        logger.info("Notification %s (%s) for job %s", event_id, event_type, payload.get("job_id"))


class RecordingNotifier(LogNotifier):
    """Test double exposing the signed headers and raw body."""

    def __init__(self, *, secret: str = "test-secret", fail: bool = False) -> None:
        super().__init__()
        self.secret = secret
        self.fail = fail
        self.requests: list[dict[str, Any]] = []

    async def deliver(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
        occurred_at: datetime,
    ) -> None:
        if self.fail:
            raise RuntimeError("simulated webhook failure")
        body = {
            "event_id": event_id,
            "type": event_type,
            "job_id": payload.get("job_id"),
            "occurred_at": occurred_at.isoformat(),
            "data": payload,
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        timestamp = str(int(occurred_at.timestamp()))
        self.requests.append(
            {
                "headers": {
                    "X-Event-Id": event_id,
                    "X-Timestamp": timestamp,
                    "X-Signature": sign_payload(self.secret, timestamp, raw),
                },
                "body": body,
                "raw": raw,
            }
        )
        await super().deliver(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )


class HmacWebhookNotifier:
    """POST a signed, at-most-once notification to the configured webhook."""

    def __init__(
        self,
        url: str,
        *,
        secret: str,
        timeout: float = 15.0,
    ) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout

    async def deliver(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
        occurred_at: datetime,
    ) -> None:
        body = {
            "event_id": event_id,
            "type": event_type,
            "job_id": payload.get("job_id"),
            "occurred_at": occurred_at.isoformat(),
            "data": payload,
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        timestamp = str(int(occurred_at.timestamp()))
        headers = {
            "Content-Type": "application/json",
            "X-Event-Id": event_id,
            "X-Timestamp": timestamp,
            "X-Signature": sign_payload(self._secret, timestamp, raw),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, content=raw, headers=headers)
            response.raise_for_status()
        logger.info("Delivered notification %s to %s", event_id, self._url)
