"""Authentication endpoints for the Creator-facing API.

Supports two authentication methods:
1. JWT cookie (new Creator flow) — ``Cookie: access_token=<jwt>``
2. Legacy API key (backward compatibility) — ``Authorization: Bearer <key>``

Both methods are accepted for the same endpoints. The review and webhook
prefixes remain open.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.security.auth import cookie_clear_response, cookie_pair_response

router = APIRouter(tags=["auth"])


@router.post("/auth/login", status_code=200)
async def login(request: Request) -> JSONResponse:
    """Issue a short-lived access token and a long-lived refresh token.

    Both are stored in httpOnly cookies for subsequent requests.
    """
    return cookie_pair_response(
        request.app.state.container.settings, "Login successful"
    )


@router.post("/auth/refresh", status_code=200)
async def refresh_token(request: Request) -> JSONResponse:
    """Rotate the refresh token and issue a new access token.

    The refresh token is validated from the ``refresh_token`` cookie.
    """
    from app.security.jwt import decode_token

    settings = request.app.state.container.settings
    refresh = request.cookies.get("refresh_token")
    if not refresh:
        return JSONResponse(
            status_code=401,
            content={"detail": {"code": "unauthorized", "message": "No refresh token"}},
        )
    try:
        decode_token(refresh, settings.jwt_secret)
    except ValueError:
        return JSONResponse(
            status_code=401,
            content={"detail": {"code": "unauthorized", "message": "Invalid refresh token"}},
        )
    return cookie_pair_response(settings, "Token refreshed")


@router.post("/auth/logout", status_code=200)
async def logout() -> JSONResponse:
    """Clear the access and refresh tokens from the cookie."""
    return cookie_clear_response()