# Automated Content Repurposing & Localization Pipeline

A single-tenant, API-only FastAPI service that turns a long-form recording into a review
bundle: 3–5 captioned 9:16 Base Clips, localized/dubbed clips for the selected Target
Languages, and per-Clip social copy plus LinkedIn and newsletter drafts.

The v1 behavior contract is [docs/spec/v1-pipeline.md](docs/spec/v1-pipeline.md); deployment
is the single-host Compose stack in [docker-compose.yml](docker-compose.yml). The runbook is
[docs/deployment.md](docs/deployment.md).

## What v1 does

```
POST /api/jobs
      │
      ▼
   RECEIVED ──▶ PROCESSING ──▶ AWAITING_SELECTION ──▶ PROCESSING ──▶ COMPLETED
                    │                  │                                 │
                    └──▶ FAILED ◀──────┘                                 └──▶ EXPIRED
                                                                          CANCELLED
```

1. **Ingest** validates the source, extracts audio and detects (or accepts) the Source
   Language.
2. **Intelligence** transcribes with word timestamps, plans 3–5 Clip candidates, scores
   them against the Quality Floor and drafts copy.
3. **Video** renders a caption-free 9:16 Base Clip Master per Clip and a captioned Base Clip
   for review.
4. **Selection Gate** pauses the Job with a cost matrix. The Creator picks a rectangular
   selection (Clips × Target Languages) and confirms the projected total.
5. **Localization** translates the selected Clips, clones the Workspace voice, synthesizes
   speech, optionally lip-syncs from the master and burns translated captions.
6. **Delivery** freezes the Review Bundle, writes the notification outbox and exposes a
   review link.

`COMPLETED` means the Review Bundle is ready, not that an external platform has accepted a
post.

## Quickstart (stubs, no paid calls)

```bash
uv sync
cp .env.example .env
uv run uvicorn --factory app.main:create_app --reload
```

Open http://localhost:8000/docs. Every POST/DELETE needs the Workspace API key and an
`Idempotency-Key`:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer dev-workspace-key" \
  -H "Idempotency-Key: demo-1" \
  -H "Content-Type: application/json" \
  -d '{"input_url": "https://storage.provider.com/raw_video.mp4", "target_languages": ["es", "de"]}'
```

The local default uses `PIPELINE_REPOSITORY_BACKEND=memory`, the in-process queue, the
local object store and deterministic stub AI adapters. Nothing is billed and no network is
required. `.data/` holds objects and render workspaces.

Poll the Job, read the gate, confirm a selection and resolve the review link:

```bash
curl -H "Authorization: Bearer dev-workspace-key" http://localhost:8000/api/jobs/<job_id>
curl -H "Authorization: Bearer dev-workspace-key" http://localhost:8000/api/jobs/<job_id>/selection
```

## API surface

All routes are under `/api`. Mutations require `Authorization: Bearer <Workspace API key>`
and `Idempotency-Key`; errors use `{"detail": {"code", "message", "details"}}`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/jobs` | Submit a remote URL or a completed Source Upload's key |
| `POST` | `/api/uploads` | Start a Source Upload (direct multipart to object storage) |
| `GET` | `/api/uploads/{upload_id}/parts` | Presigned part URLs |
| `POST` | `/api/uploads/{upload_id}/complete` | Complete a Source Upload |
| `DELETE` | `/api/uploads/{upload_id}` | Abort a Source Upload |
| `GET` | `/api/jobs` | List Jobs (`status`, `limit`, `cursor`) |
| `GET` | `/api/jobs/{job_id}` | Job view, cost summary, review URL |
| `GET` | `/api/jobs/{job_id}/selection` | Selection Gate + cost matrix |
| `POST` | `/api/jobs/{job_id}/selection` | Confirm Clips × Languages and total |
| `POST` | `/api/jobs/{job_id}/cancel` | Cancel; keeps Base Clips, prunes incomplete localized work |
| `POST` | `/api/jobs/{job_id}/retry` | Retry a `FAILED` Job from its last checkpoint |
| `POST` | `/api/jobs/{job_id}/derive` | Create a `copy` or `localization` Derived Job |
| `GET` | `/api/jobs/{job_id}/bundle` | Review Bundle manifest (API-key view) |
| `GET` | `/api/jobs/{job_id}/events` | Job Events |
| `GET` | `/api/jobs/{job_id}/cost` | Cost Ledger entries and summary |
| `POST` | `/api/jobs/{job_id}/review-link` | Rotate the review link |
| `DELETE` | `/api/jobs/{job_id}/review-link` | Revoke the review link permanently |
| `GET` | `/api/jobs/{job_id}/assets/{asset_id}` | Signed asset redirect |
| `GET` | `/api/review/{token}` | Read-only Review Bundle (token only) |
| `GET` | `/api/review/{token}/assets/{asset_id}` | Signed asset redirect (token only) |
| `GET`/`PUT` | `/api/workspace` | Settings, budgets and concurrency |
| `GET`/`PUT`/`DELETE` | `/api/workspace/voice-profile` | Single Voice Profile |
| `POST` | `/api/workspace/purge/dry-run` | Purge counts + confirmation token |
| `POST` | `/api/workspace/purge` | Confirm a two-step Workspace Purge |
| `GET` | `/api/workspace/purge/{purge_id}` | Purge status |
| `POST` | `/api/webhooks/{drive\|youtube\|zoom\|web}` | Normalized ingest triggers |
| `GET` | `/healthz`, `/readyz` | Liveness and dependency readiness |

Money crosses the API as decimal strings (for example `"1.23"`) and is stored as integer
micro-USD. Internal `Clip` objects are exposed as `segments[]` with `segment_id` to keep the
AGENTS.md schema compatible.

## Architecture

| Layer | Location | Responsibility |
| --- | --- | --- |
| Domain | `app/domain/` | `Job`, `Clip`, `Transcript`, money, scoring, selection, lifecycle |
| Ports | `app/ports/` | Protocols for AI providers, media, storage, queue, notifications |
| Agents | `app/agents/` | Ingest, Intelligence, Video Editor, Localization, Delivery |
| Orchestration | `app/pipeline/` | Stage sequencing, checkpoints, gates, retention |
| Services | `app/services/` | Cost, events, notifications, review, selection, derived, purge |
| Adapters | `app/adapters/` | In-memory, SQLite/Postgres, Redis, Silo, local store, stubs |
| API | `app/api/` | Routes, schemas, views, auth/idempotency middleware |
| Composition | `app/container.py` | The only place concrete adapters are chosen |

Agents stay stateless. The orchestrator owns status, checkpoints, cost accounting and
transitions.

### Durability

| Concern | Local default | Production |
| --- | --- | --- |
| Repository / ledger / events | In-memory | Postgres (`PIPELINE_REPOSITORY_BACKEND=postgres`) |
| Queue | In-process asyncio | Redis (`PIPELINE_QUEUE_BACKEND=redis`) |
| Object store | Local signed URLs | Silo S3 (`PIPELINE_OBJECT_STORE_BACKEND=silo`) |
| Notifications | Structured log | HMAC-signed webhook |
| Media | Stub | FFmpeg (`PIPELINE_MEDIA_BACKEND=ffmpeg`) |
| AI providers | Deterministic stubs | Ports ready for Whisper/OpenRouter/ElevenLabs/Sync Labs |

The SQL adapter mirrors the aggregate into `jobs`, `clips` and `clip_localizations` while
keeping a complete payload for checkpoint resume. The Postgres schema is
[`migrations/`](migrations/) (`001_initial.sql`, `002_source_uploads.sql`); `app.migrate` is idempotent.

> AI provider adapters are still deterministic stubs in this build: a production stack is
> durable for persistence, queueing, storage and notifications, but it does not make paid
> model calls. Replace the stub classes in `app/container.py` with implementations of the
> ports in `app/ports/`.

## Cost and safety guardrails

- **Rate card** — every paid call is priced from a versioned rate card with a 20% margin.
  A missing rate fails closed.
- **Job Budget** — default `$50`, enforced before the next paid call; every call appends to
  the append-only Cost Ledger.
- **Workspace Budget** — default `$500/month`, plus a concurrency cap (default 2) via
  workspace leases.
- **Input limits** — video minutes, transcript characters, Clip count, language fan-out,
  source bytes and allowed suffixes.
- **Retention** — raw sources, full Transcripts, caption SRTs and intermediates are pruned
  after 7 days. Base Clips, their spoken source text and caption-free masters live for the
  Workspace lifetime. A Workspace Purge is the only way to remove them.
- **Review links** — raw tokens are never stored; only the token ID and a SHA-256 hash.
  Rotation revokes the previous link, revocation is permanent, and purged Jobs return 404.
- **Notifications** — an outbox marks an attempt before sending, so delivery is at-most-once
  and signed.

## Configuration

All settings use the `PIPELINE_` prefix. Local defaults are in [`.env.example`](.env.example);
production values are in [`.env.production.example`](.env.production.example).

| Setting | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `local` | `local`, `test` or `production`; production validates configuration |
| `DATA_DIR` | `.data` | Object store and render workspace root |
| `API_BASE_URL` / `PUBLIC_BASE_URL` | localhost | Review links and asset URLs |
| `WORKSPACE_API_KEY` | `dev-workspace-key` | Bearer key for `/api` |
| `REPOSITORY_BACKEND` | `memory` | `memory`, `sqlite` or `postgres` |
| `DATABASE_URL` | unset | Async SQLAlchemy URL |
| `QUEUE_BACKEND` / `REDIS_URL` | `memory` | `memory` or `redis` |
| `OBJECT_STORE_BACKEND` | `local` | `local` or `silo` |
| `SILO_*` | unset | Endpoint, public endpoint, bucket, region, credentials |
| `MEDIA_BACKEND` | `stub` | `stub` or `ffmpeg` |
| `LIP_SYNC_ENABLED` | `false` | Enable the lip-sync stage |
| `JOB_BUDGET_USD` / `MONTHLY_BUDGET_USD` | `50.00` / `500.00` | Budget ceilings |
| `MAX_CONCURRENT_JOBS` | `2` | Workspace concurrency |
| `QUALITY_FLOOR` | `70` | Minimum Jev score for a Clip |
| `RETENTION_DAYS` | `7` | Raw/intermediate retention |
| `BACKUP_RETENTION_DAYS` | `30` | Nightly backup retention |
| `WEBHOOK_SECRET` | unset | Enables webhook authentication |
| `NOTIFICATION_WEBHOOK_URL` | unset | Enables delivery notifications |

`Settings.validate_for_runtime()` refuses to start a production process with development
secrets, non-HTTPS URLs, in-memory/local backends or a stub media renderer.

## Development

```bash
uv run pytest
uv run ruff check .
```

Tests are deterministic and make no paid calls. They cover the full Creator journey,
Selection Gate expiry and price conflicts, cancellation/retry, Derived Jobs, Workspace
Purge, review-link rotation, auth/idempotency, cost ceilings, retention and the SQLite
repository. Postgres/Redis/Silo integration and the Compose smoke test are deployment
acceptance checks described in [docs/deployment.md](docs/deployment.md).

## Documentation

- [GLOSSARY.md](GLOSSARY.md) — canonical domain language
- [docs/spec/v1-pipeline.md](docs/spec/v1-pipeline.md) — v1 API and implementation spec
- [docs/deployment.md](docs/deployment.md) — deployment, backup and restore runbook
- [docs/adr](docs/adr/) — decisions that are costly to reverse
