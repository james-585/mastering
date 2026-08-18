import numpy as np

from pathlib import Path

from real_world_validation import build_validation_report
from human_review_capture import HumanReviewRecord


def _real_human_review(decision: str, note: str) -> HumanReviewRecord:
    return HumanReviewRecord(
        reviewer="qa-automation-engineer",
        decision=decision,
        note=note,
        reviewed_at="2026-08-17T00:00:00+00:00",
        method="review_file",
    )


def test_story017_real_world_validation_report_is_auditable():
    paths = [
        "C:/Users/james/Documents/suno-mastering/Reference Tracks/Sunday Club.wav",
        "C:/Users/james/Documents/suno-mastering/Reference Tracks/Wavy_Gravy.wav",
        "C:/Users/james/Documents/suno-mastering/Reference Tracks/Leftfield_-_Melt_Audio.wav",
    ]
    human_reviews = {
        str(Path(path)): _real_human_review("pass", "Listened through on monitors; balance and loudness sound convincing and safe.")
        for path in paths
    }

    report = build_validation_report(paths, human_reviews=human_reviews)

    assert report["num_files"] == 3
    assert report["overall_decision"] in {"pass", "refine", "reject"}
    assert report["accepted_parameters"]["oversample"] == 8
    assert report["accepted_parameters"]["float64_processing"] is True

    for item in report["files"]:
        assert item["decision"] in {"pass", "refine", "reject"}
        assert item["auditable_summary"]
        assert item["tuning_decisions"]
        assert all("evidence" in decision for decision in item["tuning_decisions"])


def test_story017_validation_rejects_weak_but_safe_outcomes():
    # A quiet, near-featureless tone rather than literal digital silence: the
    # grounded module's mandatory LUFS-matching precondition (§4) raises
    # LevelMatchError on true silence (BS.1770 gates it to -inf, non-finite),
    # now that orchestration.py routes through it inline (DEF-2501) -- a real
    # "musically weak" negative-control case must still be measurable.
    sr = 48000
    quiet_tone = 0.01 * np.sin(2 * np.pi * 220.0 * np.arange(sr) / sr)
    flat = np.column_stack([quiet_tone, quiet_tone]).astype(np.float64)
    human_reviews = {
        "synthetic_validation_case": _real_human_review(
            "reject", "This synthetic case is musically weak; there is no convincing content to accept."
        )
    }
    report = build_validation_report([], synthetic_case=flat, human_reviews=human_reviews)

    assert report["overall_decision"] == "reject"
    assert any("musically weak" in decision["reason"].lower() for decision in report["files"][0]["tuning_decisions"])
