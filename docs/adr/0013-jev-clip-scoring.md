---
status: accepted
---

# Jev scores Clips; the planner explains them

Each Clip Candidate is scored with one Jev Decisions API request containing four independent `score` questions — hook strength, standalone clarity, emotional payoff and business/CTA fit — on anchored 0–4 scales. The four probability-weighted positions are converted to 0–100 and averaged equally; the Quality Floor defaults to 70. Jev is pinned to a specific version and the returned model snapshot is recorded on the Job. Because Jev returns no prose, the Selection Gate shows the planner's Clip Rationale alongside the criterion scores; no extra LLM call is made in v1.

**Consequences**: Scoring thresholds must be recalibrated when the pinned Jev version changes. The Clip Rationale can disagree with the Selection Score; they are separate signals. Jev cost is input-token based and must appear in the rate card.
