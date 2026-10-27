---
status: accepted
---

# Single-host Compose deployment

v1 runs as one Docker Compose stack on one host: Caddy, the API, the Celery worker, Postgres, Redis and Silo. Caddy is the public ingress: it terminates TLS, routes the API, and exposes a public S3 hostname for Silo while keeping the Silo console private. The API and worker share the application image; Postgres, Redis and Silo use named volumes; Silo uses the official `pgsty/silo` release image. The Compose file is the deployment contract. Pigsty and Kubernetes are not part of the v1 runtime.

A `backup` service runs nightly: a Postgres logical dump and an `mcli mirror` of the Silo bucket to an operator-provided off-host target, retained for 30 days. The restore drill is part of deployment acceptance. RPO is 24 hours.

Host volumes for Postgres, Redis, Silo and the backup target must be encrypted at rest (LUKS or provider-managed disk encryption). Caddy terminates TLS. Application-level envelope encryption is a later hardening step.

**Consequences**: The host is a single point of failure. There is no HA, no automatic failover and no horizontal scaling of the stateful services. Volume durability and the off-host backup target remain the operator's responsibility. A second volume on the same host is not a backup. A host with unencrypted volumes is out of compliance. Backups age out under their own policy; a Workspace Purge does not delete backups immediately. Silo must sign URLs for its public hostname, and bypassing Caddy breaks presigned links. Moving to managed services or a cluster later must preserve the same service boundaries and connection contracts.
