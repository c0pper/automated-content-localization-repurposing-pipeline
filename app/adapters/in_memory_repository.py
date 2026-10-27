"""Backward-compatible import for the in-memory Job repository."""

from app.adapters.in_memory_stores import InMemoryJobRepository

__all__ = ["InMemoryJobRepository"]
