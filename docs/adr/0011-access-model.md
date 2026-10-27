---
status: accepted
---

# Access is token-scoped

v1 has no user accounts. Mutating endpoints require a single Workspace API key; read-only review access uses opaque, per-Job tokens embedded in stable app-owned Review Links. Those links redirect to short-lived presigned Silo URLs, so the durable review link never expires with a signature and can be revoked.

**Consequences**: The API key must be rotatable. Review tokens are bearer credentials and must be treated as secrets. The external frontend holds the API key and performs selection; the Creator's review link remains read-only. No object-storage bucket is public.
