"""Minimal HS256 JWT encode/decode (no external JWT library required)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets as secrets_module
import time


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + ("=" * padding))


def encode_token(payload: dict, secret: str, expires_in: int = 3600) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    # Each issued token gets a unique jti so that refreshed tokens always differ
    # from the originals, even within the same second.
    payload = {
        **payload,
        "iat": now,
        "exp": now + expires_in,
        "jti": secrets_module.token_hex(8),
    }
    header_b = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b}.{payload_b}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig = _b64url_encode(signature)
    return f"{header_b}.{payload_b}.{sig}"


def decode_token(token: str, secret: str, verify_exp: bool = True) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid token segments")
        header_b, payload_b, sig = parts
        signing_input = f"{header_b}.{payload_b}".encode()
        expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        expected_sig_str = _b64url_encode(expected_sig)
        if not hmac.compare_digest(sig, expected_sig_str):
            raise ValueError("invalid signature")
        header = json.loads(_b64url_decode(header_b))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("invalid header")
        payload = json.loads(_b64url_decode(payload_b))
        if verify_exp and payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise ValueError(f"JWT decode failed: {exc}") from exc
