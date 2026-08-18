"""TC-2538 - TC-2540: human_review_capture.py (architecture.md §6, AC8/AC9)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from human_review_capture import HumanReviewRequiredError, capture_human_review


def _write_review(track_path: Path, payload: dict) -> Path:
    review_path = Path(str(track_path) + ".review.json")
    review_path.write_text(json.dumps(payload))
    return review_path


def test_tc2538_templated_note_rejected(tmp_path):
    track = tmp_path / "track.wav"
    track.write_bytes(b"x")
    _write_review(track, {
        "reviewer": "j",
        "decision": "reject",
        "note": "REJECT — real-world validation on Sunday Club; the source remained musically weak...",
        "reviewed_at": "2026-08-17T00:00:00Z",
    })

    with pytest.raises(HumanReviewRequiredError):
        capture_human_review(track, interactive=False)


def test_tc2539_note_shorter_than_10_chars_rejected(tmp_path):
    track = tmp_path / "track.wav"
    track.write_bytes(b"x")
    _write_review(track, {
        "reviewer": "j",
        "decision": "pass",
        "note": "ok good.",
        "reviewed_at": "2026-08-17T00:00:00Z",
    })

    with pytest.raises(HumanReviewRequiredError):
        capture_human_review(track, interactive=False)


def test_tc2539_note_exactly_10_chars_accepted(tmp_path):
    track = tmp_path / "track.wav"
    track.write_bytes(b"x")
    _write_review(track, {
        "reviewer": "j",
        "decision": "pass",
        "note": "acceptable",
        "reviewed_at": "2026-08-17T00:00:00Z",
    })

    record = capture_human_review(track, interactive=False)
    assert record.note == "acceptable"


def test_tc2540_non_interactive_stdin_does_not_fall_through_to_default(tmp_path, monkeypatch):
    track = tmp_path / "track.wav"
    track.write_bytes(b"x")
    # No review file present.

    class _FakeNonTtyStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", _FakeNonTtyStdin())

    with pytest.raises(HumanReviewRequiredError):
        capture_human_review(track, interactive=True)
