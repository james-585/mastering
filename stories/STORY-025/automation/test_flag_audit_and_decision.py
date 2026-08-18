"""TC-2511 - TC-2520: flag audit-line format and evaluate_quality_review's
decision authority (Gate 1 Findings 1/2, AC8/AC9)."""
from __future__ import annotations

import pytest

from grounded_quality_review import evaluate_quality_review

from conftest import (
    ARTIFACT_FLAG_CLEAR,
    DR_FLAG_CLEAR,
    F2504_ORIGINAL_RELATIVE_DB,
    make_f2501,
    patch_artifacts,
    patch_dynamic_range,
    patch_no_flags,
    patch_seven_band,
    uniform_band_deltas,
)


def _patch_all_flags_fire(monkeypatch):
    patch_dynamic_range(monkeypatch, *DR_FLAG_CLEAR)  # dr_delta = -5.0
    patch_artifacts(monkeypatch, *ARTIFACT_FLAG_CLEAR)  # delta = 0.10
    original_db = {b: 0.0 for b in F2504_ORIGINAL_RELATIVE_DB}
    processed_db = uniform_band_deltas(5.0)  # spectral_rms_shift_db = 5.00
    patch_seven_band(monkeypatch, original_db, processed_db)


def test_tc2511_all_three_flags_audit_lines(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    _patch_all_flags_fire(monkeypatch)

    result = evaluate_quality_review(original, processed, sr, human_review=None)

    assert (
        "artifact_density_regression flag (PROVISIONAL threshold 0.05, not calibrated against "
        "reference data): raw artifact_density_delta = +0.1000"
    ) in result.audit
    assert (
        "spectral_shift_significant flag (PROVISIONAL threshold 2.0 dB, not calibrated against "
        "reference data): raw spectral_rms_shift_db = 5.00 dB"
    ) in result.audit

    dr_lines = [line for line in result.audit if "dynamic_range_regression" in line]
    assert len(dr_lines) == 1
    assert "-5.00" in dr_lines[0]
    assert "PROVISIONAL" not in dr_lines[0]


def test_tc2512_flag_lines_identical_whether_human_review_none_or_populated(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    _patch_all_flags_fire(monkeypatch)
    result_a = evaluate_quality_review(original, processed, sr, human_review=None)

    _patch_all_flags_fire(monkeypatch)
    result_b = evaluate_quality_review(
        original, processed, sr,
        human_review={"reviewer": "J. Doe", "decision": "refine", "note": "Kick still a bit thin after gain matching."},
    )

    flag_lines_a = result_a.audit[1:]
    flag_lines_b = result_b.audit[1:]
    assert flag_lines_a == flag_lines_b


def test_tc2513_dr_regression_line_has_no_provisional_caveat(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_dynamic_range(monkeypatch, *DR_FLAG_CLEAR)

    result = evaluate_quality_review(original, processed, sr, human_review=None)

    dr_lines = [line for line in result.audit if "dynamic_range_regression" in line]
    assert len(dr_lines) == 1
    assert "-5.00" in dr_lines[0]
    assert "PROVISIONAL" not in dr_lines[0]


def test_tc2514_no_flags_no_flag_derived_audit_lines(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)

    result = evaluate_quality_review(original, processed, sr, human_review=None)

    assert result.flags == []
    assert result.audit == [
        "No human listening review was supplied; this result is evidence only "
        "and must not be treated as a trusted pass/reject/refine verdict."
    ]


def test_tc2515_human_review_none_produces_pending_human_review(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)

    result = evaluate_quality_review(original, processed, sr, human_review=None)

    assert result.decision == "pending_human_review"
    assert result.human_decision is None
    assert result.human_note == ""
    assert result.audit[0] == (
        "No human listening review was supplied; this result is evidence only "
        "and must not be treated as a trusted pass/reject/refine verdict."
    )


def test_tc2516_populated_human_review_sets_decision(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    human_review = {
        "reviewer": "A. Reviewer",
        "decision": "pass",
        "note": "Clear improvement in low-end definition, no new artifacts audible.",
    }

    result = evaluate_quality_review(original, processed, sr, human_review=human_review)

    assert result.decision == "pass"
    assert result.human_decision == "pass"
    assert result.human_note == "Clear improvement in low-end definition, no new artifacts audible."
    assert result.audit[0] == (
        "Human review (A. Reviewer): Clear improvement in low-end definition, "
        "no new artifacts audible."
    )


def test_tc2517_missing_reviewer_key_defaults_to_unspecified(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    human_review = {
        "decision": "refine",
        "note": "Needs another pass on the top end, slightly harsh above 8 kHz.",
    }

    result = evaluate_quality_review(original, processed, sr, human_review=human_review)

    assert result.audit[0] == (
        "Human review (unspecified): Needs another pass on "
        "the top end, slightly harsh above 8 kHz."
    )


def test_tc2518_invalid_decision_raises_value_error(monkeypatch):
    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    human_review = {"reviewer": "X", "decision": "maybe", "note": "Not sure, needs a second listen."}

    with pytest.raises(ValueError):
        evaluate_quality_review(original, processed, sr, human_review=human_review)


def test_tc2519_deterministic_before_after_across_two_runs(monkeypatch):
    original, processed, sr = make_f2501(3.0)

    def patch_all():
        patch_dynamic_range(monkeypatch, 10.0, 8.0)
        patch_artifacts(monkeypatch, 0.10, 0.12)
        patch_seven_band(monkeypatch, F2504_ORIGINAL_RELATIVE_DB, {b: (0.5 if b != "mid" else 0.0) for b in F2504_ORIGINAL_RELATIVE_DB})

    patch_all()
    result1 = evaluate_quality_review(original.copy(), processed.copy(), sr, human_review=None)
    patch_all()
    result2 = evaluate_quality_review(original.copy(), processed.copy(), sr, human_review=None)

    assert result1.before_after.keys() == result2.before_after.keys()
    for key in result1.before_after:
        assert result1.before_after[key] == pytest.approx(result2.before_after[key], abs=1e-9)


def test_tc2520_before_after_flattens_spectral_band_delta(monkeypatch):
    from conftest import F2504_PROCESSED_RELATIVE_DB

    original, processed, sr = make_f2501(0.0)
    patch_no_flags(monkeypatch)
    patch_seven_band(monkeypatch, F2504_ORIGINAL_RELATIVE_DB, F2504_PROCESSED_RELATIVE_DB)

    result = evaluate_quality_review(original, processed, sr, human_review=None)

    for band in F2504_ORIGINAL_RELATIVE_DB:
        assert f"spectral_band_delta_db.{band}" in result.before_after
        assert isinstance(result.before_after[f"spectral_band_delta_db.{band}"], float)

    for key in ("dr_delta", "artifact_density_delta", "width_delta", "peak_delta_db_unmatched",
                "spectral_rms_shift_db", "lufs_gain_applied_db"):
        assert key in result.before_after
