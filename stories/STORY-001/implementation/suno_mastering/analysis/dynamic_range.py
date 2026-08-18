"""Custom TT DR-meter implementation (architecture.md Section 2: no PyPI
package implements the published Pleasurize Music Foundation spec).

Algorithm, per channel, per the published spec:
  1. Split into non-overlapping 3-second blocks.
  2. Per block: "RMS" = sqrt(2 * mean(x**2)) (the factor of 2 rescales RMS
     to the level of an equivalent-power sine wave's peak, which is the
     published spec's convention).
  3. Per block: peak = max(abs(x)) in that block.
  4. Sort blocks by RMS descending, discard the loudest 20%.
  5. "2nd RMS" = sqrt(mean(remaining RMS**2)).
  6. "2nd peak" = second-highest per-block peak value across ALL blocks
     (guards against a single outlier peak skewing the ratio).
  7. DR (this channel) = 20*log10(2nd_peak / 2nd_RMS).
Final DR = mean across channels, rounded to the nearest integer (matching
the conventional integer "DR8"/"DR14" reporting style).

Needs calibration against known reference DR values before being fully
trusted (architecture.md Section 9, risk #2) -- implemented directly
against the published spec here.

Fully vectorized: block segmentation via reshape, no per-sample Python
loops (required for the <5 minute processing budget).
"""
from __future__ import annotations

import math

import numpy as np

_MIN_LINEAR = 1e-12


def _channel_dr(x: np.ndarray, sr: int, block_seconds: float, exclude_fraction: float) -> float:
    block_len = int(round(block_seconds * sr))
    if block_len <= 0:
        block_len = len(x) or 1
    n_blocks = len(x) // block_len

    if n_blocks < 1:
        # Track shorter than one DR block: fall back to a single-block
        # crest-factor style estimate rather than crashing.
        rms = math.sqrt(2.0 * float(np.mean(x ** 2))) if len(x) else 0.0
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        rms = max(rms, _MIN_LINEAR)
        peak = max(peak, _MIN_LINEAR)
        return 20.0 * math.log10(peak / rms)

    trimmed = x[: n_blocks * block_len].reshape(n_blocks, block_len)
    block_rms = np.sqrt(2.0 * np.mean(trimmed ** 2, axis=1))
    block_peak = np.max(np.abs(trimmed), axis=1)

    if n_blocks >= 5:
        n_exclude = max(1, int(round(n_blocks * exclude_fraction)))
    else:
        # Too few blocks for a meaningful 20% exclusion -- use all blocks.
        n_exclude = 0

    rms_order = np.argsort(-block_rms)  # descending
    keep_idx = rms_order[n_exclude:]
    if len(keep_idx) == 0:
        keep_idx = rms_order  # degenerate: keep everything rather than divide by zero
    second_rms = math.sqrt(float(np.mean(block_rms[keep_idx] ** 2)))

    peaks_desc = np.sort(block_peak)[::-1]
    second_peak = float(peaks_desc[1]) if len(peaks_desc) >= 2 else float(peaks_desc[0])

    second_rms = max(second_rms, _MIN_LINEAR)
    second_peak = max(second_peak, _MIN_LINEAR)
    return 20.0 * math.log10(second_peak / second_rms)


def _measure_dynamic_range_unrounded(audio: np.ndarray, sr: int, config) -> float:
    """Everything measure_dynamic_range() does, up to (and excluding) the
    final integer-rounding step. Extracted (STORY-002 architecture.md
    Section 5) so STORY-002's reference-analysis path can expose the exact
    float DR value for median/min/max aggregation without forking the
    underlying per-channel computation -- both this helper and the public
    measure_dynamic_range() below call _channel_dr identically; there is
    exactly one computation underneath, not two."""
    if audio.ndim == 1:
        channels = [audio]
    else:
        channels = [audio[:, c] for c in range(audio.shape[1])]

    per_channel = [
        _channel_dr(ch, sr, config.dr_block_seconds, config.dr_exclude_fraction)
        for ch in channels
    ]
    return float(np.mean(per_channel))


def measure_dynamic_range(audio: np.ndarray, sr: int, config) -> float:
    """Return the TT DR-meter value (integer-rounded dB-like scale, e.g.
    9.0 for "DR9"), averaged across channels. `audio` may be mono
    (samples,) or multichannel (samples, channels).

    Public signature/return value unchanged (STORY-002 architecture.md
    Section 5) -- this is a one-line wrapper around
    _measure_dynamic_range_unrounded() so existing call sites (e.g.
    mastering/loudness_limit.py's solver) keep the rounded convention they
    depend on."""
    dr = _measure_dynamic_range_unrounded(audio, sr, config)
    return float(math.floor(dr + 0.5))  # round-half-up, matches integer DR convention
