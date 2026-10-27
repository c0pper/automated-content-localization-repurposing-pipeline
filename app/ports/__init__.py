"""Ports define the seams between the agent fleet and third-party services.

Adapters live in ``app.adapters``; agents only depend on these Protocols.
"""

from app.ports.ai import (
    ClipPlanner,
    ClipScorer,
    Copywriter,
    LipSyncer,
    Transcriber,
    Translator,
    VoiceSynthesisResult,
    VoiceSynthesizer,
)
from app.ports.infra import (
    Clock,
    CostLedgerRepository,
    IdempotencyStore,
    JobEventRepository,
    JobRepository,
    LeaseStore,
    Notifier,
    ObjectStore,
    OutboxRepository,
    PurgeRepository,
    ReviewTokenRepository,
    TaskQueue,
    WorkspaceRepository,
)
from app.ports.media import MediaProcessor

__all__ = [
    "ClipPlanner",
    "ClipScorer",
    "Clock",
    "Copywriter",
    "CostLedgerRepository",
    "IdempotencyStore",
    "JobEventRepository",
    "JobRepository",
    "LeaseStore",
    "LipSyncer",
    "MediaProcessor",
    "Notifier",
    "ObjectStore",
    "OutboxRepository",
    "PurgeRepository",
    "ReviewTokenRepository",
    "TaskQueue",
    "Transcriber",
    "Translator",
    "VoiceSynthesisResult",
    "VoiceSynthesizer",
    "WorkspaceRepository",
]
