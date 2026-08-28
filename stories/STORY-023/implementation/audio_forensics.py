"""Automated technical forensics for the Demucs split/re-summation path.

The module implements a deterministic validation gate for clipping, phase
mismatch, and reconstruction residuals before the mastering workflow accepts a
recombined signal. All calculations are explicit, numeric, and auditable while
keeping the internal signal domain in float64.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np


_CLIPPING_SAMPLE_LIMIT = 0.999999
_PHASE_MISMATCH_THRESHOLD = -0.75
_RECONSTRUCTION_RESIDUAL_THRESHOLD = 1e-6


def _as_float64_array(signal: Any, *, name: str) -> np.ndarray:
    array = np.asarray(signal, dtype=np.float64)
    if array.size == 0:
        return array.astype(np.float64, copy=False)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or Inf values")
    return array.astype(np.float64, copy=False)


def _as_float64_stereo(signal: Any, *, name: str) -> np.ndarray:
    array = _as_float64_array(signal, name=name)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    if array.ndim != 2 or array.shape[1] not in {1, 2}:
        raise ValueError(f"{name} must be shape (samples, 1) or (samples, 2), got {array.shape}")
    return array.astype(np.float64, copy=False)


def _oversampled_true_peak(signal: np.ndarray, *, oversample: int = 8) -> float:
    if signal.size == 0:
        return 0.0
    if signal.ndim == 1:
        samples = signal.astype(np.float64, copy=False)
    else:
        samples = signal.reshape(-1)

    if oversample <= 1:
        return float(np.max(np.abs(samples)))

    sample_count = samples.size
    if sample_count < 2:
        return float(np.max(np.abs(samples)))

    source_idx = np.linspace(0.0, sample_count - 1.0, int(sample_count * oversample), endpoint=False)
    lo = np.floor(source_idx).astype(np.int64)
    hi = np.clip(lo + 1, 0, sample_count - 1)
    frac = source_idx - lo
    y0 = samples[lo]
    y1 = samples[hi]
    upsampled = y0 + (y1 - y0) * frac
    return float(np.max(np.abs(upsampled)))


def _channel_peak(signal: np.ndarray) -> tuple[str | None, float]:
    stereo = _as_float64_stereo(signal, name="signal")
    if stereo.shape[1] == 1:
        return ("left", float(np.max(np.abs(stereo[:, 0]))))
    left_peak = float(np.max(np.abs(stereo[:, 0])))
    right_peak = float(np.max(np.abs(stereo[:, 1])))
    if left_peak >= right_peak:
        return ("left", left_peak)
    return ("right", right_peak)


def _compute_phase_alignment(stereo: np.ndarray) -> float:
    stereo = _as_float64_stereo(stereo, name="stereo")
    if stereo.shape[0] < 2:
        return 1.0
    left = stereo[:, 0]
    right = stereo[:, 1]
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    if left_std < 1e-12 or right_std < 1e-12:
        return 1.0
    correlation = float(np.corrcoef(left, right)[0, 1])
    if not np.isfinite(correlation):
        return 1.0
    return correlation


def _residual_dbfs(original: np.ndarray, recombined: np.ndarray) -> float:
    original = _as_float64_array(original, name="original")
    recombined = _as_float64_array(recombined, name="recombined")
    if original.size == 0:
        return -np.inf
    if original.shape != recombined.shape:
        raise ValueError(
            f"original and recombined shapes differ: {original.shape} vs {recombined.shape}"
        )
    residual = np.abs(original - recombined)
    residual_rms = float(np.sqrt(np.mean(residual**2)))
    original_rms = float(np.sqrt(np.mean(np.abs(original) ** 2)))
    if original_rms <= 0.0:
        return -np.inf if residual_rms <= 0.0 else 0.0
    ratio = residual_rms / original_rms
    return float(20.0 * np.log10(max(ratio, 1e-15)))


def flag_clipping(signal: Any) -> bool:
    """Return True when any sample or oversampled inter-sample peak exceeds the safety limit."""
    array = _as_float64_stereo(signal, name="signal")
    if array.size == 0:
        return False
    peak = float(np.max(np.abs(array)))
    if peak > _CLIPPING_SAMPLE_LIMIT:
        return True
    true_peak = float(np.max(np.abs(_oversampled_true_peak(array))))
    return bool(true_peak > 1.0 + 1e-6)


def flag_phase_mismatch(stems: Mapping[str, Any] | Any) -> bool:
    """Flag anti-correlated stereo pairs or inverted stem channels as unsafe."""
    if isinstance(stems, Mapping):
        candidates = list(stems.values())
    else:
        candidates = [stems]

    if not candidates:
        return False

    for candidate in candidates:
        try:
            stereo = _as_float64_stereo(candidate, name="stem")
        except ValueError:
            continue
        if stereo.shape[1] < 2:
            continue
        score = _compute_phase_alignment(stereo)
        if score <= _PHASE_MISMATCH_THRESHOLD:
            return True
    return False


def measure_reconstruction_residual(original: Any, recombined: Any) -> float:
    """Measure the max absolute residual between the original and recombined signal."""
    original_arr = _as_float64_array(original, name="original")
    recombined_arr = _as_float64_array(recombined, name="recombined")
    if original_arr.shape != recombined_arr.shape:
        raise ValueError(
            f"original and recombined shapes differ: {original_arr.shape} vs {recombined_arr.shape}"
        )
    residual = float(np.max(np.abs(original_arr - recombined_arr)))
    if not np.isfinite(residual):
        raise ValueError("reconstruction residual is not finite")
    return residual


@dataclass
class DiagnosticsReport:
    sample_rate: int
    clipping_detected: bool = False
    clipping_channel: str | None = None
    clipping_peak: float = 0.0
    phase_mismatch_detected: bool = False
    phase_alignment_score: float = 1.0
    reconstruction_artifact_detected: bool = False
    residual_error_dbfs: float = -np.inf
    residual_error_max: float = 0.0
    safe: bool = True
    status: str = "pass"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_rate": int(self.sample_rate),
            "status": self.status,
            "safe": bool(self.safe),
            "clipping_detected": bool(self.clipping_detected),
            "clipping_channel": self.clipping_channel,
            "clipping_peak": float(self.clipping_peak),
            "phase_mismatch_detected": bool(self.phase_mismatch_detected),
            "phase_alignment_score": float(self.phase_alignment_score),
            "reconstruction_artifact_detected": bool(self.reconstruction_artifact_detected),
            "residual_error_dbfs": float(self.residual_error_dbfs),
            "residual_error_max": float(self.residual_error_max),
            "reasons": list(self.reasons),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_text(self) -> str:
        header = f"DiagnosticsReport(sample_rate={self.sample_rate}, safe={self.safe}, status={self.status})"
        lines = [header]
        lines.append(f"- clipping_detected: {self.clipping_detected} | channel={self.clipping_channel} | peak={self.clipping_peak:.6f}")
        lines.append(f"- phase_mismatch_detected: {self.phase_mismatch_detected} | score={self.phase_alignment_score:.6f}")
        lines.append(
            f"- reconstruction_artifact_detected: {self.reconstruction_artifact_detected} | residual_dbfs={self.residual_error_dbfs:.6f} | residual_max={self.residual_error_max:.6e}"
        )
        if self.reasons:
            lines.append("- reasons:")
            for reason in self.reasons:
                lines.append(f"  * {reason}")
        return "\n".join(lines)


def run_forensics(
    original: Any,
    recombined: Any,
    stems: Mapping[str, Any] | None,
    sample_rate: int,
) -> DiagnosticsReport:
    """Run deterministic, objective forensics on the split/re-summed signal path."""
    if int(sample_rate) <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate!r}")

    original_arr = _as_float64_stereo(original, name="original")
    recombined_arr = _as_float64_stereo(recombined, name="recombined")
    if original_arr.shape != recombined_arr.shape:
        raise ValueError(
            f"original and recombined shapes differ: {original_arr.shape} vs {recombined_arr.shape}"
        )

    clip_output = _as_float64_stereo(recombined_arr, name="recombined")
    clipping_channel, clipping_peak = _channel_peak(clip_output)
    clipping_detected = flag_clipping(recombined_arr)
    phase_candidates = stems if isinstance(stems, Mapping) else {}
    phase_mismatch_detected = flag_phase_mismatch(phase_candidates)

    if phase_candidates:
        phase_values = []
        for candidate in phase_candidates.values():
            try:
                stereo = _as_float64_stereo(candidate, name="stem")
            except ValueError:
                continue
            if stereo.shape[1] >= 2:
                phase_values.append(_compute_phase_alignment(stereo))
        phase_alignment_score = float(min(phase_values)) if phase_values else 1.0
    else:
        phase_alignment_score = _compute_phase_alignment(recombined_arr)

    residual_max = measure_reconstruction_residual(original_arr, recombined_arr)
    residual_dbfs = _residual_dbfs(original_arr, recombined_arr)
    reconstruction_artifact_detected = residual_max > _RECONSTRUCTION_RESIDUAL_THRESHOLD

    reasons: list[str] = []
    if clipping_detected:
        reasons.append(f"clipping exceeded guard threshold at {clipping_peak:.6f} peak value on {clipping_channel or 'unknown'} channel")
    if phase_mismatch_detected:
        reasons.append(
            f"phase mismatch detected; correlation score={phase_alignment_score:.6f} is below safety threshold {_PHASE_MISMATCH_THRESHOLD:.2f}"
        )
    if reconstruction_artifact_detected:
        reasons.append(
            f"reconstruction residual exceeded tolerance: max_abs={residual_max:.6e}, residual_dbfs={residual_dbfs:.6f}"
        )

    safe = not (clipping_detected or phase_mismatch_detected)
    if reconstruction_artifact_detected and safe:
        status = "warn"
    elif safe:
        status = "pass"
    else:
        status = "fail"

    return DiagnosticsReport(
        sample_rate=int(sample_rate),
        clipping_detected=clipping_detected,
        clipping_channel=clipping_channel,
        clipping_peak=clipping_peak,
        phase_mismatch_detected=phase_mismatch_detected,
        phase_alignment_score=phase_alignment_score,
        reconstruction_artifact_detected=reconstruction_artifact_detected,
        residual_error_dbfs=residual_dbfs,
        residual_error_max=residual_max,
        safe=safe,
        status=status,
        reasons=reasons,
    )


__all__ = [
    "DiagnosticsReport",
    "flag_clipping",
    "flag_phase_mismatch",
    "measure_reconstruction_residual",
    "run_forensics",
]
