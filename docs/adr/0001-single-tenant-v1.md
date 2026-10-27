---
status: accepted
---

# Single-tenant v1

The pipeline initially serves one Creator per deployment. Multi-tenancy would require auth, per-Workspace asset isolation, tenant-aware cost accounting and authorized review links before the review loop itself is proven. Jobs reserve `creator_id` and `workspace_id` in the envelope so tenancy can be added without reshaping the pipeline.

**Consequences**: Review links are Workspace-scoped in v1. A future multi-tenant move must backfill ownership for existing Jobs and assets.
