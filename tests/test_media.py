"""Rendered clips must be playable in every supported browser, stub or ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave

import pytest

from app.adapters.ffmpeg_media import FFmpegMediaProcessor
from app.adapters.stubs import StubMediaProcessor, StubTranscriber

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def _is_mp4(data: bytes) -> bool:
    return data[4:8] == b"ftyp"


async def test_stub_renders_playable_mp4_clips(tmp_path):
    media = StubMediaProcessor()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not inspected by the stub")

    master = await media.render_vertical_clip(
        source, tmp_path / "master.mp4", start_seconds=0.0, end_seconds=30.0
    )
    captioned = await media.burn_captions(
        master, "1\n00:00:00,000 --> 00:00:01,000\nHi\n", tmp_path / "clip.mp4"
    )
    dubbed = await media.replace_audio(master, tmp_path / "voice.mp3", tmp_path / "dub.mp4")

    for clip in (master, captioned, dubbed):
        assert _is_mp4(clip.read_bytes()), clip.name


async def test_stub_transcript_spans_the_real_audio_when_it_is_a_wav(tmp_path):
    """With ffmpeg media and stub AI, Clips must fall inside the actual recording."""
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * 16000 * 30)

    transcript = await StubTranscriber().transcribe(audio)

    assert transcript.duration_seconds == 30.0
    assert transcript.words[-1].end <= 30.0


async def test_stub_transcript_keeps_its_default_length_for_placeholder_audio(tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"stub media derived from source.mp4\n")

    transcript = await StubTranscriber().transcribe(audio)

    assert transcript.duration_seconds == 600.0


def _stream(path) -> dict:
    output = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(output)["streams"][0]


@pytest.fixture
def ten_bit_source(tmp_path):
    source = tmp_path / "hdr.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p10le", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest", str(source),
        ],
        check=True,
    )
    return source


@needs_ffmpeg
async def test_ffmpeg_renders_8_bit_h264_from_a_10_bit_source(tmp_path, ten_bit_source):
    """10-bit H.264 (High10) does not play in Firefox or Safari."""
    media = FFmpegMediaProcessor()

    master = await media.render_vertical_clip(
        ten_bit_source, tmp_path / "master.mp4", start_seconds=0.0, end_seconds=1.0
    )
    captioned = await media.burn_captions(
        master, "1\n00:00:00,000 --> 00:00:01,000\nHi\n", tmp_path / "clip.mp4"
    )

    for clip in (master, captioned):
        assert _stream(clip) == {"codec_name": "h264", "pix_fmt": "yuv420p"}, clip.name
