"""Composition root: build the object graph for the application.

Every third-party dependency is injected here. Swapping the stub adapters for real ones
does not require touching the agents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.adapters.in_memory_queue import InMemoryTaskQueue
from app.adapters.in_memory_stores import (
    InMemoryCostLedger,
    InMemoryIdempotencyStore,
    InMemoryJobEvents,
    InMemoryJobRepository,
    InMemoryLeaseStore,
    InMemoryOutbox,
    InMemoryPurgeRepository,
    InMemoryReviewTokens,
    InMemorySourceUploads,
    InMemoryWorkspaceRepository,
    SystemClock,
)
from app.adapters.local_object_store import LocalObjectStore
from app.adapters.notifications import HmacWebhookNotifier, LogNotifier
from app.adapters.stubs import (
    EchoTranslator,
    SilentVoiceSynthesizer,
    StubClipPlanner,
    StubClipScorer,
    StubCopywriter,
    StubLipSyncer,
    StubMediaProcessor,
    StubTranscriber,
)
from app.adapters.elevenlabs_voice import ElevenLabsVoiceSynthesizer
from app.adapters.openai_whisper import OpenAIWhisperTranscriber
from app.adapters.openrouter_copy import OpenRouterCopywriter
from app.adapters.openrouter_jev import OpenRouterClipScorer
from app.adapters.openrouter_planning import OpenRouterClipPlanner
from app.adapters.openrouter_translation import OpenRouterTranslator
from app.adapters.synclabs_lipsync import SyncLabsLipSyncer
from app.agents.delivery_agent import DeliveryAgent
from app.agents.ingest_agent import IngestAgent
from app.agents.intelligence_agent import IntelligenceAgent
from app.agents.localization_agent import LocalizationAgent
from app.agents.video_editor_agent import VideoEditorAgent
from app.config import Settings
from app.domain.rate_card import RateCard
from app.guardrails import Guardrails
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.retention import RetentionSweeper
from app.ports import (
    Clock,
    CostLedgerRepository,
    IdempotencyStore,
    JobEventRepository,
    JobRepository,
    LeaseStore,
    MediaProcessor,
    Notifier,
    ObjectStore,
    OutboxRepository,
    PurgeRepository,
    ReviewTokenRepository,
    SourceUploadRepository,
    TaskQueue,
    WorkspaceRepository,
)
from app.ports.ai import ClipPlanner, ClipScorer, Copywriter, LipSyncer, Transcriber, Translator, VoiceSynthesizer
from app.security.fetch import SafeRemoteFetcher
from app.services.cost import CostService
from app.services.derived import DerivedJobService
from app.services.events import EventService
from app.services.lifecycle import JobLifecycleService
from app.services.notifications import NotificationService
from app.services.purge import PurgeService
from app.services.review import ReviewService
from app.services.selection import SelectionService
from app.services.submission import JobSubmissionService
from app.services.uploads import SourceUploadService
from app.services.workspace import WorkspaceService
from app.workers.runner import QueueWorker


@dataclass(slots=True)
class Container:
    settings: Settings
    clock: Clock
    repository: JobRepository
    ledger: CostLedgerRepository
    event_store: JobEventRepository
    outbox: OutboxRepository
    idempotency: IdempotencyStore
    review_tokens: ReviewTokenRepository
    workspaces_repository: WorkspaceRepository
    purges: PurgeRepository
    source_uploads: SourceUploadRepository
    leases: LeaseStore
    queue: TaskQueue
    store: ObjectStore
    guardrails: Guardrails
    cost: CostService
    events: EventService
    notifications: NotificationService
    review: ReviewService
    workspaces: WorkspaceService
    selection: SelectionService
    lifecycle: JobLifecycleService
    derived: DerivedJobService
    purge: PurgeService
    uploads: SourceUploadService
    submissions: JobSubmissionService
    orchestrator: PipelineOrchestrator
    worker: QueueWorker
    retention: RetentionSweeper
    dispose: Callable[[], Awaitable[None]] | None = None


def build_container(settings: Settings | None = None, *, clock: Clock | None = None) -> Container:
    settings = settings or Settings()
    settings.validate_for_runtime()
    settings.ensure_directories()

    clock = clock or SystemClock()

    repository: JobRepository
    ledger: CostLedgerRepository
    event_store: JobEventRepository
    outbox: OutboxRepository
    idempotency: IdempotencyStore
    review_tokens: ReviewTokenRepository
    workspaces_repository: WorkspaceRepository
    purges: PurgeRepository
    source_uploads: SourceUploadRepository
    leases: LeaseStore
    dispose: Callable[[], Awaitable[None]] | None = None

    if settings.repository_backend == "memory":
        repository = InMemoryJobRepository()
        ledger = InMemoryCostLedger()
        event_store = InMemoryJobEvents()
        outbox = InMemoryOutbox()
        idempotency = InMemoryIdempotencyStore()
        review_tokens = InMemoryReviewTokens()
        workspaces_repository = InMemoryWorkspaceRepository()
        purges = InMemoryPurgeRepository()
        source_uploads = InMemorySourceUploads()
        leases = InMemoryLeaseStore(clock)
    else:
        from app.adapters.sql_repository import build_sql_repositories

        (
            repository,
            ledger,
            event_store,
            outbox,
            idempotency,
            review_tokens,
            workspaces_repository,
            purges,
            source_uploads,
            leases,
        ) = build_sql_repositories(settings, clock)
        dispose = repository.dispose  # type: ignore[attr-defined]

    queue: TaskQueue = InMemoryTaskQueue()
    if settings.queue_backend == "redis":
        from app.adapters.redis_queue import RedisTaskQueue

        queue = RedisTaskQueue(settings.redis_url)

    store: ObjectStore
    if settings.object_store_backend == "silo":
        from app.adapters.silo_object_store import SiloObjectStore

        store = SiloObjectStore(settings)
    else:
        store = LocalObjectStore(
            data_dir=settings.data_dir,
            public_base_url=settings.public_base_url,
        )

    guardrails = Guardrails(settings)

    rate_card = (
        RateCard.from_file(
            settings.rate_card_path,
            version=settings.rate_card_version,
            margin=settings.cost_margin,
        )
        if settings.rate_card_path
        else RateCard.default(
            version=settings.rate_card_version, margin=settings.cost_margin
        )
    )

    cost = CostService(
        ledger=ledger,
        workspaces=workspaces_repository,
        rate_card=rate_card,
        clock=clock,
    )
    events = EventService(events=event_store, clock=clock)

    notifier: Notifier
    if settings.notification_webhook_url:
        notifier = HmacWebhookNotifier(
            settings.notification_webhook_url,
            secret=settings.notification_signing_secret,
        )
    else:
        notifier = LogNotifier()
    notifications = NotificationService(outbox=outbox, notifier=notifier, clock=clock)

    review = ReviewService(
        tokens=review_tokens,
        clock=clock,
        secret=settings.notification_signing_secret,
        api_base_url=settings.api_base_url,
    )
    workspaces = WorkspaceService(
        workspaces=workspaces_repository,
        cost=cost,
        clock=clock,
        settings=settings,
    )
    selection = SelectionService(
        repository=repository,
        queue=queue,
        leases=leases,
        cost=cost,
        events=events,
        notifications=notifications,
        review=review,
        clock=clock,
        settings=settings,
    )
    lifecycle = JobLifecycleService(
        repository=repository,
        queue=queue,
        leases=leases,
        store=store,
        cost=cost,
        events=events,
        workspaces=workspaces,
        clock=clock,
    )

    if settings.media_backend == "ffmpeg":
        from app.adapters.ffmpeg_media import FFmpegMediaProcessor

        media: MediaProcessor = FFmpegMediaProcessor()
    else:
        media = StubMediaProcessor()

    transcriber: Transcriber = StubTranscriber()
    planner: ClipPlanner = StubClipPlanner()
    scorer: ClipScorer = StubClipScorer()
    copywriter: Copywriter = StubCopywriter()
    translator: Translator = EchoTranslator()
    voice: VoiceSynthesizer = SilentVoiceSynthesizer()
    lip_syncer: LipSyncer | None = StubLipSyncer() if settings.lip_sync_enabled else None

    if settings.openai_api_key:
        transcriber = OpenAIWhisperTranscriber(model="whisper-1")
    if settings.openrouter_api_key:
        planner = OpenRouterClipPlanner(
            model=settings.default_planning_model,
            allowlist=set(settings.planning_model_allowlist),
        )
        copywriter = OpenRouterCopywriter(model=settings.default_copy_model)
        translator = OpenRouterTranslator(model=settings.default_translation_model)
        scorer = OpenRouterClipScorer(
            model=settings.jev_model,
            allowlist=set(settings.model_allowlists.keys()),
        )
    if settings.elevenlabs_api_key:
        voice = ElevenLabsVoiceSynthesizer()
    if settings.lip_sync_enabled and settings.synclabs_api_key:
        lip_syncer = SyncLabsLipSyncer()

    ingest = IngestAgent(
        media=media,
        store=store,
        guardrails=guardrails,
        workspace_root=settings.workspace_dir,
        fetcher=SafeRemoteFetcher(
            allowed_suffixes=settings.input_suffixes,
            max_bytes=settings.max_source_bytes,
            timeout=settings.provider_timeout_seconds,
        ),
        allow_local_files=settings.environment != "production",
    )
    intelligence = IntelligenceAgent(
        transcriber=transcriber,
        planner=planner,
        scorer=scorer,
        copywriter=copywriter,
        cost=cost,
        guardrails=guardrails,
        settings=settings,
    )
    editor = VideoEditorAgent(
        media=media,
        store=store,
        workspace_root=settings.workspace_dir,
    )
    localization = LocalizationAgent(
        translator=translator,
        voice=voice,
        lip_syncer=lip_syncer,
        media=media,
        store=store,
        cost=cost,
        guardrails=guardrails,
        settings=settings,
        workspace_root=settings.workspace_dir,
    )
    delivery = DeliveryAgent(
        store=store,
        workspace_root=settings.workspace_dir,
    )

    orchestrator = PipelineOrchestrator(
        repository=repository,
        queue=queue,
        leases=leases,
        cost=cost,
        events=events,
        notifications=notifications,
        review=review,
        selection=selection,
        lifecycle=lifecycle,
        workspaces=workspaces,
        ingest=ingest,
        intelligence=intelligence,
        editor=editor,
        localization=localization,
        delivery=delivery,
        clock=clock,
        settings=settings,
    )
    purge = PurgeService(
        jobs=repository,
        ledger=ledger,
        events=event_store,
        outbox=outbox,
        idempotency=idempotency,
        review_tokens=review_tokens,
        purges=purges,
        leases=leases,
        uploads=source_uploads,
        store=store,
        clock=clock,
        settings=settings,
    )
    uploads = SourceUploadService(
        uploads=source_uploads,
        store=store,
        clock=clock,
        settings=settings,
    )
    submissions = JobSubmissionService(
        repository=repository,
        queue=queue,
        store=store,
        workspaces=workspaces,
        cost=cost,
        events=events,
        clock=clock,
        settings=settings,
        purge=purge,
        uploads=uploads,
    )
    derived = DerivedJobService(
        repository=repository,
        queue=queue,
        store=store,
        copywriter=copywriter,
        cost=cost,
        events=events,
        workspaces=workspaces,
        selection=selection,
        clock=clock,
        settings=settings,
    )

    return Container(
        settings=settings,
        clock=clock,
        repository=repository,
        ledger=ledger,
        event_store=event_store,
        outbox=outbox,
        idempotency=idempotency,
        review_tokens=review_tokens,
        workspaces_repository=workspaces_repository,
        purges=purges,
        source_uploads=source_uploads,
        leases=leases,
        queue=queue,
        store=store,
        guardrails=guardrails,
        cost=cost,
        events=events,
        notifications=notifications,
        review=review,
        workspaces=workspaces,
        selection=selection,
        lifecycle=lifecycle,
        derived=derived,
        purge=purge,
        uploads=uploads,
        submissions=submissions,
        orchestrator=orchestrator,
        worker=QueueWorker(
            queue=queue,
            orchestrator=orchestrator,
            poll_timeout=settings.worker_poll_seconds,
        ),
        retention=RetentionSweeper(
            store,
            retention_days=settings.retention_days,
            repository=repository,
            uploads=source_uploads,
            clock=clock,
            workspace_root=settings.workspace_dir,
        ),
        dispose=dispose,
    )
