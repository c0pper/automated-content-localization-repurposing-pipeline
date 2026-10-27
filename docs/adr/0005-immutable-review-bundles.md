---
status: accepted
---

# Completed Review Bundles are immutable

A Job that reaches `COMPLETED` freezes its Review Bundle. Artifact keys are stable and links may already have been sent to the Creator, so regenerating in place would silently change what was reviewed. Corrections and rejections create a Derived Job that references the original; retries may overwrite artifacts only while the Job is still incomplete. A Derived Job reuses the parent's Base Clips and regenerates only copy and/or Localization; different Base Clips require a fresh Job from the Source Recording.

A Derived Job may be created from any parent whose Base Clips are retained — `COMPLETED`, `EXPIRED` or `CANCELLED` — not only a completed parent. A Localization Derived Job re-enters the Selection Gate; a copy-only Derived Job skips it because it commits no Localization spend.

**Consequences**: Existing artifact URLs never change meaning. Storage grows with each Derived Job. Clients that need a correction must submit a new Job rather than mutate the old one. Expiry and cancellation stop a run, not the reuse value of its Base Clips.
