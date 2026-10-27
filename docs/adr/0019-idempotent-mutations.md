---
status: accepted
---

# Mutations are idempotent

Every POST/DELETE mutation requires an `Idempotency-Key` and replays the original status and body on reuse; PUT is naturally idempotent. The same key with a different request body returns `409`. Keys are retained for 7 days. Webhooks use the provider event ID as the key. This covers Job submission, Derived Jobs, selection confirmation, retry, cancel, Voice Profile registration and Workspace Purge.

**Consequences**: Clients must generate and retain keys for their retry window. The API stores a request fingerprint and the original response, and both must survive restarts. A replay must not append to the Cost Ledger or emit a second notification.
