---
status: accepted
---

# Durable infrastructure

v1 replaces process-local state with Postgres for Jobs, stage checkpoints and the notification outbox; Redis/Celery for the worker queue and scheduled expiry; and self-hosted S3-compatible object storage. Object storage is **Silo**, run from its official `pgsty/silo` container image in the all-in-one Compose stack (ADR 0014). Silo preserves the MinIO S3/Admin APIs, `MINIO_*` environment variables, disk format and `mcli`; it is not upstream MinIO.

**History**: The original decision deployed Silo through Pigsty's MINIO compatibility module. ADR 0014 moved the runtime into Compose, so the Pigsty module is not used in v1.

**Consequences**: The deployment owns Postgres, Redis and Silo. The object adapter uses the S3 API, so it can point at AWS S3 or Cloudflare R2 without application changes. Local development keeps the filesystem store; production uses the durable adapters.
