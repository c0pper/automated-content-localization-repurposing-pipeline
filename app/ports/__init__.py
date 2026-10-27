"""Ports define the seams between the agent fleet and third-party services.

Adapters live in ``app.adapters``; agents only depend on these Protocols.
"""

from app.ports.ai import (
    ClipPlanner,
    Copywriter,
    LipSyncer,
    Transcriber,
    Translator,
    VoiceSynthesizer,
)
from app.ports.infra import JobRepository, Notifier, ObjectStore, TaskQueue
from app.ports.media import MediaProcessor

__all__ = [
    "ClipPlanner",
    "Copywriter",
    "JobRepository",
    "LipSyncer",
    "MediaProcessor",
    "Notifier",
    "ObjectStore",
    "TaskQueue",
    "Transcriber",
    "Translator",
    "VoiceSynthesizer",
]
