"""STORY-002 AC8 -- non-destructive guarantee. TC-280-TC-284.

Also includes a dedicated regression test for architecture.md Section 10's
explicit "[R5]'s run-completion step re-hashes every file that was
successfully ingested and asserts the set matches -- a
NonDestructiveIntegrityError is raised if any mismatch is found" requirement
-- see test_ref_hash_reverification_mechanism_present below, and
defects.md DEF-105.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from suno_mastering.reference_analysis import pipeline as ref_pipeline
from suno_mastering.io.reference_ingest import compute_file_hash
from suno_mastering import errors

from .ref_helpers import pink_noise_stereo, write_wav, write_flac, write_mp3_ffmpeg, ref_config, ffmpeg_available


def _make_ref_folder(tmp_path, files: dict):
    d = tmp_path / "refs"
    d.mkdir()
    for name, audio_and_writer in files.items():
        audio, writer = audio_and_writer
        writer(d / name, audio, 44100)
    return str(d)


def test_tc280_wav_hash_unchanged_after_run(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    ref_dir = _make_ref_folder(tmp_path, {"a.wav": (audio, write_wav)})
    p = os.path.join(ref_dir, "a.wav")
    before = compute_file_hash(p)
    ref_pipeline.analyze_set(ref_dir, config=ref_config(hf_min_duration_s=2.0))
    after = compute_file_hash(p)
    assert before == after


def test_tc281_flac_hash_unchanged_after_run(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    ref_dir = _make_ref_folder(tmp_path, {"a.flac": (audio, write_flac)})
    p = os.path.join(ref_dir, "a.flac")
    before = compute_file_hash(p)
    ref_pipeline.analyze_set(ref_dir, config=ref_config(hf_min_duration_s=2.0))
    after = compute_file_hash(p)
    assert before == after


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc282_mp3_hash_unchanged_after_run(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    d = tmp_path / "refs"
    d.mkdir()
    p = write_mp3_ffmpeg(d / "a.mp3", audio, 44100, bitrate_kbps=192)
    before = compute_file_hash(p)
    ref_pipeline.analyze_set(str(d), config=ref_config(hf_min_duration_s=2.0))
    after = compute_file_hash(p)
    assert before == after


def test_tc283_no_disk_artifact_written(tmp_path):
    """TC-283: snapshot temp directory contents before/after a run --
    no decoded/intermediate audio artifact should persist."""
    audio = pink_noise_stereo(44100, 5.0)
    ref_dir = _make_ref_folder(tmp_path, {"a.wav": (audio, write_wav)})

    tmp_dir = tempfile.gettempdir()
    before = set(os.listdir(tmp_dir))
    ref_pipeline.analyze_set(ref_dir, config=ref_config(hf_min_duration_s=2.0))
    after = set(os.listdir(tmp_dir))
    new_files = after - before
    assert not new_files, f"New files appeared in temp dir after run: {new_files}"


def test_tc284_corrupt_file_does_not_compromise_remaining_integrity(tmp_path):
    d = tmp_path / "refs"
    d.mkdir()
    good_paths = []
    for i in range(4):
        audio = pink_noise_stereo(44100, 5.0, seed=i)
        p = write_wav(d / f"good{i}.wav", audio, 44100)
        good_paths.append(p)
    bad_path = d / "bad.wav"
    bad_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt truncated garbage")

    before_hashes = {p: compute_file_hash(p) for p in good_paths}
    result = ref_pipeline.analyze_set(str(d), config=ref_config(hf_min_duration_s=2.0))
    after_hashes = {p: compute_file_hash(p) for p in good_paths}

    assert before_hashes == after_hashes
    assert len(result.failures) == 1
    assert "bad.wav" in result.failures[0]["path"]
    assert len(result.per_track) == 4


def test_ref_hash_reverification_mechanism_present(tmp_path):
    """Architecture.md Section 10 explicitly requires: '[R5]'s
    run-completion step re-hashes every file that was successfully ingested
    and asserts the set matches -- a NonDestructiveIntegrityError is raised
    if any mismatch is found.' This test tampers with a reference file
    *during* analysis (after ingest, before the run completes) and expects
    analyze_set() to detect the mismatch and raise
    errors.NonDestructiveIntegrityError, per that explicit architectural
    requirement. See defects.md DEF-105 if this fails."""
    audio = pink_noise_stereo(44100, 5.0)
    ref_dir = _make_ref_folder(tmp_path, {"a.wav": (audio, write_wav)})
    target_path = os.path.join(ref_dir, "a.wav")

    original_analyze_track = ref_pipeline.analyze_track
    call_count = {"n": 0}

    def _tamper_after_ingest(path, config):
        result = original_analyze_track(path, config)
        call_count["n"] += 1
        if os.path.normpath(path) == os.path.normpath(target_path):
            # Simulate a mid-run mutation of the input file, after its hash
            # was computed at ingest time.
            with open(target_path, "ab") as fh:
                fh.write(b"\x00\x00\x00\x00")
        return result

    import unittest.mock as mock
    with mock.patch.object(ref_pipeline, "analyze_track", side_effect=_tamper_after_ingest):
        with pytest.raises(errors.NonDestructiveIntegrityError):
            ref_pipeline.analyze_set(ref_dir, config=ref_config(hf_min_duration_s=2.0))
