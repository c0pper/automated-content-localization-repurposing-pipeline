---
status: accepted
---

# FastAPI owns orchestration

`AGENTS.md` allows orchestration through Python/FastAPI or Make.com. FastAPI is the sole orchestrator of record: it owns Job state, stage transitions, retries and budget enforcement. Make.com, Zapier and similar tools may trigger Jobs and receive notifications, but they never store authoritative Job state. Two orchestrators would split retries and make a Job's history ambiguous.

**Consequences**: External automations integrate through the API or webhooks. Any workflow that needs to change Job state must call FastAPI rather than writing to storage directly.
