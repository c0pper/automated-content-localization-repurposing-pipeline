"""ElevenLabs voice synthesis adapter.

Implements :class:`app.ports.ai.VoiceSynthesizer` using ElevenLabs TTS.
Requires ``ELEVENLABS_API_KEY`` in environment.
"""

from __future__ import annotations

from pathlib import Path

from app.ports.ai import VoiceSynthesisResult


class ElevenLabsVoiceSynthesizer:
    async def synthesize(
        self,
        text: str,
        target_language: str,
        destination: Path,
        *,
        voice_id: str,
        model: str | None = None,
    ) -> VoiceSynthesisResult:
        import httpx
        headers = {
            "xi-api-key": __import__("os").environ.get("ELEVENLABS_API_KEY", ""),
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": model or "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            with open(destination, "wb") as f:
                f.write(response.content)

        # Return minimal VoiceSynthesisResult with alignment approximated from text length
        duration = max(len(text.split()) * 0.5, 1.0)
        words = text.split()
        alignment: list = []
        for i, token in enumerate(words):
            alignment.append({"text": token, "start": i * 0.5, "end": (i + 1) * 0.5})
        return VoiceSynthesisResult(
            audio_path=destination,
            characters=len(text),
            alignment=alignment,
        )