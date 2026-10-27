"""Shared helpers for agents.

Agents are small, typed units that receive everything they need on ``run`` and return
artifacts. They never persist job state; the orchestrator owns state transitions.
"""

from __future__ import annotations

from pathlib import Path


def workspace_for(root: Path, job_id: str) -> Path:
    path = root / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path
