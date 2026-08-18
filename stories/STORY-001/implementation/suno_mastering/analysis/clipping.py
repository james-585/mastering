"""Sample-peak + inter-sample-over (clipping/distortion) detection
(architecture.md Section 2: reuses true_peak.py's oversampled buffer).

- Sample-peak clipping: runs of consecutive full-scale samples
  (|x| >= config.clip_sample_threshold). Reports total clipped-sample count
  and the number of distinct clip "events" (contiguous runs).
- Inter-sample overs: samples in the oversampled (true-peak) buffer whose
  absolute value exceeds 0 dBFS (full scale) -- i.e. genuine reconstruction
  overshoot/distortion, distinct from the -1 dBTP *mastering* ceiling used
  elsewhere in the pipeline.
- Severity buckets (none/minor/moderate/severe) are an implementation
  convenience for the report, not a value given by the story/requirements;
  thresholds live in config so they're overridable/testable.
"""
from __future__ import annotations

import numpy as np

from .true_peak import TruePeakResult, measure_true_peak
from .types import ClippingResult

_FULL_SCALE_LINEAR = 1.0


def _count_clip_events(is_clipped: np.ndarray) -> int:
    if is_clipped.size == 0 or not is_clipped.any():
        return 0
    diff = np.diff(is_clipped.astype(np.int8))
    starts = int(np.sum(diff == 1))
    if is_clipped[0]:
        starts += 1
    return starts


def _severity(fraction_clipped: float, has_inter_sample_over: bool, config) -> str:
    if fraction_clipped == 0.0 and not has_inter_sample_over:
        return "none"
    if fraction_clipped < config.clip_minor_fraction:
        return "minor"
    if fraction_clipped < config.clip_moderate_fraction:
        return "moderate"
    return "severe"


def detect_clipping(audio: np.ndarray, sr: int, config, true_peak_result: TruePeakResult = None) -> ClippingResult:
    if audio.ndim == 1:
        flat = audio
    else:
        flat = np.max(np.abs(audio), axis=1)  # linked across channels: a clip on any channel counts

    is_clipped = np.abs(flat) >= config.clip_sample_threshold
    clipped_count = int(np.sum(is_clipped))
    clip_events = _count_clip_events(is_clipped)

    tp_result = true_peak_result or measure_true_peak(audio, sr, config)
    # DEF-103 fix (STORY-002 architecture.md Section 7.1): avoid a full-size
    # float64 abs() copy of the (large) oversampled buffer -- an OR of two
    # boolean comparisons is output-identical (including at NaN and exactly
    # +/-1.0) and allocates only boolean temporaries.
    inter_sample_overs = (tp_result.oversampled > _FULL_SCALE_LINEAR) | (
        tp_result.oversampled < -_FULL_SCALE_LINEAR
    )
    inter_sample_over_count = int(np.sum(inter_sample_overs))

    fraction_clipped = clipped_count / flat.size if flat.size else 0.0
    severity = _severity(fraction_clipped, inter_sample_over_count > 0, config)

    return ClippingResult(
        sample_peak_clipped_count=clipped_count,
        sample_peak_clip_events=clip_events,
        inter_sample_over_count=inter_sample_over_count,
        inter_sample_peak_dbtp=tp_result.dbtp,
        severity=severity,
    )
