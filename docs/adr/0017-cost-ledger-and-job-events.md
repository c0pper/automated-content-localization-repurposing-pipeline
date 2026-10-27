---
status: accepted
---

# Cost and stage history are append-only

Every paid provider call appends a Cost Ledger entry with provider, model, units, rate, estimated USD and actual USD when known. Every stage transition appends a Job Event with stage, status, timestamp and error. The Job Budget is enforced against the ledger, and the Selection Gate's Projected Localization Cost is derived from the same rate card. Entries are never edited; corrections are new entries, and each entry stores the rate used. Job Events are not application logs: they are the Job's durable timeline and are exposed through the Job API. The ledger and events are deleted only by a Workspace Purge.

**Consequences**: Budget enforcement survives restarts. Actual provider cost may be unknown or arrive later; estimated cost is the enforcement value, and actual cost is reconciled when available. The append-only history grows with every retry and Derived Job.
