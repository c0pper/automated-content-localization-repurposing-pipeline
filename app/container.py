"""Composition root: build the object graph for the application.

Every third-party dependency is injected here. Swapping the stub adapters for real ones
does not require touching the agents.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.ffmpeg_media import FFmpegMediaProcessor
from app.adapters.in_memory_queue import InMemoryTaskQueue
from app.adapters.in_memory_repository import InMemoryJobRepository
from app.adapters.local_object_store import LocalObjectStore
from app.adapters.notifications import LogNotifier, WebhookNotifier
from app.adapters.stubs import (
    EchoTranslator,
    SilentVoiceSynthesizer,
    StubClipPlanner,
    StubCopywriter,
    StubLipSyncer,
    StubMediaProcessor,
    StubTranscriber,
)
from app.agents.delivery_agent import DeliveryAgent
from app.agents.ingest_agent import IngestAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.agents.localization_agent import LocalizationAgent
from app.agents.video_editor_agent import VideoEditorAgent
from app.config import Settings
from app.guardrails import Guardrails
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.retention import RetentionSweeper
from app.ports import JobRepository, MediaProcessor, Notifier, ObjectStore, TaskQueue
from app.services.submission import JobSubmissionService
from app.workers.runner import QueueWorker


@dataclass(slots=True)
class Container:
    settings: Settings
    repository: JobRepository
    queue: TaskQueue
    store: ObjectStore
    guardrails: Guardrails
    submissions: JobSubmissionService
    orchestrator: PipelineOrchestrator
    worker: QueueWorker
    retention: RetentionSweeper


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    settings.ensure_directories()

    repository: JobRepository = InMemoryJobRepository()
    queue: TaskQueue = InMemoryTaskQueue()
    store: ObjectStore = LocalObjectStore(
        data_dir=settings.data_dir,
        public_base_url=settings.public_base_url,
    )
    guardrails = Guardrails(settings)

    if settings.media_backend == "ffmpeg":
        media: MediaProcessor = FFmpegMediaProcessor()
    else:
        media = StubMediaProcessor()

    notifier: Notifier
    if settings.notification_webhook_url:
        notifier = WebhookNotifier(settings.notification_webhook_url)
    else:
        notifier = LogNotifier()

    ingest = IngestAgent(
        media=media,
        store=store,
        guardrails=guardrails,
        workspace_root=settings.workspace_dir,
    )
    intelligence = IntelligenceAgent(
        transcriber=StubTranscriber(),
        planner=StubClipPlanner(),
        copywriter=StubCopywriter(),
        guardrails=guardrails,
        min_clips=settings.min_clips_per_job,
        max_clips=settings.max_clips_per_job,
    )
    editor = VideoEditorAgent(
        media=media,
        store=store,
        workspace_root=settings.workspace_dir,
    )
    localization = LocalizationAgent(
        translator=EchoTranslator(),
        voice=SilentVoiceSynthesizer(),
        # TODO: replace with the Sync Labs adapter when lip-sync is required.
        lip_syncer=StubLipSyncer() if settings.lip_sync_enabled else None,
        media=media,
        store=store,
        workspace_root=settings.workspace_dir,
    )
    delivery = DeliveryAgent(
        store=store,
        notifier=notifier,
        workspace_root=settings.workspace_dir,
    )

    orchestrator = PipelineOrchestrator(
        repository=repository,
        guardrails=guardrails,
        ingest=ingest,
        intelligence=intelligence,
        editor=editor,
        localization=localization,
        delivery=delivery,
    )

    return Container(
        settings=settings,
        repository=repository,
        queue=queue,
        store=store,
        guardrails=guardrails,
        submissions=JobSubmissionService(
            repository=repository,
            queue=queue,
            guardrails=guardrails,
        ),
        orchestrator=orchestrator,
        worker=QueueWorker(
            queue=queue,
            orchestrator=orchestrator,
            poll_timeout=settings.worker_poll_seconds,
        ),
        retention=RetentionSweeper(store, retention_days=settings.retention_days),
    )
