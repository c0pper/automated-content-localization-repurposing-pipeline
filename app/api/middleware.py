"""Idempotency middleware. Cookie-based JWT auth lives in app/security/auth.py."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.domain.models import IdempotencyRecord

_IDEMPOTENT_METHODS = {"POST", "DELETE"}
_OPEN_PREFIXES = ("/api/review", "/api/webhooks")


def _error(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message, "details": details or {}}},
    )


def _request_hash(method: str, path: str, query: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.encode())
    digest.update(b"\n")
    digest.update(path.encode())
    digest.update(b"\n")
    digest.update(query.encode())
    digest.update(b"\n")
    digest.update(body)
    return digest.hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in _IDEMPOTENT_METHODS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        # Auth endpoints are safe to call repeatedly; skip idempotency.
        if request.url.path.startswith("/api/auth/"):
            return await call_next(request)

        container = request.app.state.container
        workspace_id = container.settings.workspace_id
        key = request.headers.get("idempotency-key")
        if not key:
            return _error(
                422,
                "idempotency_key_required",
                "POST and DELETE require an Idempotency-Key header",
            )

        body = await request.body()
        request_hash = _request_hash(
            request.method, request.url.path, request.url.query, body
        )
        store = container.idempotency
        existing = await store.get(workspace_id, key)
        if existing is not None and existing.expires_at <= container.clock.now():
            await store.delete(workspace_id, key)
            existing = None
        if existing is not None:
            if existing.request_hash != request_hash:
                return _error(
                    409,
                    "idempotency_key_reuse",
                    "This Idempotency-Key was used with a different request",
                )
            if existing.response_status == 0:
                return _error(
                    409,
                    "idempotency_in_progress",
                    "A request with this Idempotency-Key is still in progress",
                )
            headers = dict(existing.response_headers)
            if existing.response_body:
                return JSONResponse(
                    status_code=existing.response_status,
                    content=existing.response_body,
                    headers=headers,
                )
            return Response(status_code=existing.response_status, headers=headers)

        placeholder = IdempotencyRecord(
            workspace_id=workspace_id,
            key=key,
            method=request.method,
            path=request.url.path,
            request_hash=request_hash,
            response_status=0,
            expires_at=container.clock.now()
            + timedelta(days=container.settings.idempotency_retention_days),
            created_at=container.clock.now(),
        )
        await store.put(placeholder)
        try:
            response = await call_next(request)
        except Exception:
            await store.delete(workspace_id, key)
            raise

        raw = b"".join([chunk async for chunk in response.body_iterator])
        headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() in {"content-type", "location"}
        }
        payload: dict = {}
        if raw and "application/json" in response.headers.get("content-type", ""):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}

        if response.status_code < 500:
            await store.put(
                IdempotencyRecord(
                    workspace_id=workspace_id,
                    key=key,
                    method=request.method,
                    path=request.url.path,
                    request_hash=request_hash,
                    response_status=response.status_code,
                    response_body=payload,
                    response_headers=headers,
                    expires_at=placeholder.expires_at,
                    created_at=placeholder.created_at,
                )
            )
        else:
            await store.delete(workspace_id, key)

        return Response(
            content=raw,
            status_code=response.status_code,
            headers=headers,
        )
