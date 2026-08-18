"""TC-2531 - TC-2537: match_levels() (architecture.md §4)."""
from __future__ import annotations

import numpy as np
import pytest

from lufs_matching import LevelMatchError, match_levels

from conftest import make_f2501, make_f2501_stereo, make_f2502, make_f2503


def test_tc2531_no_op_like_case_small_correction_always_applied():
    original, processed, sr = make_f2501(0.3)

    result = match_levels(original, processed, sr, tolerance_lu=0.5)

    assert result.gain_applied_db == pytest.approx(-0.3, abs=0.01)
    assert result.matched_processed_lufs == pytest.approx(result.original_lufs, abs=0.01)
    assert result.within_tolerance is True


def test_tc2532_gain_correction_case():
    original, processed, sr = make_f2501(6.0)

    result = match_levels(original, processed, sr, tolerance_lu=0.5)

    assert result.gain_applied_db == pytest.approx(-6.0, abs=0.01)
    assert result.matched_processed_lufs == pytest.approx(result.original_lufs, abs=0.01)
    assert result.within_tolerance is True
    expected_matched = processed * (10 ** (-6.0 / 20.0))
    np.testing.assert_allclose(result.matched_processed, expected_matched, atol=1e-6)


def test_tc2533_stereo_pair_gain_applied_identically_to_both_channels():
    original_stereo, processed_stereo, sr = make_f2501_stereo(4.0)

    result = match_levels(original_stereo, processed_stereo, sr, tolerance_lu=0.5)

    np.testing.assert_allclose(
        result.matched_processed[:, 0], result.matched_processed[:, 1], atol=1e-9
    )
    assert result.gain_applied_db == pytest.approx(-4.0, abs=0.01)


def test_tc2534_boundary_residual_exactly_at_tolerance_is_within(monkeypatch):
    import lufs_matching as lm

    original, processed, sr = make_f2501(1.0)
    values = iter([-14.0, -15.0, -14.5])

    def fake_measure(audio, sr_):
        return next(values)

    monkeypatch.setattr(lm, "measure_integrated_lufs", fake_measure)

    result = match_levels(original, processed, sr, tolerance_lu=0.5)

    assert result.within_tolerance is True


def test_tc2535_boundary_residual_over_tolerance_raises(monkeypatch):
    import lufs_matching as lm

    original, processed, sr = make_f2501(1.0)
    values = iter([-14.0, -15.0, -14.501])

    def fake_measure(audio, sr_):
        return next(values)

    monkeypatch.setattr(lm, "measure_integrated_lufs", fake_measure)

    with pytest.raises(LevelMatchError):
        match_levels(original, processed, sr, tolerance_lu=0.5)


def test_tc2536_non_finite_lufs_silence_raises():
    original, processed, sr = make_f2503()

    with pytest.raises(LevelMatchError):
        match_levels(original, processed, sr, tolerance_lu=0.5)


def test_tc2537_bimodal_gating_edge_case_well_defined_outcome():
    original, processed, sr = make_f2502()

    try:
        result = match_levels(original, processed, sr, tolerance_lu=0.5)
    except LevelMatchError:
        return  # well-defined outcome (a)

    assert result.within_tolerance is True  # well-defined outcome (b)
    assert np.isfinite(result.gain_applied_db)
