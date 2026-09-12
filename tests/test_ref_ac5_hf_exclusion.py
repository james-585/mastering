"""STORY-002 AC5 -- lossy-source HF exclusion / lossless-confidence
thresholds / per-sample-rate subsetting. TC-260-TC-267."""
from __future__ import annotations

import pytest

from suno_mastering.reference_analysis.aggregate import build_aggregates

from .ref_helpers import make_stub_measurements, ref_config


def _hf_44k(agg):
    return next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.44100hz")


def test_tc260_mp3_excluded_from_hf_but_still_per_track_reported():
    tracks = (
        [make_stub_measurements(f"lossless{i}", lossless=True, container="wav") for i in range(4)]
        + [make_stub_measurements("mp3one", lossless=False, container="mp3", hf_rolloff_hz=16000.0)]
    )
    agg = build_aggregates(tracks, ref_config())
    hf = _hf_44k(agg)
    assert hf.n == 4
    assert set(hf.contributing_tracks) == {f"lossless{i}" for i in range(4)}
    excluded_paths = {e["track"]: e["reason"] for e in hf.excluded}
    assert "mp3one" in excluded_paths
    assert "lossy" in excluded_paths["mp3one"].lower() or "mp3" in excluded_paths["mp3one"].lower()
    # Per-track HF-extension is still populated for the MP3 track itself
    # (AC1 requires it be reported per-track regardless of aggregate membership).
    mp3_track = next(t for t in tracks if t.track_path == "mp3one")
    assert mp3_track.hf_extension.hf_band_limit_hz is not None


def test_tc261_mp3_not_excluded_from_non_hf_aggregates():
    tracks = (
        [make_stub_measurements(f"lossless{i}", lossless=True) for i in range(4)]
        + [make_stub_measurements("mp3one", lossless=False, container="mp3")]
    )
    agg = build_aggregates(tracks, ref_config())
    for metric in ("integrated_lufs", "lra_lu", "dynamic_range_db_exact",
                   "seven_band.mid.relative_db", "mono_sum.mono_sum_level_change_db"):
        a = next(a for a in agg if a.metric == metric)
        assert a.n == 5, f"{metric} expected n=5, got {a.n}"


@pytest.mark.parametrize("n_lossless,expect_omitted,expect_low_confidence", [
    (0, True, False),   # TC-262: N=0 omits entirely
    (1, False, True),   # TC-263: N=1 flags low-confidence
    (2, False, True),   # TC-264: N=2 flags low-confidence (inclusive boundary)
    (3, False, False),  # TC-265: N=3 reports normally, unflagged
])
def test_tc262_265_lossless_n_confidence_thresholds(n_lossless, expect_omitted, expect_low_confidence):
    lossless_tracks = [make_stub_measurements(f"lossless{i}", lossless=True) for i in range(n_lossless)]
    mp3_tracks = [make_stub_measurements(f"mp3_{i}", lossless=False, container="mp3") for i in range(5 - n_lossless)]
    tracks = lossless_tracks + mp3_tracks
    agg = build_aggregates(tracks, ref_config())
    hf = _hf_44k(agg)

    if expect_omitted:
        assert hf.n == 0
        assert hf.median is None
        assert hf.note is not None and "no lossless" in hf.note.lower()
    else:
        assert hf.n == n_lossless
        if expect_low_confidence:
            assert hf.note is not None and "low-confidence" in hf.note.lower()
        else:
            assert hf.note is None


def test_tc266_mixed_sample_rates_hf_never_blended():
    tracks = (
        [make_stub_measurements(f"a{i}", sample_rate=44100, lossless=True) for i in range(4)]
        + [make_stub_measurements(f"b{i}", sample_rate=48000, lossless=True) for i in range(2)]
    )
    agg = build_aggregates(tracks, ref_config())
    hf_44 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.44100hz")
    hf_48 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.48000hz")
    assert hf_44.n == 4
    assert hf_48.n == 2
    # No single blended entry covering all 6 tracks.
    hf_entries = [a for a in agg if a.metric.startswith("hf_extension_hf_band_limit_hz.")]
    assert len(hf_entries) == 2
    assert sum(a.n for a in hf_entries) == 6


def test_tc267_mono_mp3_at_minority_rate_exercises_all_three_exclusions():
    tracks = (
        [make_stub_measurements(f"a{i}", sample_rate=44100, lossless=True) for i in range(4)]
        + [make_stub_measurements("b0", sample_rate=48000, lossless=True)]
        + [make_stub_measurements("mono_mp3_48k", sample_rate=48000, lossless=False,
                                   container="mp3", is_mono=True)]
    )
    agg = build_aggregates(tracks, ref_config())

    hf_48 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.48000hz")
    # (a) mono MP3 excluded from HF-extension aggregate on lossy grounds,
    # never qualifying as a lossless contributor to any subset.
    assert hf_48.n == 1
    assert "mono_mp3_48k" not in hf_48.contributing_tracks
    hf_reasons = {e["track"]: e["reason"] for e in hf_48.excluded}
    assert "mono_mp3_48k" in hf_reasons
    assert "lossy" in hf_reasons["mono_mp3_48k"].lower() or "mp3" in hf_reasons["mono_mp3_48k"].lower()

    # (b) excluded from stereo-width and mono-compatibility aggregates on mono grounds.
    corr = next(a for a in agg if a.metric == "overall_correlation")
    assert "mono_mp3_48k" not in corr.contributing_tracks
    corr_reasons = {e["track"]: e["reason"] for e in corr.excluded}
    assert "mono" in corr_reasons["mono_mp3_48k"].lower()

    # (c) still contributes normally to LUFS/LRA/DR/seven-band aggregates.
    lufs = next(a for a in agg if a.metric == "integrated_lufs")
    assert "mono_mp3_48k" in lufs.contributing_tracks
    assert lufs.n == 6

    # (d) two distinct exclusion reasons for the same track, not conflated.
    assert corr_reasons["mono_mp3_48k"] != hf_reasons["mono_mp3_48k"]

    # (e) remaining tracks' exclusion behavior unaffected.
    hf_44 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.44100hz")
    assert hf_44.n == 4
