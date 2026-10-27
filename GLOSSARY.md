# Automated Content Repurposing & Localization Pipeline

The domain language for turning one long-form recording by a Creator into short-form clips, localized into requested languages and presented as a Review Bundle.

## Language

### Workspace and work

**Workspace**:
The ownership boundary for a Creator's Jobs and assets. One deployment serves one Workspace in v1.
_Avoid_: Tenant, account, organization

**Creator**:
The person whose recording, voice and likeness are being repurposed, and who receives the Review Bundle.
_Avoid_: User, client, talent

**Job**:
A single pipeline run that turns one Source Recording into a Review Bundle for a set of Target Languages. The unit of status, cost and retention.
_Avoid_: Task, run, request

**Derived Job**:
A new Job created from a parent Job whose Base Clips are still retained — `COMPLETED`, `EXPIRED` or `CANCELLED` — when the Creator requests a different Localization selection or regenerated copy. It reuses the parent's Base Clips; changing the Base Clips requires a fresh Job from the Source Recording. The original Review Bundle remains untouched; a Localization Derived Job re-enters the Selection Gate.
_Avoid_: Rerun, clone, retry

### Content

**Source Recording**:
The long-form audio/video supplied for repurposing.
_Avoid_: Input file, raw video, asset

**Source Input**:
The remote URL or pre-uploaded Silo object key that identifies a Source Recording. Direct multipart uploads through the API are not accepted.
_Avoid_: Upload, file, asset URL

**Transcript**:
The timestamped, word-level text of a Source Recording.
_Avoid_: Captions (captions are a rendered artifact derived from the Transcript), subtitles

**Hook**:
The promise or angle that earns attention in the opening seconds, expressed as a title and opening line.
_Avoid_: Headline, topic, title

**Clip Candidate**:
A proposed time window from a Source Recording, with a Hook, a Clip Rationale and a Selection Score, before rendering.
_Avoid_: Segment, moment, highlight

**Clip Rationale**:
A short, planner-written explanation of why a Clip Candidate exists. It accompanies, but does not determine, the Selection Score.
_Avoid_: Reasoning, justification, explanation

**Clip**:
A rendered 9:16 excerpt selected from a Source Recording, identified by a Hook and accompanied by a caption. Clip is the canonical name in prose and code; the public JSON schema calls Clips `segments[]`, which is a wire-format alias, not a separate concept.
_Avoid_: Segment, short, cut, highlight

**Base Clip**:
A Clip in the Source Language, before Localization. It is the asset at `video_asset_url`; localized variants are not Base Clips.
_Avoid_: English Clip, original clip, source clip

**Quality Floor**:
The minimum Selection Score a Clip Candidate must reach to be rendered. A Job yields between three and five Clips and fails if fewer than three clear the floor.
_Avoid_: Threshold, cutoff

**Selection Score**:
A 0–100 score for a Clip Candidate, derived equally from hook strength, standalone clarity, emotional payoff and business/CTA fit. The Quality Floor defaults to 70.
_Avoid_: Rating, rank

**Review Bundle**:
The complete set of review material produced by one Job: every Base Clip, the Localized Clips for the confirmed selection (possibly none), and copy — including Localized Clip Copy for each selected language. It excludes the Source Recording, Transcript and working intermediates, and is not a physical archive. Once the Job completes, the Review Bundle is immutable.
_Avoid_: Delivery payload, output package, export, zip, archive

### Localization

**Source Language**:
The language spoken in the Source Recording. It is detected during the Job unless declared at submission; a declared language wins and is recorded as declared. English is the fallback only when detection is inconclusive and no language was declared.
_Avoid_: Input language

**Target Language**:
A language requested for localization, declared at submission and drawn from the Target Language Allowlist. It must differ from the Source Language; a Job fails if detection finds they are the same. The Creator may narrow the declared set at the Selection Gate but cannot add languages.
_Avoid_: Output language, translation

**Target Language Allowlist**:
The Workspace-configured set of languages a Job may target, defaulting to `en`, `es`, `de`, `pt-BR`, `fr` and `it`. Every Target Language must be on the allowlist and supported by the voice provider; Lip-sync also requires lip-sync provider support.
_Avoid_: Language list, locale set

**Localization**:
Producing speech in a Target Language for a Clip, using a synthesized voice clone and optional lip-sync.
_Avoid_: Translation (that is only the text step), dubbing

**Localized Clip**:
A Clip whose speech has been replaced with a synthesized performance in a Target Language. A subtitled-only variant is not a Localized Clip. When lip-sync is requested, it applies to this asset; Lip-sync does not create a separate variant.
_Avoid_: Dub, translated video

**Localized Clip Copy**:
The Hook and social caption for a Clip in a Target Language. It ships with the Localized Clip; LinkedIn and newsletter copy remain in the Source Language in v1.
_Avoid_: Caption, translation, localized copy

**Lip-sync**:
Optional alignment of on-screen mouth movement to a Localized Clip's audio. It is a quality treatment of a Localized Clip, not a separate asset. It is available only for Target Languages the lip-sync provider supports; requesting it for an unsupported language fails the Job.
_Avoid_: Face swap, avatar

**Voice Profile**:
A reusable provider-side voice clone belonging to a Creator, registered as a Workspace resource and referenced by ID across Jobs. The pipeline stores the provider ID, not raw voice samples, and fails if no profile is registered. One Voice Profile is used per Creator in v1.
_Avoid_: Voice model, speaker, sample

### Lifecycle and cost

**Selection Gate**:
The point after Base Clips are rendered where the Creator chooses which Clips and which already-declared Target Languages proceed to Localization. Selection is rectangular (one Clip set × one language set), may be empty, may only narrow Target Languages, and requires confirmation of a Projected Localization Cost. It is a scoping decision, not approval of the Clips.
_Avoid_: Approval, review step, sign-off

**Awaiting Selection**:
The Job state during the Selection Gate: Base Clips are ready, Localization has not started, and the Job is waiting for the Creator. An unanswered gate expires after the retention window.
_Avoid_: Paused, pending review, blocked

**Expired**:
The terminal Job state when the Creator does not answer the Selection Gate before the retention window ends. The Base Clips remain available and can seed a Derived Job; no Localization occurs and the Review Bundle is never Completed.
_Avoid_: Timed out, abandoned, cancelled

**Cancelled**:
The terminal Job state when the Creator stops a Job before completion. Base Clips already rendered remain available and can seed a Derived Job; incomplete Localized Clips are pruned; no final notification is sent.
_Avoid_: Aborted, stopped, killed

**Failed**:
The Job state after automatic retries are exhausted. It can be reopened by an explicit retry from the last committed stage. A per-Job budget failure is not retryable; a Workspace-cap failure becomes retryable only after the cap is raised or the month rolls over.
_Avoid_: Error, broken

**Retry**:
An explicit, API-key-protected re-queue of a Failed Job from its last committed stage under the same Job ID and Job Budget.
_Avoid_: Rerun, restart

**Projected Localization Cost**:
The estimated spend for the selected Clips × Target Languages, derived from the Cost Ledger rate card, shown at the Selection Gate and confirmed by the Creator before Localization begins.
_Avoid_: Quote, price, invoice

**Completed**:
The state in which every asset requested by the Job's final selection has been rendered, uploaded and announced. It does not mean the Review Bundle was approved or published.
_Avoid_: Done, delivered, approved

**Job Budget**:
The maximum projected usage and spend a Job may incur, expressed as a USD estimate backed by minute and character proxies. It defaults to $50, is computed from a provider rate card with a safety margin, and is enforced against the Cost Ledger; it fails closed when a required rate is missing. A Job that would exceed it fails before the next paid provider call.
_Avoid_: Quota, cap, allowance

**Workspace Budget**:
The monthly ceiling on aggregate spend across all Jobs in a Workspace, defaulting to $500 per calendar month. It is checked at submission and before every paid call; reaching it stops new paid work with a specific error.
_Avoid_: Account limit, quota, cap

**Concurrency Limit**:
The maximum number of Jobs in `PROCESSING` at once in a Workspace, defaulting to 2. Jobs beyond the limit wait; no paid call starts until a slot frees.
_Avoid_: Parallelism, worker count

**Cost Ledger**:
An append-only record of every paid provider call: provider, model, units, rate, estimated USD and actual USD when known. It is the source of truth for Job Budget and Workspace Budget enforcement and Projected Localization Cost.
_Avoid_: Usage log, invoice, billing

**Job Event**:
An append-only record of a Job stage transition: stage, status, timestamp and error. It is the Job timeline, not the application log.
_Avoid_: Log line, audit trail

**Notification Event**:
A signed, at-most-once webhook describing a Job transition: `selection_required`, `bundle_ready` or `selection_expired`. It carries a stable event ID and a Review Link; the Job API remains the source of truth.
_Avoid_: Callback, webhook, message

**Review Link**:
A stable, revocable URL granting read-only access to one Job's available review assets, whether or not the Job completed. It redirects to short-lived object-storage URLs and is not itself a storage URL.
_Avoid_: Presigned URL, asset URL, share link

**Workspace Purge**:
The irreversible deletion of every Job, asset, review token, cost entry and event in a Workspace, confirmed after a dry-run. It ends the retention promise for delivered assets.
_Avoid_: Reset, cleanup, wipe

**Retention Window**:
The period after which raw and intermediate artifacts are deleted. Delivered Review Bundle assets are retained for the lifetime of the Workspace, until a Workspace Purge.
_Avoid_: TTL
