"""grounded_quality_review.py (STORY-025 architecture.md §7).

Replaces STORY-015's proxy metrics (`clarity_delta`, `_spectral_tilt`) with the
project's existing grounded measurements (seven-band spectral balance, TT DR,
artifact density), computed only after a mandatory LUFS-matching precondition
(§4, CLAUDE.md §6.3). Decision authority moves entirely to the human reviewer
(§1, §7.3) -- the grounded metrics here produce evidence and risk flags, never
a pass/reject/refine decision by themselves.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-001" / "implementation",
    _REPO_ROOT / "stories" / "STORY-025" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from suno_mastering.analysis.artifact_detection import detect_artifacts
from suno_mastering.analysis.dynamic_range import measure_dynamic_range
from suno_mastering.analysis.seven_band_balance import measure_seven_band_balance

from lufs_matching import match_levels
from review_config import GroundedReviewConfig


def _as_float64(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim not in (1, 2):
        raise ValueError(f"Unsupported audio shape: {arr.shape}")
    return arr


# DEF-2502: epsilon tolerance for float64 boundary comparisons in flag conditions.
_FLAG_EPSILON = 1e-9


# _true_peak and _stereo_width ported verbatim from STORY-015's
# final_quality_review.py (architecture.md §7.4/§7.5) -- unchanged math,
# retained as supplementary before_after evidence only (no flag/decision).

def _true_peak(audio: np.ndarray, oversample: int = 8) -> float:
    arr = _as_float64(audio)
    mono = arr.mean(axis=1) if arr.ndim == 2 else arr
    if mono.size == 0:
        return 0.0
    if oversample <= 1:
        return float(np.max(np.abs(mono)))

    max_peak = 0.0
    chunk_size = 1_000_000
    for start in range(0, mono.size, chunk_size):
        chunk = mono[start : start + chunk_size]
        if chunk.size == 0:
            continue
        x = np.arange(chunk.size, dtype=np.float64)
        up = np.arange(0, chunk.size, 1.0 / oversample, dtype=np.float64)
        oversampled = np.interp(up, x, chunk)
        chunk_peak = float(np.max(np.abs(oversampled)))
        if chunk_peak > max_peak:
            max_peak = chunk_peak
    return max_peak


def _stereo_width(audio: np.ndarray) -> float:
    arr = _as_float64(audio)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return 0.0
    left = arr[:, 0]
    right = arr[:, 1]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = float(np.sqrt(np.mean(mid ** 2)))
    side_rms = float(np.sqrt(np.mean(side ** 2)))
    return float(side_rms / (mid_rms + 1e-9))


@dataclass
class GroundedMetrics:
    original_lufs: float
    processed_lufs: float
    lufs_gain_applied_db: float
    spectral_band_delta_db: Dict[str, float]   # 7 keys, "mid" delta always 0.0 by definition
    spectral_rms_shift_db: float               # RMS of the six non-"mid" band deltas
    dr_original: float
    dr_processed: float
    dr_delta: float
    artifact_density_original: float
    artifact_density_processed: float
    artifact_density_delta: float
    width_delta: float                          # retained from STORY-015 _stereo_width (§7.4)
    peak_delta_db_unmatched: float               # retained from STORY-015 _true_peak; NOT level-matched (§7.5)
    flags: List[str]                             # risk evidence only, never a verdict


def compute_grounded_metrics(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    config: GroundedReviewConfig = GroundedReviewConfig(),
) -> GroundedMetrics:
    orig = _as_float64(original)
    proc = _as_float64(processed)

    # 1. Mandatory LUFS-matching precondition (AC5/AC6) -- raises LevelMatchError,
    #    not swallowed, if the match cannot be confirmed.
    match = match_levels(orig, proc, sr, config.lufs_match_tolerance_lu)

    # 2. Seven-band spectral balance, before/after on the level-matched pair.
    seven_band_original = measure_seven_band_balance(orig, sr, config.reference_analysis)
    seven_band_processed = measure_seven_band_balance(match.matched_processed, sr, config.reference_analysis)
    original_bands = {b.band: b.relative_db for b in seven_band_original.bands}
    processed_bands = {b.band: b.relative_db for b in seven_band_processed.bands}
    spectral_band_delta_db = {
        band: processed_bands[band] - original_bands[band] for band in original_bands
    }
    # "mid" is the reference band itself (relative_db == 0.0 for both sides by
    # definition), so its delta is always exactly 0.0 and is excluded from the
    # RMS -- it would only dilute, never inform, the shift measurement.
    non_mid_deltas = [delta for band, delta in spectral_band_delta_db.items() if band != "mid"]
    spectral_rms_shift_db = float(np.sqrt(np.mean(np.square(non_mid_deltas)))) if non_mid_deltas else 0.0

    # 3. TT DR, before/after on the level-matched pair.
    dr_original = measure_dynamic_range(orig, sr, config.reference_analysis)
    dr_processed = measure_dynamic_range(match.matched_processed, sr, config.reference_analysis)
    dr_delta = dr_processed - dr_original

    # 4. Artifact density, before/after on the level-matched pair.
    _, artifact_original = detect_artifacts(orig, sr)
    _, artifact_processed = detect_artifacts(match.matched_processed, sr)
    artifact_density_delta = (
        artifact_processed.overall_artifact_density_score
        - artifact_original.overall_artifact_density_score
    )

    # 5. Width/true-peak stay on the RAW (unmatched) pair -- §7.5: true-peak
    #    safety is a property of the actual exported file at its real output
    #    level, not a relative "did it get better" comparison.
    width_delta = float(_stereo_width(proc) - _stereo_width(orig))
    peak_delta_db_unmatched = float(
        20.0 * np.log10(max(_true_peak(proc), 1e-9) / max(_true_peak(orig), 1e-9))
    )

    # 6. Flags -- risk evidence only, never a pass/fail decision by themselves.
    # DEF-2502: raw float64 subtraction can land a hair below/above an exact
    # threshold that was constructed to sit exactly at the boundary (e.g.
    # 0.150 - 0.10 == 0.049999999999999996 < 0.05), so each comparison uses a
    # small epsilon tolerance instead of a bare >=/<= on the raw delta.
    flags: List[str] = []
    if dr_delta <= -config.dr_regression_db + _FLAG_EPSILON:
        flags.append("dynamic_range_regression")
    if artifact_density_delta >= config.artifact_density_regression - _FLAG_EPSILON:
        flags.append("artifact_density_regression")
    if spectral_rms_shift_db >= config.spectral_shift_flag_db - _FLAG_EPSILON:
        flags.append("spectral_shift_significant")

    return GroundedMetrics(
        original_lufs=match.original_lufs,
        processed_lufs=match.processed_lufs,
        lufs_gain_applied_db=match.gain_applied_db,
        spectral_band_delta_db=spectral_band_delta_db,
        spectral_rms_shift_db=spectral_rms_shift_db,
        dr_original=dr_original,
        dr_processed=dr_processed,
        dr_delta=dr_delta,
        artifact_density_original=artifact_original.overall_artifact_density_score,
        artifact_density_processed=artifact_processed.overall_artifact_density_score,
        artifact_density_delta=artifact_density_delta,
        width_delta=width_delta,
        peak_delta_db_unmatched=peak_delta_db_unmatched,
        flags=flags,
    )


@dataclass
class QualityReviewResult:
    decision: str                 # "pass" | "reject" | "refine" | "pending_human_review"
    summary: str
    flags: List[str]
    before_after: Dict[str, float]   # flattened GroundedMetrics scalar fields (spectral_band_delta_db
                                       # flattened as "spectral_band_delta_db.<band>")
    human_decision: Optional[str] = None
    human_note: str = ""
    audit: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _flatten_metrics(metrics: GroundedMetrics) -> Dict[str, float]:
    flat: Dict[str, float] = {
        "original_lufs": metrics.original_lufs,
        "processed_lufs": metrics.processed_lufs,
        "lufs_gain_applied_db": metrics.lufs_gain_applied_db,
        "spectral_rms_shift_db": metrics.spectral_rms_shift_db,
        "dr_original": metrics.dr_original,
        "dr_processed": metrics.dr_processed,
        "dr_delta": metrics.dr_delta,
        "artifact_density_original": metrics.artifact_density_original,
        "artifact_density_processed": metrics.artifact_density_processed,
        "artifact_density_delta": metrics.artifact_density_delta,
        "width_delta": metrics.width_delta,
        "peak_delta_db_unmatched": metrics.peak_delta_db_unmatched,
    }
    for band, delta in metrics.spectral_band_delta_db.items():
        flat[f"spectral_band_delta_db.{band}"] = delta
    return flat


def _flag_audit_lines(metrics: GroundedMetrics, config: GroundedReviewConfig) -> List[str]:
    """Gate 1 action item (Findings 1 and 2, architecture.md §7.3): the raw
    delta value behind each flag must be stated, not just the flag name, and
    the two PROVISIONAL thresholds must be labelled as such -- exact required
    format, not a paraphrase."""
    lines: List[str] = []
    for flag in metrics.flags:
        if flag == "artifact_density_regression":
            lines.append(
                f"artifact_density_regression flag (PROVISIONAL threshold "
                f"{config.artifact_density_regression}, not calibrated against reference "
                f"data): raw artifact_density_delta = {metrics.artifact_density_delta:+.4f}"
            )
        elif flag == "spectral_shift_significant":
            lines.append(
                f"spectral_shift_significant flag (PROVISIONAL threshold "
                f"{config.spectral_shift_flag_db} dB, not calibrated against reference "
                f"data): raw spectral_rms_shift_db = {metrics.spectral_rms_shift_db:.2f} dB"
            )
        elif flag == "dynamic_range_regression":
            # dr_regression_db is a derived reuse of STORY-006's
            # dr_max_reduction_db (§7.1), not an undervalidated placeholder --
            # no PROVISIONAL caveat here (§7.3).
            lines.append(
                f"dynamic_range_regression flag (threshold dr_regression_db = "
                f"{config.dr_regression_db} dB, reused from STORY-006's "
                f"dr_max_reduction_db): raw dr_delta = {metrics.dr_delta:+.4f} dB"
            )
    return lines


def evaluate_quality_review(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    human_review: Optional[Dict[str, str]] = None,
    config: GroundedReviewConfig = GroundedReviewConfig(),
) -> QualityReviewResult:
    metrics = compute_grounded_metrics(original, processed, sr, config)
    flag_audit_lines = _flag_audit_lines(metrics, config)
    before_after = _flatten_metrics(metrics)

    if human_review is None:
        decision = "pending_human_review"
        human_decision = None
        human_note = ""
        audit = [
            "No human listening review was supplied; this result is evidence only "
            "and must not be treated as a trusted pass/reject/refine verdict."
        ] + flag_audit_lines
    else:
        decision = str(human_review.get("decision", "")).strip().lower()
        if decision not in {"pass", "reject", "refine"}:
            raise ValueError(
                f"human_review['decision'] must be one of 'pass'/'reject'/'refine'; got {decision!r}"
            )
        human_note = str(human_review.get("note", "")).strip()
        reviewer = human_review.get("reviewer", "unspecified")
        human_decision = decision
        audit = [f"Human review ({reviewer}): {human_note}"] + flag_audit_lines

    flag_summary = ", ".join(metrics.flags) if metrics.flags else "no risk flags raised"
    summary = f"{decision}: {flag_summary}."

    return QualityReviewResult(
        decision=decision,
        summary=summary,
        flags=metrics.flags,
        before_after=before_after,
        human_decision=human_decision,
        human_note=human_note,
        audit=audit,
    )
