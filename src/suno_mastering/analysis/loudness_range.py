"""Loudness range (LRA), EBU Tech 3342 / ITU-R BS.1770-4 (STORY-002
architecture.md Section 4.1).

No existing STORY-001 building block computes this -- pyloudnorm.Meter only
exposes integrated loudness, and its filter design (Meter._filters) is a
private implementation detail that must not be relied on. This module
implements BS.1770-4 Annex 1's K-weighting filter directly from the
published (public-domain, widely reproduced -- e.g. libebur128, ffmpeg's
loudnorm, pyloudnorm's own independent implementation) two-stage biquad
coefficients, then EBU Tech 3342's short-term/gating/percentile-spread
logic on top of that.

K-weighting: a high-shelf biquad (~+4 dB above ~1.7 kHz, modeling head
diffraction) cascaded with a high-pass biquad (~38 Hz, modeling reduced
low-frequency sensitivity). Coefficients below are the standard BS.1770
Annex 1 constants (f0/G/Q at a 48 kHz reference), re-derived per actual
sample rate via the standard bilinear-transform K = tan(pi * f0 / fs)
substitution -- this is the same substitution BS.1770 itself specifies for
adapting the filter to sample rates other than 48 kHz, and is why this
still applies correctly at 44.1 kHz.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from .loudness import measure_integrated_lufs
from .reference_types import LraResult

_ABSOLUTE_GATE_LUFS = -70.0
_MEAN_SQUARE_FLOOR = 1e-12


def _high_shelf_coeffs(sr: int):
    f0 = 1681.9744509555319
    g_db = 3.99984385397
    q = 0.7071752369554193

    k = np.tan(np.pi * f0 / sr)
    vh = 10.0 ** (g_db / 20.0)
    vb = vh ** 0.4996667741545416

    a0_ = 1.0 + k / q + k * k
    b0 = (vh + vb * k / q + k * k) / a0_
    b1 = 2.0 * (k * k - vh) / a0_
    b2 = (vh - vb * k / q + k * k) / a0_
    a1 = 2.0 * (k * k - 1.0) / a0_
    a2 = (1.0 - k / q + k * k) / a0_
    return np.array([b0, b1, b2]), np.array([1.0, a1, a2])


def _high_pass_coeffs(sr: int):
    f0 = 38.13547087602444
    q = 0.5003270373238773

    k = np.tan(np.pi * f0 / sr)
    a0_ = 1.0 + k / q + k * k
    a1 = 2.0 * (k * k - 1.0) / a0_
    a2 = (1.0 - k / q + k * k) / a0_
    return np.array([1.0, -2.0, 1.0]), np.array([1.0, a1, a2])


def k_weight(audio: np.ndarray, sr: int) -> np.ndarray:
    """Apply BS.1770-4's two-stage K-weighting filter. `audio` mono
    (samples,) or multichannel (samples, channels); filtering is applied
    independently per channel via scipy.signal.lfilter (direct-form II,
    matching the biquad cascade's transfer function)."""
    b1, a1 = _high_shelf_coeffs(sr)
    b2, a2 = _high_pass_coeffs(sr)

    def _filter_1d(x: np.ndarray) -> np.ndarray:
        stage1 = lfilter(b1, a1, x)
        return lfilter(b2, a2, stage1)

    if audio.ndim == 1:
        return _filter_1d(audio)
    return np.stack([_filter_1d(audio[:, c]) for c in range(audio.shape[1])], axis=1)


def _windowed_mean_squares(weighted: np.ndarray, sr: int, window_s: float, hop_s: float) -> np.ndarray:
    """Per-window, per-channel mean-square power over sliding windows of
    `window_s` seconds, hop `hop_s` seconds. Returns shape (n_windows,
    channels) even for mono input (channels=1), so channel-summing is
    uniform downstream.

    Implemented via a cumulative-sum sliding-window trick (O(n_samples)
    memory/compute), NOT by materializing every window explicitly (an
    earlier fancy-indexing version built an (n_windows, window_len,
    channels) array directly -- for a 7-minute track at 3s/100ms LRA
    windowing this is ~4200 windows * ~132300 samples/window * 2 channels *
    8 bytes ~= 8.9 GB, which is what actually blew the "seconds, not
    minutes" per-track budget during benchmarking, not the K-weighting
    filter itself). A prefix-sum of squared samples reduces this to two
    O(n) cumsum passes plus O(n_windows) index arithmetic."""
    if weighted.ndim == 1:
        weighted = weighted[:, None]
    n_samples, n_channels = weighted.shape
    window_len = max(1, int(round(window_s * sr)))
    hop_len = max(1, int(round(hop_s * sr)))
    if n_samples < window_len:
        return np.zeros((0, n_channels))

    n_windows = 1 + (n_samples - window_len) // hop_len
    starts = np.arange(n_windows) * hop_len  # (n_windows,)

    squared = weighted.astype(np.float64) ** 2
    # Prefix sum with a leading zero row so window_sum = cumsum[end] - cumsum[start].
    cumsum = np.concatenate([np.zeros((1, n_channels)), np.cumsum(squared, axis=0)], axis=0)
    window_sums = cumsum[starts + window_len] - cumsum[starts]  # (n_windows, channels)
    return window_sums / window_len


def _block_loudness_lufs(channel_sum_mean_sq: np.ndarray) -> np.ndarray:
    return -0.691 + 10.0 * np.log10(np.maximum(channel_sum_mean_sq, _MEAN_SQUARE_FLOOR))


def _gate(mean_squares: np.ndarray, relative_gate_lu: float):
    """BS.1770 two-stage gating. `mean_squares` shape (n_windows, channels).
    Returns (gated_channel_sums, gated_block_loudness_lufs, integrated_lufs)
    where integrated_lufs is the power-mean loudness over the doubly-gated
    set (channel-summed, per BS.1770's convention -- NOT averaged across
    channels, since BS.1770 sums per-channel weighted mean-square power
    before taking the log)."""
    channel_sum = np.sum(mean_squares, axis=1)  # G_i = 1.0 for mono/stereo (no surround channels)
    block_loudness = _block_loudness_lufs(channel_sum)

    abs_gate_mask = block_loudness > _ABSOLUTE_GATE_LUFS
    if not abs_gate_mask.any():
        return np.array([]), np.array([]), float("-inf")

    stage1_sum = channel_sum[abs_gate_mask]
    stage1_mean = float(np.mean(stage1_sum))  # power mean, not log-domain mean
    gamma_r = _block_loudness_lufs(np.array([stage1_mean]))[0] - abs(relative_gate_lu)

    rel_gate_mask = _block_loudness_lufs(stage1_sum) > gamma_r
    if not rel_gate_mask.any():
        gated_sum = stage1_sum
    else:
        gated_sum = stage1_sum[rel_gate_mask]

    integrated = _block_loudness_lufs(np.array([float(np.mean(gated_sum))]))[0]
    return gated_sum, _block_loudness_lufs(gated_sum), integrated


def measure_loudness_range(audio: np.ndarray, sr: int, config) -> LraResult:
    """LRA per EBU Tech 3342 / BS.1770: K-weight, 3s short-term windows at
    100ms hop, absolute -70 LUFS gate, relative -20 LU gate (deliberately
    NOT -10 LU -- see module docstring / architecture.md Section 4.1 for why
    this is a materially different, wider gate than integrated loudness's
    own -10 LU relative gate), LRA = P95 - P10 of the doubly-gated block
    loudness values.

    Also runs a self-consistency check: the same K-weighting/gating
    machinery, applied with BS.1770's own exact windowing (400ms window,
    100ms hop, -10 LU relative gate) must reproduce
    measure_integrated_lufs()'s result on the same buffer to within
    config.lra_self_consistency_tolerance_lu -- this validates the
    K-weighting filter and gating logic (LRA's own percentile-spread logic
    is a separate statistic this does not validate).
    """
    if audio.size == 0:
        return LraResult(lra_lu=0.0, n_gated_blocks=0, self_consistency_delta_lu=0.0)

    weighted = k_weight(audio, sr)

    # --- LRA: 3s window / 100ms hop / -20 LU relative gate ---
    short_term = _windowed_mean_squares(weighted, sr, config.lra_window_s, config.lra_hop_s)
    if short_term.shape[0] == 0:
        return LraResult(lra_lu=0.0, n_gated_blocks=0, self_consistency_delta_lu=0.0)
    _, gated_loudness, _ = _gate(short_term, config.lra_relative_gate_lu)
    if gated_loudness.size == 0:
        lra_lu = 0.0
    else:
        lra_lu = float(np.percentile(gated_loudness, 95) - np.percentile(gated_loudness, 10))

    # --- Self-consistency check: BS.1770 integrated-loudness windowing ---
    integrated_blocks = _windowed_mean_squares(
        weighted, sr, config.bs1770_block_s, config.bs1770_hop_s
    )
    if integrated_blocks.shape[0] == 0:
        reconstructed = float("-inf")
    else:
        _, _, reconstructed = _gate(integrated_blocks, abs(config.bs1770_relative_gate_lu))

    reference_lufs = measure_integrated_lufs(audio, sr)
    if np.isfinite(reconstructed) and np.isfinite(reference_lufs):
        delta = abs(reconstructed - reference_lufs)
    else:
        delta = 0.0 if reconstructed == reference_lufs else float("inf")

    return LraResult(
        lra_lu=lra_lu,
        n_gated_blocks=int(gated_loudness.size),
        self_consistency_delta_lu=float(delta),
    )
