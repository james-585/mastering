"""STORY-002 -- MP3 decode-tier dispatch logic. TC-385."""
from __future__ import annotations

import pytest

from suno_mastering.io import mp3_decode

from .ref_helpers import pink_noise_stereo, write_mp3_ffmpeg, ffmpeg_available


def test_tc385_dispatch_routes_to_tier1_when_probe_true(tmp_path, monkeypatch):
    calls = {"tier1": 0, "tier2": 0}
    monkeypatch.setattr(mp3_decode, "_decode_tier1", lambda path: calls.__setitem__("tier1", calls["tier1"] + 1) or "tier1-result")
    monkeypatch.setattr(mp3_decode, "_decode_tier2", lambda path: calls.__setitem__("tier2", calls["tier2"] + 1) or "tier2-result")

    result = mp3_decode.decode_mp3("dummy.mp3", probe_fn=lambda: ["WAV", "MP3", "FLAC"])
    assert result == "tier1-result"
    assert calls == {"tier1": 1, "tier2": 0}


def test_tc385_dispatch_routes_to_tier2_when_probe_false(tmp_path, monkeypatch):
    calls = {"tier1": 0, "tier2": 0}
    monkeypatch.setattr(mp3_decode, "_decode_tier1", lambda path: calls.__setitem__("tier1", calls["tier1"] + 1) or "tier1-result")
    monkeypatch.setattr(mp3_decode, "_decode_tier2", lambda path: calls.__setitem__("tier2", calls["tier2"] + 1) or "tier2-result")

    result = mp3_decode.decode_mp3("dummy.mp3", probe_fn=lambda: ["WAV", "FLAC"])
    assert result == "tier2-result"
    assert calls == {"tier1": 0, "tier2": 1}


def test_tc385_live_environment_probe_and_matching_tier(tmp_path):
    """Environment-conditional integration test against whichever branch
    the real, unmocked probe selects on this machine -- logs which tier
    was actually exercised, per architecture.md Section 12's testability
    guidance (skip, not fail, the untested branch)."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available for MP3 fixture encoding")

    audio = pink_noise_stereo(44100, 5.0)
    p = write_mp3_ffmpeg(tmp_path / "t.mp3", audio, 44100, bitrate_kbps=192)

    probe_result = mp3_decode.mp3_read_supported()
    result = mp3_decode.decode_mp3(p)
    print(f"TC-385: live probe selected {'tier1 (libsndfile)' if probe_result else 'tier2 (ffmpeg)'}")
    if probe_result:
        assert result.decoder.startswith("libsndfile-")
    else:
        assert result.decoder.startswith("ffmpeg-")
    assert result.audio.shape[0] > 0


def test_tc385_tier2_explicit_forced_path(tmp_path):
    """Directly exercises tier 2 (bypassing the probe) regardless of which
    branch is live on this machine, so tier 2's own decode correctness is
    tested even when tier 1 is the environment's default -- per
    architecture.md Section 12's 'both branches where the environment
    allows' recommendation. Also snapshots the OS temp directory
    before/after (TC-283's tier-2-specific concern: the FFmpeg subprocess
    path must be stdout-only, never a NamedTemporaryFile)."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")
    audio = pink_noise_stereo(44100, 5.0)
    p = write_mp3_ffmpeg(tmp_path / "t.mp3", audio, 44100, bitrate_kbps=192)

    import tempfile
    import os
    tmp_dir = tempfile.gettempdir()
    before = set(os.listdir(tmp_dir))
    result = mp3_decode._decode_tier2(p)
    after = set(os.listdir(tmp_dir))

    assert result.decoder.startswith("ffmpeg-")
    assert result.audio.shape[0] > 0
    assert result.channels == 2
    assert not (after - before), f"tier-2 decode left new files in temp dir: {after - before}"
