from __future__ import annotations

import os
from datetime import timedelta

from app.adapters.local_object_store import LocalObjectStore
from app.captions import build_srt
from app.domain.models import TranscriptWord
from app.domain.timestamps import format_timestamp, parse_timestamp


def test_timestamp_round_trip():
    assert format_timestamp(134.9) == "00:02:14"
    assert format_timestamp(3725) == "01:02:05"
    assert parse_timestamp("00:02:14") == 134
    assert parse_timestamp("02:14") == 134
    assert parse_timestamp("90") == 90


def test_srt_cues_are_relative_to_the_clip():
    words = [
        TranscriptWord(text="Stop", start=100.0, end=100.4),
        TranscriptWord(text="wasting", start=100.4, end=100.8),
        TranscriptWord(text="budget.", start=100.8, end=101.2),
    ]

    srt = build_srt(words, clip_start=100.0, clip_end=130.0)

    assert "00:00:00,000 --> 00:00:01,200" in srt
    assert "Stop wasting budget." in srt
    assert "00:01:40" not in srt


async def test_retention_sweeper_removes_old_workspaces(tmp_path):
    store = LocalObjectStore(
        data_dir=tmp_path,
        public_base_url="http://test/assets",
    )
    old_job = store.workspace_root / "job_old"
    old_job.mkdir()
    (old_job / "source.mp4").write_bytes(b"raw")

    recent_job = store.workspace_root / "job_recent"
    recent_job.mkdir()
    (recent_job / "source.mp4").write_bytes(b"raw")

    ancient = 1_000_000.0
    os.utime(old_job, (ancient, ancient))

    removed = await store.prune(older_than=timedelta(days=7))

    assert removed == 1
    assert not old_job.exists()
    assert recent_job.exists()


async def test_store_rejects_keys_that_escape_the_root(tmp_path):
    store = LocalObjectStore(data_dir=tmp_path, public_base_url="http://test/assets")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"data")

    try:
        await store.put(source, "../escaped.mp4")
    except ValueError:
        pass
    else:
        raise AssertionError("expected traversal key to be rejected")
