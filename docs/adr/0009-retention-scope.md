---
status: accepted
---

# Delivered bundles outlive raw media

Delivered Review Bundle assets — Base Clips, Localized Clips and copy — are retained for the lifetime of the Workspace and removed only by an explicit Workspace Purge. Each Base Clip also retains its own spoken source-text excerpt as Clip metadata for the same lifetime; this is a short Clip excerpt, not the full Transcript. The Source Recording, full Transcript, caption SRTs, intermediate audio and pre-mux renders are pruned after the 7-day Retention Window. Expired Jobs keep their Base Clips and source text under the same rule.

A Workspace Purge is a two-step destructive operation: a dry-run reports the Jobs, objects and review tokens that would be deleted, then a confirmation carrying the Workspace ID deletes them from Postgres and Silo. There is no undo. Backup copies are governed by the deployment's separate backup retention policy.

**Consequences**: Storage grows with every Job and Derived Job, plus a short source-text excerpt per Clip. Derived Jobs do not depend on the pruned Transcript. Review links never expire automatically. A Workspace Purge is irreversible and must remove database rows, object-storage keys and review tokens together.
