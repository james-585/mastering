"""Stereo phase correlation + stereo-widened-element segmentation
(architecture.md Section 8 item 2 -- resolved concrete parameters, v3:
non-overlapping windows, resolves DEF-003).

- Window: 500ms, hop 500ms -- NO overlap, windows tile the track
  contiguously (window_index = floor(t / 500ms)). v2's 250ms-hop/50%-overlap
  design is superseded: under 50% overlap every interior sample position
  falls inside exactly 2 overlapping windows by construction, which made the
  2-consecutive-window debounce below trivially always satisfied (DEF-003) --
  a single brief transient could never be filtered out. With no overlap, "2
  consecutive flagged windows" means the widened content genuinely spans
  >= 1000ms of real, disjoint track time.
- Per window: mid=(L+R)/2, side=(L-R)/2; energy = sum of squares.
- A window is stereo-widened when side_energy/mid_energy > 0.6.
- Debounce: only counts as a widened *element* (region) if >= 2 consecutive
  (contiguous, non-overlapping) windows are classified as widened
  (>= 1000ms sustained, real disjoint track time).
- Phase correlation coefficient: standard normalized cross-correlation,
  corr = sum(L*R) / sqrt(sum(L**2) * sum(R**2)), range [-1, 1].

Mono input is trivially "compatible" -- there is no stereo image to
collapse (requirements.md Section 6 edge cases).
"""
from __future__ import annotations

import numpy as np

from .types import StereoPhaseResult, StereoWidenedRegion, StereoWindowResult

_EPS = 1e-12


def correlation_coefficient(left: np.ndarray, right: np.ndarray) -> float:
    num = float(np.sum(left * right))
    denom = float(np.sqrt(np.sum(left ** 2) * np.sum(right ** 2)))
    if denom < _EPS:
        return 1.0  # both channels silent/identical-null: treat as compatible, not undefined
    return num / denom


def _windows(n_samples: int, sr: int, window_ms: float, hop_ms: float):
    window_len = max(1, int(round(window_ms / 1000.0 * sr)))
    hop_len = max(1, int(round(hop_ms / 1000.0 * sr)))
    start = 0
    while start < n_samples:
        end = min(start + window_len, n_samples)
        yield start, end
        if end >= n_samples:
            break
        start += hop_len


def analyze_stereo_phase(audio: np.ndarray, sr: int, config) -> StereoPhaseResult:
    if audio.ndim == 1 or audio.shape[1] == 1:
        return StereoPhaseResult(
            is_mono=True, overall_correlation=1.0, mono_compatible=True,
            windows=[], widened_regions=[],
        )

    left = audio[:, 0]
    right = audio[:, 1]
    n_samples = len(left)

    overall_correlation = correlation_coefficient(left, right)
    mono_compatible = overall_correlation >= config.phase_correlation_floor

    window_results = []
    for start, end in _windows(n_samples, sr, config.stereo_window_ms, config.stereo_hop_ms):
        l_win, r_win = left[start:end], right[start:end]
        mid = (l_win + r_win) / 2.0
        side = (l_win - r_win) / 2.0
        mid_energy = float(np.sum(mid ** 2))
        side_energy = float(np.sum(side ** 2))
        ratio = side_energy / mid_energy if mid_energy > _EPS else (
            float("inf") if side_energy > _EPS else 0.0
        )
        corr = correlation_coefficient(l_win, r_win)
        is_widened = ratio > config.stereo_side_mid_ratio_threshold
        window_results.append(
            StereoWindowResult(
                start_sample=start, end_sample=end,
                start_time_s=start / sr, end_time_s=end / sr,
                mid_energy=mid_energy, side_energy=side_energy,
                ratio=ratio, correlation=corr, is_widened=is_widened,
            )
        )

    widened_regions = _debounce_regions(window_results, left, right, sr, config)

    return StereoPhaseResult(
        is_mono=False,
        overall_correlation=overall_correlation,
        mono_compatible=mono_compatible,
        windows=window_results,
        widened_regions=widened_regions,
    )


def _debounce_regions(window_results, left, right, sr, config):
    """Group consecutive is_widened windows (>= stereo_debounce_windows in a
    row) into merged StereoWidenedRegion entries covering the full run."""
    regions = []
    run_start_idx = None
    for i, w in enumerate(window_results):
        if w.is_widened:
            if run_start_idx is None:
                run_start_idx = i
        else:
            if run_start_idx is not None:
                regions.append((run_start_idx, i - 1))
                run_start_idx = None
    if run_start_idx is not None:
        regions.append((run_start_idx, len(window_results) - 1))

    result = []
    for first_idx, last_idx in regions:
        if (last_idx - first_idx + 1) < config.stereo_debounce_windows:
            continue
        start_sample = window_results[first_idx].start_sample
        end_sample = window_results[last_idx].end_sample
        l_reg = left[start_sample:end_sample]
        r_reg = right[start_sample:end_sample]
        region_corr = correlation_coefficient(l_reg, r_reg)
        # DEF-006: derive mean_ratio from aggregate region mid/side energy
        # (mirrors region_corr's own approach) rather than averaging
        # per-window ratios, some of which may individually be an inf
        # sentinel (mid_energy ~ 0). Averaging only the isfinite() subset
        # degenerates to NaN when *every* window in the region is
        # inf-sentineled (a fully out-of-phase / pure-side element), and
        # even when finite windows exist it silently drops the inf ones
        # instead of letting their true energy dominate. The aggregate form
        # is always well-defined and finite (bounded by 1/_EPS).
        mid_reg = (l_reg + r_reg) / 2.0
        side_reg = (l_reg - r_reg) / 2.0
        mid_energy_total = float(np.sum(mid_reg ** 2))
        side_energy_total = float(np.sum(side_reg ** 2))
        mean_ratio = side_energy_total / max(mid_energy_total, _EPS)
        result.append(
            StereoWidenedRegion(
                start_sample=start_sample, end_sample=end_sample,
                start_time_s=start_sample / sr, end_time_s=end_sample / sr,
                region_correlation=region_corr, mean_ratio=mean_ratio,
                needs_correction=region_corr < config.phase_correlation_floor,
            )
        )
    return result
