---
status: accepted
---

# Jobs resume from committed stages

A re-queued Job resumes from its last committed stage instead of re-running ingestion, planning and rendering. Artifact keys are idempotent per Job and stage, transient provider failures are retried with backoff, notifications are sent at most once, and a Job never reaches `COMPLETED` with a partial bundle. After retry exhaustion the Job rests in `FAILED`. A `FAILED` Job can be re-queued explicitly through the retry endpoint; it resumes from the last committed stage under the same Job ID and Job Budget. A per-Job budget failure is not retryable; a Workspace-cap failure becomes retryable only after the cap changes or the month rolls over. Every attempt appends to the Cost Ledger.

**Consequences**: Every stage output must be persisted and reconstructible. Provider calls need idempotency keys or overwrite-safe artifacts. The queue must support re-delivery without duplicating a notification. The retry endpoint must be idempotent and must not reset cost or notification state.
