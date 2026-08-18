"""TC-2501 - TC-2510: compute_grounded_metrics() / GroundedMetrics (AC1, AC2, AC4, AC5, AC6).

Mocking convention per test-cases.md: monkeypatch.setattr on the names as
imported into grounded_quality_review.py's module namespace (OQ-A).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from grounded_quality_review import GroundedMetrics, compute_grounded_metrics
from lufs_matching import LevelMatchError, LevelMatchResult

from conftest import (
    ARTIFACT_FLAG_CLEAR,
    ARTIFACT_NO_FLAG,
    DR_FLAG_BOUNDARY,
    DR_NO_FLAG,
    F2504_ORIGINAL_RELATIVE_DB,
    F2504_PROCESSED_RELATIVE_DB,
    make_f2501,
    make_f2503,
    patch_artifacts,
    patch_dynamic_range,
    patch_no_flags,
    patch_seven_band,
)


def test_tc2501_spectral_rms_shift_excludes_mid(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_seven_band(monkeypatch, F2504_ORIGINAL_RELATIVE_DB, F2504_PROCESSED_RELATIVE_DB)
    patch_dynamic_range(monkeypatch, *DR_NO_FLAG)
    patch_artifacts(monkeypatch, *ARTIFACT_NO_FLAG)

    metrics = compute_grounded_metrics(original, processed, sr)

    assert metrics.spectral_band_delta_db["mid"] == 0.0
    expected = math.sqrt(19 / 6)
    wrong = math.sqrt(19 / 7)
    assert metrics.spectral_rms_shift_db == pytest.approx(expected, abs=0.001)
    assert metrics.spectral_rms_shift_db != pytest.approx(wrong, abs=0.001)


def test_tc2502_spectral_band_delta_all_seven_bands(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_seven_band(monkeypatch, F2504_ORIGINAL_RELATIVE_DB, F2504_PROCESSED_RELATIVE_DB)

    metrics = compute_grounded_metrics(original, processed, sr)

    assert set(metrics.spectral_band_delta_db.keys()) == set(F2504_ORIGINAL_RELATIVE_DB.keys())
    expected = {
        "sub": 2.0, "low": -1.0, "low_mid": 0.0, "mid": 0.0,
        "high_mid": 3.0, "high": -2.0, "air": 1.0,
    }
    for band, value in expected.items():
        assert metrics.spectral_band_delta_db[band] == pytest.approx(value, abs=0.001)


def test_tc2503_dr_delta_sign_convention(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_dynamic_range(monkeypatch, 10.0, 7.0)

    metrics = compute_grounded_metrics(original, processed, sr)

    assert metrics.dr_delta == pytest.approx(-3.0, abs=1e-9)


@pytest.mark.parametrize(
    "dr_pair,expect_flag",
    [(DR_FLAG_BOUNDARY, True), (DR_NO_FLAG, False)],
)
def test_tc2504_dr_delta_boundary(monkeypatch, dr_pair, expect_flag):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_dynamic_range(monkeypatch, *dr_pair)

    metrics = compute_grounded_metrics(original, processed, sr)

    expected_delta = dr_pair[1] - dr_pair[0]
    assert metrics.dr_delta == pytest.approx(expected_delta, abs=1e-9)
    assert ("dynamic_range_regression" in metrics.flags) is expect_flag


def test_tc2505_artifact_density_delta_sign_convention(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_artifacts(monkeypatch, 0.10, 0.20)

    metrics = compute_grounded_metrics(original, processed, sr)

    assert metrics.artifact_density_delta == pytest.approx(0.10, abs=1e-9)


@pytest.mark.parametrize(
    "artifact_pair,expect_flag",
    [(ARTIFACT_FLAG_CLEAR, True), ((0.10, 0.150), True), ((0.10, 0.149), False)],
)
def test_tc2506_artifact_density_boundary(monkeypatch, artifact_pair, expect_flag):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_artifacts(monkeypatch, *artifact_pair)

    metrics = compute_grounded_metrics(original, processed, sr)

    expected_delta = round(artifact_pair[1] - artifact_pair[0], 3)
    assert metrics.artifact_density_delta == pytest.approx(expected_delta, abs=1e-9)
    assert ("artifact_density_regression" in metrics.flags) is expect_flag


@pytest.mark.parametrize("x,expect_flag", [(2.00, True), (1.99, False)])
def test_tc2507_spectral_shift_flag_boundary(monkeypatch, x, expect_flag):
    from conftest import uniform_band_deltas

    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    original_db = {b: 0.0 for b in F2504_ORIGINAL_RELATIVE_DB}
    processed_db = uniform_band_deltas(x)
    patch_seven_band(monkeypatch, original_db, processed_db)

    metrics = compute_grounded_metrics(original, processed, sr)

    assert metrics.spectral_rms_shift_db == pytest.approx(x, abs=0.001)
    assert ("spectral_shift_significant" in metrics.flags) is expect_flag


def test_tc2508_match_levels_called_first_and_processed_side_uses_matched_array(monkeypatch):
    import grounded_quality_review as gqr

    original, processed, sr = make_f2501(6.0)
    call_order = []

    real_match = gqr.match_levels

    def spy_match_levels(orig, proc, sr_, tol):
        call_order.append("match_levels")
        return real_match(orig, proc, sr_, tol)

    seen_processed_args = {}

    def spy_seven_band(audio, sr_, config):
        call_order.append("measure_seven_band_balance")
        seen_processed_args.setdefault("seven_band", []).append(audio)
        from conftest import make_seven_band_result
        return make_seven_band_result(F2504_ORIGINAL_RELATIVE_DB)

    def spy_dr(audio, sr_, config):
        call_order.append("measure_dynamic_range")
        seen_processed_args.setdefault("dr", []).append(audio)
        return 10.0

    def spy_artifacts(audio, sr_):
        call_order.append("detect_artifacts")
        seen_processed_args.setdefault("artifacts", []).append(audio)
        from conftest import FakeArtifactResult
        return None, FakeArtifactResult(overall_artifact_density_score=0.1)

    monkeypatch.setattr(gqr, "match_levels", spy_match_levels)
    monkeypatch.setattr(gqr, "measure_seven_band_balance", spy_seven_band)
    monkeypatch.setattr(gqr, "measure_dynamic_range", spy_dr)
    monkeypatch.setattr(gqr, "detect_artifacts", spy_artifacts)

    gqr.compute_grounded_metrics(original, processed, sr)

    assert call_order[0] == "match_levels"
    assert call_order.index("match_levels") < call_order.index("measure_seven_band_balance")
    assert call_order.index("match_levels") < call_order.index("measure_dynamic_range")
    assert call_order.index("match_levels") < call_order.index("detect_artifacts")

    expected_gain = 10 ** (-6.0 / 20.0)
    matched_processed = processed * expected_gain
    # The second recorded call for each spy is the "processed" side.
    np.testing.assert_allclose(seen_processed_args["seven_band"][1], matched_processed, atol=1e-6)
    np.testing.assert_allclose(seen_processed_args["dr"][1], matched_processed, atol=1e-6)
    np.testing.assert_allclose(seen_processed_args["artifacts"][1], matched_processed, atol=1e-6)


def test_tc2509_match_levels_failure_propagates_and_measurements_not_attempted(monkeypatch):
    import grounded_quality_review as gqr

    original, processed, sr = make_f2503()

    called = {"seven_band": False, "dr": False, "artifacts": False}

    def spy_seven_band(*a, **k):
        called["seven_band"] = True
        raise AssertionError("should not be called")

    def spy_dr(*a, **k):
        called["dr"] = True
        raise AssertionError("should not be called")

    def spy_artifacts(*a, **k):
        called["artifacts"] = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(gqr, "measure_seven_band_balance", spy_seven_band)
    monkeypatch.setattr(gqr, "measure_dynamic_range", spy_dr)
    monkeypatch.setattr(gqr, "detect_artifacts", spy_artifacts)

    with pytest.raises(LevelMatchError):
        gqr.compute_grounded_metrics(original, processed, sr)

    assert called == {"seven_band": False, "dr": False, "artifacts": False}


def test_tc2510_width_and_peak_computed_on_raw_unmatched_pair(monkeypatch):
    import grounded_quality_review as gqr

    original, processed, sr = make_f2501(6.0)
    patch_no_flags(monkeypatch)

    seen = {}
    real_true_peak = gqr._true_peak
    real_stereo_width = gqr._stereo_width

    def spy_true_peak(audio, oversample=8):
        seen.setdefault("true_peak_args", []).append(np.array(audio, copy=True))
        return real_true_peak(audio, oversample)

    def spy_stereo_width(audio):
        seen.setdefault("stereo_width_args", []).append(np.array(audio, copy=True))
        return real_stereo_width(audio)

    monkeypatch.setattr(gqr, "_true_peak", spy_true_peak)
    monkeypatch.setattr(gqr, "_stereo_width", spy_stereo_width)

    gqr.compute_grounded_metrics(original, processed, sr)

    # Implementation computes peak_delta_db_unmatched as _true_peak(proc) then
    # _true_peak(orig) -- the first recorded call is the "processed" side.
    processed_arg_true_peak = seen["true_peak_args"][0]
    np.testing.assert_allclose(processed_arg_true_peak, processed, atol=1e-9)
