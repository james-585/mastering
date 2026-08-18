"""STORY-002 AC2 -- set aggregate statistics. TC-220-TC-222."""
from __future__ import annotations

import copy

from suno_mastering.reference_analysis.aggregate import build_aggregates

from .ref_helpers import make_stub_measurements, ref_config


def test_tc220_median_min_max_hand_computable(tmp_path):
    """TC-220: 5 tracks with known LUFS values -> exact median/min/max."""
    values = [-18.0, -16.0, -14.0, -12.0, -10.0]
    tracks = [make_stub_measurements(f"t{i}", integrated_lufs=v) for i, v in enumerate(values)]
    agg = build_aggregates(tracks, ref_config())
    lufs = next(a for a in agg if a.metric == "integrated_lufs")
    assert lufs.median == -14.0
    assert lufs.min == -18.0
    assert lufs.max == -10.0
    assert lufs.n == 5


def test_tc221_every_ac1_metric_has_an_aggregate_entry():
    """TC-221: every AC1 metric gets an aggregate entry, on a 5-track
    all-stereo/all-lossless/all-44.1kHz set (no exclusion rules triggered)."""
    tracks = [make_stub_measurements(f"t{i}") for i in range(5)]
    agg = build_aggregates(tracks, ref_config())
    metrics = {a.metric for a in agg}

    expected_scalar = {
        "integrated_lufs", "true_peak_dbtp", "dynamic_range_db_exact", "lra_lu",
        "overall_correlation", "mono_sum.mono_sum_level_change_db",
    }
    assert expected_scalar.issubset(metrics)
    for band in ("sub", "low", "low_mid", "mid", "high_mid", "high", "air"):
        assert f"seven_band.{band}.relative_db" in metrics
        assert f"per_band_stereo_width.{band}" in metrics
    assert any(m.startswith("hf_extension_hf_band_limit_hz.") for m in metrics)


def test_tc222_aggregate_statistics_deterministic():
    """TC-222: same input set run twice through aggregation -> bit-identical
    AggregateStat fields."""
    tracks = [make_stub_measurements(f"t{i}", integrated_lufs=-14.0 - i) for i in range(5)]
    agg1 = build_aggregates(copy.deepcopy(tracks), ref_config())
    agg2 = build_aggregates(copy.deepcopy(tracks), ref_config())
    assert agg1 == agg2
