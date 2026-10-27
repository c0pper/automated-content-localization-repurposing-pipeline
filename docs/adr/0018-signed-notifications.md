---
status: accepted
---

# Notifications are signed and at-most-once

Every notification event has a stable `event_id`, `event_type`, `job_id`, `status`, `occurred_at` and `review_url`; `selection_required` also carries `expires_at`. The event types are `selection_required`, `bundle_ready` and `selection_expired`; cancellation emits no notification. Delivery is at-most-once: the outbox marks an event claimed before the HTTP attempt and never retries an ambiguous failure. Payloads are signed with HMAC-SHA256 over a timestamp and the raw body in `X-Pipeline-Signature: t=...,v1=...`. Receivers dedupe by `event_id`; the Job API remains the source of truth.

**Consequences**: A lost notification is not replayed; the frontend must poll. Secret rotation must accept multiple verification keys during the overlap. At-most-once is lossy by design; duplicating a paid-run event is worse than losing a convenience signal.
