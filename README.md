# Automated Content Repurposing & Localization Pipeline

A FastAPI skeleton for the multi-agent platform described in [AGENTS.md](AGENTS.md):
ingest a long-form recording, extract high-value hooks, render 9:16 clips with captions,
localize them into target languages, and deliver a review bundle.

The app runs end-to-end with **deterministic stub adapters** — no API keys, no ffmpeg, and
no network access required. Real integrations plug into the same ports.

## Architecture

```
                    ┌──────────────────────────────┐
  POST /api/jobs ──▶│ JobSubmissionService         │──▶ repository + queue
  webhooks         └──────────────────────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────────┐
                    │ PipelineOrchestrator         │  owns status, budgets, retries
                    └──────────────────────────────┘
         ┌───────────┬───────────┬────────────┬───────────────┐
         ▼           ▼           ▼            ▼               ▼
   IngestAgent  Intelligence  VideoEditor  Localization   Delivery
    (extract)     (Whisper,     (FFmpeg,     (DeepL, TTS,   (S3, Slack,
                   LLM clips)    Shotstack)   lip-sync)      webhook)
```

| Layer | Location | Responsibility |
| --- | --- | --- |
| Domain | `app/domain/` | `Job`, `Segment`, `Transcript`, `ClipCandidate`, errors, timestamps |
| Ports | `app/ports/` | Protocols for media, AI providers, storage, queue, notifications |
| Agents | `app/agents/` | The five agents from AGENTS.md; stateless, typed inputs/outputs |
| Orchestration | `app/pipeline/` | Stage sequencing, budget accounting, retention |
| Adapters | `app/adapters/` | Stub + local implementations, FFmpeg backend |
| API | `app/api/` | FastAPI routes, webhook triggers, schemas |
| Composition | `app/container.py` | The only place concrete adapters are chosen |

Agents never persist state. The orchestrator moves a job through
`RECEIVED → PROCESSING (ingest → intelligence → video → localization → delivery) → COMPLETED`,
recording failures as `FAILED` with the guardrail/pipeline error.

## Quickstart

```bash
uv sync
cp .env.example .env
uv run uvicorn --factory app.main:create_app --reload
```

Open http://localhost:8000/docs. Submit a local file or a URL:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_url": "https://storage.provider.com/raw_video.mp4",
    "target_languages": ["es", "de"]
  }'
```

Poll the job:

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

A completed job matches the AGENTS.md schema and additionally carries `stage`, `usage`,
`content` (LinkedIn + newsletter copy) and `error`. Delivered artifacts are served from
`/assets` in local development.

### Webhook triggers

`POST /api/webhooks/{drive|youtube|zoom|web}` accepts the same normalized payload. When
`PIPELINE_WEBHOOK_SECRET` is set, callers must send `X-Webhook-Secret`.

### Tests

```bash
uv run pytest
uv run ruff check .
```

## What is stubbed

| Port | Local default | Production adapter to add |
| --- | --- | --- |
| `Transcriber` | `StubTranscriber` | OpenAI Whisper |
| `ClipPlanner`, `Copywriter` | `StubClipPlanner`, `StubCopywriter` | Claude 3.5 Sonnet / GPT-4o |
| `MediaProcessor` | `StubMediaProcessor` | `FFmpegMediaProcessor`, Shotstack |
| `Translator` | `EchoTranslator` | DeepL |
| `VoiceSynthesizer` | `SilentVoiceSynthesizer` | ElevenLabs voice clone |
| `LipSyncer` | `StubLipSyncer` | Sync Labs |
| `JobRepository` | `InMemoryJobRepository` | Postgres/SQLite |
| `TaskQueue` | `InMemoryTaskQueue` | Celery/Redis or QStash |
| `ObjectStore` | `LocalObjectStore` | S3 / Cloudflare R2 |
| `Notifier` | `LogNotifier` | Slack/Telegram/email webhook |

Set `PIPELINE_MEDIA_BACKEND=ffmpeg` to use the real FFmpeg renderer (requires `ffmpeg`
and `ffprobe` on `PATH`). The other AI adapters are intentionally not implemented yet;
each is a single class implementing the corresponding protocol in `app/ports/`.

> The in-memory repository and queue are process-local. Restarting the API loses jobs,
> and a crash mid-stage leaves a job in `PROCESSING`. Durable adapters are the next step.

## Guardrails (AGENTS.md § Security & Usage Guardrails)

- **Cost limits** — `Guardrails` rejects submissions over the video-minute, character,
  clip-count and language limits before the next paid call.
- **Rate limiting / queueing** — jobs enter through a `TaskQueue`; the in-process worker
  is a development stand-in for Celery/Redis or QStash.
- **Retention** — a scheduled `RetentionSweeper` deletes raw/intermediate job workspaces
  after `PIPELINE_RETENTION_DAYS` (default 7). Delivered objects are not pruned.

## Configuration

All settings use the `PIPELINE_` prefix; see [`.env.example`](.env.example).

| Setting | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `.data` | Object store + workspace root |
| `PUBLIC_BASE_URL` | `http://localhost:8000/assets` | URL prefix returned for artifacts |
| `RUN_WORKER` | `true` | Start the in-process queue worker |
| `MEDIA_BACKEND` | `stub` | `stub` or `ffmpeg` |
| `MAX_VIDEO_MINUTES` | `90` | Per-job minute budget |
| `MAX_CHARACTERS_PER_JOB` | `60000` | Transcript/localization character budget |
| `MIN_CLIPS_PER_JOB` / `MAX_CLIPS_PER_JOB` | `3` / `5` | Clip count contract |
| `MAX_TARGET_LANGUAGES` | `3` | Language fan-out limit |
| `RETENTION_DAYS` | `7` | Raw intermediate retention |
| `WEBHOOK_SECRET` | unset | Enables webhook authentication |
| `NOTIFICATION_WEBHOOK_URL` | unset | Enables real delivery notifications |

## Next steps

1. Add real adapters for Whisper/LLM, DeepL, ElevenLabs and Sync Labs.
2. Replace in-memory persistence with Postgres + Celery/Redis, including stage-level
   checkpointing so failed jobs can resume instead of restarting.
3. Publish OpenAPI clients, add auth/tenant isolation, and wire presigned upload URLs.
