"""SSRF-safe source URL and object-key validation."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit

from app.domain.errors import GuardrailViolation

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "instance-data",
}


def _reject(message: str) -> None:
    raise GuardrailViolation("unsafe_source", message)


def _is_forbidden_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return not ip.is_global or ip.is_multicast


async def validate_http_url(url: str, *, allowed_suffixes: tuple[str, ...]) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        _reject("Only HTTP(S) source URLs are accepted")
    if not parsed.hostname:
        _reject("The source URL has no host")
    if parsed.hostname.lower() in _BLOCKED_HOSTNAMES:
        _reject("The source URL points at a private or metadata host")

    suffix = Path(parsed.path).suffix.lower()
    if suffix and suffix not in allowed_suffixes:
        allowed = ", ".join(allowed_suffixes)
        raise GuardrailViolation(
            "unsupported_media_format",
            f"Unsupported media format {suffix!r}; expected one of: {allowed}",
        )

    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_forbidden_ip(str(literal)):
            _reject("The source URL resolves to a private or link-local address")
        return

    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise GuardrailViolation(
            "unsafe_source", f"Could not resolve the source host: {exc}"
        ) from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        _reject("The source host did not resolve")
    for address in addresses:
        if _is_forbidden_ip(address):
            _reject("The source URL resolves to a private or link-local address")


def validate_file_source(path: Path, *, allowed_suffixes: tuple[str, ...]) -> None:
    if not path.is_file():
        raise GuardrailViolation("invalid_input", f"Input file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in allowed_suffixes:
        allowed = ", ".join(allowed_suffixes)
        raise GuardrailViolation(
            "unsupported_media_format",
            f"Unsupported media format {suffix!r}; expected one of: {allowed}",
        )


def validate_object_key(key: str) -> None:
    if not key.startswith("uploads/"):
        raise GuardrailViolation(
            "invalid_object_key", "Object sources must live under the uploads/ prefix"
        )
    if key.startswith("/") or ".." in key.split("/"):
        raise GuardrailViolation(
            "invalid_object_key", "Object keys may not be absolute or contain traversal"
        )
    if "\\" in key or "\x00" in key:
        raise GuardrailViolation("invalid_object_key", "Object key contains invalid characters")
