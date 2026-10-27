---
status: accepted
---

# Localization waits for Creator selection

Every Job renders its Base Clips, then pauses in `AWAITING_SELECTION` instead of localizing everything. The Creator selects a rectangular subset — one set of Clips × one set of already-declared Target Languages — sees a Projected Localization Cost, and confirms. The Job resumes and localizes only that subset. An empty selection is valid and completes the Job with Base Clips only. Target Languages may be narrowed but not added, because a new language falls outside the submission's language scope. An unanswered gate expires after the retention window and ends `EXPIRED` with no localization spend.

The gate exposes a cost matrix and re-prices at confirmation. `GET /api/jobs/{id}/selection` returns the Base Clips with their Selection Scores and rationales, the declared languages, a per-Clip × per-Language cost matrix and `expires_at`. `POST /api/jobs/{id}/selection` accepts the chosen Clip and language IDs plus the expected total; if re-pricing differs, it returns `409` with the new total and starts no Localization. A Derived Job that changes Localization re-enters this gate; a copy-only Derived Job skips it.

A blind submission-time localization policy was rejected because the Creator cannot judge Clips they have not seen. Separate localization Jobs were rejected because they split one deliverable across two Jobs and two notifications.

**Consequences**: The Job lifecycle gains `AWAITING_SELECTION` and `EXPIRED`. A selection endpoint and an expiry scheduler are required. Base-Clip-only Review Bundles are valid. Localization cost is committed at selection, not at submission. Selection confirmation is a compare-and-swap on the projected cost. The gate is API-only in v1; a separate frontend owns the human surface. Two at-most-once notification events are emitted: `selection_required` when the gate opens, and `bundle_ready` or `selection_expired` when it closes.
