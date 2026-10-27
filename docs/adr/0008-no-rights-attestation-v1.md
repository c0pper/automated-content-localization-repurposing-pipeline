---
status: accepted
---

# No rights attestation in v1

v1 does not require a recorded voice/likeness rights attestation before cloning. The gate is deferred to keep the pipeline API-only and avoid inventing consent wording before a real distribution or legal constraint exists. Operators are responsible for securing rights outside the pipeline, and the product must not claim that it verifies consent.

**Consequences**: Jobs may synthesize a voice with no in-system audit trail. Adding the gate later means backfilling attestations for existing Jobs and deciding what happens to their assets. Revisit this decision before processing third-party recordings or enabling publication.
