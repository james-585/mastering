"""TC-2528 - TC-2530: STORY-015 proxy metrics must not exist in the new module
(negative controls) and must still exist, unmodified, in the deprecated module.
"""
from __future__ import annotations

import dataclasses
import inspect

import grounded_quality_review
from grounded_quality_review import (
    GroundedMetrics,
    QualityReviewResult,
    compute_grounded_metrics,
    evaluate_quality_review,
)


def test_tc2528_spectral_tilt_absent_from_grounded_module():
    assert hasattr(grounded_quality_review, "_spectral_tilt") is False

    field_names = {f.name for f in dataclasses.fields(GroundedMetrics)} | {
        f.name for f in dataclasses.fields(QualityReviewResult)
    }
    forbidden = {"spectral_tilt", "spectral_tilt_delta"}
    assert not (field_names & forbidden)


def test_tc2529_clarity_delta_absent_from_grounded_module():
    assert hasattr(grounded_quality_review, "clarity_delta") is False
    assert hasattr(grounded_quality_review, "clarity_gain") is False

    field_names = {f.name for f in dataclasses.fields(GroundedMetrics)} | {
        f.name for f in dataclasses.fields(QualityReviewResult)
    }
    forbidden = {"clarity_delta", "clarity_gain"}
    assert not (field_names & forbidden)

    source_evaluate = inspect.getsource(evaluate_quality_review)
    source_compute = inspect.getsource(compute_grounded_metrics)
    for forbidden_substr in ("clarity_delta", "_spectral_tilt"):
        assert forbidden_substr not in source_evaluate
        assert forbidden_substr not in source_compute


def test_tc2530_old_proxy_metrics_still_present_in_deprecated_module():
    """Regression lock, not a correctness test (test-cases.md §Section 5) --
    architecture.md §2 explicitly retains final_quality_review.py unmodified."""
    import final_quality_review

    assert hasattr(final_quality_review, "_spectral_tilt")
    source = inspect.getsource(final_quality_review._summary_metrics)
    assert "clarity_delta" in source
