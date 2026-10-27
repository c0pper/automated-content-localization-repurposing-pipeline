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
    (extract)     (Whisper,     (FFmpeg,     (OpenRouter,   (Silo, Slack,
                   OpenRouter)   Shotstack)   ElevenLabs,    webhook)
                                              Sync Labs)
```

| Layer | Location | Responsibility |
| --- | --- | --- |
| Domain | `app/domain/` | `Job`, `Clip` (wire alias `segments[]`), `Transcript`, `ClipCandidate`, errors, timestamps |
| Ports | `app/ports/` | Protocols for media, AI providers, storage, queue, notifications |
| Agents | `app/agents/` | The five agents from AGENTS.md; stateless, typed inputs/outputs |
| Orchestration | `app/pipeline/` | Stage sequencing, budget accounting, retention |
| Adapters | `app/adapters/` | Stub + local implementations, FFmpeg backend |
| API | `app/api/` | FastAPI routes, webhook triggers, schemas |
| Composition | `app/container.py` | The only place concrete adapters are chosen |

Agents never persist state. The current skeleton moves a job through
`RECEIVED → PROCESSING (ingest → intelligence → video → localization → delivery) → COMPLETED`,
recording failures as `FAILED` with the guardrail/pipeline error. The target lifecycle adds
`AWAITING_SELECTION` (Creator selection gate), `EXPIRED` (unanswered gate) and `CANCELLED`
(ADR 0007 and ADR 0015), plus an explicit retry of `FAILED` Jobs from their last checkpoint
(ADR 0006); the skeleton does not implement those transitions yet.

## Quickstart

```bash
uv sync
cp .env.example .env
uv run uvicorn --factory app.main:create_app --reload
```

Open http://localhost:8000/docs. Submit a remote URL or a pre-uploaded Silo object key
(direct multipart uploads through the API are out of scope):

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
`content` (LinkedIn + newsletter copy) and `error`. The target Review Bundle adds
Localized Clip Copy per selected language. Delivered artifacts are served from `/assets`
in local development.

### Target deployment

v1 ships as one Docker Compose stack on one host: Caddy, the API, the Celery worker,
Postgres, Redis, Silo and a nightly backup service. Caddy terminates TLS and exposes the
API and a public Silo S3 endpoint; the Silo console stays private. Silo runs from the
official `pgsty/silo` image. Backups mirror Postgres and Silo to an operator-provided
off-host target with 30-day retention. Host volumes and the backup target are encrypted at
rest; Caddy terminates TLS. The Compose file is not part of the skeleton yet; see
[ADR 0014](docs/adr/0014-single-host-compose.md).

### Webhook triggers

`POST /api/webhooks/{drive|youtube|zoom|web}` accepts the same normalized payload. When
`PIPELINE_WEBHOOK_SECRET` is set, callers must send `X-Webhook-Secret`.

### Tests

```bash
uv run pytest
uv run ruff check .
```

## Documentation

- [GLOSSARY.md](GLOSSARY.md) — canonical domain language
- [docs/adr](docs/adr/) — decisions that are costly to reverse

## What is stubbed

| Port | Local default | Production adapter to add |
| --- | --- | --- |
| `Transcriber` | `StubTranscriber` | OpenAI Whisper |
| `ClipPlanner`, `Copywriter` | `StubClipPlanner`, `StubCopywriter` | OpenRouter default + selectable models |
| `MediaProcessor` | `StubMediaProcessor` | `FFmpegMediaProcessor`, Shotstack |
| `Translator` | `EchoTranslator` | OpenRouter |
| `VoiceSynthesizer` | `SilentVoiceSynthesizer` | ElevenLabs voice clone |
| `LipSyncer` | `StubLipSyncer` | Sync Labs |
| `JobRepository` | `InMemoryJobRepository` | Postgres |
| `TaskQueue` | `InMemoryTaskQueue` | Celery/Redis |
| `ObjectStore` | `LocalObjectStore` | Silo (S3-compatible) |
| `Notifier` | `LogNotifier` | Slack/Telegram/email webhook |

Set `PIPELINE_MEDIA_BACKEND=ffmpeg` to use the real FFmpeg renderer (requires `ffmpeg`
and `ffprobe` on `PATH`). The other AI adapters are intentionally not implemented yet;
each is a single class implementing the corresponding protocol in `app/ports/`.

> The in-memory repository and queue are process-local. Restarting the API loses jobs,
> and a crash mid-stage leaves a job in `PROCESSING`. Durable adapters are the next step.

## Guardrails (AGENTS.md § Security & Usage Guardrails)

- **Cost limits** — every paid call is checked against a USD rate card with a safety margin
  and a default $50 Job Budget; missing rates fail closed. The append-only Cost Ledger is
  the enforcement point, and it survives restarts. Separate limits bound video minutes,
  characters, clip count and languages before the next paid call.
- **Workspace ceilings** — a monthly Workspace Budget (default $500) and a concurrency
  limit (default 2) stop repeated Jobs from bypassing the per-Job cap.
- **Encryption** — host volumes and the backup target are encrypted at rest; Caddy
  provides TLS in transit.
- **Rate limiting / queueing** — jobs enter through a `TaskQueue`; the in-process worker
  is a development stand-in for Celery/Redis.
- **Retention** — a scheduled `RetentionSweeper` deletes raw/intermediate job workspaces
  after `PIPELINE_RETENTION_DAYS` (default 7). Delivered objects are retained until an
  explicit Workspace Purge.

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

1. Add real adapters for Whisper, OpenRouter, ElevenLabs, Sync Labs and Silo.
2. Replace in-memory persistence with Postgres + Celery/Redis + Silo, including
   stage-level checkpointing, manual retry, the Cost Ledger, Job Events, the monthly
   Workspace Budget and the concurrency cap.
3. Implement the Selection Gate, cancellation/expiry, Workspace Purge, auth, review
   tokens, the Voice Profile resource, the Source Language override and presigned uploads.
4. Ship the single-host Compose stack (Caddy, api, worker, Postgres, Redis, Silo, backup)
   from ADR 0014, including the restore drill and encrypted volumes.
