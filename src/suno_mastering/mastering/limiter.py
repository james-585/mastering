"""Core lookahead limiter primitive (architecture.md Section 2, "Limiter
design note" -- recommended v1 approach).

Operates at the track's native (1x) sample rate. Produces a per-sample gain
envelope that:
  1. Never allows |sample| * gain to exceed `ceiling_linear` for any sample
     within the lookahead window (a centered minimum filter over the
     instantaneous required gain -- this is what actually guarantees no
     overs, independent of the release smoothing below).
  2. Applies release smoothing (one-pole IIR, safe because it can only ever
     be combined via elementwise minimum with the strict lookahead gain --
     see inline comments) to avoid audible pumping on fast transients.

Fully vectorized: scipy.ndimage.minimum_filter1d and scipy.signal.lfilter
are both implemented in compiled code, not Python-level per-sample loops
(required for the <5 minute processing budget).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import minimum_filter1d
from scipy.signal import lfilter

_EPS = 1e-12


@dataclass
class LimiterOutcome:
    audio: np.ndarray
    gain_envelope: np.ndarray
    max_gain_reduction_db: float


def apply_lookahead_limiter(audio: np.ndarray, sr: int, ceiling_linear: float, config) -> LimiterOutcome:
    if audio.ndim == 1:
        peak_per_sample = np.abs(audio)
    else:
        peak_per_sample = np.max(np.abs(audio), axis=1)  # linked/stereo: limit both channels together

    instant_gain = np.minimum(1.0, ceiling_linear / np.maximum(peak_per_sample, _EPS))

    lookahead_samples = max(1, int(round(config.limiter_lookahead_ms / 1000.0 * sr)))
    lookahead_gain = minimum_filter1d(instant_gain, size=lookahead_samples, mode="nearest")

    release_samples = max(1, config.limiter_release_ms / 1000.0 * sr)
    release_alpha = float(np.exp(-1.0 / release_samples))
    # Causal one-pole low-pass of the lookahead gain curve. On its own this
    # would lag the *attack* (unsafe), so it is only ever used via an
    # elementwise minimum with lookahead_gain below, which is always safe:
    # during attack lookahead_gain is the (lower, stricter) value; during
    # release the lagging smoothed curve is the (lower) value, giving a
    # gentler release without ever exceeding what lookahead_gain requires.
    smoothed_gain = lfilter([1 - release_alpha], [1, -release_alpha], lookahead_gain)

    final_gain = np.minimum(lookahead_gain, smoothed_gain)
    final_gain = np.minimum(final_gain, instant_gain)  # belt-and-braces: never exceed the instantaneous requirement

    if audio.ndim == 1:
        limited = audio * final_gain
    else:
        limited = audio * final_gain[:, None]

    max_reduction_db = float(20.0 * np.log10(max(np.min(final_gain), _EPS)))
    return LimiterOutcome(audio=limited, gain_envelope=final_gain, max_gain_reduction_db=max_reduction_db)
