from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import soundfile as sf

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-016" / "implementation",
    _REPO_ROOT / "stories" / "STORY-025" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from orchestration import MasteringOrchestrator
from grounded_quality_review import evaluate_quality_review
from environment_check import EnvironmentVerificationError, verify_stem_separation_environment
from human_review_capture import HumanReviewRecord, HumanReviewRequiredError, capture_human_review


ACCEPTED_PARAMETERS = {
    "float64_processing": True,
    "true_peak_method": "oversampled true peak",
    "oversample": 8,
    "stem_first_default": True,
    "stereo_fallback_is_explicit": True,
}


def _normalise_audio(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim == 1:
        return np.column_stack([arr, arr]).astype(np.float64)
    if arr.ndim == 2 and arr.shape[1] == 1:
        return np.column_stack([arr[:, 0], arr[:, 0]]).astype(np.float64)
    if arr.ndim == 2 and arr.shape[1] == 2:
        return arr.astype(np.float64)
    raise ValueError(f"Unsupported audio shape for validation: {arr.shape}")


def _prepare_validation_input(audio: np.ndarray, source_name: str) -> tuple[np.ndarray, str]:
    arr = _normalise_audio(audio)
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 0.98:
        scale = 0.95 / peak
        safe_arr = arr * scale
        return safe_arr, (
            f"Input peak {peak:.4f} exceeded the safe product threshold; the original file was kept untouched, and the pipeline was run on a working copy scaled to {scale:.3f}x for a safe validation pass."
        )
    return arr, "No input safety scaling was required; the original file remained the active validation source."


def _grounded_report_item(
    path: str,
    sample_rate: int,
    mode: str,
    review,
    stem_first_verified: Optional[bool],
) -> dict[str, Any]:
    """Build a report item from the grounded QualityReviewResult (§8 step 4) --
    auditable_summary/tuning_decisions are derived from review.audit (the raw
    grounded-metric evidence lines) and the actual human_note, never from a
    decision-keyed template string that could be mistaken for review prose."""
    tuning_decisions = [
        {
            "parameter": "grounded_review_evidence",
            "value": review.decision,
            "evidence": line,
            "reason": review.human_note,
        }
        for line in (review.audit or [])
    ]
    item: dict[str, Any] = {
        "path": path,
        "sample_rate": int(sample_rate),
        "decision": review.decision,
        "mode": mode,
        "auditable_summary": f"{review.summary} Human review ({review.human_decision or 'none'}): {review.human_note}",
        "tuning_decisions": tuning_decisions,
        "before_after": review.before_after,
        "flags": review.flags,
    }
    if stem_first_verified is not None:
        item["stem_first_verified"] = stem_first_verified
        if not stem_first_verified:
            item["stem_first_path_unverified"] = True
    return item


def _resolve_human_review(
    review_key: str,
    capture_path: Path,
    human_reviews: Optional[Dict[str, HumanReviewRecord]],
    interactive_review: bool,
) -> HumanReviewRecord:
    existing = (human_reviews or {}).get(review_key)
    if existing is not None:
        return existing
    if interactive_review:
        return capture_human_review(capture_path, interactive=True)
    raise HumanReviewRequiredError(
        f"No human review supplied for '{review_key}' and interactive_review is "
        f"False; build_validation_report() has no default that produces a "
        f"trusted report without a real human review (AC9)."
    )


def build_validation_report(
    paths: Sequence[str] | None = None,
    synthetic_case: np.ndarray | None = None,
    human_reviews: Optional[Dict[str, HumanReviewRecord]] = None,
    interactive_review: bool = False,
) -> dict[str, Any]:
    """Build an auditable validation report for real-world Suno material.

    The report contains one item per validation track, plus the overall product verdict.
    The accepted parameter values are explicitly captured so the tuning decisions remain
    traceable and auditable. Every trusted decision now requires a real human review
    (§8, AC9) -- there is no default path that produces a report without one.
    """
    source_paths = list(paths) if paths is not None else []
    file_items: List[dict[str, Any]] = []

    if synthetic_case is not None:
        arr = _normalise_audio(synthetic_case)
        review_record = _resolve_human_review(
            "synthetic_validation_case", Path("synthetic_validation_case"), human_reviews, interactive_review
        )
        pipeline = MasteringOrchestrator()
        result = pipeline.run(
            arr, 48000, stems={"mix": arr.copy()}, use_stems=False, human_review=review_record.as_dict()
        )
        review = evaluate_quality_review(arr, result["output"], 48000, human_review=review_record.as_dict())
        file_items.append(
            _grounded_report_item(
                path="synthetic_validation_case",
                sample_rate=48000,
                mode=str(result.get("mode", "stereo_only")),
                review=review,
                stem_first_verified=None,
            )
        )
        return {
            "num_files": 1,
            "overall_decision": review.decision,
            "accepted_parameters": ACCEPTED_PARAMETERS,
            "files": file_items,
        }

    stem_first_verified = False
    env_result_note = "No real-file validation set was processed; environment was not checked."
    if source_paths:
        try:
            env_result = verify_stem_separation_environment()
            stem_first_verified = True
            env_result_note = (
                f"Stem-first environment verified: {env_result.model_name} produced "
                f"{env_result.stem_count} finite, non-degenerate stems in {env_result.elapsed_s:.2f}s."
            )
        except EnvironmentVerificationError as exc:
            stem_first_verified = False
            env_result_note = f"Stem-first environment verification failed: {exc}"

    accepted_parameters = dict(ACCEPTED_PARAMETERS)
    accepted_parameters["stem_first_verified"] = stem_first_verified

    for path in source_paths:
        resolved = Path(path)
        if not resolved.exists():
            continue

        audio, sample_rate = sf.read(str(resolved), dtype="float64", always_2d=True)
        audio, safety_note = _prepare_validation_input(audio, str(resolved))
        review_record = _resolve_human_review(str(resolved), resolved, human_reviews, interactive_review)
        pipeline = MasteringOrchestrator()
        result = pipeline.run(
            audio, sample_rate, stems=None, use_stems=True, allow_stereo_fallback=True,
            human_review=review_record.as_dict(),
        )
        mode = str(result.get("mode", "stem_first"))
        review = evaluate_quality_review(audio, result["output"], sample_rate, human_review=review_record.as_dict())

        item = _grounded_report_item(
            path=str(resolved),
            sample_rate=sample_rate,
            mode=mode,
            review=review,
            stem_first_verified=stem_first_verified,
        )
        item["input_safety_note"] = safety_note
        item["environment_check"] = env_result_note
        file_items.append(item)

    if not file_items:
        return {
            "num_files": 0,
            "overall_decision": "reject",
            "accepted_parameters": accepted_parameters,
            "files": [],
        }

    overall_decision = "pass"
    if any(item["decision"] == "reject" for item in file_items):
        overall_decision = "reject"
    elif any(item["decision"] == "refine" for item in file_items):
        overall_decision = "refine"

    return {
        "num_files": len(file_items),
        "overall_decision": overall_decision,
        "accepted_parameters": accepted_parameters,
        "files": file_items,
    }


_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_TRACKS = _REPO_ROOT / "Reference Tracks"

DEFAULT_VALIDATION_SET = [
    str(_REFERENCE_TRACKS / "Sunday Club.wav"),
    str(_REFERENCE_TRACKS / "Wavy_Gravy.wav"),
    str(_REFERENCE_TRACKS / "Leftfield_-_Melt_Audio.wav"),
]


if __name__ == "__main__":
    report = build_validation_report(DEFAULT_VALIDATION_SET, interactive_review=True)
    print(report["overall_decision"])
    for item in report["files"]:
        print(item["path"], item["decision"], item["mode"])
