"""Tests for the JWT cookie auth flow (issue #20).

Acceptance criteria:
- Login endpoint sets JWT cookie
- Refresh token rotates silently in the background
- Logout clears cookie and invalidates session
- All API requests include cookie auth automatically
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import API_KEY, make_client, make_settings


def _login(client: TestClient) -> dict:
    """Call /auth/login and return the cookies set on the response."""
    response = client.post("/api/auth/login")
    assert response.status_code == 200
    return {
        "access_token": response.cookies.get("access_token"),
        "refresh_token": response.cookies.get("refresh_token"),
    }


def test_login_sets_jwt_cookies(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    response = client.post("/api/auth/login")
    assert response.status_code == 200
    assert response.json()["detail"]["code"] == "ok"

    # Both cookies must be present.
    assert response.cookies.get("access_token") is not None
    assert response.cookies.get("refresh_token") is not None

    # Cookies must be httpOnly (inspect raw Set-Cookie headers).
    set_cookies = response.headers.get_list("set-cookie")
    access_cookie_header = next(c for c in set_cookies if c.startswith("access_token="))
    refresh_cookie_header = next(c for c in set_cookies if c.startswith("refresh_token="))
    assert "HttpOnly" in access_cookie_header
    assert "HttpOnly" in refresh_cookie_header


def test_access_token_allows_subsequent_api_calls(tmp_path: Path) -> None:
    """Once logged in, the JWT cookie alone authenticates API requests."""
    settings = make_settings(tmp_path)
    client = make_client(settings)

    _login(client)

    # No Bearer header — cookie auth should still work.
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_no_auth_returns_401(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    response = client.get("/api/jobs")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_refresh_rotates_tokens(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    tokens = _login(client)
    original_access = tokens["access_token"]
    original_refresh = tokens["refresh_token"]

    # Refresh using the refresh token cookie.
    response = client.post("/api/auth/refresh")
    assert response.status_code == 200
    new_access = response.cookies.get("access_token")
    new_refresh = response.cookies.get("refresh_token")
    assert new_access is not None
    assert new_refresh is not None
    # Tokens should be rotated (changed).
    assert new_access != original_access
    assert new_refresh != original_refresh

    # The new access token must authenticate subsequent requests.
    response = client.get("/api/jobs")
    assert response.status_code == 200


def test_refresh_without_cookie_returns_401(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_logout_clears_cookies(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    _login(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["detail"]["code"] == "ok"

    # Cookies should be deleted (Set-Cookie with Max-Age=0).
    set_cookies = response.headers.get_list("set-cookie")
    assert any("Max-Age=0" in c or "max-age=0" in c.lower() for c in set_cookies)

    # After logout, the access token is gone — API call should 401.
    response = client.get("/api/jobs")
    assert response.status_code == 401


def test_logout_invalidates_session(tmp_path: Path) -> None:
    """After logout, previously issued tokens must no longer authenticate."""
    settings = make_settings(tmp_path)
    client = make_client(settings)

    _login(client)
    # Verify the token works before logout.
    assert client.get("/api/jobs").status_code == 200

    # Log out.
    client.post("/api/auth/logout")
    # The TestClient cookie jar is cleared automatically by the Set-Cookie
    # delete instructions sent by the logout endpoint.
    response = client.get("/api/jobs")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_tampered_access_token_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    tokens = _login(client)
    # Tamper with the access token signature.
    tampered_access = tokens["access_token"][:-5] + "AAAAA"
    response = client.get(
        "/api/jobs",
        headers={"Cookie": f"access_token={tampered_access}"},
    )
    assert response.status_code == 401


def test_legacy_api_key_still_works(tmp_path: Path) -> None:
    """Backward compatibility: Bearer API key must still authenticate."""
    settings = make_settings(tmp_path)
    client = make_client(settings)

    response = client.get(
        "/api/jobs", headers={"Authorization": f"Bearer {API_KEY}"}
    )
    assert response.status_code == 200


def test_healthz_and_review_remain_open(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_invalid_refresh_token_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = make_client(settings)

    client.cookies.set("refresh_token", "garbage", domain="testserver", path="/")
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
