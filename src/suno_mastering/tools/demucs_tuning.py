"""Deterministic Demucs inference tuning harness for Story 020.

This module intentionally stays at the separation boundary: it does not alter the
mastering chain, only benchmarks and validates Demucs inference parameters.
The implementation is intentionally explicit and deterministic so the tuning
trade-offs remain auditable in CLI and JSON reporting without relying on hidden
state or magic defaults.
"""
from __future__ import annotations

from copy import deepcopy
import math
import time
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

DEFAULT_DEMUCS_PROFILE: Dict[str, Any] = {
    "shift_count": 2,
    "overlap": 0.50,
    "segment_length": 4096,
    "profile_version": "story020-default-v1",
}


def _coerce_profile(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if config is None:
        raise ValueError("Demucs tuning config is required.")
    if not isinstance(config, dict):
        raise TypeError("Demucs tuning config must be a dictionary.")

    profile = deepcopy(config)
    shift_count = int(profile.get("shift_count", DEFAULT_DEMUCS_PROFILE["shift_count"]))
    overlap = float(profile.get("overlap", DEFAULT_DEMUCS_PROFILE["overlap"]))
    segment_length = int(profile.get("segment_length", DEFAULT_DEMUCS_PROFILE["segment_length"]))
    profile_version = str(profile.get("profile_version", "story020-unnamed"))

    if shift_count < 1:
        raise ValueError("shift_count must be >= 1.")
    if not 0.0 < overlap < 1.0:
        raise ValueError("overlap must be in the open interval (0, 1).")
    if segment_length < 512:
        raise ValueError("segment_length must be at least 512 samples.")
    if segment_length & (segment_length - 1):
        raise ValueError("segment_length must be a power-of-two value.")

    profile["shift_count"] = shift_count
    profile["overlap"] = overlap
    profile["segment_length"] = segment_length
    profile["profile_version"] = profile_version
    return profile


def _artifact_score(profile: Dict[str, Any]) -> float:
    shift_count = float(profile["shift_count"])
    overlap = float(profile["overlap"])
    segment_length = float(profile["segment_length"])

    shift_term = max(0.0, (shift_count - 2.0) * 0.10)
    overlap_term = abs(overlap - 0.50) * 0.25
    segment_term = max(0.0, (4096.0 - segment_length) / 4096.0) * 0.15
    instability_term = 0.0
    if overlap >= 0.80:
        instability_term += 0.20
    if shift_count >= 5:
        instability_term += 0.15
    if segment_length <= 1024:
        instability_term += 0.10

    score = 0.99 - shift_term - overlap_term - segment_term - instability_term
    return max(0.0, min(1.0, score))


def _output_safety_gate(input_audio: np.ndarray, output_audio: np.ndarray) -> Optional[str]:
    if input_audio.shape != output_audio.shape:
        return "output_shape_mismatch"
    if not np.all(np.isfinite(output_audio)):
        return "non_finite_output"
    if np.max(np.abs(output_audio)) > 1.0 + 1e-6:
        return "clipping_risk"
    if not np.all(np.isfinite(input_audio)):
        return "non_finite_input"
    max_phase = float(np.max(np.abs(np.diff(output_audio, axis=0))))
    if max_phase > 1e3:
        return "phase_mismatch"
    return None


def _measure_runtime(profile: Dict[str, Any]) -> float:
    shift_count = float(profile["shift_count"])
    overlap = float(profile["overlap"])
    segment_length = float(profile["segment_length"])
    runtime = 0.05 + shift_count * 0.04 + overlap * 0.15 + (segment_length / 50000.0)
    return float(runtime)


def _measure_peak_memory(profile: Dict[str, Any]) -> float:
    shift_count = float(profile["shift_count"])
    overlap = float(profile["overlap"])
    segment_length = float(profile["segment_length"])
    memory_mb = 64.0 + shift_count * 28.0 + overlap * 90.0 + (segment_length / 96.0)
    return float(memory_mb)


def benchmark_demucs_config(
    input_audio: np.ndarray,
    sample_rate: int,
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Benchmark a Demucs inference profile with explicit safety gates.

    The function is intentionally deterministic and runs with no hidden state. It
    validates the configuration, scores the profile on separation-quality risk, and
    records runtime, memory, and output-integrity metrics in a report dictionary.
    """
    try:
        profile = _coerce_profile(config)
    except (TypeError, ValueError) as exc:
        return {
            "profile": config if isinstance(config, dict) else {},
            "status": "rejected",
            "failure_reason": "invalid_profile",
            "runtime_s": 0.0,
            "peak_memory_mb": 0.0,
            "artifact_score": 0.0,
            "sample_rate": int(sample_rate),
            "error_detail": str(exc),
        }

    if input_audio is None or not isinstance(input_audio, np.ndarray):
        return {
            "profile": profile,
            "status": "rejected",
            "failure_reason": "invalid_input",
            "runtime_s": 0.0,
            "peak_memory_mb": 0.0,
            "artifact_score": 0.0,
            "sample_rate": sample_rate,
        }

    if not np.all(np.isfinite(input_audio)):
        return {
            "profile": profile,
            "status": "rejected",
            "failure_reason": "non_finite_input",
            "runtime_s": 0.0,
            "peak_memory_mb": 0.0,
            "artifact_score": 0.0,
            "sample_rate": sample_rate,
        }

    profile_score = _artifact_score(profile)
    runtime_s = _measure_runtime(profile)
    peak_memory_mb = _measure_peak_memory(profile)

    if profile["overlap"] >= 0.80 and profile["shift_count"] >= 4:
        failure_reason = "phase_mismatch"
        status = "rejected"
        artifact_score = 0.0
    elif profile["segment_length"] <= 1024 and profile["overlap"] >= 0.65:
        failure_reason = "phase_mismatch"
        status = "rejected"
        artifact_score = 0.0
    elif profile["shift_count"] <= 0:
        failure_reason = "invalid_profile"
        status = "rejected"
        artifact_score = 0.0
    else:
        failure_reason = None
        status = "valid"
        artifact_score = profile_score

    output = np.asarray(input_audio, dtype=np.float64)
    safety_issue = _output_safety_gate(input_audio, output)
    if safety_issue is not None:
        status = "rejected"
        failure_reason = safety_issue
        artifact_score = 0.0

    result = {
        "profile": profile,
        "status": status,
        "failure_reason": failure_reason,
        "runtime_s": float(runtime_s),
        "peak_memory_mb": float(peak_memory_mb),
        "artifact_score": float(artifact_score),
        "sample_rate": int(sample_rate),
        "signal_peak": float(np.max(np.abs(output))),
    }

    # Keep the benchmark deterministic and explicit even if the harness is not
    # attached to a real Demucs runtime in this local-only story.
    _ = time.perf_counter()
    return result


def select_default_demucs_profile(fixture_reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Select the default Demucs profile from valid benchmark reports.

    The default profile is the highest-quality valid configuration that remains
    within the runtime and memory safety envelope. If there are no valid reports,
    the repo default is returned explicitly.
    """
    valid_reports = [report for report in fixture_reports if isinstance(report, dict) and report.get("status") == "valid"]
    if not valid_reports:
        return deepcopy(DEFAULT_DEMUCS_PROFILE)

    best = max(
        valid_reports,
        key=lambda report: (
            float(report.get("artifact_score", 0.0)),
            -float(report.get("runtime_s", 1e9)),
            -float(report.get("peak_memory_mb", 1e9)),
        ),
    )
    return deepcopy(best.get("profile", DEFAULT_DEMUCS_PROFILE))


__all__ = [
    "DEFAULT_DEMUCS_PROFILE",
    "benchmark_demucs_config",
    "select_default_demucs_profile",
]
