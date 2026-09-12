"""Corrective EQ (pipeline stage [4]) -- RBJ Audio-EQ-Cookbook biquad
coefficient design, applied via scipy.signal.sosfiltfilt (zero-phase).

Capped at <= config.eq_max_gain_db per move, one move per flagged band
(thin low-end -> low shelf boost, muddiness/harshness -> peaking cut),
applied identically to both channels (never M/S) so tonal correction does
not itself alter the stereo image. Every move actually applied is returned
as a logged action for the report.

sosfiltfilt (zero-phase, forward-backward) is deliberately used instead of
a single-pass sosfilt so the correction doesn't introduce its own phase
shift that could work against the mono-compatibility goal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import sosfiltfilt

from .. import errors


@dataclass
class EqAction:
    band: str
    filter_type: str  # "low_shelf" | "peaking"
    center_hz: float
    gain_db: float
    reason: str


def _peaking_sos(sr: float, f0: float, gain_db: float, bandwidth_octaves: float):
    """RBJ cookbook peaking EQ, bandwidth-in-octaves parameterization."""
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / sr
    sin_w0, cos_w0 = math.sin(w0), math.cos(w0)
    alpha = sin_w0 * math.sinh((math.log(2) / 2) * bandwidth_octaves * (w0 / sin_w0))

    b0 = 1 + alpha * a
    b1 = -2 * cos_w0
    b2 = 1 - alpha * a
    a0 = 1 + alpha / a
    a1 = -2 * cos_w0
    a2 = 1 - alpha / a
    return _normalize_sos(b0, b1, b2, a0, a1, a2)


def _low_shelf_sos(sr: float, f0: float, gain_db: float, slope: float = 1.0):
    """RBJ cookbook low-shelf filter."""
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / sr
    sin_w0, cos_w0 = math.sin(w0), math.cos(w0)
    alpha = (sin_w0 / 2) * math.sqrt((a + 1 / a) * (1 / slope - 1) + 2)
    two_sqrt_a_alpha = 2 * math.sqrt(a) * alpha

    b0 = a * ((a + 1) - (a - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1) + (a - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - two_sqrt_a_alpha
    return _normalize_sos(b0, b1, b2, a0, a1, a2)


def _normalize_sos(b0, b1, b2, a0, a1, a2):
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sos


def _band_center_hz(band_hz: tuple) -> float:
    lo, hi = band_hz
    return math.sqrt(lo * hi)  # geometric mean, standard for log-frequency bands


def _band_bandwidth_octaves(band_hz: tuple) -> float:
    lo, hi = band_hz
    return math.log2(hi / lo)


def apply_corrective_eq(audio: np.ndarray, sr: int, freq_balance, config):
    """Apply capped corrective EQ moves for every flagged band in
    `freq_balance` (an analysis.types.FrequencyBalanceResult). Returns
    (audio_out, actions: list[EqAction])."""
    if sr <= 0:
        raise errors.UnsupportedFormatError(f"Invalid sample rate for EQ: {sr}")

    actions = []
    out = audio.copy()
    cap = config.eq_max_gain_db

    def apply_filter(sos, gain_db, band, filter_type, center_hz, reason):
        nonlocal out
        out = sosfiltfilt(sos, out, axis=0)  # zero-phase; axis=0 is the sample axis for both 1D and (samples, ch) 2D
        actions.append(EqAction(band=band, filter_type=filter_type, center_hz=center_hz, gain_db=gain_db, reason=reason))

    low = freq_balance.low_end
    if low.flagged:
        # Thin low-end: boost toward the reference curve, capped. deviation_db
        # is negative here (measured below reference), so -deviation_db is
        # the full gap; cap limits how much of it we close in one move.
        gain_db = min(cap, max(0.1, -low.deviation_db))
        f0 = low.range_hz[1]  # shelf corner at top of the low-end band
        sos = _low_shelf_sos(sr, f0, gain_db)
        apply_filter(sos, gain_db, "low_end", "low_shelf", f0, "thin_low_end")

    mud = freq_balance.low_mid_mud
    if mud.flagged:
        # Muddiness: cut toward the reference curve, capped. deviation_db is
        # positive here (measured above reference).
        gain_db = -min(cap, max(0.1, mud.deviation_db))
        f0 = _band_center_hz(mud.range_hz)
        bw = _band_bandwidth_octaves(mud.range_hz)
        sos = _peaking_sos(sr, f0, gain_db, bw)
        apply_filter(sos, gain_db, "low_mid_mud", "peaking", f0, "muddiness")

    presence = freq_balance.presence_harsh
    if presence.flagged:
        gain_db = -min(cap, max(0.1, presence.deviation_db))
        f0 = _band_center_hz(presence.range_hz)
        bw = _band_bandwidth_octaves(presence.range_hz)
        sos = _peaking_sos(sr, f0, gain_db, bw)
        apply_filter(sos, gain_db, "presence_harsh", "peaking", f0, "harshness")

    return out, actions
