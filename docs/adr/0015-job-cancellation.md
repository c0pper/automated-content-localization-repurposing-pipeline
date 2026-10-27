---
status: accepted
---

# Jobs are cancellable

A Job can be cancelled until it reaches `COMPLETED`, `FAILED` or `EXPIRED`. Cancellation sets `CANCELLED`; the worker checks between stages and stops before starting the next paid call. An in-flight provider call is not interrupted and may still be billed. Base Clips already rendered remain available, incomplete Localized Clips are pruned, and no `bundle_ready` or cancellation notification is sent. Cancelling a completed Job is not allowed; corrections use a Derived Job.

**Consequences**: Every stage boundary must check cancellation, and a cancel can race with a stage commit. `CANCELLED` is terminal. The frontend observes cancellation by polling the Job, not by waiting for an event.
