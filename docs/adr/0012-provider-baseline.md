---
status: accepted
---

# Provider baseline

v1 uses Whisper for transcription; OpenRouter as the single gateway for planning, copy and translation, with a default model plus selectable models; ElevenLabs for voice synthesis; Sync Labs for lip-sync; and Jev via OpenRouter for Clip scoring. DeepL was rejected as a separate integration because OpenRouter already provides selectable translation models behind one credential. Jev is a decision model, invoked through OpenRouter's Decisions API rather than the chat API, and does not generate text.

Each Workspace configures a default OpenRouter model per task — planning, copy and translation. A Job may override any of them only from a curated allowlist; arbitrary model IDs are rejected. The exact model IDs used are recorded on the Job for reproducibility and cost estimation. Target Languages are drawn from a Workspace allowlist and validated against ElevenLabs capabilities; when lip-sync is requested, they are also validated against Sync Labs.

**Consequences**: Model IDs are configuration, not code. An OpenRouter outage affects planning, copy, translation and scoring together. DeepL-specific capabilities such as glossaries are unavailable unless a separate adapter is added later. The rate card must be keyed by model, and Jev's Decisions API cost is a separate line item.
