# v1 Pipeline Implementation Spec

**Status:** Draft for review
**Sources:** `GLOSSARY.md`, ADR 0001–0020, and the accepted design decisions from rounds 1–8.
**Scope:** The backend/API implementation that brings the existing skeleton in line with the recorded design. The frontend is a separate consumer.

---

## Problem Statement

A Creator with long-form expertise can record a valuable conversation, but turning it into
review-ready short clips, localized versions and channel copy is a chain of manual tools,
provider dashboards and ad-hoc scripts. The current backend proves the shape of that chain,
but it runs as a one-shot pipeline: it localizes every clip before anyone chooses, keeps
state in memory, has no durable cost or access model, and cannot pause for a human decision.

Operators need a backend that:

- will not spend localization money on clips or languages the Creator did not choose;
- survives worker restarts and provider failures without duplicating paid work or
  notifications;
- gives the Creator one narrow, well-informed decision at the right moment;
- makes cost, access and retention explicit and enforceable;
- can run as a single-host, self-hosted service without a platform team.

## Solution

Build a single-tenant, API-only FastAPI service that turns one Source Recording into a
Review Bundle through a resumable, cost-guarded pipeline.

The pipeline ingests a remote URL or a Source Upload (ADR 0022), transcribes the audio,
detects or accepts the Source Language, plans 3–5 Clip Candidates, scores them with Jev and
the Quality Floor, renders Base Clips, and pauses at the Selection Gate. The Creator selects
a rectangular subset of Base Clips × declared Target Languages, sees the projected
localization cost, and confirms. Only that selection is translated, voiced, optionally
lip-synced, and delivered. The Job completes when the immutable Review Bundle is ready for
review; `COMPLETED` never means approved or published.

Postgres owns state, the append-only Cost Ledger and Job Events. Redis/Celery owns the work
queue. Silo owns artifacts. Caddy is the public TLS ingress. Notifications are signed,
at-most-once webhooks. A single-host Docker Compose stack is the v1 deployment.

## User Stories

1. As an Operator, I want a single Workspace API key for backend writes, so that the
   separate frontend can submit and manage Jobs without exposing provider credentials.
2. As an Operator, I want a per-Job review token that is read-only, so that a Creator can
   view a Job without receiving the Workspace API key.
3. As a Creator, I want to submit either a remote video URL or a file I upload directly,
   so that I can use the storage flow that fits my workflow.
4. As a Creator, I want to declare the Source Language when I already know it, so that a
   wrong automatic detection does not misclassify my recording.
5. As a Creator, I want the pipeline to detect the Source Language when I do not declare it,
   and fall back to English only when detection is inconclusive.
6. As a Creator, I want to choose a subset of the Workspace's allowed Target Languages, so
   that the Job only considers languages the providers support.
7. As a Creator, I want to enable lip-sync per Job, so that I do not pay for it by default.
8. As a Creator, I want to override the planning, copy or translation model from a curated
   list, so that I can tune quality and cost without changing deployment configuration.
9. As an Operator, I want submissions to reject unsupported formats, unsafe URLs, empty
   targets, duplicate targets and source/target conflicts before any paid call.
10. As a Creator, I want an idempotent submission endpoint, so that a network retry does
    not create two Jobs or charge twice.
11. As a Creator, I want to see the Job's status, stage, source language, selected
    languages, cost and failure reason, so that I know what is happening.
12. As a Creator, I want a word-level transcript used internally, so that clips and copy
    are grounded in what was actually said.
13. As a Creator, I want 3–5 Clip Candidates that pass the Quality Floor, so that I am not
    asked to choose between weak moments.
14. As a Creator, I want to see each Clip's four Jev scores and the planner's rationale, so
    that I can judge why it was selected.
15. As an Operator, I want the Job to fail before rendering if fewer than three Clip
    Candidates clear the Quality Floor, so that the pipeline does not produce a thin bundle.
16. As a Creator, I want each Base Clip rendered as a 9:16 vertical video with styled,
    word-timed captions, so that it is ready for short-form review.
17. As a Creator, I want a stable review link for the Base Clips, so that I can watch them
    before deciding what to localize.
18. As a Creator, I want a `selection_required` notification when the Selection Gate opens,
    so that I do not have to poll the API.
19. As a Creator, I want the Selection Gate to show every Base Clip × every declared Target
    Language with its projected cost, so that I can choose with the price in view.
20. As a Creator, I want to select a rectangular subset of Clips and languages, or select
    nothing, so that I control exactly what gets localized.
21. As a Creator, I want a price-change conflict when the projected total differs from what
    I confirmed, so that I never approve a different amount by accident.
22. As a Creator, I want an unanswered Selection Gate to expire after seven days with no
    localization spend, so that stale Jobs do not sit in limbo.
23. As a Creator, I want to localize only the confirmed selection, so that unselected
    languages and clips cost nothing.
24. As a Creator, I want the per-Clip Hook and social caption localized, while LinkedIn and
    newsletter copy stay in the Source Language, so that v1 copy scope is predictable.
25. As a Creator, I want the localized audio to use my Voice Profile, so that the dubbed
    clip sounds like me.
26. As a Creator, I want a missing Voice Profile to fail the Job rather than silently use a
    generic voice.
27. As a Creator, I want lip-sync to replace the localized clip when enabled, and to fail
    the Job rather than fall back, so that the output matches what I paid for.
28. As a Creator, I want an immutable Review Bundle with Base Clips, Localized Clips and
    copy, so that a completed review cannot change underneath me.
29. As a Creator, I want a stable review URL whose asset links redirect to short-lived
    presigned Silo URLs, so that links keep working without exposing credentials.
30. As a Creator, I want the review link to show whatever assets exist even if the Job did
    not complete, so that I can inspect partial work.
31. As an Operator, I want to rotate or revoke a Job's review link, so that a leaked link
    can be neutralized.
32. As a Creator, I want to cancel a Job, so that I can stop work I no longer need.
33. As an Operator, I want cancellation to leave completed Base Clips available and prune
    incomplete localized artifacts, so that the useful work is not lost.
34. As an Operator, I want to retry a failed Job from its last checkpoint under the same Job
    ID and Job Budget, so that transient failures do not require re-ingestion.
35. As an Operator, I want budget failures and configuration failures to be distinguishable
    from transient failures, so that I know whether a retry can help.
36. As a Creator, I want to create a Derived Job from retained Base Clips, so that I can
    try a different localization selection or refresh clip copy without redoing the source
    work.
37. As an Operator, I want a localization Derived Job to re-enter the Selection Gate, and a
    copy-only Derived Job to skip it, so that no localization spend is committed without a
    decision.
38. As an Operator, I want the monthly Workspace Budget and concurrency limit enforced
    before paid work, so that repeated Jobs cannot bypass the per-Job ceiling.
39. As an Operator, I want an append-only Cost Ledger and Job Event timeline, so that I can
    audit spend and understand what happened.
40. As an Operator, I want to configure the Workspace allowlist, default models, Job Budget,
    monthly budget and concurrency limit, so that policy is not hard-coded.
41. As an Operator, I want a two-step Workspace Purge, so that I can delete all Jobs and
    assets deliberately and irreversibly.
42. As an Operator, I want host volumes, the backup target and transit encrypted, so that
    the Creator's voice and likeness are protected at rest and in motion.
43. As an Operator, I want nightly backups and a restore drill, so that a single-host
    deployment has a real recovery path.
44. As a Frontend, I want deterministic error codes, pagination and stable IDs, so that I can
    build a reliable Creator experience without scraping messages.
45. As a Frontend, I want idempotent POST and DELETE operations, so that browser retries and
    double-clicks are safe.

## Implementation Decisions

### 1. Architecture and tenancy

- FastAPI owns orchestration, state transitions, cost accounting and access control.
  Make.com/Zapier may trigger a Job or receive a notification, but they do not own state.
- v1 is single-tenant: one Workspace, one Creator, one Voice Profile. `workspace_id` and
  `creator_id` are reserved on every Job and on Workspace resources so that tenancy can be
  added without rewriting the domain.
- Agents stay stateless and typed. They receive inputs and return artifacts. The
  orchestrator commits stage checkpoints, appends cost/events and decides the next
  transition.
- Ports and adapters remain the dependency boundary: `JobRepository`, `TaskQueue`,
  `ObjectStore`, `Notifier`, `Transcriber`, `ClipPlanner`, `Copywriter`, `Translator`,
  `VoiceSynthesizer`, `LipSyncer`, `MediaProcessor`, and the Jev scoring client.
- Production adapters are Postgres, Celery/Redis, Silo and HMAC webhooks. The existing
  in-memory/local adapters remain for unit tests and local development.
- The API is the product boundary. The frontend owns the Creator UI; this service owns
  JSON contracts, assets and delivery.

### 2. Domain model and vocabulary

Internal names follow `GLOSSARY.md`. The public wire keeps the existing `segments[]` /
`segment_id` aliases so the AGENTS.md schema remains valid; new code and new endpoints use
`Clip` / `clip_id` internally. A Clip's `segment_id` is its wire alias.

Core objects:

- **Job** — one pipeline run. Owns status, stage, source reference, Source Language,
  declared Target Languages, lip-sync flag, model overrides, Job Budget, parent link,
  selection, Review Bundle reference, timestamps and failure.
- **Clip** — a Base Clip. Holds the ordinal, start/end, Hook, social caption, planner
  Rationale, Jev score and four-signal breakdown, Base Clip asset key, caption-free Base Clip
  Master key, Localized Clip references, and the Clip's own spoken source text. It does not
  retain the full Transcript.
- **Base Clip Master** — the caption-free 9:16 render of a Clip. It is internal, retained for
  the Workspace lifetime and the source for both captioned Base Clips and Localized Clips.
- **Source Language** — `{code, origin}` where origin is `declared`, `detected` or
  `fallback`. `detected_code` is retained for audit when it differs from the effective code.
- **Selection** — the confirmed rectangular `segment_ids × languages` set, its expected
  total and confirmation timestamp.
- **Localized Clip** — the dubbed (and optionally lip-synced) video for one Clip × language,
  with translated burned-in captions.
- **Localized Clip Copy** — the translated Hook and social caption for one Clip × language;
  it is separate from the Clip's burned-in captions.
- **Review Bundle** — the logical, Job-addressed manifest of Base Clips, Localized Clips,
  long-form copy and Localized Clip Copy. It excludes caption-free masters and is not a zip
  or a physical archive.
- **Cost Ledger Entry** — append-only record of one paid provider call.
- **Job Event** — append-only lifecycle/audit entry.
- **Notification Outbox Entry** — one signed webhook attempt.
- **Idempotency Record** — stored response for a Workspace-scoped key.
- **Review Token** — opaque, hashed, revocable read-only access to one Job.
- **Voice Profile** — the Creator's ElevenLabs voice ID; no raw samples.
- **Workspace Settings** — allowlist, default models, budgets, concurrency and provider
  availability.
- **Derived Job** — a new Job that reuses a parent's Base Clips.
- **Purge** — a two-step Workspace deletion operation.

Conventions:

- Money is stored as integer micro-USD and exchanged as decimal strings with up to six
  fractional digits. No binary floating point is used for cost.
- Timestamps are RFC 3339 UTC.
- Scores are numbers on a 0–100 scale with two decimals; the underlying Jev signals are
  0–4 expected values with two decimals.
- Public `HH:MM:SS` timestamps remain the wire format for clip boundaries; internal
  calculations use seconds.
- IDs: `job_<12 hex>`, `ws_<12 hex>`, `clip_<job>_<ordinal>` internally; `segment_id` is the
  ordinal on the wire. Review tokens are 256-bit URL-safe random values.
- Each Clip retains its own spoken source text and a caption-free Base Clip Master for the
  lifetime of the Workspace. The text is a short excerpt, not the Transcript; the master is
  internal and is not exposed by the Review Bundle. The full Transcript, Source Recording,
  caption SRTs, intermediate audio and pre-mux renders are pruned after the Retention
  Window. Derived Jobs and later Localization use the retained Clip source text and master,
  and never need to re-transcribe a Base Clip.
- Base Clips carry Source Language burned-in captions. Localized Clips carry translated
  burned-in captions synchronized to the localized audio; the localized Hook/caption social
  copy is separate.

### 3. Lifecycle and state machine

Public statuses:

```
RECEIVED
PROCESSING
AWAITING_SELECTION
COMPLETED
FAILED
EXPIRED
CANCELLED
```

Stages:

```
ingest -> intelligence -> scoring -> video -> (Selection Gate) -> localization -> delivery
```

`stage` is `null` while a Job is `RECEIVED`, `AWAITING_SELECTION`, `COMPLETED`, `EXPIRED`,
`CANCELLED`, or while no stage is actively running. `FAILED` retains the stage at which it
failed.

Transitions:

- `RECEIVED -> PROCESSING` when a worker claims the Job and reserves a concurrency slot.
- `PROCESSING` runs `ingest`, `intelligence` (transcription + planning + copy), `scoring`
  (Jev) and `video` (Base Clips). It then becomes `AWAITING_SELECTION`; the concurrency slot
  is released.
- `AWAITING_SELECTION -> PROCESSING` when the Creator confirms a selection. The Job resumes
  at `localization` (or `delivery` for an empty selection) and re-acquires a slot.
- `AWAITING_SELECTION -> EXPIRED` when the seven-day gate lapses. No localization paid call
  is made.
- `PROCESSING -> COMPLETED` after the Review Bundle is frozen and the `bundle_ready`
  notification is durably queued.
- `PROCESSING -> FAILED` after automatic retry exhaustion, or immediately for a
  non-retryable failure.
- `FAILED -> PROCESSING` on an explicit retry, from the last committed stage.
- `RECEIVED`, `PROCESSING` or `AWAITING_SELECTION -> CANCELLED` on cancellation.
- `COMPLETED`, `EXPIRED` and `CANCELLED` are terminal. `FAILED` is terminal until an
  explicit retry reopens it.

Jobs are checkpointed after every stage. Artifact keys are idempotent per Job and stage: a
retry or crash recovery reuses already-uploaded artifacts and skips committed stages.
Localization checkpoints per Clip × language so a crash does not necessarily repeat all
paid calls. The Cost Ledger records every call that did occur, including calls that were
in flight when a Job was cancelled.

### 4. Submission and ingestion

A Job is submitted with:

```json
{
  "source": {"type": "url", "url": "https://example.com/raw.mp4"},
  "source_language": "en",
  "target_languages": ["es", "de"],
  "lip_sync": false,
  "model_overrides": {
    "planning": "openrouter/...",
    "copy": "openrouter/...",
    "translation": "openrouter/..."
  }
}
```

- `source` is a discriminated union: `url` or `object`. `object` carries a Silo key under
  the Workspace's `uploads/` prefix, normally the key returned by a completed Source Upload.
  Submitting an `object` key marks the Source Upload as attached to the Job.
- `source_language` is optional. A declared value wins over detection and is recorded as
  `declared`. Without it, the effective language is `detected` or, only when detection is
  inconclusive, `fallback` English.
- `target_languages` must be non-empty, unique, within the Workspace allowlist and within
  the configured maximum. Canonical BCP-47 casing is preserved (`pt-BR`).
- A Target Language whose primary subtag matches the effective Source Language is rejected;
  dubbing a language to itself is not a Job.
- `lip_sync` defaults to `false`. It is per Job and only accepted when the configured
  lip-sync provider is available.
- `model_overrides` is a partial map of `planning`, `copy`, `translation` to curated model
  IDs. Unknown tasks or models are rejected. Jev's model is pinned and not overridable.
- The Job Budget is snapshotted from Workspace Settings at submission. Existing Jobs are not
  repriced when the Workspace setting changes.
- The Workspace Budget and concurrency are checked at submission and before every paid
  call. A zero-or-negative remaining monthly budget rejects the submission; a full
  concurrency limit does not reject it, it queues it.

Ingestion accepts MP4/MOV/M4V with an audio track, within the configured duration and size
limits. Remote fetches are SSRF-protected: HTTP(S) only, DNS re-resolution and private /
loopback / link-local / metadata address rejection, no unsafe redirects, bounded redirects,
timeouts and a size cap. Object keys are validated for prefix, traversal and existence.
Source Recordings and extracted audio live only for the Retention Window.

Source Uploads (ADR 0022) send bytes straight from the client to the object store as a
presigned S3 multipart upload; the API never streams them, and uploading always finishes
before the Job is submitted.

1. `POST /api/uploads` declares `filename`, `content_type` and `size_bytes`. The API
   rejects an unsupported extension/content type or a size above `max_source_bytes` before
   signing anything, generates the key `uploads/{upload_id}/source.{ext}`, starts the
   multipart upload and returns the `upload_id`, `key` and `part_size_bytes` (32 MiB).
   The client-supplied filename is display metadata only.
2. `GET /api/uploads/{upload_id}/parts?numbers=1,2,3` returns presigned part URLs on
   demand, so a long upload never outlives the presign TTL. Clients PUT parts with bounded
   concurrency (4) and retry failed parts.
3. `POST /api/uploads/{upload_id}/complete` carries each part number and `ETag`. The API
   completes the multipart upload, checks that the assembled object's size equals the
   declared size and stays within `max_source_bytes`, and deletes the object on mismatch.
4. `DELETE /api/uploads/{upload_id}` aborts an in-progress upload and frees its parts.

A presigned URL authorizes exactly one HTTP method on one key (and part). Silo gets this from
SigV4; the local object store signs method, key, part number and expiry in its HMAC and
serves signed part PUTs itself, so the same client code works against both backends. Silo
CORS allows `PUT` from the configured frontend origins and exposes `ETag`. Silo aborts
incomplete multipart uploads after 24 hours. It rejects the S3 lifecycle rule for this, so the
deployment sets its stale-upload expiry and checks it at startup. Upload sessions are not resumable
across page reloads in v1.

The same submission shape is accepted by the inbound webhook endpoint. Webhooks authenticate
with the Workspace webhook secret and are idempotent on the provider event ID. Provider-native
webhook signature verification is not in v1.

### 5. Intelligence, scoring and Base Clips

- Whisper produces a word-level Transcript with timestamps. The declared Source Language is
  passed as a language hint when present; otherwise detection is used. The Transcript is an
  intermediate and is pruned after the Retention Window.
- The planner (OpenRouter, per-Job planning override or default) selects 3–5 Clip
  Candidates. Each candidate has a start/end, Hook, social caption and planner-written
  Rationale. The Rationale is stored and shown with the scores; it does not require another
  LLM call.
- Jev scores each candidate with one Decisions API request. Four `score` questions use
  0–4 scales: hook strength, standalone clarity, emotional payoff, and business/CTA fit.
  The expected value of each distribution is computed; the four expected values are
  equally weighted, averaged, and multiplied by 25 to produce the 0–100 score.
- The Quality Floor defaults to 70. Candidates at or above the floor are retained; if more
  than five clear it, the top five by score are retained. If fewer than three clear it, the
  Job fails with `quality_floor_not_met` before rendering. No silent lowering of the floor.
- Jev's model version is pinned in configuration. Jev calls are paid calls and appear in
  the Cost Ledger.
- The planner and Jev run before any video render. The copywriter generates the long-form
  LinkedIn breakdown and newsletter in the Source Language, plus the per-Clip Hook and
  social caption. Localized Clip Copy is generated later only for the selected languages.
- Each Clip is first rendered as a caption-free 9:16 Base Clip Master. The Base Clip review
  asset is then rendered from that master with styled, word-timed Source Language captions.
  v1 uses deterministic center crop; AI subject tracking is out of scope.
- The Base Clip Master and captioned Base Clip are uploaded to Silo and registered against
  the Job. Their artifact keys use the Source Language code, not a hard-coded `en`. The
  master is internal and is not listed in the Review Bundle.
- After all Base Clips and masters are available, the Job creates a review token, computes
  the selection cost matrix, enters `AWAITING_SELECTION`, and queues the
  `selection_required` notification. The concurrency slot is released.

### 6. Selection Gate

The gate lasts seven days from Base Clip readiness. It can end in three ways:

1. **Confirmed** — the Creator selects a rectangular subset and confirms the projected
   total.
2. **Expired** — no confirmation before `expires_at`; status `EXPIRED`, no localization
   spend, Base Clips retained, `selection_expired` notified.
3. **Cancelled** — status `CANCELLED`, no final notification.

The selection payload exposes every Base Clip with its score, breakdown, Rationale and Base
Clip asset URL, plus the declared Target Languages and a cost matrix for every Clip ×
Language. The full matrix total is the maximum possible localization spend. If lip-sync is
enabled, each cell includes the lip-sync cost.

The selection request carries `segment_ids`, `languages` and `expected_total_usd`. The
server re-prices the requested rectangle using the active rate card, model choices and
lip-sync flag. If the total differs from the expected total, it returns `409` with the new
matrix and total; the Creator must confirm the new amount explicitly. If the rectangle is
valid and the total matches, the Job stores the Selection, enters `PROCESSING` and starts
localization (or delivery, for an empty selection).

Selection rules:

- `languages` must be a subset of the Job's declared Target Languages. The Creator may
  narrow, never widen.
- `segment_ids` must be a subset of the Job's Base Clips.
- The selection is rectangular: every selected Clip is localized into every selected
  language. There is no per-cell selection.
- An empty selection (`segment_ids: []`, `languages: []`, expected total `0`) is valid. The
  Job skips localization, proceeds to delivery, and completes with Base Clips only.
- A non-empty selection requires both a non-empty Clip set and a non-empty language set.
- Confirmation is transactional. If expiry and confirmation race, the first transaction to
  commit wins; a confirmation after `expires_at` returns `410`.
- Replaying the same idempotency key returns the original result. A different selection
  after confirmation returns `409 selection_already_confirmed`.
- No localization paid call is made until confirmation commits.

### 7. Localization

Localization is scoped to the confirmed selection only. For each selected Clip × Language:

1. Read the Clip's retained spoken source text. It is part of the Base Clip metadata, so a
   late gate confirmation, a delayed retry or a Derived Job does not depend on the pruned
   Transcript.
2. Translate the source text for synthesized speech and for the burned-in captions.
3. Translate the Clip's Hook and social caption into Localized Clip Copy.
4. Synthesize the localized voice with the Workspace Voice Profile and obtain character or
   word alignment from the speech provider.
5. If lip-sync is enabled, run Sync Labs on the caption-free Base Clip Master plus the
   localized audio. Otherwise mux the localized audio onto the caption-free master. A
   lip-sync failure fails the cell; the non-lip-synced render is not exposed as a Localized
   Clip and is pruned.
6. Render the translated captions onto the lip-synced or caption-free video using the
   provider alignment. Captions are burned in after lip-sync, never before, so Sync Labs
   cannot distort them. The Localized Clip has target-language speech and target-language
   burned-in captions.

Long-form LinkedIn and newsletter copy stay in the Source Language. Only the per-Clip Hook
and social caption are localized in v1.

A missing Voice Profile fails the Job with `voice_profile_missing` before TTS. A requested
lip-sync that cannot run fails the Job with `lip_sync_unavailable` or a provider failure.
If caption alignment is unavailable, the cell fails with `caption_alignment_unavailable`;
guessed or proportional timings are not shipped. There is no silent fallback.

The localized Hook and social caption are separate social copy, not the burned-in captions.

Localized assets and copy are uploaded/recorded per Clip × Language. A later retry reuses
completed cells and only re-runs missing cells.

### 8. Delivery and review access

- Delivery assembles the Review Bundle manifest from the Base Clips, the confirmed
  Localized Clips, long-form copy and Localized Clip Copy. It excludes the Source Recording,
  Transcript, caption-free masters and working intermediates.
- Copy is available in the manifest and as downloadable Markdown files.
- `COMPLETED` freezes the bundle. Artifact keys and manifest content do not change in place.
  A correction is a Derived Job with new keys.
- The `bundle_ready` notification is queued after the bundle is frozen. `COMPLETED` means
  review-ready, never approved or published.
- A review token is created when the first reviewable asset exists. The stable review URL is
  app-owned and never expires automatically; it is rotatable and revocable. The token is
  stored hashed and grants read-only access to one Job.
- Asset URLs in the manifest are stable app URLs. Requesting one redirects (HTTP 302) to a
  short-lived presigned Silo URL. The raw presigned URL is never persisted or sent in the
  manifest. Changing or revoking the token invalidates the stable URL; outstanding
  presigned URLs remain valid only for their short TTL.
- The review manifest includes the Job status and every available asset, even if the Job is
  `FAILED`, `EXPIRED` or `CANCELLED`. It does not expose cost, Transcript or intermediate
  files.
- API-key consumers use an equivalent stable Job asset URL that also redirects to a
  presigned URL.
- `POST` rotates the review link and invalidates the old token; `DELETE` revokes it. Both are
  idempotent mutations.

### 9. Cost, budgets and concurrency

- A versioned USD rate card covers every paid provider/model/unit: Whisper, Jev, OpenRouter
  planning/copy/translation, ElevenLabs and Sync Labs. The active rate card version is
  recorded on ledger entries. A missing required rate fails closed before the call.
- A 20% safety margin is applied to provider rates. The ledger records the base rate, the
  margin and the charged estimate.
- Estimated cost is appended before a paid call; actual provider-reported cost is recorded
  after the call when available. A call that was in flight when a Job was cancelled is still
  recorded.
- The Job Budget defaults to $50 and is snapshotted at submission. The Workspace Budget
  defaults to $500 per calendar month (UTC). The concurrency limit defaults to 2 Jobs in
  `PROCESSING`.
- Before every paid call, the service checks the Job's ledger spend plus the projected call
  against the Job Budget and the Workspace's calendar-month spend plus the projected call
  against the Workspace Budget. It also fails closed if the rate is missing.
- A Job Budget breach fails the Job with `insufficient_job_budget`; it is not retryable.
- A Workspace Budget breach fails the Job with `workspace_budget_exceeded`; it becomes
  retryable only after the cap is raised or the calendar month rolls over.
- A full concurrency limit queues the Job in `RECEIVED`; it does not fail it. A worker
  reserves a slot before `PROCESSING` and releases it on entering `AWAITING_SELECTION` or a
  terminal state. Slot leases expire if the worker crashes.
- The Selection Gate's projected localization cost uses the same rate card and margin. It
  uses the Clip's source character count for translation and voice projection; the 20%
  margin covers language expansion. Actual provider usage is reconciled in the ledger.
- Raising a cap is an Operator action and is audited. The budgets are guardrails, not a
  billing system.

### 10. Access, idempotency and notifications

- All mutating/admin endpoints require `Authorization: Bearer <WORKSPACE_API_KEY>`. The key
  is configured at deployment, compared in constant time, and rotated by replacing the
  deployment secret and restarting. There is no v1 key-management endpoint.
- Review endpoints require only the review token in the URL and are read-only.
- POST and DELETE require `Idempotency-Key`. The key is scoped to the Workspace and retained
  for seven days. The stored record includes method, path, request hash, response status and
  response body.
  - Same key + same request returns the stored response.
  - Same key + different request returns `409 idempotency_key_reuse`.
  - A concurrent duplicate returns `409 idempotency_in_progress`.
  - PUT is naturally idempotent and does not require a key.
  - Webhook ingestion uses the provider event ID as the idempotency key.
- Notifications are signed HMAC-SHA256 webhooks. The payload contains a stable `event_id`,
  `type`, `job_id`, `occurred_at` and event-specific data. Headers carry the event ID,
  timestamp and signature over `timestamp + "." + raw_body`.
- Events are `selection_required`, `bundle_ready` and `selection_expired`. There is no
  cancellation or failure notification.
- Delivery is at-most-once. The outbox makes one delivery attempt per event; an ambiguous or
  failed attempt is recorded and not retried. Receivers should dedupe on `event_id` if they
  need stronger semantics. The Creator can always poll the Job.
- Job Events are append-only and cover receipt, stage start/end, scoring, gate open,
  selection, expiry, localization, bundle readiness, failure, cancellation, retry and
  derived-job creation. They never contain provider secrets, full Transcripts or raw media.

### 11. Cancellation, retry and Derived Jobs

- Cancellation sets a durable cancel flag and, when no stage is in flight, transitions the
  Job to `CANCELLED`. The worker checks the flag between stages and before each paid call.
  In-flight calls may still bill. Completed Base Clips remain available. Incomplete
  localized artifacts are pruned. No final notification is sent. A review link, if present,
  remains read-only and shows available assets.
- A Job can be cancelled while `RECEIVED`, `PROCESSING` or `AWAITING_SELECTION`. A terminal
  Job returns `409 invalid_state`.
- Retry is explicit, only for `FAILED`. It resumes from the last committed stage under the
  same Job ID, Job Budget and Workspace Budget. Automatic retries are only for transient
  provider failures (timeouts, 429, 5xx) with bounded backoff and jitter.
- Non-retryable failures: validation, source/target conflict, Quality Floor and per-Job
  budget. A missing Voice Profile or unavailable lip-sync fails immediately but is retryable
  once the configuration is fixed; it does not consume automatic retries. A Workspace Budget
  failure becomes retryable after the cap or month changes.
- A Derived Job is created from a parent whose Base Clips are retained: `COMPLETED`,
  `EXPIRED` or `CANCELLED`. A parent with no Base Clips (early failure) is not eligible.
- `copy` mode refreshes the per-Clip Hook and social caption from the retained Clip source
  text. It carries forward the parent's LinkedIn and newsletter copy unchanged; fresh
  long-form copy requires a fresh Job from the Source Recording. The child bundle records
  `copy_origin` for each copy asset: `generated` for the refreshed per-Clip copy and `parent`
  for the carried-forward long-form copy. It skips the Selection Gate and commits no
  localization spend.
- `localization` mode re-enters the Selection Gate with the parent's Base Clips and the
  requested Target Languages. It localizes only the new selection and produces a new Review
  Bundle. It uses the retained Clip source text and does not depend on the parent Transcript.
- Different Base Clips require a fresh Job from the Source Recording.
- The original Review Bundle is untouched. The Derived Job has its own Job ID, cost ledger,
  events, review token and artifact keys.

### 12. Retention, purge and deployment

- Delivered Review Bundle assets live for the Workspace lifetime. Each Base Clip also
  retains its spoken source text and a caption-free Base Clip Master for the Workspace
  lifetime. The Source Recording, full Transcript, caption SRTs, intermediate audio and
  pre-mux renders are pruned after seven days. Expired and cancelled Jobs keep their Base
  Clips, source text and masters under the same rule.
- Completed Source Uploads never attached to a Job are deleted by the retention sweep after
  the Retention Window; attached ones expire with their Source Recording.
- The retention sweeper is idempotent. A Workspace Purge removes delivered assets
  immediately; backups age out under the separate 30-day backup policy.
- A Workspace Purge is two-step:
  1. A dry-run reports Jobs, Base/Localized assets including masters, copy files, review
     tokens, cost entries, events and bytes, and returns a short-lived, single-use
     confirmation token bound to the Workspace.
  2. Confirmation carries the Workspace ID and token. The Workspace is locked against new
     submissions, active Jobs must be cancelled first, and the purge deletes all Jobs,
     assets, review tokens, cost entries, events and idempotency records. Workspace Settings,
     the API key and the Voice Profile remain; rotate the API key after a purge if desired.
- Backups are not deleted immediately; they are retained for 30 days. A purge is
  irreversible.
- Deployment is the all-in-one Docker Compose stack: Caddy, API, worker, Postgres, Redis,
  Silo and backup. Caddy is public TLS ingress; Silo's S3 endpoint is a public hostname so
  presigned URLs work; the Silo console stays private. Host volumes for Postgres, Redis,
  Silo and the backup target are encrypted at rest (LUKS or provider-managed disk
  encryption). Application-level envelope encryption/KMS is a later hardening step.
- The backup service runs nightly: a Postgres logical dump plus `mcli mirror` of the Silo
  bucket to an operator-provided off-host target, with 30-day retention. RPO is 24 hours.
  The restore drill is part of deployment acceptance.
- Secrets are injected through environment/Docker secrets, never committed. Migrations run
  at deploy. Liveness and readiness endpoints cover the API, database, Redis and Silo.
- Structured JSON logs, Cost Ledger and Job Events are the v1 observability surface. Metrics,
  tracing and alerting are out of scope.

### 13. API contracts

All paths are under `/api`. JSON bodies use UTF-8. Errors use:

```json
{
  "detail": {
    "code": "selection_price_changed",
    "message": "The projected total changed.",
    "details": {"current_total_usd": "2.80"}
  }
}
```

Authentication is `Authorization: Bearer <WORKSPACE_API_KEY>` except for review endpoints.
`Idempotency-Key` is required on POST/DELETE. Pagination uses `limit` (1–100, default 50) and
an opaque `cursor`; responses carry `next_cursor` or `null`.

#### Endpoint summary

| Method | Path | Auth | Idempotency | Purpose |
| --- | --- | --- | --- | --- |
| POST | `/api/jobs` | API key | required | Submit a Job |
| POST | `/api/uploads` | API key | required | Start a Source Upload |
| GET | `/api/uploads/{upload_id}/parts` | API key | — | Presigned part URLs |
| POST | `/api/uploads/{upload_id}/complete` | API key | required | Complete a Source Upload |
| DELETE | `/api/uploads/{upload_id}` | API key | required | Abort a Source Upload |
| GET | `/api/jobs` | API key | — | List Jobs |
| GET | `/api/jobs/{job_id}` | API key | — | Job status and clip view |
| GET | `/api/jobs/{job_id}/bundle` | API key | — | Review Bundle manifest |
| GET | `/api/jobs/{job_id}/events` | API key | — | Job Event timeline |
| GET | `/api/jobs/{job_id}/cost` | API key | — | Cost Ledger entries and totals |
| GET | `/api/jobs/{job_id}/selection` | API key | — | Selection Gate payload |
| POST | `/api/jobs/{job_id}/selection` | API key | required | Confirm selection |
| POST | `/api/jobs/{job_id}/cancel` | API key | required | Cancel |
| POST | `/api/jobs/{job_id}/retry` | API key | required | Retry from checkpoint |
| POST | `/api/jobs/{job_id}/derive` | API key | required | Create a Derived Job |
| POST | `/api/jobs/{job_id}/review-link` | API key | required | Rotate/issue review link |
| DELETE | `/api/jobs/{job_id}/review-link` | API key | required | Revoke review link |
| GET | `/api/jobs/{job_id}/assets/{asset_id}` | API key | — | 302 to presigned asset |
| GET | `/api/review/{token}` | review token | — | Read-only review manifest |
| GET | `/api/review/{token}/assets/{asset_id}` | review token | — | 302 to presigned asset |
| GET | `/api/workspace` | API key | — | Workspace Settings |
| PUT | `/api/workspace` | API key | — (safe) | Replace Workspace Settings |
| GET | `/api/workspace/voice-profile` | API key | — | Read Voice Profile |
| PUT | `/api/workspace/voice-profile` | API key | — (safe) | Set Voice Profile |
| DELETE | `/api/workspace/voice-profile` | API key | required | Remove Voice Profile |
| POST | `/api/workspace/purge/dry-run` | API key | required | Purge preview |
| POST | `/api/workspace/purge` | API key | required | Confirm purge |
| GET | `/api/workspace/purge/{purge_id}` | API key | — | Purge status |
| POST | `/api/webhooks/{source}` | webhook secret | required | Trigger a Job |
| GET | `/healthz` | none | — | Liveness |
| GET | `/readyz` | none | — | Readiness |

#### Submit a Job

`POST /api/jobs` → `202 Accepted`

```json
{
  "source": {"type": "url", "url": "https://example.com/raw.mp4"},
  "source_language": "en",
  "target_languages": ["es", "de"],
  "lip_sync": false,
  "model_overrides": {"translation": "openrouter/..."}
}
```

Response:

```json
{
  "job_id": "job_0123456789ab",
  "status": "RECEIVED",
  "created_at": "2026-10-27T12:00:00Z"
}
```

The response also carries `Location: /api/jobs/{job_id}`. `source_language` may be omitted.
`source` may be `{"type": "object", "key": "uploads/upl_0123456789ab/source.mp4"}`. The API returns `422` for
invalid shapes, unsupported languages/models, source/target conflicts and unsafe sources;
`409` for idempotency conflicts; `401` for a missing/invalid key.

#### Source Uploads

`POST /api/uploads` → `201 Created`

```json
{"filename": "keynote.mp4", "content_type": "video/mp4", "size_bytes": 734003200}
```

```json
{
  "upload_id": "upl_0123456789ab",
  "key": "uploads/upl_0123456789ab/source.mp4",
  "part_size_bytes": 33554432,
  "part_count": 22,
  "status": "UPLOADING"
}
```

`422` with `unsupported_media_format` or `source_too_large`.

`GET /api/uploads/{upload_id}/parts?numbers=1,2` → `200 OK`
`{"parts": [{"part_number": 1, "url": "https://..."}], "expires_at": "..."}`. `409`
`upload_not_in_progress` once completed or aborted.

`POST /api/uploads/{upload_id}/complete` → `200 OK`

```json
{"parts": [{"part_number": 1, "etag": "\"9b2c...\""}]}
```

Returns `{"upload_id", "key", "size_bytes", "status": "COMPLETED"}`. `422`
`upload_size_mismatch` (object deleted) or `upload_parts_invalid`; `409`
`upload_not_in_progress`.

`DELETE /api/uploads/{upload_id}` → `204 No Content`; aborting an already aborted upload is
a no-op, a completed one returns `409 upload_not_in_progress`.

#### Read a Job

`GET /api/jobs/{job_id}` → `200 OK`

```json
{
  "job_id": "job_0123456789ab",
  "status": "AWAITING_SELECTION",
  "stage": null,
  "source": {"type": "url", "url": "https://example.com/raw.mp4"},
  "source_language": {"code": "en", "origin": "detected", "detected_code": "en"},
  "target_languages": ["es", "de"],
  "lip_sync": false,
  "parent_job_id": null,
  "derived_mode": null,
  "created_at": "2026-10-27T12:00:00Z",
  "updated_at": "2026-10-27T12:10:00Z",
  "expires_at": "2026-11-03T12:10:00Z",
  "review_url": "https://api.example.com/api/review/tok_...",
  "segments": [
    {
      "segment_id": 1,
      "start_time": "00:02:14",
      "end_time": "00:03:05",
      "hook_title": "Why 90% of B2B SaaS Ads Fail",
      "caption": "Stop wasting budget on broad audiences...",
      "selection_score": 82.40,
      "score_breakdown": {
        "hook_strength": 3.60,
        "standalone_clarity": 3.20,
        "emotional_payoff": 3.00,
        "business_fit": 3.40
      },
      "rationale": "The contrarian hook lands in the first line and the clip stands alone.",
      "video_asset_url": "https://api.example.com/api/jobs/job_0123456789ab/assets/base_1",
      "localized_assets": {},
      "localized_copy": {}
    }
  ],
  "content": {
    "linkedin_post": "# LinkedIn breakdown...",
    "newsletter": "# Newsletter draft..."
  },
  "copy_origin": {
    "clips": "generated",
    "linkedin": "generated",
    "newsletter": "generated"
  },
  "selection": null,
  "cost": {
    "job_budget_usd": "50.00",
    "spent_usd": "1.23",
    "workspace_remaining_usd": "498.77",
    "projected_localization_usd": null
  },
  "error": null
}
```

`segments` is the wire alias for Clips. The `localized_assets` and `localized_copy` maps are
empty until localization runs. `content` is Source Language copy. `copy_origin` is
`generated` for copy produced by this Job or `parent` for long-form copy carried forward from
a copy-only Derived Job. `selection`, when present, is
`{segment_ids, languages, expected_total_usd, confirmed_at}`. `review_url` is present when a
review token exists. `expires_at` is present only at the gate. `error` is
`{code, message, retryable}` on `FAILED`.

#### Job list, bundle, events and cost

- `GET /api/jobs?status=&limit=&cursor=` returns
  `{"items": [JobSummary], "next_cursor": null}`. A summary has `job_id`, `status`, `stage`,
  `created_at`, `expires_at`, `review_url`.
- `GET /api/jobs/{job_id}/bundle` returns the same Review Bundle manifest exposed by the
  review link, but with API-key asset URLs. It includes the current partial bundle when the
  Job is not `COMPLETED`; on `COMPLETED` it is the frozen manifest.
- `GET /api/jobs/{job_id}/events?limit=&cursor=` returns
  `{"items": [{"event_id","type","stage","payload","created_at"}], "next_cursor": null}`.
- `GET /api/jobs/{job_id}/cost` returns
  `{"job_budget_usd","spent_usd","entries":[{"stage","provider","model","units","unit_type","rate_usd","estimated_usd","actual_usd","created_at"}]}`.

#### Selection Gate

`GET /api/jobs/{job_id}/selection` → `200 OK` while `AWAITING_SELECTION`; `409 invalid_state`
otherwise; `410 selection_expired` after expiry.

```json
{
  "job_id": "job_0123456789ab",
  "status": "AWAITING_SELECTION",
  "expires_at": "2026-11-03T12:10:00Z",
  "source_language": {"code": "en", "origin": "detected", "detected_code": "en"},
  "target_languages": ["es", "de"],
  "lip_sync": false,
  "segments": [
    {
      "segment_id": 1,
      "start_time": "00:02:14",
      "end_time": "00:03:05",
      "hook_title": "Why 90% of B2B SaaS Ads Fail",
      "caption": "Stop wasting budget on broad audiences...",
      "selection_score": 82.40,
      "score_breakdown": {
        "hook_strength": 3.60,
        "standalone_clarity": 3.20,
        "emotional_payoff": 3.00,
        "business_fit": 3.40
      },
      "rationale": "The contrarian hook lands in the first line and the clip stands alone.",
      "base_asset_url": "https://api.example.com/api/jobs/job_0123456789ab/assets/base_1"
    }
  ],
  "cost_matrix": [
    {"segment_id": 1, "language": "es", "translation_usd": "0.12", "voice_usd": "0.34", "lip_sync_usd": "0.00", "total_usd": "0.46"},
    {"segment_id": 1, "language": "de", "translation_usd": "0.12", "voice_usd": "0.34", "lip_sync_usd": "0.00", "total_usd": "0.46"}
  ],
  "projected_total_usd": "2.76"
}
```

`POST /api/jobs/{job_id}/selection` → `202 Accepted`

```json
{"segment_ids": [1, 2], "languages": ["es"], "expected_total_usd": "0.92"}
```

Success returns the Job snapshot with `status: "PROCESSING"`, `stage: "localization"` and
the stored `selection`. An empty selection is `{"segment_ids": [], "languages": [],
"expected_total_usd": "0.00"}` and proceeds to `delivery`.

Conflict cases:

- `409 selection_price_changed` with the new matrix/total.
- `409 selection_already_confirmed` for a different selection after confirmation.
- `409 invalid_state` outside the gate.
- `410 selection_expired` after `expires_at`.
- `422 invalid_selection` for unknown IDs, non-subset languages, or a non-rectangular set.

#### Cancel, retry and derive

- `POST /api/jobs/{job_id}/cancel` → `202` with the Job snapshot; `409 invalid_state` for a
  terminal Job.
- `POST /api/jobs/{job_id}/retry` → `202` with the Job snapshot; `409 not_retryable` when
  the failure is not retryable or the Job is not `FAILED`.
- `POST /api/jobs/{job_id}/derive` → `202` with the new Job:

```json
{
  "mode": "localization",
  "target_languages": ["fr"],
  "lip_sync": false,
  "model_overrides": {"translation": "openrouter/..."}
}
```

`mode` is `copy` or `localization`. `target_languages` is required for `localization` and
ignored for `copy`. The parent must be `COMPLETED`, `EXPIRED` or `CANCELLED` and have Base
Clips; otherwise `409 parent_not_eligible`. The child inherits the parent's Source Language
and Base Clips. A localization child enters `AWAITING_SELECTION`; a copy child skips the
gate.

#### Review links and assets

- `POST /api/jobs/{job_id}/review-link` → `200`:
  `{"review_url": "https://api.example.com/api/review/tok_...", "rotated_at": "..."}`.
  Rotating invalidates the previous token. A Job with no reviewable asset returns `409
  no_reviewable_assets`.
- `DELETE /api/jobs/{job_id}/review-link` → `204`.
- `GET /api/review/{token}` → `200` with the Review Bundle manifest. It returns `404` for an
  unknown or revoked token.
- `GET /api/review/{token}/assets/{asset_id}` → `302` with `Location` set to a short-lived
  presigned Silo URL. `404` for an unknown token/asset or a purged Job.
- `GET /api/jobs/{job_id}/assets/{asset_id}` → the same redirect for API-key consumers.

Manifest shape:

```json
{
  "job_id": "job_0123456789ab",
  "status": "COMPLETED",
  "created_at": "2026-10-27T12:00:00Z",
  "source_language": {"code": "en", "origin": "detected", "detected_code": "en"},
  "target_languages": ["es"],
  "lip_sync": false,
  "segments": [
    {
      "segment_id": 1,
      "hook_title": "Why 90% of B2B SaaS Ads Fail",
      "caption": "Stop wasting budget on broad audiences...",
      "video_asset_url": "https://api.example.com/api/review/tok_.../assets/base_1",
      "localized_assets": {"es": "https://api.example.com/api/review/tok_.../assets/clip_1_es"},
      "localized_copy": {
        "es": {
          "hook_title": "Por qué fallan el 90% de los anuncios B2B SaaS",
          "caption": "Deja de gastar presupuesto en audiencias amplias..."
        }
      }
    }
  ],
  "content": {
    "linkedin_post": "# LinkedIn breakdown...",
    "newsletter": "# Newsletter draft..."
  },
  "copy_origin": {
    "clips": "generated",
    "linkedin": "generated",
    "newsletter": "generated"
  }
}
```

For a copy-only Derived Job, `copy_origin` is `{"clips": "generated", "linkedin":
"parent", "newsletter": "parent"}`. The long-form copy is byte-for-byte the parent's copy and
is not presented as newly generated.

The manifest excludes Source Recording, Transcript, cost and intermediates. It includes
whatever assets exist for a partial Job and reports the Job's status.

#### Workspace settings and Voice Profile

`GET /api/workspace` → `200`:

```json
{
  "workspace_id": "ws_0123456789ab",
  "target_language_allowlist": ["en", "es", "de", "pt-BR", "fr", "it"],
  "default_models": {"planning": "openrouter/...", "copy": "openrouter/...", "translation": "openrouter/..."},
  "job_budget_usd": "50.00",
  "monthly_budget_usd": "500.00",
  "max_concurrent_jobs": 2,
  "max_video_minutes": 90.0,
  "current_month_spend_usd": "12.34",
  "remaining_usd": "487.66",
  "voice_profile": {"provider": "elevenlabs", "voice_id": "...", "updated_at": "..."}
}
```

`PUT /api/workspace` replaces the mutable settings document (same fields except
`workspace_id`, `max_video_minutes`, `current_month_spend_usd`, `remaining_usd` and
`voice_profile`). `max_video_minutes` is the deployment's input length limit, read-only here. It validates
the allowlist against the configured providers, budgets against positive bounds and
concurrency against the worker capacity. Changes are audited. `PUT` is safe/idempotent and
does not require an idempotency key.

`GET|PUT|DELETE /api/workspace/voice-profile` manages the single ElevenLabs voice ID.
`PUT` validates the voice with the provider and stores no raw samples. A Job without a
profile fails at localization. `DELETE` requires an idempotency key.

#### Purge

- `POST /api/workspace/purge/dry-run` → `200`:
  `{"jobs": 12, "base_clips": 48, "localized_clips": 20, "copy_files": 24,
  "review_tokens": 12, "cost_entries": 300, "events": 500, "bytes": 123456789,
  "confirmation_token": "...", "expires_at": "..."}`.
- `POST /api/workspace/purge` with `{"workspace_id": "ws_...", "confirmation_token": "..."}`
  → `202` with `{"purge_id": "purge_...", "status": "RUNNING"}`. `409 active_jobs` if any
  Job is not terminal; `410 purge_confirmation_expired` for a stale token; `409
  workspace_id_mismatch` for the wrong Workspace.
- `GET /api/workspace/purge/{purge_id}` → status and counts. The purge locks new
  submissions, deletes all Job data, assets, review tokens, cost entries, events and
  idempotency records, and leaves Workspace Settings, the API key and the Voice Profile.
  Review links return `404` afterward. Backups remain for their 30-day policy.

#### Inbound webhooks

`POST /api/webhooks/{source}` with `X-Webhook-Secret` and an `Idempotency-Key` (provider event
ID). The body matches the Job submission shape. A duplicate event returns the original Job
accepted response. The shared secret is v1's only inbound webhook authentication.

### 14. Data model

Postgres schema, expressed as tables and constraints rather than file paths:

- `workspace_settings` — `workspace_id` PK, allowlist JSONB, default models JSONB, Job Budget
  micro-USD, monthly budget micro-USD, max concurrent Jobs, created/updated timestamps.
- `workspace_audit` — append-only settings changes: id, workspace_id, actor, action, payload,
  created_at.
- `voice_profiles` — workspace_id PK, provider, voice_id, created/updated timestamps.
- `jobs` — job_id PK, workspace_id, creator_id, status, stage, source kind, URL/object key,
  declared/detected/effective Source Language and origin, Target Languages JSONB,
  lip_sync, model overrides JSONB, parent_job_id, derived_mode, copy_origin JSONB, Job Budget
  micro-USD, expires_at, error code/message, retryable, created/updated timestamps. The
  confirmed selection lives in `selections`; review tokens live in `review_tokens`.
- `clips` — clip_id PK, job_id FK, ordinal, start/end seconds, spoken source text, Hook,
  caption, Rationale, selection score, score breakdown JSONB, Base Clip asset key, Base Clip
  Master key, created_at. Unique `(job_id, ordinal)`.
- `clip_localizations` — clip_id FK, language, localized Hook, localized caption, audio key,
  video key with localized burned-in captions, lip_sync flag, status, created_at. Unique
  `(clip_id, language)`.
- `selections` — job_id PK/FK, segment_ids JSONB, languages JSONB, expected total micro-USD,
  confirmed_at.
- `cost_ledger` — id PK, job_id FK, stage, provider, model, units, unit_type, base rate,
  margin, estimated micro-USD, actual micro-USD, rate-card version, created_at. Append-only.
- `job_events` — id PK, job_id FK, type, stage, payload JSONB, created_at. Append-only.
- `notification_outbox` — id PK, event_id unique, job_id FK, type, payload JSONB, status,
  attempts, last_error, created_at, sent_at.
- `idempotency_keys` — workspace_id + key unique, method, path, request hash, response
  status, response body JSONB, created_at, expires_at.
- `source_uploads` — upload_id PK, workspace_id, key unique, provider multipart upload id,
  original filename, content type, declared size, actual size, status
  (`UPLOADING`/`COMPLETED`/`ABORTED`), job_id FK nullable (set on submission),
  created_at, completed_at.
- `review_tokens` — id PK, job_id FK, token_hash unique, created_at, rotated_at, revoked_at.
- `purges` — purge_id PK, workspace_id, status, counts JSONB, created_at, completed_at,
  error.

Enums: `job_status`, `job_stage`, `source_upload_status`, `source_language_origin`, `derived_mode`,
`notification_status`, `purge_status`. Job Event `type` is a documented string set so it can
grow without a migration.

Indexes cover Jobs by Workspace/status/created_at, Clips by Job/ordinal, cost/events by
Job/created_at, outbox by status/created_at, idempotency by expires_at, and review tokens by
hash. Foreign keys cascade from Jobs on purge; append-only tables have no normal delete path.
The purge is the only bulk deletion path.

### 15. Configuration

Runtime settings are environment-driven and validated at startup:

- Workspace API key; webhook secret; notification webhook URL; public base URL; CORS allowed
  origins.
- Postgres URL; Redis URL; Silo endpoint, bucket, region, access key, secret key; presign
  TTL (default 900 seconds); max source bytes (default 2 GB); upload part size (default
  32 MiB); frontend origins allowed for Silo upload CORS.
- Provider credentials: Whisper/OpenAI, OpenRouter, ElevenLabs, Sync Labs.
- Target allowlist (default `en, es, de, pt-BR, fr, it`), max Target Languages (default 3),
  source language support, and curated model allowlists per task.
- Pinned Jev model version.
- Job Budget (default $50), monthly Workspace Budget (default $500, UTC calendar month), max
  concurrent Jobs (default 2), Quality Floor (default 70), min/max Clips (3/5), max video
  minutes (90), max characters per Job.
- Retention Window (7 days), Selection Gate expiry (7 days), idempotency retention (7 days),
  backup retention (30 days), notification outbox behavior.
- Rate card version and path; cost margin (20%).
- Worker poll/backoff settings; provider timeout and retry-attempt limits.

The Workspace allowlist is validated against the configured TTS and lip-sync providers at
startup and on settings update. In the production composition, missing provider credentials,
missing rate-card entries or an unsupported allowlist entry fail closed at startup rather
than mid-Job. Test/local compositions may use stub providers.

### 16. Testing Decisions

**Highest seam.** The primary test seam is the HTTP API: build the app with
`create_app`/`build_container`, drive it with `TestClient` (or an ASGI client), and assert
status codes, response bodies, Job Events, Cost Ledger entries, notifications and stored
assets. The existing API and pipeline tests are the prior art; they already exercise the
container, queue worker and local object store end to end.

**What makes a good test.** Assert external behavior and state transitions, not private
method calls or agent internals. A test should be able to survive a refactor of the
orchestrator as long as the Job, budget, gate, bundle and notification contracts hold.
Use the domain glossary vocabulary in test names.

**Test layers.**

- **Domain unit tests** — state transition guards, score math (0–4 expected values ×25,
  floor 70, top five), cost math with integer micro-USD, source/target conflict rules,
  selection rectangle validation, idempotency request hashing, HMAC signing, retention
  cutoff.
- **API integration tests** — the full Creator journey through the API seam:
  submit → ingest/transcribe/plan/score/render → gate → select → localize → bundle →
  review. Also cancellation, expiry, retry, derived jobs, review-link rotation/revocation,
  Workspace Purge and settings changes.
- **Adapter contract tests** — Postgres repository, Celery/Redis queue, Silo object store
  and HMAC notifier against the real service or a test container. The same contract suite
  runs against the in-memory adapters where practical, so the test doubles do not drift.
- **Provider contract tests** — Whisper, OpenRouter, Jev, ElevenLabs and Sync Labs against
  recorded fixtures or a local fake. No live paid provider calls in CI. Verify request shape,
  response parsing, error classification and cost/usage extraction.
- **Failure and race tests** — provider 429/5xx/timeout, worker crash and checkpoint resume,
  cancel during a paid call, cancel versus expiry, selection confirmation versus expiry,
  duplicate webhook, duplicate idempotency key, price change between gate and confirmation,
  outbox ambiguous failure at-most-once behavior, missing Voice Profile, lip-sync failure,
  missing caption alignment, budget breach before the next call, and a Derived Job created
  after the Transcript has been pruned (it must use the retained Clip source text without a
  new Whisper call).
- **Caption tests** — a fake renderer records its inputs; assert that the Base Clip is
  rendered with Source Language captions from the master, a Localized Clip uses the master
  and translated captions, lip-sync runs before caption burn-in, and missing alignment fails
  without exposing a fallback asset. Assert the master is absent from the Review Bundle but
  deleted by a purge.
- **Security tests** — missing/invalid API key, review token revocation, asset path traversal,
  SSRF URL rejection, object-key prefix rejection, no secrets in events/manifests, presigned
  URL TTL, a presigned GET cannot be used to PUT (and vice versa), server-generated upload
  keys ignore client-supplied paths.
- **Source Upload tests** — initiate rejects oversize and unsupported files before signing;
  complete rejects and deletes a size mismatch; abort frees the upload; a completed upload
  submits as an `object` Job and is marked attached; an unattached upload is swept after the
  Retention Window while an attached one follows its Job. The multipart methods of the
  object-store port run in the adapter contract suite against both Silo and the local
  store.
- **Deployment tests** — Compose starts with all services healthy; Caddy serves TLS; a
  synthetic Job runs through the API; a review link resolves; a purge removes assets; a
  backup dump restores into a clean database/Silo (restore drill). These are acceptance
  tests, not unit tests.

**Deterministic fixtures.** Inject a clock for expiry, idempotency and budget-month tests.
Use a fake provider bundle with deterministic transcript, candidates, Jev distributions,
translations, voice durations and lip-sync output. Use a temp Silo/local object store and a
fresh Postgres schema per test. Queue tests use an in-memory queue for speed and a Redis
integration test for the real adapter.

**Backward-compatibility tests.** Keep the AGENTS.md wire shape (`segments[]`,
`segment_id`, `localized_assets`, `localized_copy`) covered until that schema is formally
revised. The internal rename to Clip must not break the public alias.

**Existing tests to update.** The skeleton pipeline test currently expects `COMPLETED` after
one `run` call and every language localized. After this spec it must stop at
`AWAITING_SELECTION`, then confirm a selection and finish. The existing `Segment`-oriented
assertions remain valid through the wire alias.

### 17. Out of Scope

- The Creator frontend/UI; this spec defines the API contract it consumes.
- Rights attestation or licensing checks; operators secure rights outside the pipeline
  (ADR 0008).
- Multi-tenant Workspaces, multiple Creators per Workspace, or cross-Workspace access.
- Provider-native inbound webhook signatures; v1 uses a shared secret.
- Application-level envelope encryption or KMS; host-volume encryption plus TLS is the v1
  baseline.
- Soft subtitle tracks, caption sidecars or per-platform caption files; v1 burns captions
  into the video. Localized burned-in captions are in scope for Localized Clips (ADR 0021).
- AI subject tracking/reframing; v1 uses deterministic center crop.
- Localized LinkedIn or newsletter copy; they stay in the Source Language.
- Automatic publishing to social platforms, scheduling or analytics/performance feedback.
- Billing, invoicing, payment collection or provider invoice reconciliation beyond reported
  usage. The Cost Ledger is a guardrail.
- High availability, Kubernetes, Pigsty runtime, multi-region or horizontal worker scaling.
- Real-time progress streaming; clients poll the Job and read Job Events.
- Provider-native rate-limit negotiation beyond bounded backoff and `Retry-After`.
- Migrating pre-existing Jobs/assets from the skeleton; the skeleton is pre-production.
- Model fine-tuning, custom voice training or raw voice-sample storage.
- A Workspace API key management/rotation endpoint; rotation is a deployment action.
- Purging backups immediately; backups follow their 30-day policy.
- A general-purpose workflow builder; Make.com/Zapier remain triggers/notifiers, not state
  owners.

### 18. Further Notes and Delivery Slices

The code is behind the docs. The skeleton has a one-shot orchestrator, `Segment`, in-memory
adapters and an unconditional localization fan-out. This spec is the implementation
catch-up; the first ticket should be a prefactor that introduces the domain vocabulary and
state machine without changing existing public behavior (new response fields may be added).

Proposed tracer-bullet slices, in dependency order. Each slice is intended to be demoable or
verifiable on its own. They are published as GitHub issues in
[c0pper/automated-content-localization-repurposing-pipeline](https://github.com/c0pper/automated-content-localization-repurposing-pipeline/issues).
The issue mapping is: #1 localized-captions decision (A chosen, closed); #2 domain; #3 durable
foundation; #4 reliability/cost; #5 workspace admin; #6 submission; #7 ingest; #8 planning;
#9 Base Clips; #10 Selection Gate; #11 localization; #12 delivery; #13 cancellation/retry;
#14 Derived Jobs; #15 purge/review-link rotation; #16 deployment hardening. The blocking edges
are repeated in each issue body.

1. **Domain vocabulary and lifecycle prefactor** — internal Clip vs wire Segment, new
   statuses/stages, Source Language origin, Selection, Localized Clip, Cost Ledger, Job
   Event, outbox, idempotency, review token, Voice Profile, Workspace Settings and purge
   records. Pure transition guards and score/cost helpers. Tests for transitions and wire
   aliases.
   **Blocked by:** None.
2. **Durable foundation** — Postgres schema/migrations, repository adapter, Celery/Redis
   queue, Silo object store, Compose skeleton with Caddy/Postgres/Redis/Silo, health/
   readiness, adapter contract tests. Replace production composition; keep in-memory
   adapters for tests.
   **Blocked by:** 1.
3. **Reliability and cost core** — append-only Cost Ledger and Job Events, rate card + 20%
   margin, Job and Workspace budget guard, concurrency lease, idempotency store/middleware,
   signed outbox notifier. API error envelope. Tests for budget breaches, replay, HMAC and
   at-most-once outbox.
   **Blocked by:** 2.
4. **Workspace administration** — API-key auth, Workspace Settings resource, allowlist and
   model validation, Voice Profile resource, settings audit, CORS. Tests for auth, settings
   validation and profile lifecycle.
   **Blocked by:** 3.
5. **Submission and intake** — `POST /api/jobs` and webhook intake with URL/object source,
   declared/detected Source Language field, target allowlist, source/target conflict,
   lip-sync availability, model overrides, idempotency, budget-at-submission and queueing.
   The Job is durable in `RECEIVED`.
   **Blocked by:** 4.
6. **Ingest, transcription and Source Language** — SSRF-safe fetch/object validation, probe,
   audio extraction, Whisper adapter, declared/detected/fallback language, checkpoints and
   events. The Job reaches a Transcript and Source Language.
   **Blocked by:** 5.
7. **Planning, Jev and Quality Floor** — OpenRouter planner and copywriter, Jev Decisions API
   per candidate, four 0–4 signals, score math, floor/top-five, rationale, model overrides,
   cost ledger entries, and each candidate's spoken source-text excerpt. The Job either has
   3–5 scored Clip Candidates or fails.
   **Blocked by:** 6.
8. **Base Clips and review link** — render a caption-free 9:16 Base Clip Master per Clip,
   then render the captioned Base Clip from it with Source Language captions. Upload both,
   create the review token, serve the stable review manifest and asset redirects. Masters
   are internal and retained for the Workspace lifetime. The Creator can watch Base Clips.
   **Blocked by:** 7.
9. **Selection Gate and expiry** — cost matrix, `GET/POST selection`, price-change and
   empty-selection behavior, `AWAITING_SELECTION`, seven-day expiry, `selection_required` and
   `selection_expired` notifications. The Creator can make and confirm a selection.
   **Blocked by:** 8.
10. **Localization, copy and lip-sync** — selection-scoped translation, Localized Clip Copy,
    Voice Profile use, ElevenLabs synthesis and alignment, optional Sync Labs replacement,
    translated caption render, per-cell checkpoints, failure semantics. Localized Clips are
    rendered from the caption-free master and captions are burned in after lip-sync. Only the
    confirmed rectangle is localized.
    **Blocked by:** 9.
11. **Delivery, bundle and notifications** — Review Bundle manifest, Markdown copy, freeze on
    `COMPLETED`, `bundle_ready`, review manifest for partial Jobs, immutable artifact keys.
    The Creator receives a complete review payload.
    **Blocked by:** 10.
12. **Cancellation and retry** — cancel endpoint/flag, between-stage checks, cleanup of
    incomplete localized artifacts, explicit retry from checkpoint, retryability matrix,
    no final notification on cancel. Jobs can be stopped and transient failures recovered.
    **Blocked by:** 11.
13. **Derived Jobs** — copy and localization modes, parent eligibility, inherited Base Clips,
    Clip source text and Source Language, copy scope with `copy_origin`, localization gate
    re-entry, new review token/bundle. A Derived Job after the Transcript is pruned must not
    re-transcribe. A copy-only child refreshes per-Clip copy and carries long-form copy
    forward unchanged.
    **Blocked by:** 11.
14. **Workspace Purge and review-link rotation** — dry-run/confirm purge with confirmation
    token, active-Job guard, deletion of Job data/assets/tokens/ledger/events, link rotation
    and revocation. The Workspace can be emptied deliberately.
    **Blocked by:** 11.
15. **Production deployment hardening** — Caddy TLS and public Silo hostname, encrypted host
    volumes and backup target, nightly backup service, 30-day retention, restore drill,
    startup config validation and deployment smoke tests.
    **Blocked by:** 2, 11.

Resolved clarifications:

- Each Base Clip retains its own spoken source text and a caption-free Base Clip Master for
  the Workspace lifetime. Derived Jobs and late localization use both; the full Transcript
  remains pruned after seven days.
- Localized Clips carry translated burned-in captions synchronized to the localized audio.
  Captions are burned in after lip-sync, from the caption-free master. ADR 0021 records the
  decision.
- Inbound webhooks use a shared secret, not provider-native signatures; provider signature
  verification is a hardening follow-up.
- Workspace Settings and Purge confirmation token are accepted API surfaces; the design
  decisions require the behavior, not these exact paths.
- Copy-only Derived Jobs refresh the per-Clip Hook and social caption and carry forward the
  parent's LinkedIn/newsletter copy unchanged. The child bundle marks the origin of each copy
  asset as `generated` or `parent`. Fresh long-form copy requires a fresh Job from the Source
  Recording.

Open clarifications: none.
