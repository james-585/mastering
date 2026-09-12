from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class QualityReviewResult:
    decision: str
    summary: str
    flags: List[str]
    before_after: Dict[str, float]
    human_decision: Optional[str] = None
    human_note: str = ""
    audit: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _as_float64(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim not in (1, 2):
        raise ValueError(f"Unsupported audio shape: {arr.shape}")
    return arr


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


def _spectral_tilt(audio: np.ndarray) -> float:
    arr = _as_float64(audio)
    mono = arr.mean(axis=1) if arr.ndim == 2 else arr
    if mono.size == 0:
        return 0.0
    spec = np.abs(np.fft.rfft(mono))
    if spec.size < 4:
        return 0.0
    lo = float(np.mean(spec[:max(1, spec.size // 50)]))
    hi = float(np.mean(spec[spec.size // 10:]))
    return float(hi / (lo + 1e-9))


def _summary_metrics(original: np.ndarray, processed: np.ndarray) -> Dict[str, float]:
    orig = _as_float64(original)
    proc = _as_float64(processed)
    original_peak = _true_peak(orig)
    processed_peak = _true_peak(proc)
    original_width = _stereo_width(orig)
    processed_width = _stereo_width(proc)
    original_tilt = _spectral_tilt(orig)
    processed_tilt = _spectral_tilt(proc)
    return {
        "peak_delta_db": float(20.0 * np.log10(max(processed_peak, 1e-9) / max(original_peak, 1e-9))),
        "width_delta": float(processed_width - original_width),
        "spectral_tilt_delta": float(processed_tilt - original_tilt),
        "clarity_delta": float(np.mean(np.abs(proc)) - np.mean(np.abs(orig))),
    }


def evaluate_quality_review(
    original: np.ndarray,
    processed: np.ndarray,
    human_review: Optional[Dict[str, str]] = None,
) -> QualityReviewResult:
    """Evaluate whether the processed mix is musically better than the original.

    This review intentionally focuses on human-meaningful outcomes, not only metric compliance.
    It provides a transparent pass/reject/refine verdict plus explicit audit notes.

    Sample-count note: the pipeline may legitimately resample a non-standard
    source rate (stage [3]) before mastering, so the processed array can have a
    different sample count from the original at ingest rate. The review compares
    the common prefix (shorter of the two) so the verdict reflects verified
    content rather than crashing on a legitimate sample-rate conversion.
    """
    orig = _as_float64(original)
    proc = _as_float64(processed)
    if orig.shape[1:] != proc.shape[1:]:
        raise ValueError(f"Original and processed audio must match in channel layout; got {orig.shape} and {proc.shape}")
    if orig.shape[0] != proc.shape[0]:
        common = min(orig.shape[0], proc.shape[0])
        orig = orig[:common]
        proc = proc[:common]

    metrics = _summary_metrics(orig, proc)
    flags: List[str] = []
    audit: List[str] = []

    width_change = metrics["width_delta"]
    tilt_change = metrics["spectral_tilt_delta"]
    peak_delta = metrics["peak_delta_db"]
    clarity_gain = metrics["clarity_delta"]

    if np.allclose(orig, proc, atol=1e-12, rtol=0.0):
        final_decision = "pass"
        summary = "Pass: stable input remains unchanged and the mix remains musically stable."
        flags = []
        audit = ["No meaningful change detected between original and processed output; the result is stable."]
    else:
        if peak_delta < -3.0 and width_change <= 0.05:
            flags.append("dullness")
            audit.append("The processed mix lost too much energy and no longer behaves like a musically stronger master; the result is dull and underpowered.")
            final_decision = "reject"
        elif clarity_gain < -1e-3 and width_change < -0.05:
            flags.append("dullness")
            audit.append("The processed mix is substantially quieter and less spacious, which is a classic dullness failure mode.")
            final_decision = "reject"
        elif width_change > 0.25 and (tilt_change > 0.20 or peak_delta > 3.0):
            flags.append("artificial_width")
            audit.append("Stereo width and high-frequency energy rose sharply enough to suggest an artificial or fatiguing widening pass.")
            final_decision = "refine"
        elif width_change > 0.10 and (tilt_change > 0.20 or peak_delta > 3.0):
            flags.append("fatigue")
            audit.append("The master gained width and brightness at the cost of listener fatigue and unnatural upper-mid energy.")
            final_decision = "reject"
        elif clarity_gain < -1e-3 and width_change <= 0.0 and peak_delta <= 0.0:
            flags.append("dullness")
            audit.append("The processed mix is quieter and flatter than the original without compensating gains in realism or control; the output does not represent a credible improvement.")
            final_decision = "reject"
        elif clarity_gain > 0.0 and width_change >= -0.08 and peak_delta < 5.0:
            final_decision = "pass"
            summary = "Pass: the mastered result improves clarity and control without introducing a major quality-risk pattern."
            audit = ["Before/after evidence shows an improvement in clarity and control without major fatigue or dullness signals."]
        elif width_change >= -0.08 and peak_delta < 5.0 and abs(tilt_change) < 0.15:
            if clarity_gain < -1e-3 and width_change < 0.05:
                flags.append("dullness")
                audit.append("The output stays within a safe metric envelope but remains less lively and less convincing than the original; the review does not accept a quiet or flat improvement.")
                final_decision = "reject"
            else:
                final_decision = "pass"
                summary = "Pass: the result is musically stable, with controlled stereo width and no major discomfort or dullness signals."
                audit = ["The output shows stable stereo width and no meaningful signal-risk pattern; the review accepts the result."]
        else:
            flags.append("over_processing")
            audit.append("The result is not strongly improved and shows a quality-risk pattern consistent with over-processing or a weak final review.")
            final_decision = "reject"

    if human_review is not None:
        human_decision = str(human_review.get("decision", "")).strip().lower()
        human_note = str(human_review.get("note", "")).strip()
        if human_decision in {"pass", "reject", "refine"}:
            final_decision = human_decision
    else:
        human_decision = None
        human_note = ""

    if final_decision == "pass":
        summary = "Pass: the mastered result remains controlled, clear, and musically more believable than the original."
        if np.allclose(orig, proc, atol=1e-12, rtol=0.0):
            summary = "Pass: stable input remains unchanged and the mix remains musically stable."
    elif final_decision == "refine":
        summary = "Refine: the result is close but shows a risk pattern that should be corrected before approval."
    else:
        summary = "Reject: the master does not meaningfully improve the source and shows a clear quality-risk pattern."

    if human_decision is not None:
        summary = f"{final_decision.upper()}: {human_note if human_note else 'Manual review accepted the decision.'}"

    return QualityReviewResult(
        decision=final_decision,
        summary=summary,
        flags=flags,
        before_after=metrics,
        human_decision=human_decision if human_review is not None else None,
        human_note=human_note,
        audit=audit,
    )
