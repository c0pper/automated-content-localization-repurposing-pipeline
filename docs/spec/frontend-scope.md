# Frontend Specification — Content Creator Management Portal

## Problem Statement

A Creator with long-form video can submit Jobs to the FastAPI backend and receive Base Clips, Localized Clips and copy, but there is no Creator-facing UI to manage that flow. Today the Creator must call JSON endpoints manually — submit a Job, poll status, open a Selection Gate, confirm a rectangle of clips × languages, and open a review link — all without a guided interface. The Creator cannot easily see which clips were chosen, configure localization preferences, switch target languages, or manage account settings from a modern dashboard.

## Solution

Build a single-page application frontend in React (Vite + TypeScript + Tailwind) that is the Creator's control plane for the existing API. The frontend consumes the established REST contracts (`/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/selection`, `/api/review/{token}`, `/api/workspace`, etc.) with JWT-in-httpOnly-cookie auth and Zustand state management. It provides Dashboard, Video Library, Video Details/Editor, Localization Settings and Profile pages, all mobile-first with a black theme and selectable neon accent colors (default cyan), keyboard-navigable and screen-reader friendly. Localized copy (Hook/social caption) displays in the target language while LinkedIn and newsletter copy remain in Source Language per v1 scope.

## User Stories

1. As a Creator, I want to log in to a modern dashboard so that I can see all my Jobs at a glance.
2. As a Creator, I want to see a list of my Jobs with status, stage, created date, source language and target languages, so that I know what is in progress.
3. As a Creator, I want to filter Jobs by status (RECEIVED, PROCESSING, AWAITING_SELECTION, COMPLETED, FAILED, EXPIRED, CANCELLED), so that I can focus on Jobs that need my attention.
4. As a Creator, I want to search my Jobs by keyword, so that I can find a specific recording quickly.
5. As a Creator, I want to click a Job to open its details page, so that I can review its clips, copy and assets.
6. As a Creator, I want to view each Clip's start/end time, Hook, social caption, Jev scores and planner rationale, so that I can judge why it was selected.
7. As a Creator, I want to play a Base Clip review asset with Source Language burned-in captions, so that I can verify the clip before localizing it.
8. As a Creator, I want to see whether a Job is at the Selection Gate, so that I can choose which clips and languages to localize.
9. As a Creator, I want to see a cost matrix for every Clip × Language cell at the Selection Gate, so that I can choose with price in view.
10. As a Creator, I want to select a rectangular subset of Clips and Target Languages and confirm the projected total, so that I control exactly what gets localized.
11. As a Creator, I want to select nothing (empty rectangle) so that a Job completes with Base Clips only and no localization spend.
12. As a Creator, I want to be warned if the projected total changed before I confirm, so that I never approve a different amount by accident.
13. As a Creator, I want to see localized clips with translated burned-in captions and localized Hook/social caption, so that I can review dubbed output in my target language.
14. As a Creator, I want to switch the UI language dynamically, so that the interface is readable in my preferred language.
15. As a Creator, I want dates and numbers formatted for my locale, so that the UI feels local.
16. As a Creator, I want to open the review link for a completed Job, so that I can share review-ready assets without exposing the Workspace API key.
17. As a Creator, I want to configure my Voice Profile, so that dubbed clips sound like me.
18. As a Creator, I want to enable lip-sync per Job, so that lip movement matches localized audio.
19. As a Creator, I want to set or override the planning/copy/translation model from a curated list, so that I can tune quality and cost.
20. As a Creator, I want to set a per-Job budget, so that I do not spend more than I intend.
21. As a Creator, I want to cancel a Job, so that I can stop work I no longer need.
22. As a Creator, I want to retry a failed Job from its last checkpoint, so that transient failures do not require re-ingestion.
23. As a Creator, I want to create a Derived Job from retained Base Clips, so that I can try a different localization selection without redoing source work.
24. As a Creator, I want the frontend to be usable on mobile devices, so that I can manage clips on the go.
25. As a Creator, I want to navigate the entire UI using only a keyboard, so that I am not dependent on a mouse.
26. As a Creator using a screen reader, I want all interactive elements and image/video content to have accessible labels and roles, so that I can operate the frontend independently.
27. As a Creator, I want to choose a neon accent color for the theme, so that I can personalize the workspace appearance.
28. As a Creator, I want to view my account/profile settings, so that I can manage my Workspace.
29. As a Creator, I want to see a Job's cost breakdown (spent vs budget, workspace remaining), so that I can track spend.
30. As a Creator, I want to see job failure reasons and whether they are retryable, so that I know what to do next.
31. As a Creator, I want to upload a video file from my device when creating a Job, so that I do not need to host it somewhere first.
32. As a Creator, I want to see upload progress and cancel an upload, so that I know how long a large file will take and can change my mind.
33. As a Creator, I want to see my file's duration and be warned if it is outside the allowed length before it uploads, so that I do not wait for a file the pipeline will reject.

## Implementation Decisions

- **Seam / interface boundary:** The frontend talks exclusively to the existing FastAPI backend via the documented REST contracts under `/api`. The only new backend endpoints are the Source Upload endpoints (ADR 0022): `POST /api/uploads`, `GET /api/uploads/{id}/parts`, `POST /api/uploads/{id}/complete`, `DELETE /api/uploads/{id}`. Otherwise the frontend adapts to `GET /api/jobs`, `POST /api/jobs`, `GET/PUT/DELETE /api/jobs/{id}`, `GET/POST /api/jobs/{id}/selection`, `GET /api/jobs/{id}/bundle`, `GET /api/jobs/{id}/events`, `GET /api/jobs/{id}/cost`, `POST /api/jobs/{id}/cancel`, `POST /api/jobs/{id}/retry`, `POST /api/jobs/{id}/derive`, `POST/DELETE /api/jobs/{id}/review-link`, `GET /api/review/{token}`, `GET/PUT /api/workspace`, `GET/PUT/DELETE /api/workspace/voice-profile`.
- **Authentication seam:** JWT in httpOnly cookies with a refresh-token flow; the frontend never stores tokens in localStorage and never handles provider credentials.
- **Module: Auth domain** (Zustand slice) — interface: `login`, `logout`, `getToken`, `isAuthenticated`, `user`; implementation handles cookie attachment via fetch interceptors and refresh rotation.
- **Module: Job domain** (Zustand slice) — interface: `listJobs`, `getJob`, `createJob`, `cancelJob`, `retryJob`, `deriveJob`, `confirmSelection`; implementation maps API `segments[]` wire alias to internal `Clip` vocabulary from `GLOSSARY.md`.
- **Module: Source upload** — interface: `uploadSource(file, { onProgress, signal }) → Promise<{ key }>`; implementation starts a Source Upload, fetches presigned part URLs on demand, PUTs 32 MiB parts directly to object storage with 4 in flight and per-part retry, completes the upload, and aborts it when `signal` fires. The New Job form offers **Upload** (default) or **URL**; the raw object key is never shown. Uploading starts as soon as a file is picked; "Create Job" waits for it and then submits `source: {type: "object", key}`. Removing the file or cancelling aborts the upload; leaving the page mid-upload triggers a `beforeunload` warning, and an interrupted upload is not resumed. The browser reads the file's duration locally and warns, without blocking, when it is outside the allowed length.
- **Module: Localization domain** (Zustand slice) — interface: `setTargetLanguages`, `setLipSync`, `setModelOverrides`, `setVoiceProfile`, `setUILanguage`; implementation persists preferences and drives localized asset/copy rendering.
- **Module: UI theme domain** (Zustand slice) — interface: `setAccentColor`, `setTheme`, `toggleDarkMode`; implementation applies Tailwind classes and CSS variables for black background + selectable neon accents (electric green, magenta, cyan default, amber).
- **Module: Video player domain** — interface: `playClip(assetUrl, captionsUrl)`; implementation is a `react-player` wrapper with custom controls supporting MP4/HLS and burned-in caption display.
- **Module: Review access domain** — interface: `openReviewLink(jobId)`, `rotateReviewLink`, `revokeReviewLink`; implementation builds stable review URLs that redirect to presigned Silo assets via the existing `/api/review/{token}/assets/{id}` 302 flow.
- **TypeScript types** mirror the API wire shapes (`Job`, `Clip`, `Selection`, `CostLedgerEntry`, `JobEvent`, `WorkspaceSettings`) and follow existing ID conventions (`job_<12hex>`, `clip_<job>_<ordinal>`, `segment_id` wire alias).
- **Error handling:** deterministic error codes from the API (`selection_price_changed`, `quality_floor_not_met`, `voice_profile_missing`, `lip_sync_unavailable`, `insufficient_job_budget`, `workspace_budget_exceeded`) map to user-facing messages; no scraping of message text.
- **Idempotency:** POST/DELETE mutations include an `Idempotency-Key` header scoped to the Workspace; the frontend generates and keys retry-safe requests.
- **Pagination:** `limit` (1–100, default 50) + opaque `cursor`; `next_cursor` or `null`.
- **Routing:** pages at `/dashboard`, `/library`, `/jobs/{job_id}`, `/jobs/{job_id}/localization`, `/profile`, `/auth` (login callback).
- **Accessibility:** keyboard-operable controls, focus management, ARIA labels/roles on all interactive elements, screen-reader announcements for status changes (e.g. gate opened, bundle ready), WCAG AA color contrast on black + neon accent combinations.
- **Responsive:** mobile-first Tailwind breakpoints; touch-friendly targets for clip selection and sharing buttons.

## Testing Decisions

- Good tests assert external behavior only (rendered output, user interactions, API call shapes), never Zustand internal reducer details or component implementation.
- Source upload is tested behind its own seam: `NewJobPage` tests stub `uploadSource` rather than mocking XHR/fetch; the module itself is tested against a fake upload API (progress, part retry, abort on cancel, completion before submission).
- Modules to test: Auth domain (login/refresh/logout flow), Job domain (list/create/cancel/selection confirm with mocked API), Localization domain (preference persistence), UI theme domain (accent color application), Video player (asset URL + caption source binding), Review access (token URL construction).
- Prior art: follow existing test conventions in the repo's `tests/` directory; use the in-memory/local adapters pattern from the backend as the mock analogue for API calls.
- Integration coverage for the Selection Gate flow: open gate → view matrix → select rectangle → confirm → observe `PROCESSING` + `stage: localization`.

## Out of Scope

- Backend changes beyond the Source Upload endpoints: no other new API endpoints, no GraphQL, no WebSocket for v1.
- Streaming upload bytes through the API, and resuming an interrupted upload after a page reload (ADR 0022).
- Analytics dashboard and tracking (deferred; not essential for v1 per Q10).
- AI subject tracking for vertical reframing (v1 uses deterministic center crop).
- Long-form LinkedIn/newsletter copy localization (stays in Source Language per v1).
- A separate review/end-user portal distinct from the Creator-facing app — the review link is a read-only view of the same Job data.
- Multi-tenancy UI (v1 is single-tenant); `workspace_id`/`creator_id` reserved but not exposed as a selector.

## Further Notes

- The frontend is a separate consumer of the backend per `docs/spec/v1-pipeline.md` ("The API is the product boundary. The frontend owns the Creator UI; this service owns JSON contracts, assets and delivery.").
- AGENTS.md schema (`job_id`, `status`, `input_url`, `source_language`, `target_languages`, `segments[]` with `start_time`/`end_time`/`hook_title`/`caption`/`video_asset_url`/`localized_assets`/`localized_copy`) remains the public wire shape; internal code uses `Clip`/`clip_id`.
- Money is integer micro-USD stored/exchanged as decimal strings (six fractional digits); no binary floating point for cost in the frontend either.
- Accent colors available: electric green (`#00ff00`), magenta (`#ff00ff`), cyan (`#00ffff`, default), amber (`#ffbf00`).
- Neon accent + black contrast must meet WCAG AA; each accent color gets a validated text/background pairing.
- Once `/setup-matt-pocock-skills` is run and triage vocabulary exists, publish this to the issue tracker with the `ready-for-agent` label.