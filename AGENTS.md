# AGENTS.md – Automated Content Repurposing & Localization Pipeline

## System Overview
This project is an end-to-end automated platform that ingests long-form video content from niche experts, extracts high-performing hooks, generates multi-channel social assets, and localizes (dubbing + lip-syncing) the video into target foreign languages.

The platform is designed around a multi-agent workflow orchestrated via Python/FastAPI or Make.com, interacting with specialized APIs.

---

## Autonomous Agent Fleet

### 1. Ingestion & Preprocessing Agent (`ingest_agent`)
* **Role:** Detects new media submissions, validates file formats, and prepares audio/video streams for processing.
* **Triggers:** Webhook (Google Drive / YouTube API / Zoom API / Web Dashboard form upload).
* **Tasks:**
  * Pull raw MP4/MOV assets from target storage.
  * Extract audio track (MP3/WAV) for fast LLM transcription.
  * Validate media length, resolution, and audio quality.
  * Register job state in database with a unique `job_id`.

---

### 2. Transcription & Intelligence Agent (`intelligence_agent`)
* **Role:** Transcribes media and identifies viral/high-value content segments using LLM logic.
* **Integrations:** OpenAI Whisper API; OpenRouter for planning and copy (default model plus selectable models).
* **Tasks:**
  * Generate timestamped word-level transcript from extracted audio.
  * Detect the Source Language, or accept a declared override at submission; fall back to English only when detection is inconclusive.
  * Analyze transcript for key value moments:
    * Strong hooks / contrarian takes.
    * Step-by-step frameworks.
    * High-emotion or key takeaway clips.
  * Select 3–5 optimal short-form clip candidates with precise `start_time` and `end_time` markers.
  * Generate accompanying copy:
    * Vertical video title & social media caption.
    * 1 LinkedIn text/carousel breakdown.
    * 1 Newsletter draft summarizing key insights.

---

### 3. Video Processing & Formatting Agent (`video_editor_agent`)
* **Role:** Slices long-form video, re-frames to 9:16 vertical format, and bakes in custom dynamic subtitles.
* **Integrations:** FFmpeg / Shotstack API / Cloud Render Workers.
* **Tasks:**
  * Cut video segments based on `start_time` and `end_time` timestamps provided by `intelligence_agent`.
  * Crop and center subject for vertical (9:16) aspect ratio (TikTok/Reels/Shorts).
  * Render a caption-free 9:16 Base Clip Master for each Clip and retain it for the Workspace lifetime.
  * Render the Base Clip review asset from the master with synchronized, styled kinetic captions using timestamped transcript data.
  * Output rendered MP4 files ready for preview/export; the master stays internal and is not part of the Review Bundle.

---

### 4. Localization & Dubbing Agent (`localization_agent`)
* **Role:** Translates clips into target international languages with cloned voice synthesis and optional lip-sync.
* **Integrations:** OpenRouter API / ElevenLabs API / Sync Labs (or equivalent AI lip-sync model).
* **Tasks:**
  * Translate the Clip's retained source text for synthesized speech and for burned-in captions, and translate the per-Clip Hook and social caption for the social asset. Long-form LinkedIn and newsletter copy stay in the Source Language in v1.
  * Clone the creator's voice profile using high-fidelity TTS models.
  * Synthesize localized voice audio in target language and retain the provider's character or word alignment.
  * Render from the caption-free Base Clip Master, not the captioned Base Clip.
  * (Optional) Run AI lip-syncing model on the caption-free master to align lip movement with the localized audio track.
  * Burn translated captions onto the video after lip-sync, synchronized to the localized audio. Merge translated audio track with the master. A missing Voice Profile, lip-sync failure or missing caption alignment fails the Job; there is no silent fallback.

---

### 5. Delivery & Orchestration Agent (`delivery_agent`)
* **Role:** Assembles generated assets into a final review payload and notifies the user.
* **Integrations:** Webhook / Telegram / Slack API / Silo (S3-compatible) storage.
* **Tasks:**
  * Bundle assets per job:
    * 3–5 Short-form vertical clips in the Source Language (Base Clips), captioned in the Source Language.
    * 3–5 Short-form vertical clips (Localized/Dubbed), captioned in the Target Language.
    * Social media copy localized per Clip and Target Language; LinkedIn and newsletter copy in the Source Language.
    * Caption-free Base Clip Masters are retained for the Workspace lifetime but are not part of the Review Bundle.
  * Upload rendered binaries to the Silo bucket (S3-compatible).
  * Update database status to `Completed`.
  * Send webhook/email notification to creator with access links.

---

## Agent Communication & Data Schema

```json
{
  "job_id": "job_987654321",
  "status": "PROCESSING",
  "input_url": "https://storage.provider.com/raw_video.mp4",
  "source_language": "en",
  "target_languages": ["es", "de"],
  "segments": [
    {
      "segment_id": 1,
      "start_time": "00:02:14",
      "end_time": "00:03:05",
      "hook_title": "Why 90% of B2B SaaS Ads Fail",
      "caption": "Stop wasting budget on broad audiences...",
      "video_asset_url": "https://storage.provider.com/output/clip_1_en.mp4",
      "localized_assets": {
        "es": "https://storage.provider.com/output/clip_1_es.mp4",
        "de": "https://storage.provider.com/output/clip_1_de.mp4"
      },
      "localized_copy": {
        "es": {
          "hook_title": "Por qué fallan el 90% de los anuncios B2B SaaS",
          "caption": "Deja de gastar presupuesto en audiencias amplias..."
        },
        "de": {
          "hook_title": "Warum 90% der B2B-SaaS-Anzeigen scheitern",
          "caption": "Hör auf, Budget für breite Zielgruppen zu verschwenden..."
        }
      }
    }
  ]
}
```

---

## Security & Usage Guardrails
1. **API Cost Limits:** Implement strict character/minute limits per job and append every paid call to a Cost Ledger; enforce the USD Job Budget and the monthly Workspace Budget before the next paid call.
2. **Rate Limiting:** Queue processing jobs using a worker-queue pattern (Celery/Redis), cap concurrent Jobs, and remain within third-party API rate limits.
3. **Data Retention:** Retain raw intermediate files for 7 days before auto-deleting to minimize storage expenses. Base Clips, Localized Clips, per-Clip source text and caption-free Base Clip Masters live for the Workspace lifetime and are removed only by a Workspace Purge.
4. **Encryption:** Encrypt host volumes and the backup target at rest; use TLS in transit.