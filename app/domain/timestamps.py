"""Timestamp helpers for agent payloads.

The public schema uses ``HH:MM:SS`` strings while agents work in seconds.
"""

from __future__ import annotations


def format_timestamp(seconds: float) -> str:
    """Format seconds as ``HH:MM:SS`` (rounding down)."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_timestamp(value: str) -> float:
    """Parse ``HH:MM:SS``, ``MM:SS`` or a plain number of seconds."""
    text = value.strip()
    try:
        return float(text)
    except ValueError:
        pass

    parts = text.split(":")
    if not 2 <= len(parts) <= 3:
        raise ValueError(f"Invalid timestamp: {value!r}")

    numbers = [float(part) for part in parts]
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds
