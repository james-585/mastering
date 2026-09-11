import numpy as np
import pytest

from pathlib import Path

from real_world_validation import build_validation_report
from suno_mastering.quality_review.human_review_capture import HumanReviewRecord

# Real reference tracks, not committed to the repo (large, commercially
# licensed audio) -- this is a local-only regression gate. Resolved relative
# to the repo root rather than hardcoded to one machine's home directory, and
# skipped (not failed) when the files aren't present, e.g. in CI.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_REFERENCE_DIR = _REPO_ROOT / "Reference Tracks"
_TRACK_NAMES = ["Sunday Club.wav", "Wavy_Gravy.wav", "Leftfield_-_Melt_Audio.wav"]
_ALL_TRACKS_PRESENT = all((_REFERENCE_DIR / name).exists() for name in _TRACK_NAMES)


def _real_human_review(decision: str, note: str) -> HumanReviewRecord:
    return HumanReviewRecord(
        reviewer="qa-automation-engineer",
        decision=decision,
        note=note,
        reviewed_at="2026-08-17T00:00:00+00:00",
        method="review_file",
    )


@pytest.mark.skipif(not _ALL_TRACKS_PRESENT, reason="local-only reference tracks not present")
def test_story017_real_world_validation_report_is_auditable():
    paths = [str(_REFERENCE_DIR / name) for name in _TRACK_NAMES]
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
