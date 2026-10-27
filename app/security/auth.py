"""Cookie-based JWT authentication for the Creator-facing API.

The middleware supports two authentication modes:

1. **Workspace API key** (legacy): ``Authorization: Bearer <key>``. Used by the
   existing API tests and tooling.
2. **JWT cookie** (Creator flow): ``Cookie: access_token=<jwt>``. The JWT is
   signed with HS256, stored in an httpOnly cookie, and rotated on refresh.

Both modes are accepted for the same endpoints. The review and webhook
prefixes remain open.
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.security.jwt import decode_token, encode_token

_ACCESS_COOKIE = "access_token"
_REFRESH_COOKIE = "refresh_token"
_COOKIE_SAMESITE = "Lax"
_COOKIE_SECURE = False  # set True in production behind HTTPS


def _error(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message, "details": details or {}}},
    )


def _set_cookie(response: Response, name: str, value: str, max_age: int | None) -> None:
    response.set_cookie(
        key=name,
        value=value,
        httponly=True,
        samesite=_COOKIE_SAMESITE,
        secure=_COOKIE_SECURE,
        max_age=max_age,
        path="/",
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, path="/", httponly=True, samesite=_COOKIE_SAMESITE)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticates requests via JWT cookie or Bearer API key."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in {"/healthz", "/readyz"}:
            return await call_next(request)
        if request.url.path.startswith("/api/review"):
            return await call_next(request)
        if request.url.path.startswith("/api/webhooks"):
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        container = request.app.state.container
        settings = container.settings

        # Auth endpoints are reachable without pre-existing credentials.
        if request.url.path in {"/api/auth/login", "/api/auth/refresh", "/api/auth/logout"}:
            return await call_next(request)

        # 1. JWT cookie (Creator flow)
        access_token = request.cookies.get(_ACCESS_COOKIE)
        if access_token:
            try:
                payload = decode_token(access_token, settings.jwt_secret)
                request.state.auth_user = payload.get("sub", "creator")
                return await call_next(request)
            except ValueError:
                return _error(401, "unauthorized", "The access token is invalid or expired")

        # 2. Legacy Bearer API key
        provided = request.headers.get("authorization", "")
        token = provided[7:] if provided.lower().startswith("bearer ") else ""
        expected = settings.workspace_api_key
        if expected and secrets.compare_digest(token, expected):
            request.state.auth_user = "workspace"
            return await call_next(request)

        return _error(401, "unauthorized", "Authentication is required")


def issue_tokens(settings: Any) -> tuple[str, str]:
    """Issue a short-lived access token and a long-lived refresh token."""
    access = encode_token(
        {"sub": "creator", "type": "access"},
        settings.jwt_secret,
        expires_in=settings.jwt_access_token_ttl_seconds,
    )
    refresh = encode_token(
        {"sub": "creator", "type": "refresh"},
        settings.jwt_secret,
        expires_in=settings.jwt_refresh_token_ttl_seconds,
    )
    return access, refresh


def cookie_pair_response(settings: Any, message: str, *, status_code: int = 200) -> JSONResponse:
    """Build a JSON response that also sets the JWT cookies."""
    access, refresh = issue_tokens(settings)
    response = JSONResponse(
        status_code=status_code,
        content={"detail": {"code": "ok", "message": message}},
    )
    _set_cookie(response, _ACCESS_COOKIE, access, settings.jwt_access_token_ttl_seconds)
    _set_cookie(response, _REFRESH_COOKIE, refresh, settings.jwt_refresh_token_ttl_seconds)
    return response


def cookie_clear_response() -> JSONResponse:
    """Build a JSON response that deletes both JWT cookies."""
    response = JSONResponse(
        status_code=200,
        content={"detail": {"code": "ok", "message": "Logged out"}},
    )
    _clear_cookie(response, _ACCESS_COOKIE)
    _clear_cookie(response, _REFRESH_COOKIE)
    return response
