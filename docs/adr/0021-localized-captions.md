---
status: accepted
---

# Localized Clips carry localized captions

A Base Clip burns Source Language captions into its pixels. Muxing localized audio onto that asset would leave Source Language captions visible under Target Language speech, so a Localized Clip would not be review-ready. Each Base Clip therefore retains a caption-free 9:16 Base Clip Master for the lifetime of the Workspace. The Base Clip review asset is rendered from the master with Source Language captions. A Localized Clip is rendered from the same master with localized audio and translated, timed captions; when lip-sync is requested it runs on the master before captions are burned in. Caption timings come from the speech provider's character or word alignment. A Localized Clip without synchronized caption timings fails with `caption_alignment_unavailable` rather than shipping guessed timings.

The master is internal: it is excluded from the Review Bundle and removed by a Workspace Purge. It is exempt from the 7-day intermediate rule because Derived Jobs and late localizations need it.

**Consequences**: Each Clip costs one extra retained video. Localization adds a caption render pass; alignment is part of the speech call in v1. The target-language caption font and style must be supported; the Latin-script Target Language Allowlist keeps this bounded. The Source Recording, full Transcript and pre-mux renders still expire after seven days.
