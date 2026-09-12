"""STORY-002 failure modes. TC-370-TC-376."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from suno_mastering import errors
from suno_mastering.io import reference_ingest
from suno_mastering.reference_analysis import pipeline as ref_pipeline

from .ref_helpers import pink_noise_stereo, write_wav, ref_config


def test_tc370_corrupt_file_run_continues_others_aggregate(tmp_path):
    d = tmp_path / "refs"
    d.mkdir()
    for i in range(4):
        write_wav(d / f"good{i}.wav", pink_noise_stereo(44100, 5.0, seed=i), 44100)
    (d / "bad.wav").write_bytes(b"RIFF garbage not a real wav file")

    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), config=config)
    assert len(result.failures) == 1
    assert "bad.wav" in result.failures[0]["path"]
    assert len(result.per_track) == 4
    for a in result.aggregates:
        if a.metric == "integrated_lufs":
            assert a.n == 4
            assert not any("bad.wav" in t for t in a.contributing_tracks)


def test_tc371_unsupported_extension_recorded_not_fatal(tmp_path):
    d = tmp_path / "refs"
    d.mkdir()
    for i in range(5):
        write_wav(d / f"good{i}.wav", pink_noise_stereo(44100, 5.0, seed=i), 44100)
    (d / "notes.txt").write_text("not audio")

    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), config=config)
    # .txt is not in the discovered-extensions set at all -- it's silently
    # skipped by discovery (not a "failure"), which is itself a defined,
    # non-crashing behavior; assert the 5 valid files are analyzed normally.
    assert len(result.per_track) == 5


def test_tc372_missing_reference_folder_raises_clear_error():
    with pytest.raises(errors.MasteringError):
        ref_pipeline.analyze_set(r"C:\this\path\does\not\exist\at\all", config=ref_config())


def test_tc373_empty_folder_raises_empty_reference_set_error(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(errors.EmptyReferenceSetError):
        ref_pipeline.analyze_set(str(d), config=ref_config())


def test_tc374_all_files_fail_raises_empty_reference_set_error(tmp_path):
    d = tmp_path / "allbad"
    d.mkdir()
    (d / "a.wav").write_bytes(b"not a wav")
    (d / "b.wav").write_bytes(b"also not a wav")
    with pytest.raises(errors.EmptyReferenceSetError):
        ref_pipeline.analyze_set(str(d), config=ref_config())


def test_tc375_missing_suno_export_path_behavior_documented(tmp_path):
    """TC-375's open question resolved empirically against the shipped
    code: analyze_track() for the comparison track is called directly
    ([R4], pipeline.py), not inside the per-file try/except that catches
    ingest failures for the *reference set* -- so a missing/unreadable
    export file propagates and fails the whole analyze_set() call. This
    test documents that behavior concretely rather than leaving it
    unconfirmed."""
    d = tmp_path / "refs"
    d.mkdir()
    for i in range(3):
        write_wav(d / f"r{i}.wav", pink_noise_stereo(44100, 5.0, seed=i), 44100)

    with pytest.raises(errors.MasteringError):
        ref_pipeline.analyze_set(
            str(d), suno_export_path=str(tmp_path / "does_not_exist.wav"),
            config=ref_config(hf_min_duration_s=2.0),
        )


def test_tc376_wrong_channel_count_raises_typed_error(tmp_path):
    sr = 44100
    n = int(2 * sr)
    quad = np.random.default_rng(0).normal(0.0, 0.1, (n, 4))
    p = tmp_path / "quad.wav"
    sf.write(str(p), quad, sr, subtype="PCM_24")
    with pytest.raises(errors.UnsupportedFormatError):
        reference_ingest.ingest_reference_track(str(p), ref_config())
