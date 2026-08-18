"""Windowed M/S narrowing correction (pipeline stage [5]), architecture.md
Section 8 item 2.

For each stereo-widened region (from analysis.stereo_phase) whose region
correlation is below the 0.0 floor, scale down the side-channel energy
within that region by the minimum amount needed to bring correlation back
to >= 0.0 (not a full mono-sum -- least correction necessary). A minimal
side-scale factor `k` is found via bounded, deterministic bisection search
(same approach as the loudness solver: fixed max-iteration count, no
wall-clock cutoffs, for AC10 reproducibility). A 50ms raised-cosine
crossfade is applied at each region boundary to avoid zipper/pumping
artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..analysis.stereo_phase import correlation_coefficient


@dataclass
class StereoCorrectionAction:
    start_time_s: float
    end_time_s: float
    original_correlation: float
    corrected_correlation: float
    side_scale_factor: float


def _correlation_for_scale(mid: np.ndarray, side: np.ndarray, k: float) -> float:
    left = mid + k * side
    right = mid - k * side
    return correlation_coefficient(left, right)


def _find_min_side_scale(mid: np.ndarray, side: np.ndarray, target: float, max_iterations: int) -> float:
    """Bisection for the largest k in [0, 1] such that correlation(k) >=
    target. k=0 fully collapses to mono (correlation -> 1.0); k=1 is
    unmodified. Correlation is monotonically non-increasing in k, so
    bisection converges deterministically."""
    lo, hi = 0.0, 1.0
    if _correlation_for_scale(mid, side, hi) >= target:
        return hi  # already compliant, no correction needed
    for _ in range(max_iterations):
        mid_k = (lo + hi) / 2.0
        if _correlation_for_scale(mid, side, mid_k) >= target:
            lo = mid_k
        else:
            hi = mid_k
    return lo


def _raised_cosine_ramp(n: int) -> np.ndarray:
    if n <= 0:
        return np.array([])
    t = np.linspace(0, np.pi, n)
    return 0.5 * (1 - np.cos(t))  # 0 -> 1


def correct_stereo_widened_elements(audio: np.ndarray, sr: int, widened_regions, config):
    """audio: (samples, 2) stereo buffer. Returns (audio_out, actions)."""
    if audio.ndim != 2 or audio.shape[1] != 2:
        return audio, []

    left = audio[:, 0].copy()
    right = audio[:, 1].copy()
    n_samples = len(left)

    envelope = np.ones(n_samples, dtype=np.float64)
    actions = []

    crossfade_len = max(1, int(round(config.stereo_crossfade_ms / 1000.0 * sr)))

    for region in widened_regions:
        if not region.needs_correction:
            continue

        start, end = region.start_sample, region.end_sample
        l_reg = left[start:end]
        r_reg = right[start:end]
        mid = (l_reg + r_reg) / 2.0
        side = (l_reg - r_reg) / 2.0

        k = _find_min_side_scale(mid, side, config.phase_correlation_floor, config.solver_max_iterations)

        region_len = end - start
        fade_len = min(crossfade_len, region_len // 2) if region_len > 1 else 0

        region_envelope = np.full(region_len, k, dtype=np.float64)
        if fade_len > 0:
            fade_in = 1.0 - (1.0 - k) * _raised_cosine_ramp(fade_len)
            fade_out = 1.0 - (1.0 - k) * _raised_cosine_ramp(fade_len)[::-1]
            region_envelope[:fade_len] = fade_in
            region_envelope[-fade_len:] = fade_out

        envelope[start:end] = np.minimum(envelope[start:end], region_envelope)

        corrected_corr = _correlation_for_scale(mid, side, k)
        actions.append(
            StereoCorrectionAction(
                start_time_s=start / sr, end_time_s=end / sr,
                original_correlation=region.region_correlation,
                corrected_correlation=corrected_corr,
                side_scale_factor=k,
            )
        )

    if not actions:
        return audio, actions

    mid_full = (left + right) / 2.0
    side_full = (left - right) / 2.0 * envelope
    out = np.stack([mid_full + side_full, mid_full - side_full], axis=1)
    return out, actions
