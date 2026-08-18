"""human_review_capture.py (STORY-025 architecture.md §6).

Real (non-simulated) human listening capture. Two supported input sources,
either of which must yield a fully-populated, non-templated record -- there
is no third "skip" path (§6.1):

1. Structured review file: '<track_path>.review.json' alongside the track,
   containing {"reviewer", "decision", "note", "reviewed_at"}.
2. Interactive CLI prompt via input(), only when interactive=True and stdin
   is a real TTY -- a non-interactive process cannot produce a "real" human
   review, so that path raises rather than silently defaulting (§6.1).

The anti-templating check (§6.2) rejects notes that are too short or that
match the literal auto-generated phrases STORY-017's old _summarise_decision()/
_build_tuning_decisions() used to produce, so a stale copy-paste of the old
auto-text cannot pass as if a human wrote it.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_VALID_DECISIONS = {"pass", "reject", "refine"}
_MIN_NOTE_LENGTH = 10

# Exact templated phrases (or unmistakable fragments of them) that STORY-017's
# old _summarise_decision()/_build_tuning_decisions() generated as auto-text
# standing in for a real listen (§6.2). A note containing any of these cannot
# be accepted as a real human review.
_DENYLIST_PHRASES = (
    "REJECT — real-world validation on",
    "REFINE — real-world validation on",
    "the source remained musically weak",
    "musically weak or over-processed",
    "reviewed under the real product ceiling check",
    "stayed within project safety and audibility rules",
    "the output must be musically convincing to pass",
    "review accepted the actual result and captured the relevant before/after proof",
    "close but not yet product-fit without a more specific corrective change",
    "the validation result is musically weak and not accepted",
    "no meaningful change was introduced",
    "not clearly convincing and needs a human review before acceptance",
)


@dataclass
class HumanReviewRecord:
    reviewer: str
    decision: str            # "pass" | "reject" | "refine"
    note: str
    reviewed_at: str          # ISO 8601
    method: str                # "review_file" | "cli_prompt"

    def as_dict(self) -> dict:
        return {
            "reviewer": self.reviewer,
            "decision": self.decision,
            "note": self.note,
            "reviewed_at": self.reviewed_at,
            "method": self.method,
        }


class HumanReviewRequiredError(RuntimeError):
    """Raised when no valid, non-templated human review can be obtained."""


def _validate_decision(decision: str) -> str:
    lowered = str(decision).strip().lower()
    if lowered not in _VALID_DECISIONS:
        raise HumanReviewRequiredError(
            f"decision must be one of {sorted(_VALID_DECISIONS)}; got {decision!r}"
        )
    return lowered


def _validate_note(note: str) -> str:
    stripped = str(note).strip()
    if len(stripped) < _MIN_NOTE_LENGTH:
        raise HumanReviewRequiredError(
            f"Review note must be at least {_MIN_NOTE_LENGTH} characters after "
            f"stripping; got {len(stripped)} ({stripped!r})."
        )
    lowered = stripped.lower()
    for phrase in _DENYLIST_PHRASES:
        if phrase.lower() in lowered:
            raise HumanReviewRequiredError(
                f"Review note matches a templated auto-generated phrase ({phrase!r}); "
                f"a stale copy of the old auto-text cannot pass as a human review."
            )
    return stripped


def _read_review_file(review_path: Path) -> Optional[HumanReviewRecord]:
    if not review_path.exists():
        return None
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HumanReviewRequiredError(
            f"Could not parse review file {review_path}: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        reviewer = str(data["reviewer"]).strip()
        decision = _validate_decision(data["decision"])
        note = _validate_note(data["note"])
        reviewed_at = str(data["reviewed_at"]).strip()
    except KeyError as exc:
        raise HumanReviewRequiredError(
            f"Review file {review_path} is missing required key {exc}"
        ) from exc

    if not reviewer:
        raise HumanReviewRequiredError(f"Review file {review_path} has an empty 'reviewer'.")
    if not reviewed_at:
        raise HumanReviewRequiredError(f"Review file {review_path} has an empty 'reviewed_at'.")

    return HumanReviewRecord(
        reviewer=reviewer,
        decision=decision,
        note=note,
        reviewed_at=reviewed_at,
        method="review_file",
    )


def _prompt_cli(track_path: Path) -> HumanReviewRecord:
    if not sys.stdin.isatty():
        raise HumanReviewRequiredError(
            f"No review file found for {track_path} and stdin is not a TTY; a "
            f"non-interactive environment cannot produce a real human review."
        )

    print(f"Human review required for: {track_path}")
    reviewer = input("Reviewer name: ").strip()
    if not reviewer:
        raise HumanReviewRequiredError("Reviewer name must not be empty.")
    decision = _validate_decision(input("Decision (pass/reject/refine): "))
    note = _validate_note(input("Note (what did you hear? min 10 chars, no templated prose): "))
    reviewed_at = datetime.now(timezone.utc).isoformat()

    return HumanReviewRecord(
        reviewer=reviewer,
        decision=decision,
        note=note,
        reviewed_at=reviewed_at,
        method="cli_prompt",
    )


def capture_human_review(
    track_path: Path,
    interactive: bool = True,
) -> HumanReviewRecord:
    """Look for '<track_path>.review.json' first; if absent and interactive is
    True, prompt at the terminal. Validates decision/note per §6.2. Raises
    HumanReviewRequiredError if neither source yields a valid record."""
    track_path = Path(track_path)
    review_path = Path(str(track_path) + ".review.json")

    record = _read_review_file(review_path)
    if record is not None:
        return record

    if not interactive:
        raise HumanReviewRequiredError(
            f"No review file found at {review_path} and interactive review was "
            f"not enabled; refusing to default to an unreviewed result."
        )

    return _prompt_cli(track_path)
