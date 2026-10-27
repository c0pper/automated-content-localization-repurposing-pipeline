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
* **Integrations:** OpenAI Whisper API, Anthropic Claude 3.5 Sonnet / OpenAI GPT-4o API.
* **Tasks:**
  * Generate timestamped word-level transcript from extracted audio.
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
  * Burn in synchronized, styled kinetic captions using timestamped transcript data.
  * Output rendered MP4 files ready for preview/export.

---

### 4. Localization & Dubbing Agent (`localization_agent`)
* **Role:** Translates clips into target international languages with cloned voice synthesis and optional lip-sync.
* **Integrations:** ElevenLabs API / DeepL API / Sync Labs (or equivalent AI lip-sync model).
* **Tasks:**
  * Translate transcript segment into target language (e.g., Spanish, German, Portuguese) preserving domain nuance.
  * Clone the creator's voice profile using high-fidelity TTS models.
  * Synthesize localized voice audio in target language.
  * (Optional) Run AI lip-syncing model on vertical video to align lip movement with localized audio track.
  * Merge translated audio track with video asset.

---

### 5. Delivery & Orchestration Agent (`delivery_agent`)
* **Role:** Assembles generated assets into a final review payload and notifies the user.
* **Integrations:** Webhook / Telegram / Slack API / Frontend Dashboard Storage (S3).
* **Tasks:**
  * Bundle assets per job:
    * 3–5 Short-form vertical clips (English).
    * 3–5 Short-form vertical clips (Localized/Dubbed).
    * Social media copy & newsletter text files.
  * Upload rendered binaries to cloud storage bucket (AWS S3 / Cloudflare R2).
  * Update database status to `Completed`.
  * Send webhook/email notification to creator with access links.

---

## Agent Communication & Data Schema

```json
{
  "job_id": "job_987654321",
  "status": "PROCESSING",
  "input_url": "https://storage.provider.com/raw_video.mp4",
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
      }
    }
  ]
}
```

---

## Security & Usage Guardrails
1. **API Cost Limits:** Implement strict character/minute limits per job to prevent runaway cloud usage costs.
2. **Rate Limiting:** Queue processing jobs using a worker-queue pattern (e.g., Celery/Redis or QStash) to remain within third-party API rate limits.
3. **Data Retention:** Retain raw intermediate files for 7 days before auto-deleting to minimize storage expenses.