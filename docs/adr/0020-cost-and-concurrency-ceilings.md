---
status: accepted
---

# Cost and concurrency are capped per Workspace

Each Job defaults to a $50 Job Budget. A Workspace defaults to a $500 calendar-month Workspace Budget and 2 concurrent Jobs. The monthly ceiling is checked at submission and before every paid call; the concurrency limit gates `PROCESSING`. Both are enforced against the Cost Ledger. A running Job that would cross the monthly ceiling fails before the next paid call with a specific error; new submissions are rejected until the cap is raised or the month rolls over. A per-Job budget failure is never retryable; a Workspace-cap failure becomes retryable only after the cap changes or the month rolls over.

**Consequences**: A Job can fail mid-run when the Workspace cap is reached. Raising a cap is an operator action and is audited. The ceilings are guardrails, not a billing system.
